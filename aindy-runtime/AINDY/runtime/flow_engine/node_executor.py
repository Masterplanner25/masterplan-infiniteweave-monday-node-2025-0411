from AINDY.runtime.flow_engine.registry import NODE_REGISTRY
from AINDY.runtime.flow_engine.shared import _resolve_retry_policy, time

POLICY: dict = {
    "max_retries": 3,
    "blocked_nodes": [],
    "max_flow_duration_seconds": 300,
}
_FLOW_RETRY_POLICY = _resolve_retry_policy(execution_type="flow")


def enforce_policy(node_name: str) -> None:
    if node_name in POLICY["blocked_nodes"]:
        raise PermissionError(f"Node '{node_name}' is blocked by policy")


def execute_node(node_name: str, state: dict, context: dict) -> dict:
    enforce_policy(node_name)
    if node_name not in NODE_REGISTRY:
        raise KeyError(
            f"Node '{node_name}' not in registry. "
            f"Available: {list(NODE_REGISTRY.keys())}"
        )

    node_fn = NODE_REGISTRY[node_name]
    attempt = context["attempts"].get(node_name, 0) + 1
    context["attempts"][node_name] = attempt
    context["node_name"] = node_name

    from AINDY.memory.memory_helpers import enrich_context, record_execution_feedback

    enrich_context(context)
    start_ms = int(time.time() * 1000)
    result = node_fn(state, context)
    end_ms = int(time.time() * 1000)
    result["_execution_time_ms"] = end_ms - start_ms

    status = result.get("status", "")
    if status == "SUCCESS":
        outcome = "success"
    elif status == "FAILURE":
        outcome = "failure"
    else:
        outcome = "neutral"
    record_execution_feedback(context, outcome)
    return result


def resolve_next_node(current_node: str, state: dict, flow: dict):
    edges = flow["edges"].get(current_node, [])
    if not edges:
        return None

    first = edges[0]
    if isinstance(first, dict):
        for edge in edges:
            if edge["condition"](state):
                return edge["target"]
        return None
    return first
