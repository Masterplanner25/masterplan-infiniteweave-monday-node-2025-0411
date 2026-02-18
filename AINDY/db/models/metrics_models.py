from sqlalchemy import Column, Integer, Float, String, Date, DateTime, ForeignKey, UniqueConstraint
from db.database import Base
from datetime import datetime


class Engagement(Base):
    __tablename__ = "engagements"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    likes = Column(Integer)
    shares = Column(Integer)
    comments = Column(Integer)
    clicks = Column(Integer)
    time_on_page = Column(Float)
    total_views = Column(Integer)
    # Add other engagement-related columns

class AIEfficiency(Base):
    __tablename__ = "ai_efficiencies"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    ai_contributions = Column(Integer)
    human_contributions = Column(Integer)
    total_tasks = Column(Integer)
    # Add other AI efficiency columns

class Impact(Base):
    __tablename__ = "impacts"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    reach = Column(Integer)
    engagement = Column(Integer)
    conversion = Column(Integer)
    # Add other impact-related columns

class Efficiency(Base):
    __tablename__ = "efficiencies"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    focused_effort = Column(Float)
    ai_utilization = Column(Float)
    time = Column(Float)
    capital = Column(Float)
    # Add other efficiency columns

class RevenueScaling(Base):
    __tablename__ = "revenue_scalings"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    ai_leverage = Column(Float)
    content_distribution = Column(Float)
    time = Column(Float)
    audience_engagement = Column(Float)
    # Add other revenue scaling columns

class ExecutionSpeed(Base):
    __tablename__ = "execution_speeds"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    ai_automations = Column(Float)
    systemized_workflows = Column(Float)
    decision_lag = Column(Float)
    # Add other execution speed columns

class AttentionValue(Base):
    __tablename__ = "attention_values"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    content_output = Column(Float)
    platform_presence = Column(Float)
    time = Column(Float)
    # Add other attention value columns

class EngagementRate(Base):
    __tablename__ = "engagement_rates"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    total_interactions = Column(Float)
    total_views = Column(Integer)
    # Add other engagement rate columns

class BusinessGrowth(Base):
    __tablename__ = "business_growths"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    revenue = Column(Float)
    expenses = Column(Float)
    scaling_friction = Column(Float)
    # Add other business growth columns

class MonetizationEfficiency(Base):
    __tablename__ = "monetization_efficiencies"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    total_revenue = Column(Float)
    audience_size = Column(Float)
    # Add other monetization efficiency columns

class AIProductivityBoost(Base):
    __tablename__ = "ai_productivity_boosts"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    tasks_with_ai = Column(Float)
    tasks_without_ai = Column(Float)
    time_saved = Column(Float)
    # Add other AI productivity boost columns

class LostPotential(Base):
    __tablename__ = "lost_potentials"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    missed_opportunities = Column(Float)
    time_delayed = Column(Float)
    gains_from_action = Column(Float)
    # Add other lost potential columns

class DecisionEfficiency(Base):
    __tablename__ = "decision_efficiencies"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    automated_decisions = Column(Float)
    manual_decisions = Column(Float)
    processing_time = Column(Float)
    # Add other decision efficiency columns

class CanonicalMetricDB(Base):
    __tablename__ = "canonical_metrics"

    __table_args__ = (
        UniqueConstraint(
            "masterplan_id",
            "platform",
            "scope_type",
            "scope_id",
            "period_type",
            "period_start",
            name="uq_canonical_period_scope"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    # --- RELATIONSHIPS ---
    masterplan_id = Column(Integer, ForeignKey("master_plans.id"), nullable=False)
    user_id = Column(Integer, nullable=True)

    # --- CONTEXT ---
    platform = Column(String)
    scope_type = Column(String)
    scope_id = Column(String, nullable=True)

    period_type = Column(String)
    period_start = Column(Date)
    period_end = Column(Date)

    created_at = Column(DateTime, default=datetime.utcnow)

    # --- RAW TOTALS ---
    passive_visibility = Column(Float)
    active_discovery = Column(Float)
    unique_reach = Column(Float)
    interaction_volume = Column(Float)
    deep_attention_units = Column(Float)
    intent_signals = Column(Float)
    conversion_events = Column(Float)
    growth_velocity = Column(Float)
    audience_quality_score = Column(Float)

    # --- DERIVED RATES ---
    interaction_rate = Column(Float)
    attention_rate = Column(Float)
    intent_rate = Column(Float)
    conversion_rate = Column(Float)
    discovery_ratio = Column(Float)
    growth_rate = Column(Float)