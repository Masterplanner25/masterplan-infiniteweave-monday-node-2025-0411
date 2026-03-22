# /services/task_services.py
import time
import uuid
import threading
import logging
import os
import socket
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from db.database import SessionLocal
from db.models.task import Task
from db.models.background_task_lease import BackgroundTaskLease
from services.calculation_services import save_calculation, calculate_twr, TaskInput
from db.mongo_setup import get_mongo_client

logger = logging.getLogger(__name__)

_BACKGROUND_LOCK = threading.Lock()
_BACKGROUND_STARTED = False
_BACKGROUND_STOP_EVENT = None
_BACKGROUND_THREADS: list[threading.Thread] = []
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
    now = datetime.utcnow()
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
            if lease.expires_at and lease.expires_at > now and lease.owner_id != instance_id:
                log.warning(
                    "Background task lease held by %s (expires_at=%s).",
                    lease.owner_id,
                    lease.expires_at.isoformat(),
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
    now = datetime.utcnow()
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
            lease.expires_at = datetime.utcnow()
            lease.heartbeat_at = datetime.utcnow()
            db.commit()
            log.info("Background task lease released by %s.", instance_id)
    except Exception as exc:
        db.rollback()
        log.warning("Failed to release background task lease: %s", exc)
    finally:
        db.close()


def _run_lease_heartbeat(stop_event: threading.Event, log: logging.Logger | None = None):
    log = log or logger
    while not stop_event.is_set():
        if not _refresh_background_lease(log=log):
            log.warning("Stopping background tasks due to lost lease.")
            stop_event.set()
            return
        stop_event.wait(_BACKGROUND_LEASE_TTL_SECONDS / 3)

# ----------------------------
# Core CRUD Task Management
# ----------------------------

def create_task(db: Session, name: str, category="general", priority="medium", due_date=None, 
                dependencies=None, scheduled_time=None, reminder_time=None, recurrence=None, user_id: str | uuid.UUID | None = None):
    """Creates a new task entry in the database."""
    if not user_id:
        raise ValueError("user_id is required to create a task")
    if dependencies is None:
        dependencies = []
    task = Task(
        name=name,  # ✅ Fixed column name
        category=category,
        priority=priority,
        due_date=due_date,
        scheduled_time=scheduled_time,
        reminder_time=reminder_time,
        recurrence=recurrence,
        user_id=uuid.UUID(str(user_id)),
        time_spent=0,
        task_complexity=1,
        skill_level=1,
        ai_utilization=1,
        task_difficulty=1,
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    logger.info("Created task: %s", task.name)
    return task


def find_task(db: Session, name: str, user_id: str | uuid.UUID | None):
    """Find a task by name."""
    # ✅ Fixed column name here too
    if not user_id:
        return None
    return db.query(Task).filter(Task.name == name, Task.user_id == uuid.UUID(str(user_id))).first()


def start_task(db: Session, name: str, user_id: str | uuid.UUID | None):
    """Start tracking time for a task."""
    task = find_task(db, name, user_id=user_id)
    if not task:
        return f"❌ Task '{name}' not found."

    if not getattr(task, "start_time", None):
        task.start_time = datetime.now()
        task.status = "in_progress"
        db.commit()
        return f"▶️ Started task: {task.name}"
    return f"⚠️ Task '{name}' already started."


def pause_task(db: Session, name: str, user_id: str | uuid.UUID | None):
    """Pause an in-progress task."""
    task = find_task(db, name, user_id=user_id)
    if not task:
        return "❌ Task not found."

    if getattr(task, "status", None) == "in_progress":
        now = datetime.now()
        duration = (now - task.start_time).total_seconds()
        task.time_spent += duration
        task.status = "paused"
        db.commit()
        return f"⏸ Paused task: {task.name}"
    return f"⚠️ Task '{name}' is not in progress."


def complete_task(db: Session, name: str, user_id: str = None):
    """
    Mark task complete, log duration, AND update Social Velocity.
    """
    task = find_task(db, name, user_id=user_id)
    if not task:
        return "❌ Task not found."

    now = datetime.now()
    if getattr(task, "start_time", None):
        task.time_spent += (now - task.start_time).total_seconds()

    task.status = "completed"
    task.end_time = now
    db.commit()

    # Write task completion to memory (fire-and-forget)
    if user_id:
        try:
            from services.memory_capture_engine import MemoryCaptureEngine
            engine = MemoryCaptureEngine(
                db=db,
                user_id=user_id,
                agent_namespace="user",
            )
            engine.evaluate_and_capture(
                event_type="task_completed",
                content=f"Task completed: {task.name} (time_spent: {task.time_spent:.0f}s)",
                source="task_service",
                tags=["task", "completion"],
                context={"time_spent_seconds": task.time_spent},
            )
        except Exception:
            pass

    # Auto-feedback: task completion reinforces related decision memories
    try:
        if db and user_id:
            from db.dao.memory_node_dao import MemoryNodeDAO
            from runtime.memory import MemoryOrchestrator

            task_title = getattr(task, "name", "")
            orchestrator = MemoryOrchestrator(MemoryNodeDAO)
            context = orchestrator.get_context(
                user_id=str(user_id),
                query=task_title,
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
            for memory_id in context.ids:
                feedback_dao.record_feedback(
                    node_id=memory_id,
                    outcome="success",
                    user_id=str(user_id),
                )
    except Exception:
        pass

    # Calculate TWR
    task_input = TaskInput(
        task_name=task.name, # Pydantic model uses 'task_name', DB uses 'name'
        time_spent=task.time_spent / 3600, 
        task_complexity=task.task_complexity,
        skill_level=task.skill_level,
        ai_utilization=task.ai_utilization,
        task_difficulty=task.task_difficulty
    )
    twr_score = calculate_twr(task_input)
    
    save_calculation(db, "Time-to-Wealth Ratio", twr_score, user_id=str(user_id))
    save_calculation(db, "Execution Speed", task.time_spent, user_id=str(user_id))

    # Update Social Velocity
    try:
        mongo = get_mongo_client()
        db_mongo = mongo["aindy_social_layer"]
        profiles = db_mongo["profiles"]
        
        profiles.update_one(
            {"user_id": str(user_id)},
            {
                "$inc": {
                    "metrics_snapshot.execution_velocity": 1, 
                    "metrics_snapshot.twr_score": twr_score * 0.1 
                },
                "$set": {
                    "updated_at": datetime.utcnow()
                }
            }
        )
        logger.info("[Velocity Engine] Profile updated. TWR impact: %s", twr_score)
    except Exception as e:
        logger.warning("[Velocity Engine] Failed to sync with Social Layer: %s", e)

    return f"✅ Completed task: {task.name} (TWR: {twr_score:.2f})"

# ----------------------------
# Background / Recurrence Logic
# ----------------------------

def _check_reminders_once(log: logging.Logger | None = None):
    log = log or logger
    db = SessionLocal()
    try:
        now = datetime.now()
        tasks = db.query(Task).all()
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


def _run_check_reminders(stop_event: threading.Event, log: logging.Logger | None = None):
    log = log or logger
    while not stop_event.is_set():
        _check_reminders_once(log=log)
        stop_event.wait(60)

def _handle_recurrence_once(log: logging.Logger | None = None):
    log = log or logger
    db = SessionLocal()
    try:
        tasks = db.query(Task).filter(Task.status == "completed").all()
        _ = tasks
    except Exception as e:
        log.warning("[Recurrence Error] %s", e)
    finally:
        db.close()


def _run_handle_recurrence(stop_event: threading.Event, log: logging.Logger | None = None):
    log = log or logger
    while not stop_event.is_set():
        _handle_recurrence_once(log=log)
        stop_event.wait(60)


def check_reminders():
    _check_reminders_once()


def handle_recurrence():
    _handle_recurrence_once()


def start_background_tasks(enable: bool = True, log: logging.Logger | None = None):
    log = log or logger
    if not enable:
        log.info("Background task runner disabled by configuration.")
        return None

    global _BACKGROUND_STARTED, _BACKGROUND_STOP_EVENT, _BACKGROUND_THREADS
    with _BACKGROUND_LOCK:
        if _BACKGROUND_STARTED:
            log.info("Background task runner already started.")
            return _BACKGROUND_STOP_EVENT
        if not _acquire_background_lease(log=log):
            log.warning("Background task runner not started (lease unavailable).")
            return None
        _BACKGROUND_STARTED = True
        _BACKGROUND_STOP_EVENT = threading.Event()
        _BACKGROUND_THREADS = [
            threading.Thread(
                target=_run_lease_heartbeat,
                args=(_BACKGROUND_STOP_EVENT, log),
                daemon=True,
                name="task_lease_heartbeat",
            ),
            threading.Thread(
                target=_run_handle_recurrence,
                args=(_BACKGROUND_STOP_EVENT, log),
                daemon=True,
                name="task_recurrence",
            ),
            threading.Thread(
                target=_run_check_reminders,
                args=(_BACKGROUND_STOP_EVENT, log),
                daemon=True,
                name="task_reminders",
            ),
        ]
        for thread in _BACKGROUND_THREADS:
            thread.start()
        log.info("Background task runner started (%s threads).", len(_BACKGROUND_THREADS))
        return _BACKGROUND_STOP_EVENT


def stop_background_tasks(log: logging.Logger | None = None, timeout: float = 5.0):
    log = log or logger
    global _BACKGROUND_STARTED, _BACKGROUND_STOP_EVENT, _BACKGROUND_THREADS
    with _BACKGROUND_LOCK:
        if not _BACKGROUND_STARTED:
            return
        if _BACKGROUND_STOP_EVENT:
            _BACKGROUND_STOP_EVENT.set()
        for thread in _BACKGROUND_THREADS:
            thread.join(timeout=timeout)
        _BACKGROUND_THREADS = []
        _BACKGROUND_STOP_EVENT = None
        _BACKGROUND_STARTED = False
        _release_background_lease(log=log)
        log.info("Background task runner stopped.")
