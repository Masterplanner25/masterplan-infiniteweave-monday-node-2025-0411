from __future__ import annotations

from db.dao.memory_node_dao import MemoryNodeDAO
from db.models.agent_run import AgentRun
from db.models.user_identity import UserIdentity
from db.models.user_score import UserScore
from core.execution_signal_helper import queue_system_event


def initialize_signup_state(*, db, user) -> dict:
    identity = (
        db.query(UserIdentity)
        .filter(UserIdentity.user_id == user.id)
        .first()
    )
    if identity is None:
        identity = UserIdentity(
            user_id=user.id,
            preferred_languages=[],
            preferred_tools=[],
            avoided_tools=[],
            evolution_log=[],
        )
        db.add(identity)
        db.commit()
        db.refresh(identity)

    memory_dao = MemoryNodeDAO(db)
    initial_memory = memory_dao.save(
        content="User account created",
        source="auth.register",
        tags=["identity", "identity_init"],
        user_id=str(user.id),
        node_type="insight",
        extra={
            "type": "identity",
            "context": "identity_init",
        },
    )

    score = db.query(UserScore).filter(UserScore.user_id == user.id).first()
    if score is None:
        score = UserScore(
            user_id=user.id,
            master_score=0.0,
            execution_speed_score=0.0,
            decision_efficiency_score=0.0,
            ai_productivity_boost_score=0.0,
            focus_quality_score=0.0,
            masterplan_progress_score=0.0,
            confidence="baseline",
            data_points_used=0,
            trigger_event="identity_created",
        )
        db.add(score)
        db.commit()
        db.refresh(score)

    agent_run = (
        db.query(AgentRun)
        .filter(
            AgentRun.user_id == user.id,
            AgentRun.goal == "Initial agent context",
        )
        .first()
    )
    if agent_run is None:
        agent_run = AgentRun(
            user_id=user.id,
            agent_type="identity_boot",
            goal="Initial agent context",
            status="initialized",
            plan={
                "status": "initialized",
                "steps": 0,
            },
            executive_summary="Execution context initialized during signup.",
            steps_total=0,
            steps_completed=0,
            current_step=0,
            result={
                "status": "initialized",
                "steps": 0,
            },
        )
        db.add(agent_run)
        db.commit()
        db.refresh(agent_run)

    queue_system_event(
        db=db,
        event_type="identity.created",
        user_id=user.id,
        payload={
            "email": user.email,
            "timestamp": user.created_at.isoformat() if user.created_at else None,
            "memory_node_id": initial_memory["id"],
            "agent_run_id": str(agent_run.id),
        },
        required=True,
    )

    return {
        "memory": initial_memory,
        "metrics": {
            "score": score.master_score,
            "trajectory": "baseline",
        },
        "agent_context": {
            "status": "initialized",
            "steps": 0,
            "run_id": str(agent_run.id),
        },
    }
