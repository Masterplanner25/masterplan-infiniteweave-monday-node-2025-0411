from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from AINDY.db.models.agent_registry import AgentRegistry
from AINDY.db.models.system_event import SystemEvent
from AINDY.agents.agent_message_bus import publish_task_request
from AINDY.domain.goal_service import rank_goals
from AINDY.platform_layer.system_state_service import compute_current_state
from AINDY.utils.uuid_utils import normalize_uuid


STALE_AGENT_MINUTES = 10


def register_or_update_agent(
    db,
    *,
    agent_id: str,
    capabilities: list[str] | None = None,
    current_state: dict[str, Any] | None = None,
    load: float = 0.0,
    health_status: str = "healthy",
) -> dict[str, Any]:
    normalized_agent_id = normalize_uuid(agent_id)
    row = db.query(AgentRegistry).filter(AgentRegistry.agent_id == normalized_agent_id).first()
    if row is None:
        row = AgentRegistry(agent_id=normalized_agent_id)
        db.add(row)
    row.capabilities = capabilities or row.capabilities or []
    row.current_state = current_state or row.current_state or {}
    row.load = max(0.0, min(1.0, float(load or 0.0)))
    row.health_status = health_status or "healthy"
    row.last_seen = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return serialize_agent_registry(row)


def list_agents(db, *, include_stale: bool = False) -> list[dict[str, Any]]:
    query = db.query(AgentRegistry).order_by(AgentRegistry.last_seen.desc())
    rows = query.all()
    now = datetime.now(timezone.utc)
    results = []
    for row in rows:
        serialized = serialize_agent_registry(row)
        serialized["stale"] = _is_stale(row.last_seen, now)
        if include_stale or not serialized["stale"]:
            results.append(serialized)
    return results


def get_agent_status(db) -> dict[str, Any]:
    agents = list_agents(db, include_stale=True)
    healthy = sum(1 for agent in agents if agent["health_status"] == "healthy" and not agent["stale"])
    degraded = sum(1 for agent in agents if agent["health_status"] == "degraded" and not agent["stale"])
    critical = sum(1 for agent in agents if agent["health_status"] == "critical" or agent["stale"])
    return {
        "total_agents": len(agents),
        "healthy_agents": healthy,
        "degraded_agents": degraded,
        "critical_agents": critical,
        "agents": agents,
    }


def assign_task(
    db,
    task: dict[str, Any],
    *,
    user_id: str | None = None,
    trace_id: str | None = None,
    sender_agent_id: str | None = None,
) -> dict[str, Any] | None:
    candidates = _rank_candidate_agents(db, task, user_id=user_id)
    if not candidates:
        return None
    best = candidates[0]
    if sender_agent_id:
        publish_task_request(
            db=db,
            sender_agent_id=sender_agent_id,
            recipient_agent_id=best["agent_id"],
            task=task,
            user_id=user_id,
            trace_id=trace_id,
        )
    return best


