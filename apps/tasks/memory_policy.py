"""Task-owned memory policies."""


POLICIES = {
    "task_completed": {
        "significance": 0.5,
        "node_type": "outcome",
        "tags": ["task", "completion"],
    },
    "task_failed": {
        "significance": 0.8,
        "node_type": "outcome",
        "memory_type": "failure",
        "tags": ["task", "failure"],
    },
}


def register(register_policy):
    for event_type, policy in POLICIES.items():
        register_policy(event_type, policy)
