# /services/task_services.py
import threading
import time
from sqlalchemy.orm import Session
from db.models import CalculationResult
from db.models.task_schemas import TaskCreate, TaskAction
from services.calculation_services import save_calculation  # from your existing services.py
from db.models import TaskInput
from fastapi import BackgroundTasks
from db.config import SessionLocal
from db.models.models import Task
from datetime import datetime, timedelta

# ----------------------------
# Core CRUD Task Management
# ----------------------------

def create_task(db: Session, name: str, category="general", priority="medium", due_date=None,
                dependencies=None, scheduled_time=None, reminder_time=None, recurrence=None):
    """Creates a new task entry in the database."""
    task = Task(
        task_name=name,
        time_spent=0,
        task_complexity=1,
        skill_level=1,
        ai_utilization=1,
        task_difficulty=1
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    print(f"✅ Created task: {task.task_name}")
    return task


def find_task(db: Session, name: str):
    """Find a task by name."""
    return db.query(Task).filter(Task.task_name == name).first()


def start_task(db: Session, name: str):
    """Starts tracking time for a task."""
    task = find_task(db, name)
    if not task:
        return f"❌ Task '{name}' not found."

    if not getattr(task, "start_time", None):
        task.start_time = datetime.datetime.now()
        task.status = "in_progress"
        db.commit()
        return f"▶️ Started task: {task.task_name}"
    else:
        return f"⚠️ Task '{name}' already started."


def pause_task(db: Session, name: str):
    """Pauses an in-progress task."""
    task = find_task(db, name)
    if not task:
        return "Task not found."

    if getattr(task, "status", None) == "in_progress":
        now = datetime.datetime.now()
        duration = (now - task.start_time).total_seconds()
        task.time_spent += duration
        task.status = "paused"
        db.commit()
        return f"⏸ Paused task: {task.task_name}"
    return f"⚠️ Task '{name}' is not in progress."


def complete_task(db: Session, name: str):
    """Completes a task and logs its total duration."""
    task = find_task(db, name)
    if not task:
        return "Task not found."

    now = datetime.datetime.now()
    if getattr(task, "start_time", None):
        task.time_spent += (now - task.start_time).total_seconds()
    task.status = "completed"
    task.end_time = now
    db.commit()

    # Save to efficiency metrics table
    save_calculation(db, "Execution Speed", task.time_spent)
    return f"✅ Completed task: {task.task_name} (Total: {task.time_spent / 3600:.2f} hrs)"


# ----------------------------
# Recurrence + Reminder Threads
# ----------------------------

def check_reminders(db: Session):
    """Checks tasks with reminders and prints alerts."""
    while True:
        now = datetime.now()
        tasks = db.query(Task).all()
        for t in tasks:
            if getattr(t, "reminder_time", None):
                if now >= t.reminder_time and t.status != "completed":
                    print(f"🔔 Reminder: Task '{t.task_name}' is due soon!")
                    t.reminder_time = None
                    db.commit()
        time.sleep(60)


def handle_recurrence(*args, **kwargs):
    """Runs the recurrence logic in its own independent DB session."""
    db = SessionLocal()
    try:
        print("[Recurrence] Checking completed tasks for recurrence...")
        tasks = db.query(Task).filter(Task.status == "completed").all()
        for task in tasks:
            print(f"Recurring task detected: {task.name}")
        db.commit()
        print("[Recurrence] Cycle complete.")
    except Exception as e:
        print(f"[Recurrence Error] {e}")
        db.rollback()
    finally:
        db.close()
