from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, JSON, Text, Date, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from AINDY.db.database import Base



class MasterPlan(Base):
    __tablename__ = "master_plans"
    __table_args__ = (
        Index(
            "uq_masterplan_genesis_session_id",
            "linked_genesis_session_id",
            unique=True,
            postgresql_where=text("linked_genesis_session_id IS NOT NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    start_date = Column(DateTime, nullable=False)
    duration_years = Column(Float, nullable=False)
    target_date = Column(DateTime, nullable=False)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    # Lifecycle status: draft | locked | active | archived
    status = Column(String, nullable=True, default="draft")

    is_active = Column(Boolean, default=False)
    is_origin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    activated_at = Column(DateTime, nullable=True)

    # --- Genesis Structured Data ---
    structure_json = Column(JSON, nullable=True)
    
    # Options: Stable | Accelerated | Aggressive | Reduced
    posture = Column(String, nullable=True)  
    
    version_label = Column(String, nullable=True)
    locked_at = Column(DateTime, nullable=True)

    # Self-referential relationship for parent/child plans
    parent_id = Column(Integer, ForeignKey("master_plans.id"), nullable=True)
    parent = relationship("MasterPlan", remote_side=[id])

    linked_genesis_session_id = Column(Integer, ForeignKey("genesis_sessions.id"), nullable=True)

    # --- Relationships ---
    canonical_metrics = relationship(
        "CanonicalMetricDB",
        backref="masterplan",
        cascade="all, delete-orphan"
    )

    # --- Threshold Configuration ---
    wcu_target = Column(Float, default=3000)
    revenue_target = Column(Float, default=100000)

    books_required = Column(Integer, default=3)
    platform_required = Column(Boolean, default=True)
    studio_required = Column(Boolean, default=True)
    playbooks_required = Column(Integer, default=2)

    # --- Live Progress ---
    total_wcu = Column(Float, default=0)
    gross_revenue = Column(Float, default=0)
    books_published = Column(Integer, default=0)
    platform_live = Column(Boolean, default=False)
    studio_ready = Column(Boolean, default=False)
    active_playbooks = Column(Integer, default=0)

    phase = Column(Integer, default=1)

    # --- Anchor + ETA Projection ---
    anchor_date = Column(DateTime, nullable=True)          # user-declared milestone date
    goal_value = Column(Float, nullable=True)              # e.g. 100000.0 (revenue), 10 (books)
    goal_unit = Column(String, nullable=True)              # e.g. "USD", "books", "tasks"
    goal_description = Column(Text, nullable=True)         # human-readable goal summary

    projected_completion_date = Column(Date, nullable=True)   # ETA computed by eta_service
    current_velocity = Column(Float, nullable=True)           # tasks completed per day (14-day rolling)
    days_ahead_behind = Column(Integer, nullable=True)        # positive=ahead, negative=behind
    eta_last_calculated = Column(DateTime(timezone=True), nullable=True)
    eta_confidence = Column(String, nullable=True)            # "high" | "medium" | "low" | "insufficient_data"


class GenesisSessionDB(Base):
    __tablename__ = "genesis_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)

    status = Column(String, default="active")  # active | paused | synthesized | locked | abandoned

    summarized_state = Column(JSON, nullable=True)

    # Block 1 additions
    synthesis_ready = Column(Boolean, nullable=False, default=False)
    draft_json = Column(JSON, nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
