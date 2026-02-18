# schemas/freelance.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class FreelanceOrderCreate(BaseModel):
    client_name: str
    client_email: str
    service_type: str
    project_details: Optional[str] = None
    price: Optional[float] = 0.0


class FreelanceOrderResponse(BaseModel):
    id: int
    client_name: str
    client_email: str
    service_type: str
    project_details: Optional[str]
    ai_output: Optional[str]
    price: float
    status: str
    created_at: datetime

    class Config:
        orm_mode = True


class FeedbackCreate(BaseModel):
    order_id: int
    rating: Optional[int]
    feedback_text: Optional[str]


class FeedbackResponse(BaseModel):
    id: int
    order_id: int
    rating: Optional[int]
    feedback_text: Optional[str]
    ai_summary: Optional[str]
    created_at: datetime

    class Config:
        orm_mode = True


class RevenueMetricsResponse(BaseModel):
    id: int
    date: datetime
    total_revenue: float
    avg_execution_time: Optional[float]
    income_efficiency: Optional[float]
    ai_productivity_boost: Optional[float]

    class Config:
        orm_mode = True
