from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from db.models.goal_state import GoalState
from db.models.goals import Goal
from utils.uuid_utils import normalize_uuid


def create_goal(
    db,
    *,
    user_id: str,
    name: str,
    description: str | None = None,
    goal_type: str = "strategic",
    priority: float = 0.5,
    status: str = "active",
    success_metric: dict[str, Any] | None = None,
) -> dict[str, Any]:
    goal = Goal(
        user_id=normalize_uuid(user_id),
        name=str(name).strip(),
        description=description,
        goal_type=str(goal_type or "strategic").strip().lower(),
        priority=float(priority or 0.5),
        status=str(status or "active").strip().lower(),
        success_metric=success_metric or {},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    state = _get_or_create_goal_state(db, goal.id)
    db.refresh(goal)
    return _serialize_goal(goal, state)


def get_active_goals(db, user_id: str | None) -> list[dict[str, Any]]:
    if not user_id:
        return []
    rows = (
        db.query(Goal, GoalState)
        .outerjoin(GoalState, GoalState.goal_id == Goal.id)
        .filter(Goal.user_id == normalize_uuid(user_id), Goal.status == "active")
        .order_by(Goal.priority.desc(), Goal.updated_at.desc())
        .all()
    )
    return [_serialize_goal(goal, state) for goal, state in rows]


def rank_goals(
    db,
    user_id: str | None,
    *,
    system_state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    goals = get_active_goals(db, user_id)
    if not goals:
        return []

    state = system_state or {}
    health_status = str(state.get("health_status") or "healthy").lower()
    system_load = float(state.get("system_load") or 0.0)
    failure_rate = float(state.get("failure_rate") or 0.0)

    ranked = []
    for goal in goals:
        progress_gap = max(0.0, 1.0 - float(goal.get("progress") or 0.0))
        success_signal = float(goal.get("success_signal") or 0.0)
        base_priority = float(goal.get("priority") or 0.0)
        score = base_priority * 0.45 + progress_gap * 0.30 + max(0.0, success_signal) * 0.15
        if health_status == "critical" and goal.get("goal_type") == "operational":
            score -= 0.10
        if system_load >= 0.75 and goal.get("goal_type") == "learning":
            score -= 0.05
        if failure_rate >= 0.25:
            score -= min(0.10, abs(min(0.0, success_signal)) * 0.10)
        enriched = dict(goal)
        enriched["ranked_priority"] = round(max(0.0, min(1.5, score)), 4)
        enriched["progress_gap"] = round(progress_gap, 4)
        ranked.append(enriched)

    ranked.sort(key=lambda item: item["ranked_priority"], reverse=True)
    return ranked


def update_goal_progress(db, goal_id: str, result: dict[str, Any]) -> dict[str, Any] | None:
    goal = db.query(Goal).filter(Goal.id == goal_id).first()
    if not goal:
        return None
    state = _get_or_create_goal_state(db, goal.id)

    progress_delta = float(result.get("progress_delta") or 0.0)
    success_delta = float(result.get("success_signal_delta") or 0.0)
    action = result.get("action")

    state.progress = round(max(0.0, min(1.0, float(state.progress or 0.0) + progress_delta)), 4)
    state.success_signal = round(max(-1.0, min(1.0, float(state.success_signal or 0.0) + success_delta)), 4)
    state.last_update = datetime.now(timezone.utc)
    actions = list(state.recent_actions or [])
    if action:
        actions.append(action)
    state.recent_actions = actions[-10:]
    goal.updated_at = datetime.now(timezone.utc)
    if state.progress >= 0.999:
        goal.status = "completed"
    db.commit()
    db.refresh(state)
    db.refresh(goal)
    return _serialize_goal(goal, state)


def detect_goal_drift(db, user_id: str | None) -> list[dict[str, Any]]:
    drift: list[dict[str, Any]] = []
    for goal in get_active_goals(db, user_id):
        success_signal = float(goal.get("success_signal") or 0.0)
        progress = float(goal.get("progress") or 0.0)
        if success_signal < -0.35 or (progress < 0.15 and len(goal.get("recent_actions") or []) >= 5):
            drift.append(
                {
                    "goal_id": goal["id"],
                    "name": goal["name"],
                    "reason": "repeated_failures" if success_signal < -0.35 else "low_progress",
                    "progress": progress,
                    "success_signal": success_signal,
                }
            )
    return drift


def calculate_goal_alignment(goals: list[dict[str, Any]], text: str | None) -> float:
    if not goals or not text:
        return 0.0
    action_terms = set(_extract_terms(text))
    if not action_terms:
        return 0.0

    best = 0.0
    for goal in goals:
        goal_terms = set(_extract_terms(" ".join(filter(None, [goal.get("name"), goal.get("description")]))))
        if not goal_terms:
            continue
        overlap = len(action_terms & goal_terms)
        if overlap == 0:
            continue
        coverage = overlap / max(1, len(goal_terms))
        weighted = coverage * float(goal.get("ranked_priority") or goal.get("priority") or 0.0)
        best = max(best, weighted)
    return round(min(1.0, best), 4)


def update_goals_from_execution(
    db,
    *,
    user_id: str | None,
    workflow_type: str | None,
    execution_result: Any,
    success: bool,
) -> list[dict[str, Any]]:
    goals = rank_goals(db, user_id)
    if not goals:
        return []

    text = _result_text(workflow_type, execution_result)
    if not text:
        return []

    updates = []
    for goal in goals[:5]:
        alignment = calculate_goal_alignment([goal], text)
        if alignment < 0.15:
            continue
        progress_delta = alignment * (0.08 if success else -0.03)
        success_delta = alignment * (0.12 if success else -0.18)
        updated = update_goal_progress(
            db,
            goal["id"],
            {
                "progress_delta": progress_delta,
                "success_signal_delta": success_delta,
                "action": {
                    "workflow_type": workflow_type,
                    "success": success,
                    "alignment": alignment,
                    "text": text[:200],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            },
        )
        if updated:
            updates.append(updated)
    return updates


def get_goal_states(db, user_id: str | None) -> list[dict[str, Any]]:
    return rank_goals(db, user_id)


def distribute_goals(
    db,
    goals: list[dict[str, Any]],
    *,
    agent_candidates: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    from services.agent_coordinator import list_agents

    candidates = agent_candidates or list_agents(db)
    assignments: list[dict[str, Any]] = []
    ranked_candidates = list(candidates)
    for goal in goals:
        ranked_candidates.sort(key=lambda item: (item.get("load", 1.0), item.get("health_status") != "healthy"))
        if not ranked_candidates:
            break
        best = ranked_candidates[0]
        assignments.append(
            {
                "goal_id": goal.get("id"),
                "goal_name": goal.get("name"),
                "agent_id": best.get("agent_id"),
                "goal_type": goal.get("goal_type"),
                "priority": goal.get("ranked_priority") or goal.get("priority"),
            }
        )
    return assignments


def _get_or_create_goal_state(db, goal_id) -> GoalState:
    state = db.query(GoalState).filter(GoalState.goal_id == goal_id).first()
    if state:
        return state
    state = GoalState(goal_id=goal_id, progress=0.0, recent_actions=[], success_signal=0.0)
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def _serialize_goal(goal: Goal, state: GoalState | None) -> dict[str, Any]:
    return {
        "id": str(goal.id),
        "user_id": str(goal.user_id),
        "name": goal.name,
        "description": goal.description,
        "goal_type": goal.goal_type,
        "priority": float(goal.priority or 0.0),
        "status": goal.status,
        "success_metric": goal.success_metric or {},
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
        "updated_at": goal.updated_at.isoformat() if goal.updated_at else None,
        "progress": float(getattr(state, "progress", 0.0) or 0.0),
        "last_update": state.last_update.isoformat() if state and state.last_update else None,
        "recent_actions": list(getattr(state, "recent_actions", []) or []),
        "success_signal": float(getattr(state, "success_signal", 0.0) or 0.0),
    }


def _extract_terms(text: str | None) -> list[str]:
    if not text:
        return []
    return [
        term
        for term in str(text).lower().replace(".", " ").replace("_", " ").replace("-", " ").split()
        if len(term) > 2
    ]


def _result_text(workflow_type: str | None, execution_result: Any) -> str:
    parts = [workflow_type or ""]
    if isinstance(execution_result, dict):
        for key in ("task_result", "goal", "message", "title", "suggested_goal"):
            value = execution_result.get(key)
            if isinstance(value, str):
                parts.append(value)
        orchestration = execution_result.get("orchestration")
        if isinstance(orchestration, dict):
            next_action = orchestration.get("next_action")
            if isinstance(next_action, dict):
                for key in ("title", "task_name", "suggested_goal", "type"):
                    value = next_action.get(key)
                    if isinstance(value, str):
                        parts.append(value)
    elif isinstance(execution_result, str):
        parts.append(execution_result)
    return " ".join(part for part in parts if part).strip()
