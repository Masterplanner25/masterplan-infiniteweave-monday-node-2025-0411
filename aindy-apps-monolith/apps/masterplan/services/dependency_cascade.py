"""
Dependency cascade logic for masterplan task activation.

Rules:
  A task is READY if:
    1. It has no dependency relationships, OR
    2. All tasks it depends on have status="completed"
  A task is BLOCKED if any dependency is not completed.
  A task is ORPHANED if a dependency was deleted without completion.

This module reads task state via syscall and activates tasks only through the
tasks syscall layer.
"""
from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _dispatch(name: str, payload: dict, *, user_id: str, db: "Session"):
    from AINDY.kernel.syscall_dispatcher import SyscallContext, get_dispatcher

    ctx = SyscallContext(
        execution_unit_id=str(uuid.uuid4()),
        user_id=str(user_id),
        capabilities=[
            "masterplan.read",
            "task.read",
            "task.start",
            "task.write",
        ],
        trace_id="",
        metadata={"_db": db},
    )
    return get_dispatcher().dispatch(name, payload, ctx)


def evaluate_task_readiness(
    db: "Session",
    masterplan_id: str | int,
    user_id: str,
) -> dict[str, list[str]]:
    """
    Evaluate all tasks in a masterplan and categorise by readiness.
    Returns:
      {
        "ready":   [task_ids that should be activated],
        "blocked": [task_ids waiting on incomplete dependencies],
        "orphaned":[task_ids whose dependencies no longer exist],
      }
    """
    result = _dispatch(
        "sys.v1.tasks.get_graph_context",
        {"masterplan_id": str(masterplan_id), "user_id": str(user_id)},
        user_id=str(user_id),
        db=db,
    )
    if result["status"] != "success":
        logger.warning("[cascade] Could not fetch task graph: %s", result.get("error"))
        return {"ready": [], "blocked": [], "orphaned": []}

    graph_result = result.get("data") or {}
    nodes = graph_result.get("nodes") or {}
    critical_path = list(graph_result.get("critical_path") or [])
    plan_nodes = {
        str(task_id): task_data
        for task_id, task_data in nodes.items()
        if str(task_data.get("masterplan_id")) == str(masterplan_id)
    }
    all_ids = set(plan_nodes.keys())

    ready: list[str] = []
    blocked: list[str] = []
    orphaned: list[str] = []

    for task_id, task_data in plan_nodes.items():
        status = str(task_data.get("status") or "")
        if status in {"completed", "in_progress"}:
            continue

        deps = [str(dep) for dep in (task_data.get("depends_on") or [])]
        if not deps:
            ready.append(task_id)
            continue

        missing = [dep for dep in deps if dep not in all_ids]
        if missing:
            orphaned.append(task_id)
            continue

        unmet = [
            dep for dep in deps
            if str((plan_nodes.get(dep) or {}).get("status") or "") != "completed"
        ]
        if unmet:
            blocked.append(task_id)
        else:
            ready.append(task_id)

    if critical_path:
        critical_ready = [
            str(task_id)
            for task_id in critical_path
            if str(task_id) in set(ready)
        ]
        trailing_ready = [task_id for task_id in ready if task_id not in set(critical_ready)]
        ready = critical_ready + trailing_ready

    return {"ready": ready, "blocked": blocked, "orphaned": orphaned}


def activate_ready_tasks(
    db: "Session",
    masterplan_id: str | int,
    user_id: str,
) -> list[str]:
    """
    Start and queue automation for ready tasks that have automation metadata.
    Returns list of activated task IDs.
    """
    readiness = evaluate_task_readiness(db, masterplan_id, user_id)
    activated: list[str] = []

    for task_id in readiness["ready"]:
        try:
            task_result = _dispatch(
                "sys.v1.task.get",
                {"task_id": int(task_id), "user_id": str(user_id)},
                user_id=str(user_id),
                db=db,
            )
            if task_result["status"] != "success":
                logger.warning("[cascade] Could not load task %s: %s", task_id, task_result.get("error"))
                continue

            task = ((task_result.get("data") or {}).get("task") or {})
            task_name = task.get("name")
            automation_type = task.get("automation_type")
            automation_config = task.get("automation_config")
            status = str(task.get("status") or "")

            if not task_name:
                continue
            if not automation_type or automation_config is None:
                continue
            if status in {"completed", "in_progress"}:
                continue

            start_result = _dispatch(
                "sys.v1.task.start",
                {"task_name": task_name, "user_id": str(user_id)},
                user_id=str(user_id),
                db=db,
            )
            if start_result["status"] != "success":
                logger.warning("[cascade] Failed to start task %s: %s", task_id, start_result.get("error"))
                continue
            start_message = (
                (((start_result.get("data") or {}).get("task_start_result") or {}).get("message"))
                or ""
            )
            if "blocked" in start_message.lower() or "not found" in start_message.lower():
                logger.warning("[cascade] Task %s did not become startable: %s", task_id, start_message)
                continue

            _dispatch(
                "sys.v1.task.queue_automation",
                {
                    "task_id": int(task_id),
                    "automation_type": automation_type,
                    "automation_config": automation_config,
                    "reason": "masterplan_dependency_ready",
                    "user_id": str(user_id),
                },
                user_id=str(user_id),
                db=db,
            )
            activated.append(str(task_id))
            logger.info("[cascade] Task %s activated via automation cascade", task_id)
        except Exception as exc:
            logger.warning("[cascade] Failed to activate task %s: %s", task_id, exc)

    return activated
