# code_agent.py — Coding Agent (powered by qwen2.5-coder:7b)
#
# Pipeline:
#   main agent (llama3.2:3b) hits unknown tool
#       → coding_agent() called here
#       → qwen2.5-coder:7b writes the function
#       → sandbox runs + validates it
#       → saved to utils.py permanently
#       → hot-reloaded into live TOOLS dict
#       → result returned to main agent as observation

import json
import sys
import io
import traceback
import ollama

from config import CODER_MODEL

# =========================================================================
# System prompt — tuned for qwen2.5-coder
# =========================================================================

CODER_SYSTEM_PROMPT = """You are a Python coding agent for a crypto market analysis tool.
Your only job: write a single working Python function and return it as JSON.

STRICT OUTPUT FORMAT — respond with ONLY this JSON, nothing else, no markdown:
{
  "function_name": "snake_case_name",
  "description": "one line description of what it does",
  "code": "def snake_case_name(args: str) -> str:\\n    ..."
}

RULES:
- Function signature: def name(args: str) -> str
- Parse args like this: parts = [p.strip() for p in args.split(",")]
- Return a human-readable string result
- DO NOT add import statements — these are already available: requests, json, math
- Binance base URL: https://api.binance.com/api/v3

CRITICAL — BINANCE KLINE STRUCTURE:
/klines returns a list of lists. Each candle is a list:
  candle[0] = open time (int ms)
  candle[1] = open price (str)
  candle[2] = high price (str)
  candle[3] = low price (str)
  candle[4] = close price (str)  ← use this for price calculations
  candle[5] = volume (str)

Always cast to float: float(candle[4])
NEVER use dict keys like candle["close"] — it will crash.

REFERENCE IMPLEMENTATION (follow this exact pattern):
def calculate_sma(args: str) -> str:
    parts = [p.strip() for p in args.split(",")]
    symbol = parts[0].upper()
    period = int(parts[1]) if len(parts) > 1 else 20
    tf = parts[2] if len(parts) > 2 else "1h"
    r = requests.get("https://api.binance.com/api/v3/klines",
                     params={"symbol": symbol, "interval": tf, "limit": period})
    r.raise_for_status()
    closes = [float(c[4]) for c in r.json()]
    sma = sum(closes) / len(closes)
    return f"{symbol} SMA({period}) on {tf} = {sma:.4f}"
"""

# =========================================================================
# Sandbox — safe isolated execution
# =========================================================================

def run_in_sandbox(code: str, fn_name: str, fn_input: str):
    """
    Execute generated code in an isolated namespace.
    Returns (result_str, success_bool, error_str)
    """
    import requests as _req
    import math as _math

    namespace = {
        "requests": _req,
        "math":     _math,
        "json":     json,
    }

    old_stdout = sys.stdout
    sys.stdout = io.StringIO()

    try:
        exec(compile(code, "<generated>", "exec"), namespace)

        if fn_name not in namespace:
            sys.stdout = old_stdout
            return None, False, f"Function '{fn_name}' was not found after exec — check the function name matches exactly."

        result = namespace[fn_name](fn_input)
        sys.stdout = old_stdout
        return str(result), True, ""

    except Exception:
        sys.stdout = old_stdout
        return None, False, traceback.format_exc()


# =========================================================================
# Persist to utils.py
# =========================================================================

def save_to_utils(fn_name: str, code: str, description: str):
    """Append the new function to utils.py and register it in TOOLS dict."""
    try:
        with open("utils.py", "r") as f:
            content = f.read()

        if f"def {fn_name}(" in content:
            print(f"  [coder] '{fn_name}' already exists in utils.py — skipping")
            return

        marker = "# =========================================================================\n# Tool registry"
        if marker not in content:
            print("  [coder] WARNING: could not find Tool registry marker in utils.py")
            return

        # Insert function body before the TOOLS registry block
        new_content = content.replace(
            marker,
            f"\n\n{code.strip()}\n\n\n{marker}"
        )

        # Add to TOOLS dict — insert before the closing }
        insert_at  = new_content.rfind("}")
        padding    = " " * max(1, 20 - len(fn_name))
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
# Hot-reload into live TOOLS dict (no restart needed)
# =========================================================================

