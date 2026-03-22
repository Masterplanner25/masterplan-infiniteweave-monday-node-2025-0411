from __future__ import annotations

from datetime import datetime
from typing import Iterable, List
import math

from .types import MemoryItem, RecallRequest


class MemoryScorer:
    def score(self, nodes: Iterable[dict], request: RecallRequest | None) -> List[MemoryItem]:
        scored: List[MemoryItem] = []
        now = datetime.utcnow()
        trace_node_ids = set()
        if request and request.metadata:
            trace_node_ids = set(request.metadata.get("trace_node_ids", []))

        for node in nodes or []:
            similarity = _safe_float(node.get("semantic_score", node.get("similarity", 0.0)))
            recency = _safe_float(node.get("recency_score", 0.0))
            if not recency:
                recency = _compute_recency(node.get("created_at"), now)

            success_rate = _safe_float(node.get("success_rate", 0.0))
            low_value_flag = False
            extra = node.get("extra") if isinstance(node, dict) else None
            if isinstance(extra, dict) and extra.get("success_rate") is not None:
                success_rate = _safe_float(extra.get("success_rate"))
            if isinstance(extra, dict) and extra.get("low_value_flag") is True:
                low_value_flag = True
            usage_frequency = _safe_float(node.get("usage_frequency", node.get("usage_count", 0.0)))
            graph_bonus = _safe_float(node.get("graph_score", 0.0))

            success_weight = 0.20
            if usage_frequency and usage_frequency > 5:
                success_weight = 0.25

            trace_bonus = 0.0
            node_id = node.get("id")
            if node_id and node_id in trace_node_ids:
                trace_bonus = 0.10

            score = (
                similarity * 0.40
                + recency * 0.15
                + success_rate * success_weight
                + _normalize_usage(usage_frequency) * 0.10
                + graph_bonus * 0.15
                + trace_bonus
            )
            if low_value_flag:
                score *= 0.5

            item = MemoryItem(
                id=str(node.get("id")),
                content=str(node.get("content", "")),
                node_type=node.get("node_type") or "unknown",
                score=round(score, 4),
                similarity=round(similarity, 4),
                recency=round(recency, 4),
                success_rate=round(success_rate, 4),
                usage_frequency=round(usage_frequency, 4),
                tags=node.get("tags") or [],
                raw=node,
            )
            scored.append(item)

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored


def _normalize_usage(value: float) -> float:
    if value <= 0:
        return 0.0
    return min(1.0, math.log1p(value) / math.log(101))


def _safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _compute_recency(created_at, now: datetime) -> float:
    if not created_at:
        return 0.5
    try:
        if isinstance(created_at, str):
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00")).replace(tzinfo=None)
        else:
            created = created_at
        age_days = max(0, (now - created).days)
        return math.exp(-age_days / 30.0)
    except Exception:
        return 0.5
