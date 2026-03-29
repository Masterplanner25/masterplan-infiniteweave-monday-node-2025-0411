# /routers/task_router.py
import uuid
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from db.database import get_db
from services import task_services
from services.execution_envelope import success
from schemas.task_schemas import TaskCreate, TaskAction
from services.task_services import handle_recurrence
from services.auth_service import get_current_user
from utils.trace_context import ensure_trace_id


router = APIRouter(prefix="/tasks", tags=["Tasks"])


def _serialize_task(task) -> dict:
    return {
        "task_id": task.id,
        "task_name": task.name,
        "category": task.category,
        "priority": task.priority,
        "status": getattr(task, "status", "unknown"),
        "time_spent": task.time_spent,
        "masterplan_id": getattr(task, "masterplan_id", None),
        "parent_task_id": getattr(task, "parent_task_id", None),
        "depends_on": getattr(task, "depends_on", []) or [],
        "dependency_type": getattr(task, "dependency_type", "hard"),
        "automation_type": getattr(task, "automation_type", None),
        "automation_config": getattr(task, "automation_config", None),
    }

@router.post("/create")
def create_task(
    task: TaskCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    created = task_services.create_task(
        db=db,
        name=task.name,
        category=task.category,
        priority=task.priority,
        due_date=task.due_date,
        masterplan_id=task.masterplan_id,
        parent_task_id=task.parent_task_id,
        dependency_type=task.dependency_type,
        dependencies=task.dependencies,
        automation_type=task.automation_type,
        automation_config=task.automation_config,
        scheduled_time=task.scheduled_time,
        reminder_time=task.reminder_time,
        recurrence=task.recurrence,
        user_id=current_user["sub"],
    )
    return success(_serialize_task(created), [], ensure_trace_id())

@router.post("/start")
def start_task(
    task: TaskAction,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = task_services.start_task(db, task.name, user_id=current_user["sub"])
    return success({"message": result}, [], ensure_trace_id())

@router.post("/pause")
def pause_task(
    task: TaskAction,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = task_services.pause_task(db, task.name, user_id=current_user["sub"])
    return success({"message": result}, [], ensure_trace_id())

@router.post("/complete")
def complete_task(
    task: TaskAction,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return task_services.execute_task_completion(db, task.name, user_id=current_user["sub"])

@router.get("/list")
def list_tasks(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    tasks = db.query(task_services.Task).filter(
        task_services.Task.user_id == uuid.UUID(str(current_user["sub"]))
    ).all()
    return success([
        _serialize_task(t)
        for t in tasks
    ], [], ensure_trace_id())

@router.post("/recurrence/check")
def trigger_recurrence(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """
    Triggers the recurrence check job asynchronously.
    Public — no auth required (internal maintenance endpoint).
    """
    background_tasks.add_task(handle_recurrence)
    return success({"message": "Recurrence job started in background."}, [], ensure_trace_id())

