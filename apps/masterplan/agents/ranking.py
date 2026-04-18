"""Masterplan-aware agent ranking strategy."""

from __future__ import annotations

from typing import Any


def rank_agents(candidates: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
    ranked = [dict(candidate) for candidate in candidates]
    goal_bonus = _goal_alignment_bonus(context)
    if goal_bonus:
        for candidate in ranked:
            score = float(candidate.get("coordination_score") or 0.0) + goal_bonus
            candidate["coordination_score"] = round(max(0.0, min(1.5, score)), 4)
    ranked.sort(key=lambda item: item["coordination_score"], reverse=True)
    return ranked


def _goal_alignment_bonus(context: dict[str, Any]) -> float:
    db = context.get("db")
    user_id = context.get("user_id")
    task = context.get("task") if isinstance(context.get("task"), dict) else {}
    if db is None or not user_id:
        return 0.0

    task_text = " ".join(
        filter(None, [str(task.get("name") or ""), str(task.get("description") or ""), str(task.get("goal") or "")])
    ).lower()
    if not task_text:
        return 0.0

    try:
        from AINDY.platform_layer.registry import get_job
        from AINDY.platform_layer.system_state_service import compute_current_state

        rank_goals = get_job("goals.rank")
        if rank_goals is None:
            return 0.0
        goals = rank_goals(db, user_id, system_state=compute_current_state(db)) or []
    except Exception:
        return 0.0

    return max(
        (
            float(goal.get("ranked_priority", 0.0) or 0.0)
            for goal in goals
            if any(term in task_text for term in str(goal.get("name") or "").lower().split())
        ),
        default=0.0,
    ) * 0.15


def register() -> None:
    from AINDY.platform_layer.registry import register_agent_ranking_strategy

    register_agent_ranking_strategy(rank_agents)
