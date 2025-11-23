# /services/task_services.py
import time
from sqlalchemy.orm import Session
from datetime import datetime
from db.database import SessionLocal
from db.models.models import Task
from services.calculation_services import save_calculation, calculate_twr, TaskInput
from db.mongo_setup import get_mongo_client

# ----------------------------
# Core CRUD Task Management
# ----------------------------

def create_task(db: Session, name: str, category="general", priority="medium", due_date=None, 
                dependencies=None, scheduled_time=None, reminder_time=None, recurrence=None):
    """Creates a new task entry in the database."""
    task = Task(
        name=name,  # ✅ Fixed column name
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
    print(f"✅ Created task: {task.name}")
    return task


def find_task(db: Session, name: str):
    """Find a task by name."""
    # ✅ Fixed column name here too
    return db.query(Task).filter(Task.name == name).first()


def start_task(db: Session, name: str):
    """Start tracking time for a task."""
    task = find_task(db, name)
    if not task:
        return f"❌ Task '{name}' not found."

    if not getattr(task, "start_time", None):
        task.start_time = datetime.now()
        task.status = "in_progress"
        db.commit()
        return f"▶️ Started task: {task.name}"
    return f"⚠️ Task '{name}' already started."


def pause_task(db: Session, name: str):
    """Pause an in-progress task."""
    task = find_task(db, name)
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


def complete_task(db: Session, name: str):
    """
    Mark task complete, log duration, AND update Social Velocity.
    """
    task = find_task(db, name)
    if not task:
        return "❌ Task not found."

    now = datetime.now()
    if getattr(task, "start_time", None):
        task.time_spent += (now - task.start_time).total_seconds()
    
    task.status = "completed"
    task.end_time = now
    db.commit()

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
    
    save_calculation(db, "Time-to-Wealth Ratio", twr_score)
    save_calculation(db, "Execution Speed", task.time_spent)

    # Update Social Velocity
    try:
        mongo = get_mongo_client()
        db_mongo = mongo["aindy_social_layer"]
        profiles = db_mongo["profiles"]
        
        profiles.update_one(
            {"username": "me"},
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
        print(f"🚀 [Velocity Engine] Profile updated! TWR impact: {twr_score}")
    except Exception as e:
        print(f"⚠️ [Velocity Engine] Failed to sync with Social Layer: {e}")

    return f"✅ Completed task: {task.name} (TWR: {twr_score:.2f})"

# ----------------------------
# Background / Recurrence Logic
# ----------------------------

def check_reminders():
    while True:
        db = SessionLocal()
        try:
            now = datetime.now()
            tasks = db.query(Task).all()
            for t in tasks:
                if getattr(t, "reminder_time", None):
                    if now >= t.reminder_time and t.status != "completed":
                        print(f"🔔 Reminder: Task '{t.name}' is due soon!")
                        t.reminder_time = None
                        db.commit()
        except Exception as e:
            print(f"[Reminder Error] {e}")
        finally:
            db.close()
        time.sleep(60)

def handle_recurrence():
    while True:
        db = SessionLocal()
        try:
            tasks = db.query(Task).filter(Task.status == "completed").all()
            pass 
        except Exception as e:
            print(f"[Recurrence Error] {e}")
        finally:
            db.close()
        time.sleep(60)