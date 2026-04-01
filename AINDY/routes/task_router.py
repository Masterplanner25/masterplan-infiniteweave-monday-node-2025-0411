# /routers/task_router.py
from fastapi import APIRouter, Depends, BackgroundTasks, Request
from sqlalchemy.orm import Session
from core.execution_helper import execute_with_pipeline_sync
from db.database import get_db
from schemas.task_schemas import TaskCreate, TaskAction
from services.auth_service import get_current_user


router = APIRouter(prefix="/tasks", tags=["Tasks"])


def _execute_tasks(request: Request, route_name: str, handler, *, db: Session, user_id: str, input_payload=None):
    return execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        input_payload=input_payload,
        metadata={"db": db, "source": "task_router"},
    )


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
    request: Request,
    task: TaskCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(_ctx):
        from services.flow_engine import run_flow
        result = run_flow(
            "task_create",
            {
                "task_name": task.name,
                "category": task.category,
                "priority": task.priority,
                "due_date": task.due_date.isoformat() if task.due_date else None,
                "masterplan_id": task.masterplan_id,
                "parent_task_id": task.parent_task_id,
                "dependency_type": task.dependency_type,
                "dependencies": task.dependencies,
                "automation_type": task.automation_type,
                "automation_config": task.automation_config,
                "scheduled_time": task.scheduled_time.isoformat() if task.scheduled_time else None,
                "reminder_time": task.reminder_time.isoformat() if task.reminder_time else None,
                "recurrence": task.recurrence,
            },
            db=db,
            user_id=user_id,
        )
        if result.get("status") == "error":
            raise RuntimeError(
                (result.get("data") or {}).get("message", "Task create flow failed")
            )
        return result.get("data")

    return _execute_tasks(request, "tasks.create", handler, db=db, user_id=user_id, input_payload={"task_name": task.name})

@router.post("/start")
def start_task(
    request: Request,
    task: TaskAction,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(_ctx):
        from services.flow_engine import run_flow
        result = run_flow(
            "task_start",
            {"task_name": task.name},
            db=db,
            user_id=user_id,
        )
        if result.get("status") == "error":
            raise RuntimeError(
                (result.get("data") or {}).get("message", "Task start flow failed")
            )
        return result.get("data")

    return _execute_tasks(request, "tasks.start", handler, db=db, user_id=user_id, input_payload={"task_name": task.name})

@router.post("/pause")
def pause_task(
    request: Request,
    task: TaskAction,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(_ctx):
        from services.flow_engine import run_flow
        result = run_flow(
            "task_pause",
            {"task_name": task.name},
            db=db,
            user_id=user_id,
        )
        if result.get("status") == "error":
            raise RuntimeError(
                (result.get("data") or {}).get("message", "Task pause flow failed")
            )
        return result.get("data")

    return _execute_tasks(request, "tasks.pause", handler, db=db, user_id=user_id, input_payload={"task_name": task.name})

@router.post("/complete")
def complete_task(
    request: Request,
    task: TaskAction,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(_ctx):
        from services.flow_engine import run_flow
        result = run_flow(
            "task_completion",
            {"task_name": task.name},
            db=db,
            user_id=user_id,
        )
        if result.get("status") == "error":
            raise RuntimeError(
                (result.get("data") or {}).get("message", "Task completion flow failed")
            )
        return result.get("data")

    return _execute_tasks(request, "tasks.complete", handler, db=db, user_id=user_id, input_payload={"task_name": task.name})

@router.get("/list")
def list_tasks(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        from services.flow_engine import run_flow
        result = run_flow("tasks_list", {}, db=db, user_id=user_id)
        if result.get("status") == "error":
            raise RuntimeError((result.get("data") or {}).get("message", "Tasks list flow failed"))
        return result.get("data")
    return _execute_tasks(request, "tasks.list", handler, db=db, user_id=user_id)

@router.post("/recurrence/check")
def trigger_recurrence(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Triggers the recurrence check job asynchronously."""
    user_id = str(current_user["sub"])
    def handler(_ctx):
        from services.flow_engine import run_flow
        result = run_flow("tasks_recurrence_check", {}, db=db, user_id=user_id)
        if result.get("status") == "error":
            raise RuntimeError((result.get("data") or {}).get("message", "Recurrence check failed"))
        return result.get("data")
    return _execute_tasks(request, "tasks.recurrence.check", handler, db=db, user_id=user_id)

