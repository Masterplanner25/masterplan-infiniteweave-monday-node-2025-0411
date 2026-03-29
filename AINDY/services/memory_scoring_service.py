from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from services.memory_persistence import MemoryNodeModel


def score_memory(memory_node: dict[str, Any]) -> float:
    impact_score = float(memory_node.get("impact_score", 0.0) or 0.0)
    usage_count = float(memory_node.get("usage_count", 0.0) or 0.0)
    memory_type = str(memory_node.get("memory_type") or memory_node.get("node_type") or "insight").lower()
    extra = memory_node.get("extra") or {}
    signal_frequency = float(extra.get("signal_frequency", 0.0) or 0.0)

    recency_score = _compute_recency(memory_node.get("created_at"))
    frequency_score = min(1.0, math.log1p(max(0.0, usage_count)) / math.log(11))
    signal_frequency_score = min(1.0, math.log1p(max(0.0, signal_frequency)) / math.log(11))
    impact_component = min(1.0, impact_score / 5.0)
    type_weight = {
        "failure": 1.25,
        "outcome": 1.0,
        "decision": 0.95,
        "insight": 0.85,
    }.get(memory_type, 0.8)

    weighted = (
        impact_component * 0.35
        + recency_score * 0.20
        + frequency_score * 0.15
        + signal_frequency_score * 0.20
        + min(1.0, type_weight / 1.25) * 0.10
    ) * type_weight
    return round(weighted, 4)


def get_relevant_memories(context: dict[str, Any], db, limit: int = 8) -> list[dict[str, Any]]:
    user_id = context.get("user_id")
    if not user_id:
        return []

    trigger_event = str(context.get("trigger_event") or "").lower()
    goal_terms = set(_extract_terms(context))

    rows = (
        db.query(MemoryNodeModel)
        .filter(MemoryNodeModel.user_id == user_id)
        .order_by(
            MemoryNodeModel.impact_score.desc(),
            MemoryNodeModel.created_at.desc(),
            MemoryNodeModel.id.desc(),
        )
        .limit(max(limit * 3, 20))
        .all()
    )

    ranked: list[dict[str, Any]] = []
    for row in rows:
        node = _serialize_memory_node(row)
        relevance_boost = 0.0
        node_terms = set(_extract_node_terms(node))

        if trigger_event:
            event_type = str((node.get("extra") or {}).get("event_type") or "").lower()
            if trigger_event in event_type or trigger_event.replace("_", ".") in event_type:
                relevance_boost += 0.2
        if goal_terms and node_terms:
            overlap = len(goal_terms & node_terms)
            if overlap:
                relevance_boost += min(0.2, overlap * 0.05)

        node["weighted_score"] = round(score_memory(node) + relevance_boost, 4)
        node["type"] = _normalize_signal_type(node)
        node["cause_summary"] = (
            (node.get("extra") or {}).get("relationship_summary")
            or f"{node.get('memory_type', 'insight')} memory from {node.get('source') or 'unknown source'}"
        )
        node["outcome"] = (
            (node.get("extra") or {}).get("event_type")
            or node.get("memory_type")
            or node.get("node_type")
        )
        ranked.append(node)

    ranked.sort(key=lambda item: item["weighted_score"], reverse=True)
    return ranked[:limit]


def _normalize_signal_type(node: dict[str, Any]) -> str:
    memory_type = str(node.get("memory_type") or node.get("node_type") or "insight").lower()
    if memory_type == "failure":
        return "failure"
    if memory_type in {"outcome", "decision"}:
        return "success"
    return "pattern"


def _compute_recency(created_at: Any) -> float:
    if not created_at:
        return 0.5
    now = datetime.now(timezone.utc)
    try:
        if isinstance(created_at, str):
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        else:
            created = created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = max(0, (now - created).days)
        return math.exp(-age_days / 21.0)
    except Exception:
        return 0.5


def _serialize_memory_node(row: MemoryNodeModel) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "content": row.content,
        "tags": row.tags or [],
        "node_type": row.node_type,
        "memory_type": row.memory_type,
        "source": row.source,
        "source_event_id": str(row.source_event_id) if row.source_event_id else None,
        "root_event_id": str(row.root_event_id) if row.root_event_id else None,
        "causal_depth": row.causal_depth or 0,
        "impact_score": float(row.impact_score or 0.0),
        "usage_count": row.usage_count or 0,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "extra": row.extra or {},
    }


def _extract_terms(context: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for value in (
        context.get("trigger_event"),
        context.get("goal"),
        context.get("current_state"),
    ):
        if isinstance(value, str):
            terms.extend(value.lower().replace(".", " ").replace("_", " ").split())
    constraints = context.get("constraints") or []
    if isinstance(constraints, list):
        for constraint in constraints:
            if isinstance(constraint, str):
                terms.extend(constraint.lower().split())
    return [term for term in terms if len(term) > 2]


def _extract_node_terms(node: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for value in (
        node.get("content"),
        node.get("source"),
        (node.get("extra") or {}).get("event_type"),
    ):
        if isinstance(value, str):
            terms.extend(value.lower().replace(".", " ").replace("_", " ").split())
    for tag in node.get("tags") or []:
        if isinstance(tag, str):
            terms.extend(tag.lower().replace(".", " ").replace("_", " ").split())
    return [term for term in terms if len(term) > 2]
