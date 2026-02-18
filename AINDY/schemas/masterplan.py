from pydantic import BaseModel
from datetime import datetime

class MasterPlanCreate(BaseModel):
    version: str
    start_date: datetime
    duration_years: float
    is_origin: bool = False
    is_active: bool = False
     # --- Threshold Configuration ---
    wcu_target: float = 3000
    revenue_target: float = 100000

    books_required: int = 3
    platform_required: bool = True
    studio_required: bool = True
    playbooks_required: int = 2

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