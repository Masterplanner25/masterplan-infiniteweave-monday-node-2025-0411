from pydantic import BaseModel


class TaskInput(BaseModel):
    """Pydantic model for calculating TWR (Time-to-Wealth Ratio)."""
    task_name: str
    time_spent: float  # In hours
    task_complexity: int  # 1-5 scale
    skill_level: int  # 1-5 scale
    ai_utilization: int  # 1-5 scale
    task_difficulty: int  # 1-5 scale



class EngagementInput(BaseModel):
    """Tracks user interactions with content to measure engagement quality."""
    likes: int
    shares: int
    comments: int
    clicks: int
    time_on_page: float  # In seconds
    total_views: int



class AIEfficiencyInput(BaseModel):
    """Measures social media engagement performance based on user actions."""

    ai_contributions: int  # Number of AI-generated outputs
    human_contributions: int  # Number of human edits or contributions
    total_tasks: int  # Total tasks completed with AI assistance




class ImpactInput(BaseModel):
    """Calculates reach, engagement, and conversion to determine content impact."""

    reach: int  # Total audience reached
    engagement: int  # Number of interactions (likes, shares, comments)
    conversion: int  # Actions taken (sign-ups, purchases, etc.)




class EfficiencyInput(BaseModel):
    """Quantifies how efficiently effort, time, and capital are turned into output."""

    focused_effort: float
    ai_utilization: float
    time: float
    capital: float

  


class RevenueScalingInput(BaseModel):
    """Estimates revenue potential based on content scale, AI leverage, and audience engagement."""

    ai_leverage: float
    content_distribution: float
    time: float
    audience_engagement: float



class ExecutionSpeedInput(BaseModel):
    """Calculates task completion speed based on automation and systemization."""

    ai_automations: float
    systemized_workflows: float
    decision_lag: float



class AttentionValueInput(BaseModel):
    """Evaluates attention generated through content and platform presence over time."""

    content_output: float
    platform_presence: float
    time: float



class EngagementRateInput(BaseModel):
    """Determines audience engagement by comparing interactions to total views."""

    total_interactions: float
    total_views: float



class BusinessGrowthInput(BaseModel):
    """Measures net business growth by subtracting expenses and adjusting for scaling friction."""

    revenue: float
    expenses: float
    scaling_friction: float



class MonetizationEfficiencyInput(BaseModel):
    """Tracks revenue per audience member to assess monetization effectiveness."""

    total_revenue: float
    audience_size: float



class AIProductivityBoostInput(BaseModel):
    """Measures productivity gain from AI assistance compared to manual output."""
    tasks_with_ai: float
    tasks_without_ai: float
    time_saved: float



class LostPotentialInput(BaseModel):
    """Quantifies the cost of inaction by comparing missed opportunity delays to gains."""

    missed_opportunities: float
    time_delayed: float
    gains_from_action: float




class DecisionEfficiencyInput(BaseModel):
    """Evaluates how efficiently decisions are made using automation versus manual inputs."""
    automated_decisions: float
    manual_decisions: float
    processing_time: float


class ViralityInput(BaseModel):
    share_rate: float
    engagement_rate: float
    conversion_rate: float
    time_factor: float    