"""
A.I.N.D.Y. SDK quickstart example.

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
import logging
import os

from AINDY.sdk.aindy_sdk import AINDYClient, AINDYError

logger = logging.getLogger(__name__)

BASE_URL = os.environ.get("AINDY_BASE_URL", "http://localhost:8000")
API_KEY = os.environ.get("AINDY_API_KEY", "aindy_replace_me")

client = AINDYClient(base_url=BASE_URL, api_key=API_KEY)

logger.info("=== Reading memory ===")
try:
    result = client.memory.read("/memory/shawn/entities/**", limit=5)
    nodes = result["data"]["nodes"]
    logger.info("  Found %s nodes (syscall took %sms)", len(nodes), result["duration_ms"])
    for node in nodes[:3]:
        logger.info("  • %s", node.get("content", "")[:60])
except AINDYError as exc:
    logger.warning("  [error] %s", exc)
    nodes = []

logger.info("\n=== Running flow ===")
try:
    analysis = client.flow.run("analyze_entities", {"data": nodes})
    logger.info("  Flow status: %s", analysis["status"])
    if analysis["status"] == "success":
        logger.info("  Output keys: %s", list(analysis["data"].keys()))
except AINDYError as exc:
    logger.warning("  [error] %s", exc)
    analysis = {"status": "error", "data": {}}

logger.info("\n=== Writing memory ===")
try:
    write_result = client.memory.write(
        "/memory/shawn/insights/outcome",
        f"Quickstart ran: found {len(nodes)} entities, flow status={analysis['status']}",
        tags=["sdk-demo", "quickstart"],
        node_type="insight",
    )
    logger.info("  Write status: %s", write_result["status"])
    if write_result["status"] == "success":
        node_id = write_result["data"].get("node", {}).get("id", "?")
        logger.info("  Node ID: %s", node_id)
except AINDYError as exc:
    logger.warning("  [error] %s", exc)

logger.info("\n=== Emitting event ===")
try:
    event_result = client.events.emit(
        "quickstart.completed",
        {
            "node_count": len(nodes),
            "flow_status": analysis["status"],
        },
    )
    logger.info("  Event status: %s", event_result["status"])
except AINDYError as exc:
    logger.warning("  [error] %s", exc)

logger.info("\n=== Running Nodus script ===")
try:
    nodus_result = client.nodus.run_script(
        script="""
let msg = "Hello from the SDK quickstart"
set_state("message", msg)
emit("sdk.hello", {text: msg})
""",
        input={},
    )
    logger.info("  Nodus status: %s", nodus_result["nodus_status"])
    logger.info("  Output state: %s", nodus_result.get("output_state", {}))
    logger.info("  Events emitted: %s", nodus_result.get("events_emitted", 0))
except AINDYError as exc:
    logger.warning("  [error] %s", exc)

logger.info("\n=== Syscall registry ===")
try:
    registry = client.syscalls.list(version="v1")
    logger.info("  Available versions: %s", registry["versions"])
    logger.info("  Total syscalls: %s", registry["total_count"])
    for action in sorted(registry["syscalls"].get("v1", {}).keys()):
        spec = registry["syscalls"]["v1"][action]
        deprecated = " [DEPRECATED]" if spec.get("deprecated") else ""
        logger.info("  • sys.v1.%s%s", action, deprecated)
except AINDYError as exc:
    logger.warning("  [error] %s", exc)

logger.info("\nDone.")
