from pydantic import BaseModel, Field
from datetime import datetime


class ResearchResultBase(BaseModel):
    query: str
    summary: str


class ResearchResultCreate(ResearchResultBase):
    """Schema used when creating a new research result."""
    pass


class ResearchResultResponse(ResearchResultBase):
    """Schema used when returning a research result to the frontend."""
    id: int
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True  # ✅ Pydantic v2 replacement for orm_mode
