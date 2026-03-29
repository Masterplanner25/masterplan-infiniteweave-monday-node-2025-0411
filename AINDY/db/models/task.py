from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from db.database import Base


class Task(Base):
    """
    Unified Task Model
    Combines performance metrics (from main.py)
    with scheduling, recurrence, and status fields (from models.py).
    Powers A.I.N.D.Y.’s Execution Engine + Reminder System.
    """
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    # --- Core Task Identity ---
    name = Column(String, nullable=False, index=True)
    category = Column(String, default="general")
    priority = Column(String, default="medium")
    status = Column(String, default="pending")  # pending, in_progress, paused, completed
    masterplan_id = Column(Integer, ForeignKey("master_plans.id"), nullable=True, index=True)
    parent_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True, index=True)
    depends_on = Column(JSON, nullable=False, default=list)
    dependency_type = Column(String, default="hard")
    automation_type = Column(String, nullable=True)
    automation_config = Column(JSON, nullable=True)

    # --- Timing and Scheduling ---
    due_date = Column(DateTime, nullable=True)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    duration = Column(Float, default=0.0)
    scheduled_time = Column(DateTime, nullable=True)
    reminder_time = Column(DateTime, nullable=True)
    recurrence = Column(String, nullable=True)  # daily, weekly, monthly

    # --- Performance & AI Metrics ---
    time_spent = Column(Float, default=0.0)  # in hours
    task_complexity = Column(Integer, default=1)
    skill_level = Column(Integer, default=1)
    ai_utilization = Column(Integer, default=0)
    task_difficulty = Column(Integer, default=1)

    # --- Ownership ---
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    user = relationship("User", back_populates="tasks")
    masterplan = relationship("MasterPlan", backref="tasks")
    parent_task = relationship("Task", remote_side=[id], backref="child_tasks")
