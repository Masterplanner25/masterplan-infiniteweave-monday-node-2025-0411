from pydantic import BaseModel
from datetime import datetime

class MasterPlanInput(BaseModel):
    name: str
    start_date: datetime
    duration_years: int

    wcu_target: float
    revenue_target: float

    books_required: int
    platform_required: bool
    studio_required: bool
    playbooks_required: int
