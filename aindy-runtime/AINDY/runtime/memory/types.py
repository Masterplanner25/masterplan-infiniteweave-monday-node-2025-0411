from __future__ import annotations

from typing import Any, List, Optional


class MemoryItem:
    def __init__(
        self,
        id: str,
        content: str,
        node_type: str,
        score: float = 0.0,
        similarity: float = 0.0,
        recency: float = 0.0,
        success_rate: float = 0.0,
        usage_frequency: float = 0.0,
        tags: Optional[List[str]] = None,
        raw: Optional[dict] = None,
    ):
        self.id = id
        self.content = content
        self.node_type = node_type
        self.score = score
        self.similarity = similarity
        self.recency = recency
        self.success_rate = success_rate
        self.usage_frequency = usage_frequency
        self.tags = tags or []
        self.raw = raw or {}


class MemoryContext:
    def __init__(
        self,
        items: List[MemoryItem],
        total_tokens: int,
        metadata: Optional[dict] = None,
        formatted: str = "",
    ):
        self.items = items
        self.total_tokens = total_tokens
        self.metadata = metadata or {}
        self.formatted = formatted

    @property
    def ids(self) -> List[str]:
        return [item.id for item in self.items]


class RecallRequest:
    def __init__(
        self,
        query: str,
        user_id: str,
        task_type: str,
        metadata: Optional[dict] = None,
    ):
        self.query = query
        self.user_id = user_id
        self.task_type = task_type
        self.metadata = metadata or {}
