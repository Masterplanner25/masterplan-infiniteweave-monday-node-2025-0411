# /routers/task_router.py
import uuid
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from db.database import get_db
from services import task_services
from schemas.task_schemas import TaskCreate, TaskAction
from services.task_services import handle_recurrence
from services.auth_service import get_current_user


router = APIRouter(prefix="/tasks", tags=["Tasks"])

@router.post("/create")
def create_task(
    task: TaskCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # TODO: Scope task to current_user["sub"] when user_id is added to Task model
    return task_services.create_task(
        db=db,
        name=task.name,
        category=task.category,
        priority=task.priority,
        due_date=task.due_date,
        dependencies=task.dependencies,
        scheduled_time=task.scheduled_time,
        reminder_time=task.reminder_time,
        recurrence=task.recurrence,
        user_id=current_user["sub"],
    )

@router.post("/start")
def start_task(
    task: TaskAction,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return task_services.start_task(db, task.name, user_id=current_user["sub"])

@router.post("/pause")
def pause_task(
    task: TaskAction,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return task_services.pause_task(db, task.name, user_id=current_user["sub"])

@router.post("/complete")
def complete_task(
    task: TaskAction,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return task_services.complete_task(db, task.name, user_id=current_user["sub"])

@router.get("/list")
def list_tasks(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    tasks = db.query(task_services.Task).filter(
        task_services.Task.user_id == uuid.UUID(str(current_user["sub"]))
    ).all()
    return [
        {
            "task_name": t.name,
            "status": getattr(t, "status", "unknown"),
            "time_spent": t.time_spent,
        }
        for t in tasks
    ]

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
    return {"message": "Recurrence job started in background."}

