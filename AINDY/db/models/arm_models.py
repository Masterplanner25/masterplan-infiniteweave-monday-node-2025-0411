# db/models/arm_models.py
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from db.database import Base


# -------------------------------------------------------
#  ARMRun — high-level record of each reasoning session
# -------------------------------------------------------
class ARMRun(Base):
    """
    Tracks a single ARM reasoning or code-generation event.
    Includes runtime metrics and short result summary.
    """

    __tablename__ = "arm_runs"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String, nullable=False)
    operation = Column(String, default="analysis")  # analysis | generation | audit
    result_summary = Column(Text)
    runtime = Column(Float)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    logs = relationship("ARMLog", back_populates="run", cascade="all, delete-orphan")


# -------------------------------------------------------
#  ARMLog — granular event & audit messages
# -------------------------------------------------------
class ARMLog(Base):
    """
    Low-level logs emitted by the ARM during reasoning.
    Useful for debugging, audit trails, and traceability.
    """

    __tablename__ = "arm_logs"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("arm_runs.id"))
    timestamp = Column(DateTime, default=func.now())
    level = Column(String, default="INFO")
    message = Column(Text)

    # Relationship back-reference
    run = relationship("ARMRun", back_populates="logs")


# -------------------------------------------------------
#  ARMConfig — persistent configuration parameters
# -------------------------------------------------------
class ARMConfig(Base):
    """
    Stores adjustable DeepSeek ARM configuration parameters.
    Each update is versioned so historical tuning is preserved.
    """

    __tablename__ = "arm_configs"

    id = Column(Integer, primary_key=True, index=True)
    parameter = Column(String, nullable=False)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime, default=func.now())
