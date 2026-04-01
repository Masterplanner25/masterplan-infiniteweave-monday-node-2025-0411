"""
Memory Loop Template
────────────────────
Pattern:  read memory → process → write results back

Fill in the four marked lines and run:
    python template.py
"""
import os, sys
from pathlib import Path

# SDK path (adjust if installed differently)
sys.path.insert(0, str(Path(__file__).parents[3] / "sdk"))
from aindy import AINDYClient, AINDYError

# ── 1. Connect ────────────────────────────────────────────────────────────────

client = AINDYClient(
    base_url=os.environ.get("AINDY_BASE_URL", "http://localhost:8000"),
    api_key=os.environ.get("AINDY_API_KEY", ""),
)

# ── 2. Configure (fill these in) ─────────────────────────────────────────────

READ_PATH   = "/memory/{user}/data/*"          # ← CHANGE THIS  (source path)
FLOW_NAME   = "process"                        # ← CHANGE THIS  (registered flow name)
WRITE_PATH  = "/memory/{user}/output"          # ← CHANGE THIS  (destination path)
EVENT_TYPE  = "loop.complete"                  # ← CHANGE THIS  (completion event)

# ── 3. Run ────────────────────────────────────────────────────────────────────

def run() -> None:
    # Read
    read = client.memory.read(READ_PATH, limit=50)
    nodes = read["data"]["nodes"]
    print(f"Read {len(nodes)} node(s) from {READ_PATH}")

    if not nodes:
        print("Nothing to process.")
        return

    # Process
    result = client.flow.run(FLOW_NAME, {"nodes": nodes})
    output = result["data"]
    print(f"Flow '{FLOW_NAME}' → {result['status']} ({result['duration_ms']}ms)")

    # Write
    summary = output.get("summary") or str(output)
    write = client.memory.write(
        path=WRITE_PATH,
        content=summary,
        tags=["template", "output"],
        node_type="outcome",
        extra=output,
    )
    node_id = write["data"]["node"]["id"]
    print(f"Wrote result → {WRITE_PATH}/{node_id[:8]}...")

    # Emit
    client.events.emit(EVENT_TYPE, {"node_count": len(nodes), "output_id": node_id})
    print(f"Event emitted: {EVENT_TYPE}")


if __name__ == "__main__":
    try:
        run()
    except AINDYError as e:
        print(f"Error [{e.status_code}]: {e.message}")
        sys.exit(1)
