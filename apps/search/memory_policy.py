"""Search-owned memory policies."""


POLICIES = {
    "leadgen_search": {
        "significance": 0.4,
        "node_type": "outcome",
        "tags": ["leadgen", "search"],
    },
}


def register(register_policy):
    for event_type, policy in POLICIES.items():
        register_policy(event_type, policy)
