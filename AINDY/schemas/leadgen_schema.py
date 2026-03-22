from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class LeadGenItem(BaseModel):
    company: str
    url: str
    fit_score: Optional[float] = None
    intent_score: Optional[float] = None
    data_quality_score: Optional[float] = None
    overall_score: Optional[float] = None
    reasoning: Optional[str] = None
    search_score: Optional[float] = None
    created_at: Optional[datetime] = None


class LeadGenResponse(BaseModel):
    query: str
    count: int
    results: List[LeadGenItem]
