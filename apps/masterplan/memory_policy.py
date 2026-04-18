"""Masterplan-owned memory policies."""


POLICIES = {
    "genesis_message": {
        "significance": 0.3,
        "node_type": "insight",
        "tags": ["genesis", "conversation"],
        "shared_namespaces": ["genesis"],
    },
    "genesis_synthesized": {
        "significance": 0.9,
        "node_type": "decision",
        "memory_type": "decision",
        "tags": ["genesis", "synthesis"],
        "shared_namespaces": ["genesis"],
    },
    "masterplan_locked": {
        "significance": 1.0,
        "node_type": "decision",
        "memory_type": "decision",
        "tags": ["genesis", "masterplan"],
        "shared_namespaces": ["genesis"],
    },
    "masterplan_activated": {
        "significance": 1.0,
        "node_type": "decision",
        "memory_type": "decision",
        "tags": ["genesis", "activation"],
        "shared_namespaces": ["genesis"],
    },
}


def register(register_policy):
    for event_type, policy in POLICIES.items():
        register_policy(event_type, policy)
