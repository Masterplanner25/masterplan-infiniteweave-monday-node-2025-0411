"""
Scheduled Agent Template
─────────────────────────
Pattern:  cron fires → Nodus script runs → writes output → emits event

Set up once. Runs forever without you.

Fill in the four marked lines and run:
    python template.py setup
    python template.py run-now   # test without waiting for cron
    python template.py cancel
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "sdk"))
from aindy import AINDYClient, AINDYError

# ── 1. Connect ────────────────────────────────────────────────────────────────

client = AINDYClient(
    base_url=os.environ.get("AINDY_BASE_URL", "http://localhost:8000"),
    api_key=os.environ.get("AINDY_API_KEY", ""),
)

# ── 2. Configure (fill these in) ─────────────────────────────────────────────

CRON_EXPR     = "0 9 * * *"                    # ← CHANGE THIS  (when to run)
NAMESPACE     = "/memory/{user}"               # ← CHANGE THIS  (memory prefix)
FLOW_NAME     = "daily_analysis"               # ← CHANGE THIS  (flow to run)
OUTPUT_EVENT  = "agent.run.complete"           # ← CHANGE THIS  (event to emit)

SCHEDULE_NAME = "my_scheduled_agent"           # job name — must be unique per user

# ── 3. The agent script ───────────────────────────────────────────────────────
#
# This runs on every cron tick. Edit the body — keep the top/bottom boilerplate.

AGENT_SCRIPT = f"""
let ns = "{NAMESPACE}"

// ── Your logic here ──────────────────────────────────────────────────────────

let data = sys("sys.v1.memory.read", {{path: ns + "/**", limit: 100}})
let nodes = data.data.nodes

let result = sys("sys.v1.flow.run", {{
    flow_name: "{FLOW_NAME}",
    input:     {{nodes: nodes}}
}})

sys("sys.v1.memory.write", {{
    path:      ns + "/output/outcome",
    content:   result.data.summary,
    tags:      ["scheduled", "auto"],
    node_type: "outcome"
}})

// ── Boilerplate — do not remove ───────────────────────────────────────────────
emit("{OUTPUT_EVENT}", {{node_count: nodes.length, status: result.status}})
set_state("done",        true)
set_state("node_count",  nodes.length)
set_state("summary",     result.data.summary)
"""

# ── 4. Commands ───────────────────────────────────────────────────────────────

def cmd_setup() -> None:
    # Upload script
    client.nodus.upload_script(SCHEDULE_NAME, AGENT_SCRIPT, overwrite=True)
    print(f"Script uploaded:  {SCHEDULE_NAME}")

    # Clear any existing schedule with this name
    try:
        client.delete(f"/platform/nodus/schedule/{SCHEDULE_NAME}")
    except AINDYError:
        pass

    # Create schedule
    sched = client.post("/platform/nodus/schedule", {
        "name":      SCHEDULE_NAME,
        "flow_name": SCHEDULE_NAME,
        "cron_expr": CRON_EXPR,
        "state":     {"namespace": NAMESPACE},
    })
    print(f"Schedule created: {CRON_EXPR}")
    print(f"Next run:         {sched.get('next_run_at', '—')}")
    print("\nDone. Run `python template.py run-now` to test immediately.")


def cmd_run_now() -> None:
    result = client.nodus.run_script(
        script_name=SCHEDULE_NAME,
        input={"namespace": NAMESPACE},
    )
    status   = result.get("nodus_status") or result.get("status")
    duration = result.get("duration_ms", "?")
    state    = result.get("output_state", {})
    print(f"Status:    {status}  ({duration}ms)")
    print(f"Nodes:     {state.get('node_count', '?')}")
    print(f"Summary:   {state.get('summary', '—')}")


def cmd_cancel() -> None:
    client.delete(f"/platform/nodus/schedule/{SCHEDULE_NAME}")
    print(f"Schedule cancelled: {SCHEDULE_NAME}")


def cmd_status() -> None:
    jobs = client.get("/platform/nodus/schedule")
    job  = next((j for j in jobs.get("jobs", []) if j["name"] == SCHEDULE_NAME), None)
    if not job:
        print("No active schedule.")
        return
    print(f"Name:      {job['name']}")
    print(f"Cron:      {job['cron_expr']}")
    print(f"Next run:  {job.get('next_run_at', '—')}")
    print(f"Last run:  {job.get('last_run_at', 'never')}")
    print(f"Active:    {'yes' if job.get('is_active') else 'no'}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["setup", "run-now", "cancel", "status"])
    args = p.parse_args()
    try:
        {"setup": cmd_setup, "run-now": cmd_run_now,
         "cancel": cmd_cancel, "status": cmd_status}[args.command]()
    except AINDYError as e:
        print(f"Error [{e.status_code}]: {e.message}")
        sys.exit(1)
