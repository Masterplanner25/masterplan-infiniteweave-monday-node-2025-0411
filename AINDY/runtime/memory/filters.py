from __future__ import annotations

from collections import defaultdict, deque
from typing import List

from .types import MemoryItem, RecallRequest


class MemoryFilter:
    def apply(self, scored_nodes: List[MemoryItem], request: RecallRequest) -> List[MemoryItem]:
        if not scored_nodes:
            return []

        filtered = [n for n in scored_nodes if (n.score or 0.0) >= 0.25]
        if not filtered:
            return []

        filtered = _dedupe(filtered)
        filtered = _apply_diversity(filtered, request)
        return filtered


def _dedupe(nodes: List[MemoryItem]) -> List[MemoryItem]:
    seen_ids = set()
    seen_content = set()
    output = []
    for node in nodes:
        if node.id in seen_ids:
            continue
        content_key = (node.content or "").strip().lower()
        if content_key and content_key in seen_content:
            continue
        seen_ids.add(node.id)
        if content_key:
            seen_content.add(content_key)
        output.append(node)
    return output


def _apply_diversity(nodes: List[MemoryItem], request: RecallRequest) -> List[MemoryItem]:
    diversity_factor = request.metadata.get("diversity_factor", 0.2)
    if diversity_factor <= 0:
        return nodes

    grouped = defaultdict(deque)
    for node in nodes:
        grouped[node.node_type].append(node)

    output = []
    type_order = list(grouped.keys())

    while type_order:
        for node_type in list(type_order):
            queue = grouped.get(node_type)
            if not queue:
                type_order.remove(node_type)
                continue
            output.append(queue.popleft())
            if not queue:
                type_order.remove(node_type)

    return output
