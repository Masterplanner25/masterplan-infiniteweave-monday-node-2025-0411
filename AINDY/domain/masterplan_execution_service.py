from __future__ import annotations

import uuid
from typing import Any

from AINDY.db.models.automation_log import AutomationLog
from AINDY.db.models.masterplan import MasterPlan
from AINDY.db.models.task import Task
from AINDY.domain.task_services import create_task


_CHILD_KEYS = ("phases", "milestones", "steps", "tasks", "actions", "initiatives", "objectives")


def sync_masterplan_tasks(
    *,
    db,
    masterplan: MasterPlan,
    user_id: str | uuid.UUID,
    replace_existing: bool = False,
) -> dict[str, Any]:
    owner_user_id = uuid.UUID(str(user_id))
    existing = (
        db.query(Task)
        .filter(Task.user_id == owner_user_id, Task.masterplan_id == masterplan.id)
        .order_by(Task.id.asc())
        .all()
    )
    if existing and not replace_existing:
        return {
            "generated": 0,
            "total_tasks": len(existing),
            "task_ids": [task.id for task in existing],
            "skipped": True,
        }

    if replace_existing and existing:
        protected = [task.id for task in existing if task.status == "completed"]
        if protected:
            raise ValueError("masterplan_tasks_completed_cannot_replace")
        for task in existing:
            db.delete(task)
        db.flush()

    roots = _extract_root_items(masterplan.structure_json or {})
    created_ids: list[int] = []
    previous_root_task_id: int | None = None
    for index, item in enumerate(roots):
        created = _create_task_branch(
            db=db,
            owner_user_id=owner_user_id,
            masterplan_id=masterplan.id,
            item=item,
            fallback_name=f"MasterPlan Task {index + 1}",
            parent_task_id=None,
            sibling_dependency_id=previous_root_task_id,
        )
        if created is None:
            continue
        created_ids.extend(created["task_ids"])
        previous_root_task_id = created["root_task_id"]

    db.commit()
    return {
        "generated": len(created_ids),
        "total_tasks": (
            db.query(Task)
            .filter(Task.user_id == owner_user_id, Task.masterplan_id == masterplan.id)
            .count()
        ),
        "task_ids": created_ids,
        "skipped": False,
    }


