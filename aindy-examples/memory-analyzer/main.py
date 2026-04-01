"""
Memory Analyzer — A.I.N.D.Y. example project

Loads tasks from data/tasks.json, writes them to memory, runs pattern
analysis, writes structured insights back, and emits a completion event.

Usage:
    python main.py

Environment:
    AINDY_BASE_URL   Server URL (default: http://localhost:8000)
    AINDY_API_KEY    Platform API key (required)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Allow running without installing the SDK by finding it relative to this file.
SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if SDK_PATH.exists() and str(SDK_PATH) not in sys.path:
    sys.path.insert(0, str(SDK_PATH))

from aindy import AINDYClient, AINDYError
from analyzer import analyze

# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL         = os.environ.get("AINDY_BASE_URL", "http://localhost:8000")
API_KEY          = os.environ.get("AINDY_API_KEY", "")
MEMORY_NAMESPACE = "/memory/examples"
DATA_FILE        = Path(__file__).parent / "data" / "tasks.json"

# ── Helpers ───────────────────────────────────────────────────────────────────

def header(text: str) -> None:
    width = 45
    print(f"\n{'━' * width}")
    print(f"  {text}")
    print(f"{'━' * width}")


def step(n: int, total: int, text: str) -> None:
    print(f"\n[{n}/{total}] {text}")


def check_env() -> None:
    if not API_KEY:
        print("ERROR: Set AINDY_API_KEY environment variable.")
        print("       Create a key: POST /platform/keys")
        sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    check_env()
    t_start = time.monotonic()

    header("A.I.N.D.Y. Memory Analyzer")

    client = AINDYClient(base_url=BASE_URL, api_key=API_KEY)

    # ── Step 1: Load sample data ──────────────────────────────────────────────
    step(1, 5, "Loading sample data...")
    with open(DATA_FILE) as f:
        raw_tasks = json.load(f)
    print(f"  Loaded {len(raw_tasks)} tasks from {DATA_FILE.name}")

    # ── Step 2: Write tasks to memory ─────────────────────────────────────────
    step(2, 5, "Writing tasks to memory...")
    written_nodes = []
    for task in raw_tasks:
        try:
            result = client.memory.write(
                path=f"{MEMORY_NAMESPACE}/tasks/outcome",
                content=task["content"],
                tags=task.get("tags", []),
                node_type=task.get("node_type", "outcome"),
                extra={
                    "status":   task.get("status", "unknown"),
                    "priority": task.get("priority", "medium"),
                    "owner":    task.get("owner", "unassigned"),
                    "blocker":  task.get("blocker"),
                },
            )
            node = result["data"]["node"]
            written_nodes.append(node)
            short_id = node["id"][:8]
            print(f"  ✓ {task['content'][:45]:<45}  →  {short_id}...")
        except AINDYError as e:
            print(f"  ✗ Failed to write '{task['content'][:40]}': {e.message}")

    print(f"\n  Wrote {len(written_nodes)}/{len(raw_tasks)} tasks.")

    # ── Step 3: Read them back and run analysis flow ──────────────────────────
    step(3, 5, "Running analysis flow...")
    try:
        read_result = client.memory.read(
            path=f"{MEMORY_NAMESPACE}/tasks/*",
            limit=100,
        )
        task_nodes = read_result["data"]["nodes"]

        # Also run the local pattern detector (no server round-trip needed)
        analysis = analyze(task_nodes)

        # Attempt the flow — fall back gracefully if not registered
        try:
            flow_result = client.flow.run(
                "analyze_tasks",
                {"nodes": task_nodes, "context": "memory-analyzer example"},
            )
            print(f"  Flow:     analyze_tasks")
            print(f"  Status:   {flow_result['status']}")
            print(f"  Duration: {flow_result['duration_ms']}ms")
            # Merge flow output into analysis if the flow returned a summary
            if flow_result.get("data", {}).get("summary"):
                analysis["summary"] = flow_result["data"]["summary"]
        except AINDYError as e:
            print(f"  Flow unavailable ({e.message[:60]}) — using local analysis.")

    except AINDYError as e:
        print(f"  Read failed: {e}")
        task_nodes = written_nodes  # fall back to what we wrote
        analysis = analyze(task_nodes)

    # ── Step 4: Write insights to memory ──────────────────────────────────────
    step(4, 5, "Writing insights to memory...")
    insight_ids = []
    for insight in analysis["insights"]:
        try:
            result = client.memory.write(
                path=f"{MEMORY_NAMESPACE}/insights/decision",
                content=insight["content"],
                tags=insight["tags"],
                node_type="decision",
                extra=insight.get("data", {}),
            )
            node = result["data"]["node"]
            insight_ids.append(node["id"])
            print(f"  ✓ {insight['type']:<25}  →  {node['id'][:8]}...")
        except AINDYError as e:
            print(f"  ✗ Failed to write {insight['type']}: {e.message}")

    # ── Step 5: Summary ────────────────────────────────────────────────────────
    step(5, 5, "Summary")
    bd = analysis["status_breakdown"]
    total   = len(task_nodes)
    done    = bd.get("completed", 0)
    wip     = bd.get("in-progress", 0)
    blocked = bd.get("blocked", 0)
    top_tags_str = ", ".join(analysis["top_tags"][:3]) or "—"
    bottleneck   = analysis["bottleneck_tag"] or "none detected"

    print(f"  ┌─────────────────────────────────────────┐")
    print(f"  │  Tasks loaded:      {total:<4}                 │")
    print(f"  │  Completed:         {done:<4} ({analysis['completion_rate']:.1f}%)         │")
    print(f"  │  In progress:       {wip:<4}                 │")
    print(f"  │  Blocked:           {blocked:<4}                 │")
    print(f"  │  Top tags:          {top_tags_str:<22} │")
    print(f"  │  Bottleneck:        {bottleneck:<22} │")
    print(f"  │  Insights written:  {len(insight_ids):<4}                 │")
    print(f"  └─────────────────────────────────────────┘")

    # Emit completion event
    try:
        ev = client.events.emit("analysis.complete", {
            "namespace":       MEMORY_NAMESPACE,
            "task_count":      total,
            "completion_rate": analysis["completion_rate"],
            "insight_count":   len(insight_ids),
            "bottleneck":      analysis["bottleneck_tag"],
        })
        print(f"\n  Event emitted: analysis.complete")
    except AINDYError as e:
        print(f"\n  Event skipped: {e.message}")

    elapsed = round(time.monotonic() - t_start, 2)
    print(f"\n  Memory path: {MEMORY_NAMESPACE}/")
    print(f"\nDone in {elapsed}s")


if __name__ == "__main__":
    main()
