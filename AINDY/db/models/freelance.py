# db/models/freelance.py

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import relationship
from db.database import Base


class FreelanceOrder(Base):
    __tablename__ = "freelance_orders"

    id = Column(Integer, primary_key=True, index=True)
    client_name = Column(String, nullable=False)
    client_email = Column(String, nullable=False)
    service_type = Column(String, nullable=False)
    project_details = Column(Text, nullable=True)
    ai_output = Column(Text, nullable=True)
    price = Column(Float, nullable=False, default=0.0)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class ClientFeedback(Base):
    __tablename__ = "client_feedback"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("freelance_orders.id", ondelete="CASCADE"))
    rating = Column(Integer, nullable=True)
    feedback_text = Column(Text, nullable=True)
    ai_summary = Column(Text, nullable=True)
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
