import uuid
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from AINDY.db.database import Base


# -------------------------------------------------------
#  AnalysisResult — full audit record for each ARM analysis
# -------------------------------------------------------
class AnalysisResult(Base):
    """
    Stores the complete record of each ARM reasoning analysis session.
    Supports audit trails, Infinity Algorithm metrics, and replay.
    """

    __tablename__ = "analysis_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    file_path = Column(String)
    file_type = Column(String)
    analysis_type = Column(String, default="analyze")   # analyze | generate | audit
    prompt_used = Column(Text)
    model_used = Column(String)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    execution_seconds = Column(Float)
    result_summary = Column(Text)
    result_full = Column(Text)
    task_priority = Column(Float)                        # Infinity Algorithm TP score
    status = Column(String, default="success")           # success | failed | blocked
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship — one analysis can spawn many code generations
    generations = relationship(
        "CodeGeneration", back_populates="analysis", cascade="all, delete-orphan"
    )


# -------------------------------------------------------
#  CodeGeneration — record for each code gen / refactor
# -------------------------------------------------------
class CodeGeneration(Base):
    """
    Stores every code generation or refactoring operation performed by ARM.
    Links back to the analysis session that preceded it (optional).
    """

    __tablename__ = "code_generations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    analysis_id = Column(
        UUID(as_uuid=True),
        ForeignKey("analysis_results.id", ondelete="SET NULL"),
        nullable=True,
    )
    generation_type = Column(String, default="generate")  # refactor | generate | explain
    original_code = Column(Text)
    generated_code = Column(Text)
    language = Column(String)
    model_used = Column(String)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    execution_seconds = Column(Float)
    quality_notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship back to analysis
    analysis = relationship("AnalysisResult", back_populates="generations")


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
