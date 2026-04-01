"""
upload_scripts.py — upload all shared Nodus scripts to A.I.N.D.Y.

Usage:
    python upload_scripts.py

Environment:
    AINDY_BASE_URL   Server URL (default: http://localhost:8000)
    AINDY_API_KEY    Platform API key (required)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

SDK_PATH = Path(__file__).resolve().parents[1] / "sdk"
if SDK_PATH.exists() and str(SDK_PATH) not in sys.path:
    sys.path.insert(0, str(SDK_PATH))

from aindy import AINDYClient, AINDYError

BASE_URL = os.environ.get("AINDY_BASE_URL", "http://localhost:8000")
API_KEY  = os.environ.get("AINDY_API_KEY", "")

# Map: (filename, script_name_to_register)
SCRIPTS = [
    ("analyze.nodus",        "memory_analyze"),
    ("approval_flow.nodus",  "approval_flow"),
    ("daily_briefing.nodus", "daily_briefing"),
    ("task_processor.nodus", "task_processor"),
]

# Pull scripts from sub-example directories too
SCRIPT_SEARCH_DIRS = [
    Path(__file__).parent,
    Path(__file__).parent.parent / "memory-analyzer"  / "nodus",
    Path(__file__).parent.parent / "event-automation"  / "nodus",
    Path(__file__).parent.parent / "scheduled-agent"   / "nodus",
]


def find_script(filename: str) -> Path | None:
    for d in SCRIPT_SEARCH_DIRS:
        p = d / filename
        if p.exists():
            return p
    return None


def main() -> None:
    if not API_KEY:
        print("ERROR: Set AINDY_API_KEY environment variable.")
        sys.exit(1)

    client = AINDYClient(base_url=BASE_URL, api_key=API_KEY)
    print("Uploading Nodus scripts...\n")

    uploaded = 0
    for filename, script_name in SCRIPTS:
        path = find_script(filename)
        if path is None:
            print(f"  ✗ {script_name:<20}  ({filename} not found — skipping)")
            continue
        try:
            with open(path) as f:
                source = f.read()
            client.nodus.upload_script(script_name, source, overwrite=True)
            print(f"  ✓ {script_name:<20}  ({filename})")
            uploaded += 1
        except AINDYError as e:
            print(f"  ✗ {script_name:<20}  ERROR: {e.message}")

    print(f"\n{uploaded} script(s) uploaded.")


if __name__ == "__main__":
    main()
