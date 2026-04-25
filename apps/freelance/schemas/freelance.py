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
    masterplan_id: Optional[int] = None
    task_id: Optional[int] = None
    automation_type: Optional[str] = None
    automation_config: Optional[dict] = None
    delivery_type: Optional[str] = "manual"
    delivery_config: Optional[dict] = None
    auto_generate_delivery: bool = False


class FreelanceDeliveryConfigUpdate(BaseModel):
    delivery_type: Optional[str] = None
    delivery_config: Optional[dict] = None


class RefundRequest(BaseModel):
    reason: Optional[str] = None


class SubscriptionCancelRequest(BaseModel):
    reason: Optional[str] = None


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
    masterplan_id: Optional[int] = None
    task_id: Optional[int] = None
    automation_log_id: Optional[str] = None
    automation_type: Optional[str] = None
    automation_config: Optional[dict] = None
    delivery_type: Optional[str] = None
    delivery_config: Optional[dict] = None
    delivery_status: Optional[str] = None
    external_response: Optional[dict] = None
    delivery_quality_score: Optional[float] = None
    time_to_completion_seconds: Optional[float] = None
    income_efficiency: Optional[float] = None
    started_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    created_at: datetime


class RefundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: int
    refund_id: str
    status: str
    payment_status: str
    refunded_at: datetime
    reason: Optional[str] = None
    amount_cents: Optional[int] = None


class SubscriptionStatusResponse(BaseModel):
    order_id: int
    status: str
    subscription_status: Optional[str] = None
    subscription_period_end: Optional[datetime] = None
    reason: Optional[str] = None


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
    success_signal: Optional[float]
    created_at: datetime


class RevenueMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: datetime
    total_revenue: float
    avg_execution_time: Optional[float]
    income_efficiency: Optional[float]
    ai_productivity_boost: Optional[float]
    avg_delivery_quality: Optional[float]
