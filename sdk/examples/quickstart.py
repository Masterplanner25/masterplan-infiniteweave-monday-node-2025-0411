"""
A.I.N.D.Y. SDK — quickstart example.

Run against a local server:

    # 1. Start the backend
    cd AINDY && uvicorn main:app --reload

    # 2. Create a Platform API key (one-time)
    curl -s -X POST http://localhost:8000/platform/keys \
      -H "Authorization: Bearer <your-jwt>" \
      -H "Content-Type: application/json" \
      -d '{"name": "sdk-demo", "scopes": ["memory.read", "memory.write", "flow.run", "event.emit"]}' \
      | python -m json.tool

    # 3. Run this example
    API_KEY=aindy_... python sdk/examples/quickstart.py
"""
import os
import sys

# Allow running from the repo root without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aindy import AINDYClient, AINDYError

BASE_URL = os.environ.get("AINDY_BASE_URL", "http://localhost:8000")
API_KEY  = os.environ.get("AINDY_API_KEY", "aindy_replace_me")

client = AINDYClient(base_url=BASE_URL, api_key=API_KEY)

# ── Step 1: Read memory nodes ────────────────────────────────────────────────
print("=== Reading memory ===")
try:
    result = client.memory.read("/memory/shawn/tasks/**", limit=5)
    nodes = result["data"]["nodes"]
    print(f"  Found {len(nodes)} nodes (syscall took {result['duration_ms']}ms)")
    for n in nodes[:3]:
        print(f"  • {n.get('content', '')[:60]}")
except AINDYError as e:
    print(f"  [error] {e}")
    nodes = []

# ── Step 2: Run a flow ───────────────────────────────────────────────────────
print("\n=== Running flow ===")
try:
    analysis = client.flow.run("analyze_tasks", {"data": nodes})
    print(f"  Flow status: {analysis['status']}")
    if analysis["status"] == "success":
        print(f"  Output keys: {list(analysis['data'].keys())}")
except AINDYError as e:
    print(f"  [error] {e}")
    analysis = {"status": "error", "data": {}}

# ── Step 3: Write an insight ─────────────────────────────────────────────────
print("\n=== Writing memory ===")
try:
    write_result = client.memory.write(
        "/memory/shawn/insights/outcome",
        f"Quickstart ran: found {len(nodes)} tasks, flow status={analysis['status']}",
        tags=["sdk-demo", "quickstart"],
        node_type="insight",
    )
    print(f"  Write status: {write_result['status']}")
    if write_result["status"] == "success":
        node_id = write_result["data"].get("node", {}).get("id", "?")
        print(f"  Node ID: {node_id}")
except AINDYError as e:
    print(f"  [error] {e}")

# ── Step 4: Emit an event ────────────────────────────────────────────────────
print("\n=== Emitting event ===")
try:
    ev = client.events.emit("quickstart.completed", {
        "node_count": len(nodes),
        "flow_status": analysis["status"],
    })
    print(f"  Event status: {ev['status']}")
except AINDYError as e:
    print(f"  [error] {e}")

# ── Step 5: Run a Nodus script inline ───────────────────────────────────────
print("\n=== Running Nodus script ===")
try:
    nodus_result = client.nodus.run_script(
        script="""
let msg = "Hello from the SDK quickstart"
set_state("message", msg)
emit("sdk.hello", {text: msg})
""",
        input={},
    )
    print(f"  Nodus status: {nodus_result['nodus_status']}")
    print(f"  Output state: {nodus_result.get('output_state', {})}")
    print(f"  Events emitted: {nodus_result.get('events_emitted', 0)}")
except AINDYError as e:
    print(f"  [error] {e}")

# ── Step 6: Inspect syscall registry ────────────────────────────────────────
print("\n=== Syscall registry ===")
try:
    registry = client.syscalls.list(version="v1")
    print(f"  Available versions: {registry['versions']}")
    print(f"  Total syscalls: {registry['total_count']}")
    for action in sorted(registry["syscalls"].get("v1", {}).keys()):
        spec = registry["syscalls"]["v1"][action]
        deprecated = " [DEPRECATED]" if spec.get("deprecated") else ""
        print(f"  • sys.v1.{action}{deprecated}")
except AINDYError as e:
    print(f"  [error] {e}")

print("\nDone.")
