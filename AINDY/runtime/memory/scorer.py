from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List
import math
import logging

from .native_scorer import (
    get_native_scorer_stats,
    score_memory_nodes as score_memory_nodes_native,
)
from .types import MemoryItem, RecallRequest

logger = logging.getLogger(__name__)


class MemoryScorer:
    def score(self, nodes: Iterable[dict], request: RecallRequest | None) -> List[MemoryItem]:
        now = datetime.now(timezone.utc)
        trace_node_ids = set()
        if request and request.metadata:
            trace_node_ids = set(request.metadata.get("trace_node_ids", []))

        prepared_nodes = [_prepare_node(node, trace_node_ids=trace_node_ids, now=now) for node in (nodes or [])]
        scores = _score_nodes(prepared_nodes)

        scored: List[MemoryItem] = []
        for prepared, score in zip(prepared_nodes, scores):
            node = prepared["node"]
            similarity = prepared["similarity"]
            recency = prepared["recency"]
            success_rate = prepared["success_rate"]
            usage_frequency = prepared["usage_frequency"]

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


def _prepare_node(node: dict, *, trace_node_ids: set, now: datetime) -> dict:
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
    impact_score = _safe_float(node.get("impact_score", 0.0))

    trace_bonus = 0.0
    node_id = node.get("id")
    if node_id and node_id in trace_node_ids:
        trace_bonus = 0.10

    return {
        "node": node,
        "similarity": similarity,
        "recency": recency,
        "success_rate": success_rate,
        "usage_frequency": usage_frequency,
        "graph_bonus": graph_bonus,
        "impact_score": impact_score,
        "trace_bonus": trace_bonus,
        "low_value_flag": low_value_flag,
    }


def _score_nodes(prepared_nodes: list[dict]) -> list[float]:
    native_result = score_memory_nodes_native(
        similarities=[node["similarity"] for node in prepared_nodes],
        recencies=[node["recency"] for node in prepared_nodes],
        success_rates=[node["success_rate"] for node in prepared_nodes],
        usage_frequencies=[node["usage_frequency"] for node in prepared_nodes],
        graph_bonuses=[node["graph_bonus"] for node in prepared_nodes],
        impact_scores=[node["impact_score"] for node in prepared_nodes],
        trace_bonuses=[node["trace_bonus"] for node in prepared_nodes],
        low_value_flags=[node["low_value_flag"] for node in prepared_nodes],
    )
    native_scores = native_result["scores"]
    if native_scores is not None:
        return native_scores

    if native_result["error"] not in {None, "disabled", "unavailable"}:
        logger.warning(
            "[MemoryScorer] native scorer fallback error=%s stats=%s",
            native_result["error"],
            get_native_scorer_stats(),
        )

    return [_score_node_python(node) for node in prepared_nodes]


def _score_node_python(prepared: dict) -> float:
    usage_frequency = prepared["usage_frequency"]
    success_weight = 0.20
    if usage_frequency and usage_frequency > 5:
        success_weight = 0.25

    impact_bonus = min(1.0, prepared["impact_score"] / 5.0) * 0.15

    score = (
        prepared["similarity"] * 0.40
        + prepared["recency"] * 0.15
        + prepared["success_rate"] * success_weight
        + _normalize_usage(usage_frequency) * 0.10
        + prepared["graph_bonus"] * 0.15
        + impact_bonus
        + prepared["trace_bonus"]
    )
    if prepared["low_value_flag"]:
        score *= 0.5
    return score


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
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        else:
            created = created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = max(0, (now - created).days)
        return math.exp(-age_days / 30.0)
    except Exception:
        return 0.5
