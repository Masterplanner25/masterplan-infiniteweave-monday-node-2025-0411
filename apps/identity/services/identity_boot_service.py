from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
from AINDY.db.models.agent_run import AgentRun
from AINDY.db.models.flow_run import FlowRun
from apps.analytics.models import UserScore
from AINDY.memory.memory_persistence import MemoryNodeModel
from AINDY.platform_layer.user_ids import parse_user_id


_BOOT_MEMORY_LIMIT = 20
_BOOT_RUN_LIMIT = 10
_BOOT_FLOW_LIMIT = 10


def _tag_memory_context(node: dict[str, Any], *, context: str) -> dict[str, Any]:
    extra = dict(node.get("extra") or {})
    extra["context"] = context
    return {
        **node,
        "context": context,
        "extra": extra,
    }


def get_recent_memory(
    user_id: str | UUID,
    db: Session,
    *,
    limit: int = _BOOT_MEMORY_LIMIT,
    context: str = "identity_boot",
) -> list[dict[str, Any]]:
    normalized_user_id = parse_user_id(user_id) if user_id is not None else None
    dao = MemoryNodeDAO(db)
    rows = (
        db.query(MemoryNodeModel)
        .filter(MemoryNodeModel.user_id == normalized_user_id)
        .order_by(MemoryNodeModel.created_at.desc(), MemoryNodeModel.id.desc())
        .limit(limit)
        .all()
    )
    return [_tag_memory_context(dao._node_to_dict(row), context=context) for row in rows]


def _count_user_memory(user_id: str | UUID, db: Session) -> int:
    normalized_user_id = parse_user_id(user_id) if user_id is not None else None
    if normalized_user_id is None:
        return 0
    return (
        db.query(MemoryNodeModel.id)
        .filter(MemoryNodeModel.user_id == normalized_user_id)
        .count()
    )


def _count_user_agent_runs(user_id: str | UUID, db: Session) -> int:
    normalized_user_id = parse_user_id(user_id) if user_id is not None else None
    if normalized_user_id is None:
        return 0
    return (
        db.query(AgentRun.id)
        .filter(AgentRun.user_id == normalized_user_id)
        .count()
    )


def _count_active_flows(user_id: str | UUID, db: Session) -> int:
    normalized_user_id = parse_user_id(user_id) if user_id is not None else None
    if normalized_user_id is None:
        return 0
    return (
        db.query(FlowRun.id)
        .filter(
            FlowRun.user_id == normalized_user_id,
            FlowRun.status.in_(("running", "waiting")),
        )
        .count()
    )


def get_recent_agent_runs(
    user_id: str | UUID,
    db: Session,
    *,
    limit: int = _BOOT_RUN_LIMIT,
) -> list[dict[str, Any]]:
    from AINDY.agents.agent_runtime import run_to_dict

    normalized_user_id = parse_user_id(user_id) if user_id is not None else None
    rows = (
        db.query(AgentRun)
        .filter(AgentRun.user_id == normalized_user_id)
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        .limit(limit)
        .all()
    )
    result = []
    for row in rows:
        item = run_to_dict(row)
        item["goal"] = item.get("objective")
        result.append(item)
    return result


def get_user_metrics(user_id: str | UUID, db: Session) -> dict[str, Any] | None:
    normalized_user_id = parse_user_id(user_id) if user_id is not None else None
    score = db.query(UserScore).filter(UserScore.user_id == normalized_user_id).first()
    if not score:
        return None
    return {
        "user_id": str(user_id),
        "score": score.master_score,
        "trajectory": score.confidence or "baseline",
        "master_score": score.master_score,
        "kpis": {
            "execution_speed": score.execution_speed_score,
            "decision_efficiency": score.decision_efficiency_score,
            "ai_productivity_boost": score.ai_productivity_boost_score,
            "focus_quality": score.focus_quality_score,
            "masterplan_progress": score.masterplan_progress_score,
        },
        "metadata": {
            "confidence": score.confidence,
            "data_points_used": score.data_points_used,
            "trigger_event": score.trigger_event,
            "calculated_at": score.calculated_at.isoformat()
            if score.calculated_at
            else None,
        },
    }


def get_active_flows(
    user_id: str | UUID,
    db: Session,
    *,
    limit: int = _BOOT_FLOW_LIMIT,
) -> list[dict[str, Any]]:
    normalized_user_id = parse_user_id(user_id) if user_id is not None else None
    rows = (
        db.query(FlowRun)
        .filter(
            FlowRun.user_id == normalized_user_id,
            FlowRun.status.in_(("running", "waiting")),
        )
        .order_by(FlowRun.created_at.desc(), FlowRun.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "flow_name": row.flow_name,
            "workflow_type": row.workflow_type,
            "status": row.status,
            "trace_id": row.trace_id,
            "current_node": row.current_node,
            "waiting_for": row.waiting_for,
            "state": row.state,
            "error_message": row.error_message,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        }
        for row in rows
    ]


def boot_identity_context(user_id: str | UUID, db: Session) -> dict[str, Any]:
    memory_nodes = get_recent_memory(user_id, db)
    agent_runs = get_recent_agent_runs(user_id, db)
    metrics = get_user_metrics(user_id, db)
    flows = get_active_flows(user_id, db)

    system_state = {
        "memory_count": _count_user_memory(user_id, db),
        "active_runs": _count_user_agent_runs(user_id, db),
        "score": metrics.get("master_score") if metrics else None,
        "active_flows": _count_active_flows(user_id, db),
    }

    return {
        "user_id": str(user_id),
        "memory": memory_nodes,
        "runs": agent_runs,
        "metrics": metrics,
        "flows": flows,
        "system_state": system_state,
    }


