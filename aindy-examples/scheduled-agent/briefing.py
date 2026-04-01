"""
briefing.py — display helpers for the scheduled-agent example.

Formats briefing output and reading history from memory.
"""
from __future__ import annotations

from typing import Any


def print_briefing_box(output_state: dict[str, Any]) -> None:
    """Print a formatted briefing box from Nodus output_state."""
    briefing   = output_state.get("briefing", "—")
    node_count = output_state.get("node_count", 0)
    blocked    = output_state.get("blocked", 0)
    flow_ran   = output_state.get("flow_ran", False)

    width = 50
    lines = _wrap(briefing, width - 4)

    print(f"  ┌{'─' * width}┐")
    for line in lines:
        print(f"  │  {line:<{width - 2}}│")
    print(f"  └{'─' * width}┘")
    print()

    print(f"  Nodes scanned:   {node_count}")
    if blocked:
        print(f"  ⚠ Blocked tasks: {blocked}")
    print(f"  Deep analysis:   {'yes (flow ran)' if flow_ran else 'no (< 3 nodes)'}")


def print_briefing_history(nodes: list[dict[str, Any]], limit: int = 5) -> None:
    """Print recent briefing nodes from memory."""
    shown = nodes[:limit]
    if not shown:
        print("  No briefings found.")
        return
    for node in shown:
        created = node.get("created_at", "—")[:19].replace("T", " ")
        extra   = node.get("extra", {})
        count   = extra.get("total", "?")
        content = node.get("content", "")[:60]
        print(f"  • {created}  {str(count):>3} nodes  \"{content}\"")


def _wrap(text: str, width: int) -> list[str]:
    """Wrap text to the given width."""
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 <= width:
            current = (current + " " + word).lstrip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]
