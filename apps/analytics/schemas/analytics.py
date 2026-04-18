from pydantic import BaseModel
from datetime import date
from typing import Optional


class LinkedInRawInput(BaseModel):

    masterplan_id: int

    period_type: str              # daily, weekly, monthly, yearly
    period_start: date
    period_end: date

    scope_type: str               # aggregate or content
    scope_id: Optional[str] = None

    impressions: float
    members_reached: float

    search_appearances: float = 0

    likes: float = 0
    comments: float = 0
    shares: float = 0

    watch_time_minutes: float = 0

    profile_views: float = 0
    link_clicks: float = 0

    follows: float = 0
    new_followers: float = 0

    audience_quality_score: float = 0
