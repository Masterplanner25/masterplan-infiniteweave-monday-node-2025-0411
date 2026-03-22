from __future__ import annotations

from typing import List

from .types import MemoryContext, MemoryItem


class ContextBuilder:
    def build(self, nodes: List[MemoryItem]) -> MemoryContext:
        blocks = []
        total_tokens = 0

        for node in nodes:
            score_display = f"{node.score:.2f}" if node.score is not None else "0.00"
            block = f"[{node.node_type.upper()} | score={score_display}]\n{node.content}"
            blocks.append(block)
            total_tokens += _estimate_tokens(block)

        formatted = "\n\n".join(blocks)
        metadata = {
            "count": len(nodes),
            "blocks": len(blocks),
        }
        return MemoryContext(
            items=nodes,
            total_tokens=total_tokens,
            metadata=metadata,
            formatted=formatted,
        )


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)
