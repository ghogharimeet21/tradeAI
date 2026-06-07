# coding_agent.py
#
# Pipeline:
#   app.py detects unknown tool
#       → generate_spec()  — llama3.2:3b converts user query into a clean technical spec
#       → coding_agent()   — qwen2.5-coder:7b writes the function from that spec
#       → sandbox validates it
#       → saved to utils.py + hot-reloaded into live TOOLS

import re
import json
import sys
import io
import traceback
import ollama

from config import MAIN_MODEL, CODER_MODEL

# =========================================================================
# Step 1 — Spec generator (llama3.2:3b)
# Converts the user's natural language query into a precise technical brief
# so qwen gets a clean spec, not a vague user sentence
# =========================================================================

SPEC_PROMPT = """You are a technical spec writer for a crypto tool.

Given a user query and a missing function name, write a precise technical specification
for what that Python function should do.

Respond ONLY with this JSON, nothing else:
{
  "function_name": "exact_function_name_snake_case",
  "purpose": "one sentence: what it calculates and returns",
  "inputs": "describe what the args string contains e.g. 'BTCUSDT,14,1h'",
  "output": "describe the return string format e.g. 'BTCUSDT MACD(12,26) on 1h: value — SIGNAL'"
}
"""

def generate_spec(missing_tool: str, fn_input: str, user_query: str) -> dict:
    """
    Use llama3.2:3b to turn the user query into a clean technical spec for qwen.
    Returns a dict with function_name, purpose, inputs, output.
    """
    print(f"  [spec] generating spec for '{missing_tool}' via {MAIN_MODEL}...")

    prompt = f"""User query: "{user_query}"
Missing function: "{missing_tool}"
Input it received: "{fn_input}"

Write a precise technical spec for this function."""

    try:
        response = ollama.chat(
            model=MAIN_MODEL,
            messages=[
                {"role": "system", "content": SPEC_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            format="json",
            options={"temperature": 0.1}
        )
        spec = json.loads(response["message"]["content"])
        print(f"  [spec] ✓ purpose: {spec.get('purpose', '?')}")
        return spec
    except Exception as e:
        print(f"  [spec] failed ({e}) — using fallback spec")
        # Fallback: minimal spec inferred from the function name
        return {
            "function_name": missing_tool,
            "purpose": f"Calculate {missing_tool.replace('_', ' ')} for a crypto symbol",
            "inputs": fn_input,
            "output": "human-readable string with the calculated result"
        }


# =========================================================================
# Step 2 — Code generator (qwen2.5-coder:7b)
# =========================================================================

CODER_SYSTEM_PROMPT = """You are a Python coding agent for a crypto market analysis tool.
Write one Python function and return it as JSON.

OUTPUT FORMAT — return ONLY this JSON object, no markdown, no explanation, no extra text:
{
  "function_name": "exact_snake_case_name",
  "description": "one line description",
  "code": "def exact_snake_case_name(args: str) -> str:\\n    ..."
}

RULES:
- Signature must be: def name(args: str) -> str
- Parse args: parts = [p.strip() for p in args.split(",")]
- Always return a string
- DO NOT write any import statements — requests, json, math are already in scope
- Binance base URL: https://api.binance.com/api/v3

CRITICAL — BINANCE KLINE FORMAT:
/klines returns a list of lists. Each candle is a plain list:
  candle[0] = open time (int)
  candle[1] = open price (str)
  candle[2] = high price (str)
  candle[3] = low price (str)
  candle[4] = close price (str)   ← always use this for price
  candle[5] = volume (str)

ALWAYS: float(candle[4])  for close price
NEVER:  candle["close"]   — this will crash, it is a list not a dict

WORKING PATTERN TO FOLLOW:
def calculate_sma(args: str) -> str:
    parts = [p.strip() for p in args.split(",")]
    symbol = parts[0].upper()
    period = int(parts[1]) if len(parts) > 1 else 20
    tf = parts[2] if len(parts) > 2 else "1h"
    r = requests.get("https://api.binance.com/api/v3/klines",
                     params={"symbol": symbol, "interval": tf, "limit": period + 10})
    r.raise_for_status()
    closes = [float(c[4]) for c in r.json()]
    sma = sum(closes[-period:]) / period
    return f"{symbol} SMA({period}) on {tf} = {sma:.4f}"
"""


# =========================================================================
# Code cleaner — strips markdown fences qwen sometimes adds
# =========================================================================

def _clean_code(code: str) -> str:
    """Remove markdown fences, leading/trailing whitespace, stray backticks."""
    # Strip ```python ... ``` or ``` ... ```
    code = re.sub(r"^```(?:python)?\s*", "", code.strip(), flags=re.IGNORECASE)
    code = re.sub(r"\s*```$", "", code.strip())
    # Remove any line that is only backticks
    lines = [l for l in code.splitlines() if l.strip() != "```"]
    return "\n".join(lines).strip()


# =========================================================================
# Sandbox executor
# =========================================================================

def run_in_sandbox(code: str, fn_name: str, fn_input: str):
    """
    Execute generated code in an isolated namespace.
    Returns (result_str, success_bool, error_str)
    """
    import requests as _req
    import math as _math

    namespace = {"requests": _req, "math": _math, "json": json}

    old_stdout = sys.stdout
    sys.stdout = io.StringIO()

    try:
        exec(compile(code, "<generated>", "exec"), namespace)

        if fn_name not in namespace:
            sys.stdout = old_stdout
            # Try to find any def in the code and warn clearly
            defined = [l.split("(")[0].replace("def ", "").strip()
                       for l in code.splitlines() if l.strip().startswith("def ")]
            hint = f" Found these instead: {defined}" if defined else ""
            return None, False, f"Function '{fn_name}' not found after exec.{hint}"

        result = namespace[fn_name](fn_input)
        sys.stdout = old_stdout
        return str(result), True, ""

    except Exception:
        sys.stdout = old_stdout
        return None, False, traceback.format_exc()


# =========================================================================
# Save to utils.py
# =========================================================================

def save_to_utils(fn_name: str, code: str, description: str):
    try:
        with open("utils.py", "r") as f:
            content = f.read()

        if f"def {fn_name}(" in content:
            print(f"  [coder] '{fn_name}' already in utils.py — skipping")
            return

        marker = "# =========================================================================\n# Tool registry"
        if marker not in content:
            print("  [coder] WARNING: Tool registry marker not found in utils.py")
            return

        new_content = content.replace(
            marker,
            f"\n\n{code.strip()}\n\n\n{marker}"
        )

        insert_at = new_content.rfind("}")
        padding   = " " * max(1, 20 - len(fn_name))
        new_content = (
            new_content[:insert_at]
            + f'    "{fn_name}":{padding}{fn_name},\n'
            + new_content[insert_at:]
        )

        with open("utils.py", "w") as f:
            f.write(new_content)

        print(f"  [coder] ✓ '{fn_name}' saved to utils.py permanently")

    except Exception as e:
        print(f"  [coder] save failed: {e}")


# =========================================================================
# Hot-reload into live TOOLS dict
# =========================================================================

def hot_reload(fn_name: str, code: str):
    try:
        import requests, math, utils

        ns = {"requests": requests, "math": math, "json": json}
        exec(compile(code, "<generated>", "exec"), ns)

        if fn_name in ns:
            utils.TOOLS[fn_name] = ns[fn_name]
            print(f"  [coder] ✓ '{fn_name}' hot-reloaded into live TOOLS")
        else:
            print(f"  [coder] hot-reload: '{fn_name}' not found in namespace")

    except Exception as e:
        print(f"  [coder] hot-reload failed: {e}")


# =========================================================================
# Error hints — specific fix guidance fed back to qwen
# =========================================================================

def _error_hint(error: str) -> str:
    if "KeyError" in error:
        return "\nFIX: You used a string key on a list. Binance klines are LISTS. Use candle[4] not candle['close']."
    if "IndexError" in error:
        return "\nFIX: Index out of range. Increase the 'limit' param in your klines call."
    if "TypeError" in error and "float" in error:
        return "\nFIX: Prices are strings in Binance responses. Cast with float(): float(candle[4])"
    if "NameError" in error:
        return "\nFIX: Do NOT write import statements. requests, json, and math are already available."
    if "not found after exec" in error:
        return "\nFIX: The function_name in your JSON must exactly match the def name in your code."
    if "JSONDecodeError" in error or "raise_for_status" in error:
        return "\nFIX: API call failed. Check the endpoint URL and parameters carefully."
    return ""


# =========================================================================
# Main entry point
# =========================================================================

def coding_agent(missing_tool: str, fn_input: str, user_query: str = "") -> str:
    """
    1. llama3.2:3b generates a clean technical spec from the user query
    2. qwen2.5-coder:7b writes the function from that spec
    3. Sandbox validates it, saved + hot-reloaded on success
    """
    print(f"\n  [coder] '{missing_tool}' not in TOOLS — starting coding pipeline...")

    # ── Step 1: Generate spec via llama ──────────────────────────────────
    spec = generate_spec(missing_tool, fn_input, user_query)

    # Always use the original missing_tool name — don't let spec rename it
    # (keeps consistency with what the main agent expects)
    spec["function_name"] = missing_tool

    # ── Step 2: Build focused prompt for qwen ────────────────────────────
    user_message = f"""Write a Python function with this exact specification:

Function name: {spec['function_name']}
Purpose: {spec['purpose']}
Input format: {spec['inputs']}
Expected output: {spec['output']}

The function will be called with: "{fn_input}"

Follow the working pattern in your instructions exactly.
function_name in your JSON must be: {spec['function_name']}
"""

    messages = [
        {"role": "system", "content": CODER_SYSTEM_PROMPT},
        {"role": "user",   "content": user_message},
    ]

    for attempt in range(1, 4):
        print(f"  [coder] qwen generating... (attempt {attempt}/3)")

        try:
            response = ollama.chat(
                model=CODER_MODEL,
                messages=messages,
                format="json",
                options={"temperature": 0.1}
            )

            raw  = response["message"]["content"]
            data = json.loads(raw)

            # Always enforce the correct function name — ignore whatever qwen returned
            fn_name = missing_tool
            code    = _clean_code(data.get("code", ""))
            desc    = data.get("description", "")

            # If qwen used a different def name in the code body, rename it
            code = re.sub(
                rf"^def \w+\(", f"def {fn_name}(", code, count=1, flags=re.MULTILINE
            )

            if not code:
                messages += [
                    {"role": "assistant", "content": raw},
                    {"role": "user",      "content": "The 'code' field is empty. Write the complete function body."},
                ]
                continue

            print(f"  [coder] testing in sandbox...")
            result, success, error = run_in_sandbox(code, fn_name, fn_input)

            if success:
                print(f"  [coder] ✓ success")
                save_to_utils(fn_name, code, desc)
                hot_reload(fn_name, code)
                return result

            hint      = _error_hint(error)
            last_line = error.strip().splitlines()[-1]
            print(f"  [coder] sandbox failed: {last_line}")

            messages += [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        f"Your code failed:\n\n{error}\n"
                        f"{hint}\n\n"
                        f"Fix it. The function name must be exactly: {fn_name}"
                    )
                },
            ]

        except json.JSONDecodeError:
            print("  [coder] invalid JSON from qwen — retrying...")
            messages += [
                {"role": "user", "content": "Return ONLY the JSON object. No markdown, no explanation, nothing else."}
            ]
        except Exception as e:
            print(f"  [coder] unexpected error: {e}")
            break

    return f"Coding agent could not implement '{missing_tool}' after 3 attempts."