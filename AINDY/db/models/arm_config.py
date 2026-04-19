from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSON

from AINDY.db.database import Base


class ArmConfig(Base):
    __tablename__ = "arm_config"

    id = Column(String(32), primary_key=True, default="default")
    model = Column(String(128), nullable=False, default="gpt-4o")
    analysis_model = Column(String(128), nullable=False, default="gpt-4o")
    generation_model = Column(String(128), nullable=False, default="gpt-4o")
    temperature = Column(Float, nullable=False, default=0.2)
    generation_temperature = Column(Float, nullable=False, default=0.4)
    max_chunk_tokens = Column(Integer, nullable=False, default=4000)
    max_output_tokens = Column(Integer, nullable=False, default=2000)
    retry_limit = Column(Integer, nullable=False, default=3)
    retry_delay_seconds = Column(Integer, nullable=False, default=2)
    max_file_size_bytes = Column(Integer, nullable=False, default=100_000)
    allowed_extensions = Column(JSON, nullable=False, default=list)
    task_complexity_default = Column(Integer, nullable=False, default=3)
    task_urgency_default = Column(Integer, nullable=False, default=5)
    resource_cost_default = Column(Integer, nullable=False, default=2)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
