# app.py — Market Data Agentic AI
# Main agent: llama3.2:3b  (reasoning + analysis)
# Coding agent: qwen2.5-coder:7b  (writes missing tools on demand)

import json
import ollama

from config import MAIN_MODEL
from prompts import SYSTEM_PROMPT
from utils import TOOLS
from coding_agent import coding_agent


def run_agent():
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    print(f"Market Agent ready  [{MAIN_MODEL}]")
    print(f"Coding Agent ready  [qwen2.5-coder:7b]")
    print("Type 'exit' to quit.\n")

    while True:
        try:
            query = input(">> ").strip()
            if not query:
                continue
            if query.lower() in ["exit", "quit"]:
                break

            messages.append({
                "role": "user",
                "content": json.dumps({"type": "user", "user": query})
            })

            while True:
                response = ollama.chat(
                    model=MAIN_MODEL,
                    messages=messages,
                    format="json"
                )

                result = response["message"]["content"]
                messages.append({"role": "assistant", "content": result})

                try:
                    call = json.loads(result)
                except json.JSONDecodeError:
                    print("Agent Error: invalid JSON from LLM.")
                    break

                if call.get("type") == "output":
                    print(f"\nAgent: {call.get('output')}\n")
                    break

                elif call.get("type") == "action":
                    fn_name  = call.get("function")
                    fn_input = call.get("input", "")

                    print(f"  [action] {fn_name}({fn_input})")

                    if fn_name in TOOLS:
                        # Known tool — run directly
                        try:
                            observation = TOOLS[fn_name](fn_input)
                        except Exception as e:
                            observation = f"Tool error: {e}"
                    else:
                        # Unknown tool — hand off to coding agent
                        observation = coding_agent(
                            missing_tool=fn_name,
                            fn_input=fn_input,
                            context=f"User asked: {query}"
                        )

                    print(f"  [observe] {str(observation)[:120]}...")

                    messages.append({
                        "role": "user",
                        "content": json.dumps({
                            "type": "observation",
                            "observation": observation
                        })
                    })

                elif call.get("type") == "plan":
                    print(f"  [plan] {call.get('plan')}")

        except KeyboardInterrupt:
            print("\nExiting...")
            break


if __name__ == "__main__":
    run_agent()