def get_masterplan_execution_status(*, db, masterplan_id: int, user_id: str | uuid.UUID) -> dict[str, Any]:
    owner_user_id = uuid.UUID(str(user_id))
    tasks = (
        db.query(Task)
        .filter(Task.user_id == owner_user_id, Task.masterplan_id == masterplan_id)
        .order_by(Task.id.asc())
        .all()
    )
    task_counts = {
        "total": len(tasks),
        "completed": sum(1 for task in tasks if task.status == "completed"),
        "pending": sum(1 for task in tasks if task.status == "pending"),
        "blocked": sum(1 for task in tasks if task.status == "blocked"),
        "in_progress": sum(1 for task in tasks if task.status == "in_progress"),
        "paused": sum(1 for task in tasks if task.status == "paused"),
    }
    task_lookup = {task.id: task for task in tasks}
    task_ids = set(task_lookup)
    logs = (
        db.query(AutomationLog)
        .filter(AutomationLog.user_id == owner_user_id)
        .order_by(AutomationLog.created_at.desc())
        .limit(250)
        .all()
    )
    relevant_logs = []
    for log in logs:
        payload = log.payload or {}
        if payload.get("masterplan_id") == masterplan_id or payload.get("task_id") in task_ids:
            relevant_logs.append(log)
    automation_counts = {
        "total": len(relevant_logs),
        "pending": sum(1 for log in relevant_logs if log.status == "pending"),
        "running": sum(1 for log in relevant_logs if log.status == "running"),
        "success": sum(1 for log in relevant_logs if log.status == "success"),
        "failed": sum(1 for log in relevant_logs if log.status == "failed"),
        "deferred": sum(1 for log in relevant_logs if log.status == "deferred"),
        "ignored": sum(1 for log in relevant_logs if log.status == "ignored"),
    }
    task_items = [
        {
            "task_id": task.id,
            "name": task.name,
            "status": task.status,
            "priority": task.priority,
            "parent_task_id": task.parent_task_id,
            "depends_on": task.depends_on or [],
            "automation_type": task.automation_type,
            "automation_config": task.automation_config,
        }
        for task in tasks
    ]
    failed_automations = [
        {
            "automation_log_id": log.id,
            "task_id": (log.payload or {}).get("task_id"),
            "task_name": (log.payload or {}).get("task_name") or log.task_name,
            "status": log.status,
            "error_message": log.error_message,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in relevant_logs
        if log.status == "failed"
    ]
    return {
        "tasks": task_counts,
        "automations": automation_counts,
        "task_items": task_items,
        "failed_automations": failed_automations,
    }


def _extract_root_items(structure_json: dict[str, Any]) -> list[Any]:
    if not isinstance(structure_json, dict):
        return []
    for key in _CHILD_KEYS:
        value = structure_json.get(key)
        if isinstance(value, list) and value:
            return value
    return []


def _extract_children(item: Any) -> list[Any]:
    if isinstance(item, dict):
        for key in _CHILD_KEYS:
            value = item.get(key)
            if isinstance(value, list) and value:
                return value
    return []


def _task_name_from_item(item: Any, fallback_name: str) -> str:
    if isinstance(item, str):
        return item.strip() or fallback_name
    if isinstance(item, dict):
        for key in ("name", "title", "label", "objective", "summary", "description"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return fallback_name


def _category_from_item(item: Any, fallback: str) -> str:
    if isinstance(item, dict) and item.get("category"):
        return str(item["category"])
    return fallback


def _priority_from_item(item: Any) -> str:
    if isinstance(item, dict) and item.get("priority"):
        return str(item["priority"])
    return "medium"


def _automation_from_item(item: Any) -> tuple[str | None, dict[str, Any] | None]:
    if not isinstance(item, dict):
        return None, None
    automation = item.get("automation")
    if isinstance(automation, dict):
        automation_type = automation.get("type") or item.get("automation_type")
        return str(automation_type) if automation_type else None, dict(automation)
    automation_type = item.get("automation_type")
    automation_config = item.get("automation_config")
    return (
        str(automation_type) if automation_type else None,
        dict(automation_config) if isinstance(automation_config, dict) else None,
    )


def _create_task_branch(
    *,
    db,
    owner_user_id: uuid.UUID,
    masterplan_id: int,
    item: Any,
    fallback_name: str,
    parent_task_id: int | None,
    sibling_dependency_id: int | None,
) -> dict[str, Any] | None:
    name = _task_name_from_item(item, fallback_name)
    automation_type, automation_config = _automation_from_item(item)
    dependencies = []
    if sibling_dependency_id is not None:
        dependencies.append({"task_id": sibling_dependency_id, "dependency_type": "hard"})
    created = create_task(
        db=db,
        name=name,
        category=_category_from_item(item, "masterplan"),
        priority=_priority_from_item(item),
        masterplan_id=masterplan_id,
        parent_task_id=parent_task_id,
        dependency_type="hard",
        dependencies=dependencies,
        automation_type=automation_type,
        automation_config=automation_config,
        user_id=owner_user_id,
    )
    created_ids = [created.id]
    previous_child_id: int | None = None
    for index, child in enumerate(_extract_children(item)):
        child_branch = _create_task_branch(
            db=db,
            owner_user_id=owner_user_id,
            masterplan_id=masterplan_id,
            item=child,
            fallback_name=f"{name} Step {index + 1}",
            parent_task_id=created.id,
            sibling_dependency_id=previous_child_id,
        )
        if child_branch is None:
            continue
        created_ids.extend(child_branch["task_ids"])
        previous_child_id = child_branch["root_task_id"]
    return {"root_task_id": created.id, "task_ids": created_ids}

