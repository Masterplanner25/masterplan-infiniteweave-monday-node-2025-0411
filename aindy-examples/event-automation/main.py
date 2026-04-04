"""
Event-Driven Automation — A.I.N.D.Y. example project

Demonstrates the WAIT/RESUME pattern: one command starts a workflow that
suspends waiting for an approval signal; another command sends that signal
and the workflow automatically resumes.

Usage:
    python main.py start                          # start the workflow
    python main.py approve [--reviewer NAME]      # send approval
    python main.py reject  [--reason TEXT]        # send rejection
    python main.py status                         # check current state
    python main.py reset                          # clear local state

Environment:
    AINDY_BASE_URL   Server URL (default: http://localhost:8000)
    AINDY_API_KEY    Platform API key (required)
"""
# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if SDK_PATH.exists() and str(SDK_PATH) not in sys.path:
    sys.path.insert(0, str(SDK_PATH))

from aindy import AINDYClient, AINDYError
from workflow import clear_state, load_state, print_separator, save_state

# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL         = os.environ.get("AINDY_BASE_URL", "http://localhost:8000")
API_KEY          = os.environ.get("AINDY_API_KEY", "")
MEMORY_NAMESPACE = "/memory/examples/automation"
DATA_FILE        = Path(__file__).parent / "data" / "triggers.json"
NODUS_SCRIPT     = Path(__file__).parent / "nodus" / "approval_flow.nodus"

# ── Helpers ───────────────────────────────────────────────────────────────────

def header() -> None:
    print("\n" + "━" * 45)
    print("  Event-Driven Automation")
    print("━" * 45)


def make_client() -> AINDYClient:
    if not API_KEY:
        print("ERROR: Set AINDY_API_KEY environment variable.")
        sys.exit(1)
    return AINDYClient(base_url=BASE_URL, api_key=API_KEY)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_start(client: AINDYClient) -> None:
    """Load triggers, write to memory, start the approval workflow."""
    print("\n[start] Loading triggers...")
    with open(DATA_FILE) as f:
        triggers = json.load(f)
    print(f"  Loaded {len(triggers)} trigger(s) from {DATA_FILE.name}")

    # Write pending tasks to memory
    print("\n[start] Writing pending tasks to memory...")
    for t in triggers:
        try:
            result = client.memory.write(
                path=f"{MEMORY_NAMESPACE}/pending/outcome",
                content=t["content"],
                tags=t.get("tags", []),
                node_type=t.get("node_type", "outcome"),
                extra={
                    "status":    t.get("status"),
                    "requires":  t.get("requires", []),
                    "priority":  t.get("priority"),
                    "risk":      t.get("risk"),
                    "rollback":  t.get("rollback"),
                },
            )
            node_id = result["data"]["node"]["id"]
            print(f"  ✓ {t['content'][:45]:<45}  →  {node_id[:8]}...")
        except AINDYError as e:
            print(f"  ✗ {t['content'][:40]}: {e.message}")

    # Upload and start the Nodus approval flow
    print("\n[start] Starting approval workflow...")
    with open(NODUS_SCRIPT) as f:
        source = f.read()

    client.nodus.upload_script("approval_flow", source, overwrite=True)

    result = client.nodus.run_script(
        script_name="approval_flow",
        input={"namespace": MEMORY_NAMESPACE},
    )

    run_id = result.get("run_id") or result.get("trace_id", "unknown")
    status = result.get("nodus_status") or result.get("status", "unknown")

    save_state({"run_id": run_id, "namespace": MEMORY_NAMESPACE})

    print("  Script:  approval_flow")
    print(f"  Run ID:  {run_id}")
    print(f"  Status:  {status}")

    if status in ("waiting", "WAITING"):
        print_separator()
        print("Waiting for review signal...")
        print("(run `python main.py approve` in another terminal)")
        print()
        # Poll for completion (max 10 minutes)
        _poll_for_completion(client, run_id)
    else:
        _print_outcome(result)


def cmd_approve(client: AINDYClient, reviewer: str) -> None:
    """Send an approval signal to resume the waiting workflow."""
    _send_signal(client, approved=True, reviewer=reviewer,
                 note=f"All items verified by {reviewer}. Approved to proceed.")


def cmd_reject(client: AINDYClient, reason: str) -> None:
    """Send a rejection signal to resume the waiting workflow."""
    _send_signal(client, approved=False, reviewer="reviewer",
                 note=reason)


