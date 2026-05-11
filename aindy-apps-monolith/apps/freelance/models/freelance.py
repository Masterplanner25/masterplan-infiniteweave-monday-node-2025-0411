# db/models/freelance.py

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, JSON, Index, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from AINDY.db.database import Base


class FreelanceOrder(Base):
    __tablename__ = "freelance_orders"
    __table_args__ = (
        Index(
            "ux_freelance_orders_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_name = Column(String, nullable=False)
    client_email = Column(String, nullable=False)
    service_type = Column(String, nullable=False)
    project_details = Column(Text, nullable=True)
    ai_output = Column(Text, nullable=True)
    price = Column(Float, nullable=False, default=0.0)
    status = Column(String, default="pending")
    masterplan_id = Column(Integer, ForeignKey("master_plans.id"), nullable=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True, index=True)
    automation_log_id = Column(String, ForeignKey("automation_logs.id"), nullable=True, index=True)
    automation_type = Column(String, nullable=True)
    automation_config = Column(JSON, nullable=True)
    delivery_type = Column(String, nullable=True, default="manual")
    delivery_config = Column(JSON, nullable=True)
    delivery_status = Column(String, nullable=True, default="pending")
    external_response = Column(JSON, nullable=True)
    stripe_payment_intent_id = Column(String, nullable=True, index=True)
    stripe_payment_link_id = Column(String, nullable=True, index=True)
    payment_confirmed_at = Column(DateTime, nullable=True)
    payment_status = Column(String, nullable=True, default="none")
    refund_id = Column(String, nullable=True)
    refunded_at = Column(DateTime, nullable=True)
    refund_reason = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True, index=True)
    stripe_customer_id = Column(String, nullable=True)
    subscription_status = Column(String, nullable=True)
    subscription_period_end = Column(DateTime, nullable=True)
    idempotency_key = Column(String(255), nullable=True)
    delivery_quality_score = Column(Float, nullable=True)
    time_to_completion_seconds = Column(Float, nullable=True)
    income_efficiency = Column(Float, nullable=True)
    started_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class ClientFeedback(Base):
    __tablename__ = "client_feedback"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("freelance_orders.id", ondelete="CASCADE"))
    rating = Column(Integer, nullable=True)
    feedback_text = Column(Text, nullable=True)
    ai_summary = Column(Text, nullable=True)
    success_signal = Column(Float, nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=func.now())

    order = relationship("FreelanceOrder", backref="feedback")


class RevenueMetrics(Base):
    __tablename__ = "revenue_metrics"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, default=func.now())
    total_revenue = Column(Float, nullable=False, default=0.0)
    avg_execution_time = Column(Float, nullable=True)
    income_efficiency = Column(Float, nullable=True)
    ai_productivity_boost = Column(Float, nullable=True)
    avg_delivery_quality = Column(Float, nullable=True)


class PaymentRecord(Base):
    __tablename__ = "freelance_payment_records"
    __table_args__ = (
        Index(
            "ux_freelance_payment_records_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("freelance_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    stripe_payment_intent_id = Column(String, nullable=True, index=True)
    stripe_payment_link_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="pending")
    confirmed_at = Column(DateTime, nullable=True)
    idempotency_key = Column(String(255), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    order = relationship("FreelanceOrder", backref="payment_records")


class RefundRecord(Base):
    __tablename__ = "freelance_refund_records"
    __table_args__ = (
        Index(
            "ux_freelance_refund_records_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("freelance_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    stripe_payment_intent_id = Column(String, nullable=True, index=True)
    stripe_refund_id = Column(String, nullable=True, index=True)
    reason = Column(String, nullable=True)
    amount_cents = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default="pending")
    processed_at = Column(DateTime, nullable=True)
    idempotency_key = Column(String(255), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    order = relationship("FreelanceOrder", backref="refund_records")


class WebhookEvent(Base):
    __tablename__ = "freelance_webhook_events"
    __table_args__ = (
        Index(
            "ux_freelance_webhook_events_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "ux_freelance_webhook_events_stripe_event_id",
            "stripe_event_id",
            unique=True,
            postgresql_where=text("stripe_event_id IS NOT NULL"),
            sqlite_where=text("stripe_event_id IS NOT NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    stripe_event_id = Column(String(255), nullable=True, index=True)
    event_type = Column(String(100), nullable=True)
    idempotency_key = Column(String(255), nullable=False)
    payload = Column(JSON, nullable=True)
    processing_status = Column(String, nullable=False, default="pending")
    outcome = Column(String(32), nullable=True)
    error = Column(Text, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
