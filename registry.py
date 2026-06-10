"""
registry.py — Tool/function registry manager for tradeAI.

WORKFLOW (enforced by convention):
  1. Before adding a new tool, call: registry.find("your intent")
  2. If a match is returned, use that tool — do not create a duplicate.
  3. If no match, create the tool in utils.py, register it here, update registry.json.

The registry is the single source of truth for:
  - What tools exist and what they do
  - Why each tool exists (reasoning)
  - Inputs / outputs / dependencies
  - Anti-patterns (what NOT to write because a tool already covers it)
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# Load registry from disk
# ─────────────────────────────────────────────────────────────────────────────

_REGISTRY_PATH = Path(__file__).parent / "registry.json"


def _load() -> dict:
    with open(_REGISTRY_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _save(data: dict) -> None:
    with open(_REGISTRY_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    print(f"[registry] Saved → {_REGISTRY_PATH}")


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def list_tools() -> list[str]:
    """Return the names of all registered tools."""
    return list(_load()["tools"].keys())


def get_tool(name: str) -> Optional[dict]:
    """
    Return full metadata for a tool by exact name, or None if not found.

    Example
    -------
    >>> meta = registry.get_tool("calculate_rsi")
    >>> print(meta["purpose"])
    """
    return _load()["tools"].get(name)


def find(intent: str) -> list[dict]:
    """
    Search the registry for tools whose purpose, reasoning, or
    do_not_duplicate_for fields contain the intent keywords.

    Always call this BEFORE writing a new function.

    Returns a list of matching tool metadata dicts (may be empty).

    Example
    -------
    >>> matches = registry.find("overbought oversold momentum")
    >>> for m in matches:
    ...     print(m["name"], "—", m["purpose"])
    """
    data = _load()
    intent_lower = intent.lower()
    keywords = intent_lower.split()
    results = []

    for tool_meta in data["tools"].values():
        searchable = " ".join([
            tool_meta.get("purpose", ""),
            tool_meta.get("reasoning", ""),
            " ".join(tool_meta.get("do_not_duplicate_for", [])),
            tool_meta.get("name", ""),
        ]).lower()

        if any(kw in searchable for kw in keywords):
            results.append(tool_meta)

    return results


def check_before_create(intent: str) -> None:
    """
    Pretty-print a pre-creation check result to stdout.

    Call this at the top of any code generation workflow before
    deciding whether to write a new function.

    Example
    -------
    >>> registry.check_before_create("rolling average of closes")
    """
    matches = find(intent)
    print(f"\n[registry] Pre-creation check for intent: '{intent}'")
    print("─" * 60)
    if matches:
        print(f"  ⚠  {len(match := matches)} existing tool(s) already cover this:\n")
        for m in matches:
            print(f"  ► {m['name']}")
            print(f"    Purpose : {m['purpose']}")
            print(f"    Reasoning: {m['reasoning']}")
            if m.get("do_not_duplicate_for"):
                dup_str = "\n              ".join(m["do_not_duplicate_for"])
                print(f"    Do NOT duplicate for: {dup_str}")
            print()
        print("  → REUSE one of the tools above instead of creating a new one.")
    else:
        print("  ✓  No existing tool found. Safe to create a new one.")
        print("  → After creating it, call registry.add_tool(...) to register it.")
    print("─" * 60 + "\n")


def add_tool(
    *,
    name: str,
    defined_in: str,
    purpose: str,
    reasoning: str,
    inputs: dict,
    outputs: str,
    dependencies: list[str],
    do_not_duplicate_for: list[str] | None = None,
    examples: list[str] | None = None,
    **extra,
) -> None:
    """
    Register a newly created tool in the registry.

    Raises ValueError if a tool with that name already exists —
    update via update_tool() instead.

    Example
    -------
    >>> registry.add_tool(
    ...     name="calculate_macd",
    ...     defined_in="utils.py",
    ...     purpose="Calculate MACD line, signal line, and histogram",
    ...     reasoning="Combines EMA crossover with momentum histogram. Use instead of writing raw EMA subtraction code.",
    ...     inputs={"args": "str — 'SYMBOL,FAST,SLOW,SIGNAL,INTERVAL'"},
    ...     outputs="str — MACD, signal, histogram values + BULLISH/BEARISH label",
    ...     dependencies=["requests", "BINANCE_BASE", "/klines endpoint"],
    ...     do_not_duplicate_for=["MACD computation", "EMA difference"],
    ...     examples=["calculate_macd('BTCUSDT,12,26,9,1h')"],
    ... )
    """
    data = _load()
    if name in data["tools"]:
        raise ValueError(
            f"[registry] Tool '{name}' already exists. "
            "Use update_tool() to modify an existing entry."
        )

    entry = {
        "name": name,
        "defined_in": defined_in,
        "purpose": purpose,
        "reasoning": reasoning,
        "inputs": inputs,
        "outputs": outputs,
        "dependencies": dependencies,
    }
    if do_not_duplicate_for is not None:
        entry["do_not_duplicate_for"] = do_not_duplicate_for
    if examples is not None:
        entry["examples"] = examples
    entry.update(extra)

    data["tools"][name] = entry
    data["_meta"]["last_updated"] = _today()
    _save(data)
    print(f"[registry] ✓ Registered new tool: '{name}'")


def update_tool(name: str, **fields) -> None:
    """
    Update one or more fields on an existing registry entry.

    Example
    -------
    >>> registry.update_tool("calculate_rsi", reasoning="Updated: also use for divergence detection")
    """
    data = _load()
    if name not in data["tools"]:
        raise KeyError(f"[registry] Tool '{name}' not found. Use add_tool() to create it.")
    data["tools"][name].update(fields)
    data["_meta"]["last_updated"] = _today()
    _save(data)
    print(f"[registry] ✓ Updated tool: '{name}'")


def get_constant(key: str) -> Optional[dict]:
    """Return a registered constant by key, or None."""
    return _load()["constants"].get(key)


def print_summary() -> None:
    """Print a compact summary of all registered tools."""
    data = _load()
    print(f"\n{'═'*62}")
    print(f"  tradeAI Tool Registry  (v{data['_meta']['version']})")
    print(f"  Last updated: {data['_meta']['last_updated']}")
    print(f"{'═'*62}")

    print("\n  CONSTANTS")
    for k, v in data["constants"].items():
        print(f"    {k:30s} → {str(v['value'])[:40]}")

    print("\n  TOOLS")
    for name, meta in data["tools"].items():
        short_purpose = textwrap.shorten(meta["purpose"], width=48)
        print(f"    {name:28s} — {short_purpose}")

    print("\n  AGENT")
    for name, meta in data.get("agent", {}).items():
        short_purpose = textwrap.shorten(meta["purpose"], width=48)
        print(f"    {name:28s} — {short_purpose}")

    print(f"\n{'═'*62}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _today() -> str:
    from datetime import date
    return date.today().isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# CLI convenience: python registry.py [find <intent>] [summary] [tool <name>]
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    if not args or args[0] == "summary":
        print_summary()
    elif args[0] == "find" and len(args) > 1:
        check_before_create(" ".join(args[1:]))
    elif args[0] == "tool" and len(args) > 1:
        meta = get_tool(args[1])
        if meta:
            print(json.dumps(meta, indent=2))
        else:
            print(f"No tool named '{args[1]}' found.")
    else:
        print("Usage:")
        print("  python registry.py summary")
        print("  python registry.py find <intent keywords>")
        print("  python registry.py tool <tool_name>")