def cmd_status(client: AINDYClient) -> None:
    """Show the current workflow state."""
    state = load_state()
    run_id = state.get("run_id")
    if not run_id:
        print("No workflow in progress. Run `python main.py start`.")
        return

    print(f"\nRun ID:    {run_id}")
    print(f"Namespace: {state.get('namespace', MEMORY_NAMESPACE)}")

    try:
        info = client.execution.get(run_id)
        print(f"Status:    {info['data']['status']}")
        print(f"Syscalls:  {info['data']['syscall_count']}")
    except AINDYError as e:
        print(f"Could not fetch execution info: {e.message}")

    # Show memory tree
    try:
        tree = client.memory.tree(state.get("namespace", MEMORY_NAMESPACE))
        flat = tree["data"]["flat"]
        print(f"\nMemory ({len(flat)} node(s)):")
        for node in flat:
            print(f"  [{node['node_type']:8s}] {node['content'][:60]}")
    except AINDYError:
        pass


def cmd_reset() -> None:
    """Clear local workflow state."""
    clear_state()
    print("Workflow state cleared.")


# ── Internal ──────────────────────────────────────────────────────────────────

def _send_signal(
    client: AINDYClient,
    approved: bool,
    reviewer: str,
    note: str,
) -> None:
    state = load_state()
    if not state.get("run_id"):
        print("No workflow in progress. Run `python main.py start` first.")
        sys.exit(1)

    label = "APPROVAL" if approved else "REJECTION"
    print(f"\nSending {label} signal...")
    print(f"  Reviewer: {reviewer}")
    print(f"  Note:     {note}")

    try:
        ev = client.events.emit("task.review.requested", {
            "approved": approved,
            "reviewer": reviewer,
            "note":     note,
        })
        print(f"  ✓ Signal emitted — id: {ev['data'].get('event_id', 'ok')}")
    except AINDYError as e:
        print(f"  ✗ Failed to emit signal: {e.message}")
        sys.exit(1)


def _poll_for_completion(client: AINDYClient, run_id: str, max_wait: int = 600) -> None:
    """Poll the execution status until it leaves the waiting state."""
    deadline = time.monotonic() + max_wait
    interval = 2

    while time.monotonic() < deadline:
        time.sleep(interval)
        try:
            info = client.execution.get(run_id)
            status = info["data"]["status"]
            if status in ("success", "SUCCESS"):
                print_separator("RESUMED")
                _print_memory_outcome(client)
                clear_state()
                print("\nDone.")
                return
            if status in ("failed", "FAILED", "error"):
                print(f"\nWorkflow failed: {info['data'].get('error', 'unknown error')}")
                clear_state()
                return
        except AINDYError:
            pass  # server may still be processing — keep polling

    print(f"\nTimed out after {max_wait}s. The workflow is still waiting.")
    print("Run `python main.py approve` to complete it, or `python main.py status` to check.")


def _print_memory_outcome(client: AINDYClient) -> None:
    """Print the results written to memory after resume."""
    namespace = load_state().get("namespace", MEMORY_NAMESPACE)
    try:
        insights = client.memory.read(f"{namespace}/review/*")
        for node in insights["data"]["nodes"]:
            print(f"\n  Decision: {node['content']}")
            extra = node.get("extra", {})
            if extra.get("reviewer"):
                print(f"  Reviewer: {extra['reviewer']}")
            if extra.get("outcome"):
                print(f"  Outcome:  {extra['outcome'].upper()}")

        approved_nodes = client.memory.read(f"{namespace}/approved/*")
        acount = len(approved_nodes["data"]["nodes"])
        if acount:
            print(f"\n  Approved items written to memory: {acount}")
    except AINDYError:
        pass


def _print_outcome(result: dict) -> None:
    state = result.get("output_state", {})
    outcome = state.get("outcome", "unknown")
    print(f"\n  Outcome:  {outcome.upper()}")
    if state.get("reviewer"):
        print(f"  Reviewer: {state['reviewer']}")
    if state.get("processed_count"):
        print(f"  Processed: {state['processed_count']} task(s)")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Event-Driven Automation — A.I.N.D.Y. example",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("start",  help="Start the approval workflow")

    ap = sub.add_parser("approve", help="Send an approval signal")
    ap.add_argument("--reviewer", default="reviewer",
                    help="Reviewer name (default: reviewer)")

    rp = sub.add_parser("reject", help="Send a rejection signal")
    rp.add_argument("--reason", default="Does not meet requirements",
                    help="Rejection reason")

    sub.add_parser("status", help="Show current workflow state")
    sub.add_parser("reset",  help="Clear local workflow state")

    args = parser.parse_args()

    header()

    if args.command == "reset":
        cmd_reset()
        return

    client = make_client()

    if args.command == "start":
        cmd_start(client)
    elif args.command == "approve":
        cmd_approve(client, reviewer=args.reviewer)
    elif args.command == "reject":
        cmd_reject(client, reason=args.reason)
    elif args.command == "status":
        cmd_status(client)


if __name__ == "__main__":
    main()
