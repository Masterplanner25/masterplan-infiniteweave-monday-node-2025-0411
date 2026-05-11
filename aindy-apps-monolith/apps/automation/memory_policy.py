"""Automation-owned memory policies."""


POLICIES = {
    "error_encountered": {
        "significance": 0.8,
        "node_type": "insight",
        "memory_type": "failure",
        "tags": ["error", "learning"],
    },
    "insight_detected": {"significance": 0.7, "node_type": "insight"},
    "flow_completion": {"significance": 0.5, "node_type": "outcome"},
}


def register(register_policy):
    for event_type, policy in POLICIES.items():
        register_policy(event_type, policy)
