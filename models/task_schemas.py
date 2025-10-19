# /models/task_schemas.py
from pydantic import BaseModel
from typing import Optional, List

class TaskCreate(BaseModel):
    name: str
    category: Optional[str] = "general"
    priority: Optional[str] = "medium"
    due_date: Optional[str] = None
    dependencies: Optional[List[str]] = []
    scheduled_time: Optional[str] = None
    reminder_time: Optional[str] = None
    recurrence: Optional[str] = None  # "daily", "weekly", "monthly"

class TaskAction(BaseModel):
    name: str
