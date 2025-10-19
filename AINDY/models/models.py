from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Float, DateTime, func
from config import Base  
from seo import SEOInput, MetaInput
from sqlalchemy import Column, String, DateTime, Text, ForeignKey

class CalculationResult(Base):
    """SQLAlchemy model for storing calculated metric results."""

    __tablename__ = "calculation_results"

    id = Column(Integer, primary_key=True, index=True)
    metric_name = Column(String, index=True)
    result_value = Column(Float)
    created_at = Column(DateTime, default=func.now())


class TaskInput(BaseModel):
    """Pydantic model for calculating TWR (Time-to-Wealth Ratio)."""
    task_name: str
    time_spent: float  # In hours
    task_complexity: int  # 1-5 scale
    skill_level: int  # 1-5 scale
    ai_utilization: int  # 1-5 scale
    task_difficulty: int  # 1-5 scale


from pydantic import BaseModel


class EngagementInput(BaseModel):
    """Tracks user interactions with content to measure engagement quality."""
    likes: int
    shares: int
    comments: int
    clicks: int
    time_on_page: float  # In seconds
    total_views: int


from pydantic import BaseModel


class AIEfficiencyInput(BaseModel):
    """Measures social media engagement performance based on user actions."""

    ai_contributions: int  # Number of AI-generated outputs
    human_contributions: int  # Number of human edits or contributions
    total_tasks: int  # Total tasks completed with AI assistance


from pydantic import BaseModel


class ImpactInput(BaseModel):
    """Calculates reach, engagement, and conversion to determine content impact."""

    reach: int  # Total audience reached
    engagement: int  # Number of interactions (likes, shares, comments)
    conversion: int  # Actions taken (sign-ups, purchases, etc.)


from pydantic import BaseModel


class EfficiencyInput(BaseModel):
    """Quantifies how efficiently effort, time, and capital are turned into output."""

    focused_effort: float
    ai_utilization: float
    time: float
    capital: float


from pydantic import BaseModel  


class RevenueScalingInput(BaseModel):
    """Estimates revenue potential based on content scale, AI leverage, and audience engagement."""

    ai_leverage: float
    content_distribution: float
    time: float
    audience_engagement: float


from pydantic import BaseModel


class ExecutionSpeedInput(BaseModel):
    """Calculates task completion speed based on automation and systemization."""

    ai_automations: float
    systemized_workflows: float
    decision_lag: float


from pydantic import BaseModel


class AttentionValueInput(BaseModel):
    """Evaluates attention generated through content and platform presence over time."""

    content_output: float
    platform_presence: float
    time: float


from pydantic import BaseModel


class EngagementRateInput(BaseModel):
    """Determines audience engagement by comparing interactions to total views."""

    total_interactions: float
    total_views: float


from pydantic import BaseModel


class BusinessGrowthInput(BaseModel):
    """Measures net business growth by subtracting expenses and adjusting for scaling friction."""

    revenue: float
    expenses: float
    scaling_friction: float


from pydantic import BaseModel


class MonetizationEfficiencyInput(BaseModel):
    """Tracks revenue per audience member to assess monetization effectiveness."""

    total_revenue: float
    audience_size: float


from pydantic import BaseModel


class AIProductivityBoostInput(BaseModel):
    """Measures productivity gain from AI assistance compared to manual output."""
    tasks_with_ai: float
    tasks_without_ai: float
    time_saved: float


from pydantic import BaseModel


class LostPotentialInput(BaseModel):
    """Quantifies the cost of inaction by comparing missed opportunity delays to gains."""

    missed_opportunities: float
    time_delayed: float
    gains_from_action: float


from pydantic import BaseModel


class DecisionEfficiencyInput(BaseModel):
    """Evaluates how efficiently decisions are made using automation versus manual inputs."""
    automated_decisions: float
    manual_decisions: float
    processing_time: float

class DropPointDB(Base):
    __tablename__ = "drop_points"
    id = Column(String, primary_key=True, index=True)
    title = Column(String)
    platform = Column(String)
    url = Column(String, nullable=True)
    date_dropped = Column(DateTime)
    core_themes = Column(Text)
    tagged_entities = Column(Text)
    intent = Column(String)

class PingDB(Base):
    __tablename__ = "pings"
    id = Column(String, primary_key=True, index=True)
    drop_point_id = Column(String, ForeignKey("drop_points.id"))
    ping_type = Column(String)
    source_platform = Column(String)
    date_detected = Column(DateTime)
    connection_summary = Column(Text, nullable=True)
    external_url = Column(String, nullable=True)
    reaction_notes = Column(Text, nullable=True)

# --- Task Model for Task Services ---
from sqlalchemy import Boolean, ForeignKey
from sqlalchemy.orm import relationship

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
