# /services/task_services.py
import logging
import os
import socket
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from AINDY.db.database import SessionLocal
from AINDY.db.models.background_task_lease import BackgroundTaskLease
from apps.tasks.models import Task
from AINDY.db.mongo_setup import get_mongo_client
from AINDY.core.system_event_service import emit_system_event
from apps.tasks.events import TaskEventTypes as SystemEventTypes
from apps.tasks.services.analytics_bridge import (
    get_kpi_snapshot_via_syscall,
    save_calculation_via_syscall,
)
from apps.tasks.services.masterplan_bridge import (
    assert_masterplan_owned_via_syscall,
    get_active_masterplan_via_syscall,
    get_eta_via_syscall,
)

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _user_uuid(user_id: str | uuid.UUID | None) -> uuid.UUID | None:
    if not user_id:
        return None
    return uuid.UUID(str(user_id))


def _emit_task_event(
    db: Session,
    *,
    event_type: str,
    user_id: str | uuid.UUID | None,
    payload: dict[str, Any],
) -> None:
    """Persist task lifecycle events on an isolated session."""
    event_db = SessionLocal()
    try:
        emit_system_event(
            db=event_db,
            event_type=event_type,
            user_id=user_id,
            payload=payload,
            source="task",
        )
    except Exception as exc:
        logger.warning("[task] system event emit failed (%s): %s", event_type, exc)
    finally:
        event_db.close()


def _serialize_dependency(task_id: int, dependency_type: str = "hard") -> dict[str, Any]:
    return {"task_id": int(task_id), "dependency_type": dependency_type or "hard"}


