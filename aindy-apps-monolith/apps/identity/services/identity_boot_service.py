from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
from AINDY.db.models.flow_run import FlowRun
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
    from AINDY.kernel.syscall_dispatcher import dispatch_syscall

    result = dispatch_syscall(
        "sys.v1.agent.count_runs",
        {"user_id": str(user_id)},
        db=db,
        user_id=str(user_id),
    )
    if result.get("status") != "success":
        return 0
    return int(result.get("data", {}).get("count", 0))


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
    from AINDY.kernel.syscall_dispatcher import dispatch_syscall

    result = dispatch_syscall(
        "sys.v1.agent.list_recent_runs",
        {"user_id": str(user_id), "limit": limit},
        db=db,
        user_id=str(user_id),
    )
    if result.get("status") != "success":
        return []
    rows = list(result.get("data", {}).get("runs", []))
    for row in rows:
        row["goal"] = row.get("objective")
    return rows


def get_user_metrics(user_id: str | UUID, db: Session) -> dict[str, Any] | None:
    from AINDY.platform_layer.registry import get_job

    normalized_user_id = parse_user_id(user_id) if user_id is not None else None
    get_snapshot = get_job("analytics.kpi_snapshot")
    if get_snapshot is None:
        return None
    score = get_snapshot(user_id=normalized_user_id, db=db)
    if not score:
        return None
    return {
        "user_id": str(user_id),
        "score": score.get("master_score"),
        "trajectory": score.get("confidence") or "baseline",
        "master_score": score.get("master_score"),
        "kpis": {
            "execution_speed": score.get("execution_speed"),
            "decision_efficiency": score.get("decision_efficiency"),
            "ai_productivity_boost": score.get("ai_productivity_boost"),
            "focus_quality": score.get("focus_quality"),
            "masterplan_progress": score.get("masterplan_progress"),
        },
        "metadata": {
            "confidence": score.get("confidence"),
            "data_points_used": score.get("data_points_used"),
            "trigger_event": score.get("trigger_event"),
            "calculated_at": score.get("calculated_at"),
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


