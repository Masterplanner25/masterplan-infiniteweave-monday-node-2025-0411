# /routers/task_router.py
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from db.config import get_db
from services import task_services
from db.models.task_schemas import TaskCreate, TaskAction
from services.task_services import handle_recurrence


router = APIRouter(prefix="/tasks", tags=["Tasks"])

@router.post("/create")
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    return task_services.create_task(
        db=db,
        name=task.name,
        category=task.category,
        priority=task.priority,
        due_date=task.due_date,
        dependencies=task.dependencies,
        scheduled_time=task.scheduled_time,
        reminder_time=task.reminder_time,
        recurrence=task.recurrence
    )

@router.post("/start")
def start_task(task: TaskAction, db: Session = Depends(get_db)):
    return task_services.start_task(db, task.name)

@router.post("/pause")
def pause_task(task: TaskAction, db: Session = Depends(get_db)):
    return task_services.pause_task(db, task.name)

@router.post("/complete")
def complete_task(task: TaskAction, db: Session = Depends(get_db)):
    return task_services.complete_task(db, task.name)

@router.get("/list")
def list_tasks(db: Session = Depends(get_db)):
    tasks = db.query(task_services.Task).all()
    return [
        {
            "task_name": t.task_name,
            "status": getattr(t, "status", "unknown"),
            "time_spent": t.time_spent,
        }
        for t in tasks
    ]
@router.post("/recurrence/check")
def trigger_recurrence(background_tasks: BackgroundTasks):
    """
    Triggers the recurrence check job asynchronously.
    """
    background_tasks.add_task(handle_recurrence)
    return {"message": "Recurrence job started in background."}