def _normalize_dependencies(dependencies: list[Any] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for dependency in dependencies or []:
        if isinstance(dependency, dict):
            task_id = dependency.get("task_id")
            dep_type = dependency.get("dependency_type", "hard")
        else:
            task_id = getattr(dependency, "task_id", None)
            dep_type = getattr(dependency, "dependency_type", "hard")
        if task_id is None:
            continue
        normalized.append(_serialize_dependency(int(task_id), str(dep_type or "hard")))
    return normalized


def _dependency_ids(task: Task) -> list[int]:
    ids: list[int] = []
    for dependency in task.depends_on or []:
        if isinstance(dependency, dict) and dependency.get("task_id") is not None:
            ids.append(int(dependency["task_id"]))
    if task.parent_task_id is not None and int(task.parent_task_id) not in ids:
        ids.append(int(task.parent_task_id))
    return ids


def _validate_dependencies(
    db: Session,
    owner_user_id: uuid.UUID,
    dependencies: list[dict[str, Any]],
    parent_task_id: int | None,
) -> None:
    referenced_ids = {int(item["task_id"]) for item in dependencies}
    if parent_task_id is not None:
        referenced_ids.add(int(parent_task_id))
    if not referenced_ids:
        return
    existing_ids = {
        task_id
        for (task_id,) in db.query(Task.id).filter(
            Task.user_id == owner_user_id,
            Task.id.in_(referenced_ids),
        ).all()
    }
    missing = sorted(referenced_ids - existing_ids)
    if missing:
        raise ValueError(f"dependencies_not_found:{','.join(str(item) for item in missing)}")


def _dependencies_complete(db: Session, task: Task, user_id: str | uuid.UUID | None) -> bool:
    dependency_ids = _dependency_ids(task)
    if not dependency_ids:
        return True
    owner_user_id = _user_uuid(user_id)
    completed = (
        db.query(Task)
        .filter(
            Task.user_id == owner_user_id,
            Task.id.in_(dependency_ids),
            Task.status == "completed",
        )
        .count()
    )
    return completed == len(set(dependency_ids))


def _recompute_task_status(db: Session, task: Task, user_id: str | uuid.UUID | None) -> str:
    if task.status == "completed":
        return task.status
    if _dependencies_complete(db, task, user_id=user_id):
        if task.status == "blocked":
            task.status = "pending"
    else:
        if task.status in {"pending", "paused"}:
            task.status = "blocked"
    return task.status


def build_task_graph(tasks: list[Task]) -> dict[str, Any]:
    nodes = {
        int(task.id): {
            "task_id": int(task.id),
            "name": task.name,
            "priority": task.priority,
            "status": task.status,
            "depends_on": _dependency_ids(task),
            "automation_type": getattr(task, "automation_type", None),
            "masterplan_id": getattr(task, "masterplan_id", None),
        }
        for task in tasks
    }
    downstream = {task_id: [] for task_id in nodes}
    indegree = {task_id: 0 for task_id in nodes}
    for task_id, node in nodes.items():
        for dependency_id in node["depends_on"]:
            if dependency_id not in nodes:
                continue
            downstream[dependency_id].append(task_id)
            indegree[task_id] += 1

    queue = deque(sorted(task_id for task_id, degree in indegree.items() if degree == 0))
    topo_order: list[int] = []
    while queue:
        current = queue.popleft()
        topo_order.append(current)
        for child_id in downstream[current]:
            indegree[child_id] -= 1
            if indegree[child_id] == 0:
                queue.append(child_id)

    if len(topo_order) != len(nodes):
        raise ValueError("task_dependency_cycle_detected")

    critical_weight = {task_id: 1 for task_id in nodes}
    for task_id in reversed(topo_order):
        children = downstream[task_id]
        if children:
            critical_weight[task_id] = 1 + max(critical_weight[child_id] for child_id in children)

    ready = [
        task_id
        for task_id in topo_order
        if nodes[task_id]["status"] in {"pending", "paused", "in_progress"}
        and all(
            nodes[dependency_id]["status"] == "completed"
            for dependency_id in nodes[task_id]["depends_on"]
            if dependency_id in nodes
        )
    ]
    blocked = [
        task_id
        for task_id in topo_order
        if nodes[task_id]["status"] != "completed" and task_id not in ready
    ]
    return {
        "nodes": nodes,
        "downstream": downstream,
        "topological_order": topo_order,
        "critical_weight": critical_weight,
        "ready": ready,
        "blocked": blocked,
    }


def get_task_graph_context(db: Session, user_id: str | uuid.UUID | None) -> dict[str, Any]:
    owner_user_id = _user_uuid(user_id)
    if not owner_user_id:
        return {"nodes": {}, "ready": [], "blocked": [], "critical_path": []}
    tasks = db.query(Task).filter(Task.user_id == owner_user_id).order_by(Task.id.asc()).all()
    if not tasks:
        return {"nodes": {}, "ready": [], "blocked": [], "critical_path": []}
    graph = build_task_graph(tasks)
    critical_path = sorted(
        graph["ready"],
        key=lambda task_id: (
            -graph["critical_weight"].get(task_id, 0),
            0 if graph["nodes"][task_id]["priority"] == "high" else 1 if graph["nodes"][task_id]["priority"] == "medium" else 2,
            task_id,
        ),
    )
    return {
        "nodes": graph["nodes"],
        "ready": critical_path,
        "blocked": graph["blocked"],
        "critical_path": critical_path,
        "critical_weight": graph["critical_weight"],
    }


def get_next_ready_task(db: Session, user_id: str | uuid.UUID | None) -> dict[str, Any] | None:
    context = get_task_graph_context(db, user_id)
    task_id = next(iter(context.get("critical_path") or []), None)
    if task_id is None:
        return None
    node = (context.get("nodes") or {}).get(task_id)
    if not node:
        return None
    return {
        "task_id": task_id,
        "name": node["name"],
        "priority": node["priority"],
        "status": node["status"],
        "critical_weight": (context.get("critical_weight") or {}).get(task_id, 1),
    }


def _unlock_downstream_tasks(db: Session, task: Task, user_id: str | uuid.UUID | None) -> list[dict[str, Any]]:
    owner_user_id = _user_uuid(user_id)
    unlocked: list[dict[str, Any]] = []
    candidates = (
        db.query(Task)
        .filter(Task.user_id == owner_user_id, Task.status.in_(["blocked", "pending", "paused"]))
        .all()
    )
    for candidate in candidates:
        if task.id not in _dependency_ids(candidate):
            continue
        previous_status = candidate.status
        new_status = _recompute_task_status(db, candidate, user_id=user_id)
        if previous_status == "blocked" and new_status == "pending":
            unlocked.append({"task_id": candidate.id, "name": candidate.name, "status": candidate.status})
    return unlocked


# Lease constants kept for _acquire/_release helpers used during startup
_BACKGROUND_LEASE_NAME = "task_background_runner"
_BACKGROUND_OWNER_ID = None
_BACKGROUND_LEASE_TTL_SECONDS = 120


def _get_instance_id() -> str:
    return (
        os.environ.get("INSTANCE_ID")
        or os.environ.get("HOSTNAME")
        or socket.gethostname()
        or "unknown-instance"
    )


def _acquire_background_lease(log: logging.Logger | None = None) -> bool:
    log = log or logger
    instance_id = _get_instance_id()
    now = _now_utc()
    expires_at = now + timedelta(seconds=_BACKGROUND_LEASE_TTL_SECONDS)
    db = SessionLocal()
    try:
        lease = (
            db.query(BackgroundTaskLease)
            .filter(BackgroundTaskLease.name == _BACKGROUND_LEASE_NAME)
            .with_for_update(nowait=False)
            .first()
        )
        if lease:
            lease_expires_at = _ensure_aware_utc(lease.expires_at)
            if lease_expires_at and lease_expires_at > now and lease.owner_id != instance_id:
                log.warning(
                    "Background task lease held by %s (expires_at=%s).",
                    lease.owner_id,
                    lease_expires_at.isoformat(),
                )
                return False
            lease.owner_id = instance_id
            lease.acquired_at = now
            lease.heartbeat_at = now
            lease.expires_at = expires_at
        else:
            lease = BackgroundTaskLease(
                name=_BACKGROUND_LEASE_NAME,
                owner_id=instance_id,
                acquired_at=now,
                heartbeat_at=now,
                expires_at=expires_at,
            )
            db.add(lease)
        db.commit()
        global _BACKGROUND_OWNER_ID
        _BACKGROUND_OWNER_ID = instance_id
        log.info("Background task lease acquired by %s.", instance_id)
        return True
    except Exception as exc:
        db.rollback()
        log.warning("Failed to acquire background task lease: %s", exc)
        return False
    finally:
        db.close()


def _refresh_background_lease(log: logging.Logger | None = None) -> bool:
    log = log or logger
    instance_id = _BACKGROUND_OWNER_ID or _get_instance_id()
    now = _now_utc()
    expires_at = now + timedelta(seconds=_BACKGROUND_LEASE_TTL_SECONDS)
    db = SessionLocal()
    try:
        lease = (
            db.query(BackgroundTaskLease)
            .filter(BackgroundTaskLease.name == _BACKGROUND_LEASE_NAME)
            .with_for_update(nowait=False)
            .first()
        )
        if not lease or lease.owner_id != instance_id:
            log.warning("Background task lease lost (owner=%s).", getattr(lease, "owner_id", None))
            return False
        lease.heartbeat_at = now
        lease.expires_at = expires_at
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        log.warning("Failed to refresh background task lease: %s", exc)
        return False
    finally:
        db.close()


def _release_background_lease(log: logging.Logger | None = None) -> None:
    log = log or logger
    instance_id = _BACKGROUND_OWNER_ID or _get_instance_id()
    db = SessionLocal()
    try:
        lease = (
            db.query(BackgroundTaskLease)
            .filter(BackgroundTaskLease.name == _BACKGROUND_LEASE_NAME)
            .first()
        )
        if lease and lease.owner_id == instance_id:
            current_time = _now_utc()
            lease.expires_at = current_time
            lease.heartbeat_at = current_time
            db.commit()
            log.info("Background task lease released by %s.", instance_id)
    except Exception as exc:
        db.rollback()
        log.warning("Failed to release background task lease: %s", exc)
    finally:
        db.close()


# ----------------------------
# Core CRUD Task Management
# ----------------------------


def create_task(
    db: Session,
    name: str,
    category="general",
    priority="medium",
    due_date=None,
    masterplan_id: int | None = None,
    parent_task_id: int | None = None,
    dependency_type: str = "hard",
    dependencies=None,
    automation_type: str | None = None,
    automation_config: dict[str, Any] | None = None,
    scheduled_time=None,
    reminder_time=None,
    recurrence=None,
    user_id: str | uuid.UUID | None = None,
):
    """Creates a new task entry in the database."""
    owner_user_id = _user_uuid(user_id)
    if not owner_user_id:
        raise ValueError("user_id is required to create a task")
    if masterplan_id is not None:
        assert_masterplan_owned_via_syscall(masterplan_id, str(owner_user_id), db)
    normalized_dependencies = _normalize_dependencies(dependencies)
    _validate_dependencies(db, owner_user_id, normalized_dependencies, parent_task_id)
    task = Task(
        name=name,
        category=category,
        priority=priority,
        due_date=due_date,
        masterplan_id=masterplan_id,
        parent_task_id=parent_task_id,
        depends_on=normalized_dependencies,
        dependency_type=dependency_type or "hard",
        automation_type=automation_type,
        automation_config=automation_config,
        scheduled_time=scheduled_time,
        reminder_time=reminder_time,
        recurrence=recurrence,
        user_id=owner_user_id,
        time_spent=0,
        task_complexity=1,
        skill_level=1,
        ai_utilization=1,
        task_difficulty=1,
        status="pending",
    )
    _recompute_task_status(db, task, user_id=owner_user_id)
    db.add(task)
    db.commit()
    db.refresh(task)
    logger.info("Created task: %s", task.name)
    _emit_task_event(
        db,
        event_type=SystemEventTypes.TASK_CREATED,
        user_id=owner_user_id,
        payload={"task_id": task.id, "name": task.name, "category": task.category},
    )
    try:
        from AINDY.core.execution_unit_service import ExecutionUnitService
        ExecutionUnitService(db).create(
            eu_type="task",
            user_id=owner_user_id,
            source_type="task",
            source_id=str(task.id),
            status="pending",
            extra={"task_name": task.name, "category": task.category, "priority": task.priority},
        )
    except Exception as _eu_exc:
        logger.warning("[EU] task create hook — non-fatal | error=%s", _eu_exc)
    return task


def find_task(db: Session, name: str, user_id: str | uuid.UUID | None):
    """Find a task by name."""
    if not user_id:
        return None
    return db.query(Task).filter(Task.name == name, Task.user_id == _user_uuid(user_id)).first()


def start_task(db: Session, name: str, user_id: str | uuid.UUID | None):
    """Start tracking time for a task."""
    task = find_task(db, name, user_id=user_id)
    if not task:
        return f"Task '{name}' not found."
    if not _dependencies_complete(db, task, user_id=user_id):
        _recompute_task_status(db, task, user_id=user_id)
        db.commit()
        return f"Task '{name}' is blocked until dependencies complete."

    if not getattr(task, "start_time", None):
        task.start_time = datetime.now()
        task.status = "in_progress"
        db.commit()
        _emit_task_event(
            db,
            event_type=SystemEventTypes.TASK_STARTED,
            user_id=_user_uuid(user_id),
            payload={"task_id": task.id, "name": task.name},
        )
        try:
            from AINDY.core.execution_unit_service import ExecutionUnitService
            _eus = ExecutionUnitService(db)
            _eu = _eus.get_by_source("task", str(task.id))
            if _eu:
                _eus.update_status(_eu.id, "executing")
        except Exception as _eu_exc:
            logger.warning("[EU] task start hook — non-fatal | error=%s", _eu_exc)
        return f"Started task: {task.name}"
    return f"Task '{name}' already started."


def pause_task(db: Session, name: str, user_id: str | uuid.UUID | None):
    """Pause an in-progress task."""
    task = find_task(db, name, user_id=user_id)
    if not task:
        return "Task not found."

    if getattr(task, "status", None) == "in_progress":
        now = datetime.now()
        duration = (now - task.start_time).total_seconds()
        task.time_spent += duration
        task.status = "paused"
        db.commit()
        _emit_task_event(
            db,
            event_type=SystemEventTypes.TASK_PAUSED,
            user_id=_user_uuid(user_id),
            payload={"task_id": task.id, "name": task.name},
        )
        try:
            from AINDY.core.execution_unit_service import ExecutionUnitService
            _eus = ExecutionUnitService(db)
            _eu = _eus.get_by_source("task", str(task.id))
            if _eu:
                _eus.update_status(_eu.id, "waiting")
        except Exception as _eu_exc:
            logger.warning("[EU] task pause hook — non-fatal | error=%s", _eu_exc)
        return f"Paused task: {task.name}"
    return f"Task '{name}' is not in progress."


def complete_task(db: Session, name: str, user_id: str = None):
    """
    Mark task complete and persist the primary domain mutation.
    """
    owner_user_id = _user_uuid(user_id)
    task = find_task(db, name, user_id=user_id)
    if not task:
        return "Task not found."
    if not _dependencies_complete(db, task, user_id=user_id):
        _recompute_task_status(db, task, user_id=user_id)
        db.commit()
        raise ValueError(f"task_blocked:{task.name}")

    now = datetime.now()
    if getattr(task, "start_time", None):
        task.time_spent += (now - task.start_time).total_seconds()

    task.status = "completed"
    task.end_time = now
    unlocked_tasks = _unlock_downstream_tasks(db, task, user_id=user_id)
    db.commit()
    _emit_task_event(
        db,
        event_type=SystemEventTypes.TASK_COMPLETED,
        user_id=owner_user_id,
        payload={"task_id": task.id, "name": task.name},
    )
    try:
        from AINDY.core.execution_unit_service import ExecutionUnitService
        _eus = ExecutionUnitService(db)
        _eu = _eus.get_by_source("task", str(task.id))
        if _eu:
            _eus.update_status(_eu.id, "completed")
    except Exception as _eu_exc:
        logger.warning("[EU] task complete hook — non-fatal | error=%s", _eu_exc)

    save_calculation_via_syscall(
        db,
        "Execution Speed",
        task.time_spent,
        user_id=str(owner_user_id),
    )

    unlocked_names = ", ".join(item["name"] for item in unlocked_tasks)
    if unlocked_names:
        return f"Completed task: {task.name} | unlocked: {unlocked_names}"
    return f"Completed task: {task.name}"


def get_task_by_id(db: Session, task_id: int, user_id: str | uuid.UUID | None) -> Task | None:
    owner_user_id = _user_uuid(user_id)
    if not owner_user_id:
        return None
    return (
        db.query(Task)
        .filter(Task.id == int(task_id), Task.user_id == owner_user_id)
        .first()
    )


def queue_task_automation(
    db: Session,
    task: Task,
    user_id: str | uuid.UUID | None,
    *,
    reason: str,
) -> dict[str, Any] | None:
    if not task or not getattr(task, "automation_type", None):
        return None
    owner_user_id = _user_uuid(user_id)
    if not owner_user_id:
        return None

    from AINDY.core.execution_dispatcher import dispatch_autonomous_job

    payload = {
        "task_id": task.id,
        "task_name": task.name,
        "masterplan_id": task.masterplan_id,
        "automation_type": task.automation_type,
        "automation_config": task.automation_config or {},
        "user_id": str(owner_user_id),
    }
    return dispatch_autonomous_job(
        task_name="automation.execute",
        payload=payload,
        user_id=owner_user_id,
        source="masterplan_task" if task.masterplan_id else "task_automation",
        trigger_type="system",
        trigger_context={
            "goal": f"task:{task.name}",
            "importance": 0.7 if task.priority == "high" else 0.5 if task.priority == "medium" else 0.3,
            "reason": reason,
            "masterplan_id": task.masterplan_id,
        },
    ).envelope


def orchestrate_task_completion(db: Session, name: str, user_id: str | uuid.UUID | None) -> dict:
    owner_user_id = _user_uuid(user_id)
    task = find_task(db, name, user_id=user_id)
    if not task or not owner_user_id:
        return {
            "memory_captured": False,
            "feedback_recorded": 0,
            "social_sync": False,
            "eta_recalculated": False,
            "score_orchestrated": False,
            "next_action": None,
            "unlocked_tasks": [],
            "task_graph": {},
        }

    memory_captured = False
    feedback_recorded = 0
    social_sync = False
    eta_recalculated = False
    unlocked_tasks = _unlock_downstream_tasks(db, task, user_id=user_id)
    automation_runs: list[dict[str, Any]] = []

    try:
        from AINDY.core.execution_signal_helper import queue_memory_capture
        # Task completion memory capture is routed through a MemoryCaptureEngine-backed helper.

        node = queue_memory_capture(
            db=db,
            user_id=str(owner_user_id),
            agent_namespace="user",
            event_type="task_completed",
            content=f"Task completed: {task.name} (time_spent: {task.time_spent:.0f}s)",
            source="task_service",
            tags=["task", "completion"],
            context={"time_spent_seconds": task.time_spent},
        )
        memory_captured = node is not None
    except Exception as exc:
        logger.warning("Task completion memory capture failed: %s", exc)

    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.runtime.memory import MemoryOrchestrator

        orchestrator = MemoryOrchestrator(MemoryNodeDAO)
        memory_context = orchestrator.get_context(
            user_id=str(owner_user_id),
            query=task.name,
            task_type="analysis",
            db=db,
            max_tokens=400,
            metadata={
                "tags": ["decision", "task"],
                "node_type": "decision",
                "limit": 2,
            },
        )

        feedback_dao = MemoryNodeDAO(db)
        for memory_id in memory_context.ids:
            feedback_dao.record_feedback(
                node_id=memory_id,
                outcome="success",
                user_id=str(owner_user_id),
            )
            feedback_recorded += 1
    except Exception as exc:
        logger.warning("Task completion feedback failed: %s", exc)

    try:
        mongo = get_mongo_client()
        db_mongo = mongo["aindy_social_layer"]
        profiles = db_mongo["profiles"]
        kpi_snapshot = get_kpi_snapshot_via_syscall(str(owner_user_id), db) or {}
        master_score = float(kpi_snapshot.get("master_score", 0.0) or 0.0)
        execution_speed_score = float(kpi_snapshot.get("execution_speed", 0.0) or 0.0)
        profiles.update_one(
            {"user_id": str(owner_user_id)},
            {
                "$inc": {
                    "metrics_snapshot.execution_velocity": 1,
                },
                "$set": {
                    "metrics_snapshot.infinity_score": master_score,
                    "metrics_snapshot.execution_speed_score": execution_speed_score,
                    "updated_at": datetime.now(timezone.utc),
                },
            },
        )
        social_sync = True
    except Exception as exc:
        logger.warning("[Velocity Engine] Failed to sync with Social Layer: %s", exc)

    try:
        active_plan = get_active_masterplan_via_syscall(str(owner_user_id), db)
        if active_plan and active_plan.get("anchor_date"):
            get_eta_via_syscall(active_plan["id"], str(owner_user_id), db)
            eta_recalculated = True
    except Exception as exc:
        logger.warning("Task completion ETA recalculation failed: %s", exc)

    orchestration = {"next_action": None}
    try:
        from AINDY.platform_layer.registry import get_job

        execute_infinity_orchestrator = get_job("analytics.infinity_execute")
        if execute_infinity_orchestrator is None:
            raise RuntimeError("analytics.infinity_execute job is not registered")

        orchestration = execute_infinity_orchestrator(
            user_id=owner_user_id,
            trigger_event="task_completion",
            db=db,
        )
    except Exception as exc:
        logger.warning("Task completion orchestration failed: %s", exc)

    try:
        current_task_automation = queue_task_automation(
            db=db,
            task=task,
            user_id=owner_user_id,
            reason="task_completed",
        )
        if current_task_automation:
            automation_runs.append(
                {
                    "task_id": task.id,
                    "task_name": task.name,
                    "automation_type": task.automation_type,
                    "dispatch": current_task_automation,
                }
            )
        for unlocked in unlocked_tasks:
            unlocked_task = get_task_by_id(db, unlocked["task_id"], owner_user_id)
            dispatch = queue_task_automation(
                db=db,
                task=unlocked_task,
                user_id=owner_user_id,
                reason="task_unlocked",
            )
            if dispatch:
                automation_runs.append(
                    {
                        "task_id": unlocked_task.id,
                        "task_name": unlocked_task.name,
                        "automation_type": unlocked_task.automation_type,
                        "dispatch": dispatch,
                    }
                )
    except Exception as exc:
        logger.warning("Task automation dispatch failed: %s", exc)

    task_graph = {}
    try:
        task_graph = get_task_graph_context(db, user_id=owner_user_id)
    except Exception as exc:
        logger.warning("Task graph refresh failed: %s", exc)

    return {
        "memory_captured": memory_captured,
        "feedback_recorded": feedback_recorded,
        "social_sync": social_sync,
        "eta_recalculated": eta_recalculated,
        "score_orchestrated": True,
        "next_action": orchestration["next_action"],
        "unlocked_tasks": unlocked_tasks,
        "automation_runs": automation_runs,
        "task_graph": task_graph,
    }


def execute_task_completion(db: Session, name: str, user_id: str | uuid.UUID | None) -> dict:
    from AINDY.runtime.flow_engine import execute_intent

    return execute_intent(
        intent_data={
            "workflow_type": "task_completion",
            "task_name": name,
        },
        db=db,
        user_id=str(user_id) if user_id is not None else None,
    )


# ----------------------------
# Background / Recurrence Logic
# ----------------------------


def _check_reminders_once(log: logging.Logger | None = None, *, user_id=None):
    log = log or logger
    db = SessionLocal()
    try:
        now = datetime.now()
        q = db.query(Task)
        if user_id is not None:
            q = q.filter(Task.user_id == user_id)
        tasks = q.all()
        for t in tasks:
            if getattr(t, "reminder_time", None):
                if now >= t.reminder_time and t.status != "completed":
                    log.info("Reminder: Task '%s' is due soon!", t.name)
                    t.reminder_time = None
                    db.commit()
    except Exception as e:
        log.warning("[Reminder Error] %s", e)
    finally:
        db.close()


def _handle_recurrence_once(log: logging.Logger | None = None, *, user_id=None):
    log = log or logger
    db = SessionLocal()
    try:
        q = db.query(Task).filter(Task.status == "completed")
        if user_id is not None:
            q = q.filter(Task.user_id == user_id)
        tasks = q.all()
        _ = tasks
    except Exception as e:
        log.warning("[Recurrence Error] %s", e)
    finally:
        db.close()


def check_reminders():
    _check_reminders_once()


def handle_recurrence():
    _handle_recurrence_once()


def is_background_leader() -> bool:
    """Return True if this instance currently holds the background task lease."""
    return _BACKGROUND_OWNER_ID is not None and _BACKGROUND_OWNER_ID == _get_instance_id()


def _heartbeat_lease_job() -> None:
    """
    APScheduler job — refresh the background task lease every 60 seconds.
    Registered in scheduler_service._register_system_jobs() on leader instances only.
    Logs a warning if the lease has been lost; never raises.
    """
    try:
        result = _refresh_background_lease()
        if not result:
            logger.warning(
                "[BackgroundTaskLease] Heartbeat: lease refresh failed — lease may have been lost."
            )
    except Exception as exc:  # pragma: no cover
        logger.warning("[BackgroundTaskLease] Heartbeat job raised unexpectedly: %s", exc)


def start_background_tasks(enable: bool = True, log: logging.Logger | None = None) -> bool:
    """
    Called from main.py lifespan on startup.

    Acquires the inter-instance DB lease so that only one process runs
    background jobs in multi-instance deployments.

    Returns:
        True  — lease acquired; caller should start APScheduler.
        False — lease unavailable or disabled; caller must NOT start APScheduler.
    """
    log = log or logger
    if not enable:
        log.info("Background task runner disabled by configuration.")
        return False

    if not _acquire_background_lease(log=log):
        log.warning("Background task runner not started (lease unavailable — another instance holds it).")
        return False

    log.info("Background tasks initialized via APScheduler (daemon threads eliminated).")
    return True


def stop_background_tasks(log: logging.Logger | None = None, timeout: float = 5.0) -> None:
    """
    Called from main.py lifespan on shutdown.
    Releases the inter-instance DB lease.
    APScheduler is shut down separately via scheduler_service.stop().
    """
    log = log or logger
    _release_background_lease(log=log)
    log.info("Background task lease released.")


def list_tasks(db: Session, user_id: str | uuid.UUID | None) -> list[Task]:
    """Return all tasks for a user, newest first."""
    return (
        db.query(Task)
        .filter(Task.user_id == user_id)
        .order_by(Task.id.desc())
        .all()
    )


