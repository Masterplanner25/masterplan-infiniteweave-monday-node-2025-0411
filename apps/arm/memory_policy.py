"""ARM-owned memory policies."""


POLICIES = {
    "arm_analysis_complete": {
        "significance": 0.7,
        "node_type": "insight",
        "tags": ["arm", "analysis"],
    },
    "arm_generation_complete": {
        "significance": 0.6,
        "node_type": "outcome",
        "tags": ["arm", "codegen"],
        "shared_namespaces": ["arm"],
    },
}


def register(register_policy):
    for event_type, policy in POLICIES.items():
        register_policy(event_type, policy)
