from __future__ import annotations

from typing import Any


def response_for_execution(executed: list[dict[str, Any]]) -> str:
    """Turn successful local tool results into natural, short Brainbox replies."""
    if not executed:
        return "I understood the request, but I need confirmation before I can do that."

    parts: list[str] = []
    for item in executed:
        name = item.get("name")
        result = item.get("result") or {}
        if name == "open_application":
            app = result.get("name") if isinstance(result, dict) else None
            parts.append(f"Done bro, {app or 'the app'} is open.")
        elif name == "get_pc_status":
            if isinstance(result, dict):
                parts.append(f"Your PC is running {result.get('platform', 'Windows')} with {result.get('memory_available_gb', '?')} GB of memory available.")
            else:
                parts.append("Your PC status is available.")
        else:
            parts.append(f"Done bro, {name} completed.")
    return " ".join(parts)