def broadcast_task(
    db,
    task: dict[str, Any],
    *,
    user_id: str | None = None,
    trace_id: str | None = None,
    sender_agent_id: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    ranked = _rank_candidate_agents(db, task, user_id=user_id)[:limit]
    if sender_agent_id:
        for candidate in ranked:
            publish_task_request(
                db=db,
                sender_agent_id=sender_agent_id,
                recipient_agent_id=candidate["agent_id"],
                task=task,
                user_id=user_id,
                trace_id=trace_id,
            )
    return ranked


def decide_execution_mode(
    db,
    *,
    local_agent_id: str | None,
    task: dict[str, Any],
    user_id: str | None = None,
) -> dict[str, Any]:
    ranked = _rank_candidate_agents(db, task, user_id=user_id)
    if not ranked:
        return {"mode": "local", "selected_agent": None, "candidates": []}

    best = resolve_conflict(ranked)
    if local_agent_id and str(best["agent_id"]) == str(local_agent_id):
        return {"mode": "local", "selected_agent": best, "candidates": ranked[:3]}
    if len(ranked) >= 2 and abs(ranked[0]["coordination_score"] - ranked[1]["coordination_score"]) <= 0.05:
        return {"mode": "collaborate", "selected_agent": best, "candidates": ranked[:3]}
    return {"mode": "delegate", "selected_agent": best, "candidates": ranked[:3]}


def coordination_graph(db, *, user_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    query = (
        db.query(SystemEvent)
        .filter(SystemEvent.agent_id.isnot(None))
        .order_by(SystemEvent.timestamp.desc())
        .limit(limit)
    )
    if user_id:
        query = query.filter(SystemEvent.user_id == normalize_uuid(user_id))
    rows = query.all()
    nodes = {}
    edges = []
    for row in rows:
        agent_key = str(row.agent_id)
        nodes[agent_key] = {
            "id": agent_key,
            "health_status": None,
            "load": None,
        }
        payload = row.payload or {}
        recipient = payload.get("recipient_agent_id")
        if recipient:
            edges.append(
                {
                    "source": agent_key,
                    "target": str(recipient),
                    "event_type": row.type,
                    "trace_id": row.trace_id,
                    "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                }
            )
    for agent in list_agents(db, include_stale=True):
        nodes[str(agent["agent_id"])] = {
            "id": str(agent["agent_id"]),
            "health_status": agent["health_status"],
            "load": agent["load"],
        }
    return {"nodes": list(nodes.values()), "edges": edges}


def _rank_candidate_agents(db, task: dict[str, Any], *, user_id: str | None = None) -> list[dict[str, Any]]:
    system_state = compute_current_state(db)
    goals = rank_goals(db, user_id, system_state=system_state) if user_id else []
    task_capabilities = set(task.get("required_capabilities") or task.get("capabilities") or [])
    task_text = " ".join(
        filter(None, [str(task.get("name") or ""), str(task.get("description") or ""), str(task.get("goal") or "")])
    ).lower()

    rows = list_agents(db, include_stale=False)
    ranked = []
    for row in rows:
        capability_overlap = 0.0
        capabilities = set(row.get("capabilities") or [])
        if task_capabilities:
            capability_overlap = len(task_capabilities & capabilities) / max(1, len(task_capabilities))
        elif capabilities:
            capability_overlap = 0.5

        goal_bonus = 0.0
        if goals and task_text:
            goal_bonus = max(
                (
                    goal.get("ranked_priority", 0.0)
                    for goal in goals
                    if any(term in task_text for term in str(goal.get("name") or "").lower().split())
                ),
                default=0.0,
            ) * 0.15

        past_performance = _agent_performance_score(db, row["agent_id"], user_id=user_id)
        score = (
            capability_overlap * 0.45
            + (1.0 - float(row.get("load") or 0.0)) * 0.20
            + past_performance * 0.20
            + (0.15 if row.get("health_status") == "healthy" else 0.05 if row.get("health_status") == "degraded" else 0.0)
            + goal_bonus
        )
        enriched = dict(row)
        enriched["coordination_score"] = round(max(0.0, min(1.5, score)), 4)
        enriched["capability_overlap"] = round(capability_overlap, 4)
        enriched["past_performance"] = round(past_performance, 4)
        ranked.append(enriched)
    ranked.sort(key=lambda item: item["coordination_score"], reverse=True)
    return ranked


def resolve_conflict(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        raise ValueError("resolve_conflict requires at least one candidate")
    if len(candidates) == 1:
        return candidates[0]

    top_score = float(candidates[0].get("coordination_score") or 0.0)
    tied = [
        candidate for candidate in candidates
        if abs(float(candidate.get("coordination_score") or 0.0) - top_score) <= 0.05
    ]
    tied.sort(
        key=lambda item: (
            -(float(item.get("capability_overlap") or 0.0)),
            float(item.get("load") or 1.0),
            -(float(item.get("past_performance") or 0.0)),
        )
    )
    return tied[0]


def _agent_performance_score(db, agent_id: str, *, user_id: str | None = None) -> float:
    query = db.query(SystemEvent).filter(SystemEvent.agent_id == normalize_uuid(agent_id))
    if user_id:
        query = query.filter(SystemEvent.user_id == normalize_uuid(user_id))
    rows = query.order_by(SystemEvent.timestamp.desc()).limit(50).all()
    if not rows:
        return 0.5
    successes = sum(1 for row in rows if row.type.endswith(".completed") or row.type == "execution.completed")
    failures = sum(1 for row in rows if row.type.endswith(".failed") or row.type.startswith("error."))
    total = max(1, successes + failures)
    return max(0.1, min(1.0, (successes + 0.5) / (total + 1.0)))


def _is_stale(last_seen: datetime | None, now: datetime) -> bool:
    if not last_seen:
        return True
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    return last_seen < now - timedelta(minutes=STALE_AGENT_MINUTES)


def serialize_agent_registry(row: AgentRegistry) -> dict[str, Any]:
    return {
        "agent_id": str(row.agent_id),
        "capabilities": row.capabilities or [],
        "current_state": row.current_state or {},
        "load": float(row.load or 0.0),
        "health_status": row.health_status,
        "last_seen": row.last_seen.isoformat() if row.last_seen else None,
    }


