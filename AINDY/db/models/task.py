from sqlalchemy import Column, Integer, String, Float, DateTime
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

    # --- Optional Future Relationships ---
    # user_id = Column(Integer, ForeignKey("users.id"))
    # user = relationship("User", back_populates="tasks")