def hot_reload(fn_name: str, code: str):
    """Inject the new function into the running TOOLS dict immediately."""
    try:
        import requests, math, utils

        ns = {"requests": requests, "math": math, "json": json}
        exec(compile(code, "<generated>", "exec"), ns)

        if fn_name in ns:
            utils.TOOLS[fn_name] = ns[fn_name]
            print(f"  [coder] ✓ '{fn_name}' hot-reloaded into live TOOLS")
        else:
            print(f"  [coder] hot-reload: function not found in namespace")

    except Exception as e:
        print(f"  [coder] hot-reload failed: {e}")


# =========================================================================
# Error hint helper — gives qwen specific guidance based on error type
# =========================================================================

def _error_hint(error: str) -> str:
    if "KeyError" in error:
        return "\nFIX: You indexed a list with a string key. Binance klines are LISTS. Use candle[4] not candle['close']."
    if "IndexError" in error:
        return "\nFIX: Index out of range. Make sure 'limit' in your klines request is large enough."
    if "TypeError" in error and "float" in error:
        return "\nFIX: Binance returns prices as strings. Always wrap with float(): float(candle[4])"
    if "NameError" in error:
        return "\nFIX: Do NOT write import statements. requests, json, and math are already available."
    if "JSONDecodeError" in error or "raise_for_status" in error:
        return "\nFIX: The API call failed. Double-check the endpoint URL and parameters."
    return ""


# =========================================================================
# Main entry point — called from app.py when tool is missing
# =========================================================================

def coding_agent(missing_tool: str, fn_input: str, context: str = "") -> str:
    """
    Spawns qwen2.5-coder to write a missing tool function.
    Returns the function's output string (same format as any other tool).
    """
    print(f"\n  [coder] '{missing_tool}' not in TOOLS — handing off to {CODER_MODEL}...")

    user_message = f"""Write a function called `{missing_tool}`.

Input it will receive: "{fn_input}"
Purpose: {context or "Infer from the function name and input values."}

Follow the reference implementation pattern exactly.
Use float(candle[4]) for close prices from /klines.
Do not add any import statements.
"""

    messages = [
        {"role": "system", "content": CODER_SYSTEM_PROMPT},
        {"role": "user",   "content": user_message},
    ]

    for attempt in range(1, 4):
        print(f"  [coder] generating... (attempt {attempt}/3)")

        try:
            response = ollama.chat(
                model=CODER_MODEL,
                messages=messages,
                format="json",
                options={"temperature": 0.1}  # low temp = more deterministic code
            )

            raw  = response["message"]["content"]
            data = json.loads(raw)

            fn_name = data.get("function_name", missing_tool)
            code    = data.get("code", "").strip()
            desc    = data.get("description", "")

            if not code:
                messages += [
                    {"role": "assistant", "content": raw},
                    {"role": "user",      "content": "The 'code' field is empty. Write the complete function."},
                ]
                continue

            print(f"  [coder] testing '{fn_name}' in sandbox...")
            result, success, error = run_in_sandbox(code, fn_name, fn_input)

            if success:
                print(f"  [coder] ✓ works correctly")
                save_to_utils(fn_name, code, desc)
                hot_reload(fn_name, code)
                return result

            # Feed error + specific hint back to qwen for self-correction
            hint = _error_hint(error)
            last_line = error.strip().splitlines()[-1]
            print(f"  [coder] failed: {last_line}")

            messages += [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        f"Your code failed with this error:\n\n{error}\n"
                        f"{hint}\n\n"
                        "Fix the issue and return the corrected JSON."
                    )
                },
            ]

        except json.JSONDecodeError:
            print("  [coder] model returned invalid JSON — retrying...")
            messages += [
                {"role": "user", "content": "Your response was not valid JSON. Return ONLY the JSON object, no other text."}
            ]
        except Exception as e:
            print(f"  [coder] unexpected error: {e}")
            break

    return f"Coding agent could not implement '{missing_tool}' after 3 attempts."