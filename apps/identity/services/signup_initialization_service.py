from __future__ import annotations

from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
from apps.agent.models.agent_run import AgentRun
from AINDY.db.models.user_identity import UserIdentity
from AINDY.core.execution_signal_helper import queue_system_event


def _ensure_user_score_via_syscall(*, db, user_id) -> dict:
    import uuid

    from AINDY.kernel.syscall_dispatcher import SyscallContext, get_dispatcher

    ctx = SyscallContext(
        execution_unit_id=str(uuid.uuid4()),
        user_id=str(user_id),
        capabilities=["analytics.write"],
        trace_id="",
        metadata={"_db": db},
    )
    result = get_dispatcher().dispatch(
        "sys.v1.analytics.init_user_score",
        {"user_id": str(user_id)},
        ctx,
    )
    if result["status"] != "success":
        raise RuntimeError(result.get("error", "analytics.init_user_score failed"))
    return dict(result.get("data") or {})


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

    score = _ensure_user_score_via_syscall(db=db, user_id=user.id)

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
            "score": score.get("master_score", 0.0),
            "trajectory": "baseline",
        },
        "agent_context": {
            "status": "initialized",
            "steps": 0,
            "run_id": str(agent_run.id),
        },
    }

