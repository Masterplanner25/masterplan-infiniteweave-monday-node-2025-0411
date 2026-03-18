# schemas/freelance.py
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class FreelanceOrderCreate(BaseModel):
    client_name: str
    client_email: str
    service_type: str
    project_details: Optional[str] = None
    price: Optional[float] = 0.0


class FreelanceOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_name: str
    client_email: str
    service_type: str
    project_details: Optional[str]
    ai_output: Optional[str]
    price: float
    status: str
    created_at: datetime


class FeedbackCreate(BaseModel):
    order_id: int
    rating: Optional[int]
    feedback_text: Optional[str]


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    rating: Optional[int]
    feedback_text: Optional[str]
    ai_summary: Optional[str]
    created_at: datetime


class RevenueMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: datetime
    total_revenue: float
    avg_execution_time: Optional[float]
    income_efficiency: Optional[float]
    ai_productivity_boost: Optional[float]
