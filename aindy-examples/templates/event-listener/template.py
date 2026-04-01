"""
Event Listener Template
───────────────────────
Pattern:  wait for event → react → repeat

Starts a Nodus script that loops, waiting for a trigger event.
Each time the event fires, the handler flow runs.

Fill in the three marked lines and run:
    python template.py
"""
import os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "sdk"))
from aindy import AINDYClient, AINDYError

# ── 1. Connect ────────────────────────────────────────────────────────────────

client = AINDYClient(
    base_url=os.environ.get("AINDY_BASE_URL", "http://localhost:8000"),
    api_key=os.environ.get("AINDY_API_KEY", ""),
)

# ── 2. Configure (fill these in) ─────────────────────────────────────────────

TRIGGER_EVENT = "task.created"           # ← CHANGE THIS  (event type to wait for)
HANDLER_FLOW  = "handle_task"            # ← CHANGE THIS  (flow to run on each event)
WRITE_PATH    = "/memory/{user}/handled" # ← CHANGE THIS  (where to write results)

# ── 3. Upload the listener script ────────────────────────────────────────────

LISTENER_SCRIPT = f"""
// Auto-generated listener — do not edit manually; edit template.py instead
let running = true
while running {{
    let signal = sys("sys.v1.event.wait", {{
        event_type: "{TRIGGER_EVENT}",
        timeout_seconds: 3600
    }})

    let payload = signal.data.payload

    let result = sys("sys.v1.flow.run", {{
        flow_name: "{HANDLER_FLOW}",
        input:     {{event: payload}}
    }})

    sys("sys.v1.memory.write", {{
        path:      "{WRITE_PATH}",
        content:   result.data.summary,
        tags:      ["handled", "auto"],
        node_type: "outcome",
        extra:     {{trigger: "{TRIGGER_EVENT}", result: result.data}}
    }})

    emit("{TRIGGER_EVENT}.handled", {{
        flow:   "{HANDLER_FLOW}",
        status: result.status
    }})

    // Loop — wait for the next event
    running = true
}}
"""

def run() -> None:
    # Upload the listener
    client.nodus.upload_script("event_listener", LISTENER_SCRIPT, overwrite=True)
    print(f"Listener uploaded.")
    print(f"  Trigger:  {TRIGGER_EVENT}")
    print(f"  Handler:  {HANDLER_FLOW}")
    print(f"  Output:   {WRITE_PATH}")

    # Start it (it suspends immediately at event.wait)
    result = client.nodus.run_script(script_name="event_listener", input={})
    run_id = result.get("run_id") or result.get("trace_id")
    print(f"\nListener running — run_id: {run_id}")
    print(f"Status: {result.get('nodus_status', result.get('status'))}")
    print(f"\nWaiting for '{TRIGGER_EVENT}' events...")
    print("Send one with:")
    print(f"  python -c \""
          f"import os,sys; sys.path.insert(0,'../../../sdk'); "
          f"from aindy import AINDYClient; "
          f"c=AINDYClient(os.environ['AINDY_BASE_URL'],os.environ['AINDY_API_KEY']); "
          f"c.events.emit('{TRIGGER_EVENT}',{{'id':'test-1'}})\"")


if __name__ == "__main__":
    try:
        run()
    except AINDYError as e:
        print(f"Error [{e.status_code}]: {e.message}")
        sys.exit(1)
