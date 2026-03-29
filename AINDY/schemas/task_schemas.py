# /models/task_schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List


class TaskDependency(BaseModel):
    task_id: int
    dependency_type: str = "hard"


class TaskCreate(BaseModel):
    name: str
    category: Optional[str] = "general"
    priority: Optional[str] = "medium"
    due_date: Optional[str] = None
    masterplan_id: Optional[int] = None
    parent_task_id: Optional[int] = None
    dependency_type: Optional[str] = "hard"
    dependencies: List[TaskDependency] = Field(default_factory=list)
    automation_type: Optional[str] = None
    automation_config: Optional[dict] = None
    scheduled_time: Optional[str] = None
    reminder_time: Optional[str] = None
    recurrence: Optional[str] = None  # "daily", "weekly", "monthly"

class TaskAction(BaseModel):
    name: str
