from __future__ import annotations

from typing import Dict, List

from .types import RecallRequest


class Strategy:
    def __init__(self, node_types: List[str], initial_pool_size: int, diversity_factor: float):
        self.node_types = node_types
        self.initial_pool_size = initial_pool_size
        self.diversity_factor = diversity_factor


STRATEGIES: Dict[str, Strategy] = {
    "analysis": Strategy(
        node_types=["outcome", "insight"],
        initial_pool_size=15,
        diversity_factor=0.3,
    ),
    "codegen": Strategy(
        node_types=["outcome"],
        initial_pool_size=10,
        diversity_factor=0.1,
    ),
    "strategy": Strategy(
        node_types=["decision", "insight"],
        initial_pool_size=20,
        diversity_factor=0.5,
    ),
    "nodus_execution": Strategy(
        node_types=["outcome", "decision"],
        initial_pool_size=12,
        diversity_factor=0.2,
    ),
}


class StrategySelector:
    def select(self, request: RecallRequest) -> Strategy:
        return STRATEGIES.get(
            request.task_type,
            Strategy(["outcome"], 10, 0.2),
        )
