# /routers/task_router.py
import logging

from fastapi import APIRouter, Depends, BackgroundTasks, Request
from sqlalchemy.orm import Session
from AINDY.core.execution_gate import to_envelope
from AINDY.core.execution_service import ExecutionContext
from AINDY.core.execution_service import run_execution
from AINDY.core.observability_events import emit_observability_event
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from apps.tasks.schemas.task_schemas import TaskCreate, TaskAction
from AINDY.services.auth_service import get_current_user
from apps.tasks.events import TaskEventTypes as SystemEventTypes

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/tasks", tags=["Tasks"])


def _execute_tasks(request: Request, route_name: str, handler, *, db: Session, user_id: str, input_payload=None):
    return run_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="task_router",
            operation=route_name,
            start_payload=input_payload or {},
        ),
        lambda: handler(None),
    )


def _flow_envelope(result: dict) -> dict:
    """Embed execution_envelope into flow result data. Returns the data dict."""
    data = result.get("data")
    if not isinstance(data, dict):
        data = {} if data is None else {"result": data}
    data.setdefault("execution_envelope", to_envelope(
        eu_id=result.get("run_id"),
        trace_id=result.get("trace_id"),
        status=str(result.get("status") or "UNKNOWN").upper(),
        output=None,
        error=result.get("error"),
        duration_ms=None,
        attempt_count=None,
    ))
    return data


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
@limiter.limit("30/minute")
def create_task(
    request: Request,
    task: TaskCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    _task_result: dict = {}

    def handler(_ctx):
        from AINDY.runtime.flow_engine import run_flow
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
        data = result.get("data")
        if isinstance(data, dict):
            _task_result.update(data)
        return _flow_envelope(result)

    response = _execute_tasks(request, "tasks.create", handler, db=db, user_id=user_id, input_payload={"task_name": task.name})

    # TERMINAL — emitted after the pipeline so any internal rollback is already settled.
    # user_id intentionally omitted: the pipeline's FK errors can roll back the users
    # row in the test session, and the FK on system_events.user_id would fail.
    # The event is still fully observable via trace_id and payload.
    try:
        emit_observability_event(
            event_type=SystemEventTypes.TASK_CREATED,
            user_id=None,
            payload={
                "operation": "create",
                "name": task.name,
                "user_id": user_id,
                "task_id": _task_result.get("task_id"),
            },
            source="task",
        )
    except Exception as _obs_exc:
        logger.warning("[task] observability emit failed (create): %s", _obs_exc)

    return response

@router.post("/start")
@limiter.limit("30/minute")
def start_task(
    request: Request,
    task: TaskAction,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(_ctx):
        from AINDY.runtime.flow_engine import run_flow
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
        return _flow_envelope(result)

    return _execute_tasks(request, "tasks.start", handler, db=db, user_id=user_id, input_payload={"task_name": task.name})

@router.post("/pause")
@limiter.limit("30/minute")
def pause_task(
    request: Request,
    task: TaskAction,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(_ctx):
        from AINDY.runtime.flow_engine import run_flow
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
        return _flow_envelope(result)

    return _execute_tasks(request, "tasks.pause", handler, db=db, user_id=user_id, input_payload={"task_name": task.name})

@router.post("/complete")
@limiter.limit("30/minute")
def complete_task(
    request: Request,
    task: TaskAction,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(_ctx):
        from AINDY.runtime.flow_engine import run_flow
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
        return _flow_envelope(result)

    return _execute_tasks(request, "tasks.complete", handler, db=db, user_id=user_id, input_payload={"task_name": task.name})

@router.get("/list")
@limiter.limit("60/minute")
def list_tasks(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        from apps.tasks.services.task_service import list_tasks
        tasks = list_tasks(db, user_id=current_user["sub"])
        return {
            "tasks": [_serialize_task(task) for task in tasks],
            "execution_envelope": to_envelope(
                eu_id=None, trace_id=None, status="SUCCESS",
                output=None, error=None, duration_ms=None, attempt_count=1,
            ),
        }
    return _execute_tasks(request, "tasks.list", handler, db=db, user_id=user_id)

@router.post("/recurrence/check")
@limiter.limit("30/minute")
def trigger_recurrence(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Triggers the recurrence check job asynchronously."""
    user_id = str(current_user["sub"])
    def handler(_ctx):
        from AINDY.runtime.flow_engine import run_flow
        result = run_flow("tasks_recurrence_check", {}, db=db, user_id=user_id)
        if result.get("status") == "error":
            raise RuntimeError((result.get("data") or {}).get("message", "Recurrence check failed"))
        return _flow_envelope(result)
    return _execute_tasks(request, "tasks.recurrence.check", handler, db=db, user_id=user_id)



