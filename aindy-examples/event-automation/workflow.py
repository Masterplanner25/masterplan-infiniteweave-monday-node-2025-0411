"""
workflow.py — state helpers for the event-automation example.

Manages the run_id across two separate process invocations using a local
state file (.workflow_state.json). In production you'd use a DB or cache.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

STATE_FILE = Path(__file__).parent / ".workflow_state.json"


def save_state(data: dict[str, Any]) -> None:
    """Persist workflow state to local file."""
    existing = load_state()
    existing.update(data)
    with open(STATE_FILE, "w") as f:
        json.dump(existing, f, indent=2)


def load_state() -> dict[str, Any]:
    """Load persisted workflow state."""
    if not STATE_FILE.exists():
        return {}
    with open(STATE_FILE) as f:
        return json.load(f)


def clear_state() -> None:
    """Delete persisted workflow state."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def get_run_id() -> str | None:
    """Return the current run_id, or None if no workflow is in progress."""
    return load_state().get("run_id")


def print_separator(label: str = "") -> None:
    width = 50
    if label:
        pad = (width - len(label) - 2) // 2
        print(f"\n{'─' * pad} {label} {'─' * pad}")
    else:
        print(f"\n{'─' * width}")
