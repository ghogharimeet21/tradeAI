# agent.py — Market Data Agentic AI (ReAct loop, Binance tools, Ollama)
#
# ⚠  TOOL REGISTRY — before adding new tools or analysis functions:
#   1. python registry.py find "<intent>"      — check if it exists
#   2. python registry.py summary              — see all registered tools
#   3. If absent: add to utils.py + call registry.add_tool(...)

import json
import ollama





# =========================================================================
# Agent loop
# =========================================================================
from prompts import SYSTEM_PROMPT
from utils import TOOLS
import registry as reg

def run_agent():
    reg.print_summary()          # show registered tools on every startup
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    print("Market Agent ready. Type 'exit' to quit.\n")

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
                    model="llama3.2:3b",
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
                    fn_input = call.get("input")

                    print(f"  [action] {fn_name}({fn_input})")

                    if fn_name in TOOLS:
                        try:
                            observation = TOOLS[fn_name](fn_input)
                        except Exception as e:
                            observation = f"Tool error: {e}"

                        print(f"  [observe] {observation[:120]}...")

                        messages.append({
                            "role": "user",
                            "content": json.dumps({
                                "type": "observation",
                                "observation": observation
                            })
                        })
                    else:
                        print(f"Agent Error: unknown tool '{fn_name}'")
                        break

                elif call.get("type") == "plan":
                    print(f"  [plan] {call.get('plan')}")

        except KeyboardInterrupt:
            print("\nExiting...")
            break


if __name__ == "__main__":
    run_agent()