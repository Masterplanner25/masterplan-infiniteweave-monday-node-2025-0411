from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime


class ResearchResultBase(BaseModel):
    query: str
    summary: str


class ResearchResultCreate(ResearchResultBase):
    """Schema used when creating a new research result."""
    pass


class ResearchResultResponse(ResearchResultBase):
    """Schema used when returning a research result to the frontend."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
