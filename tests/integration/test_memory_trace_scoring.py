from __future__ import annotations

from AINDY.runtime.memory.scorer import MemoryScorer
from AINDY.runtime.memory.types import RecallRequest


def test_trace_bonus_applied():
    scorer = MemoryScorer()
    nodes = [
        {"id": "node-1", "content": "a", "node_type": "insight", "similarity": 0.5},
        {"id": "node-2", "content": "b", "node_type": "insight", "similarity": 0.5},
    ]
    request = RecallRequest(query="", user_id="u1", task_type="analysis", metadata={"trace_node_ids": {"node-2"}})

    scored = scorer.score(nodes, request)
    assert scored[0].id == "node-2"
