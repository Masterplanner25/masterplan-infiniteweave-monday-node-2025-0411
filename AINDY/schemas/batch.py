from pydantic import BaseModel, Field
from typing import List

from schemas.analytics_inputs import (
    AIProductivityBoostInput,
    LostPotentialInput,
    DecisionEfficiencyInput,
    TaskInput,
    EngagementInput,
    AIEfficiencyInput,
    ImpactInput,
    EfficiencyInput,
    RevenueScalingInput,
    ExecutionSpeedInput,
    AttentionValueInput,
    EngagementRateInput,
    BusinessGrowthInput,
    MonetizationEfficiencyInput,
)

class BatchInput(BaseModel):
    ai_productivity_boost: List[AIProductivityBoostInput] = Field(default_factory=list)
    lost_potential: List[LostPotentialInput] = Field(default_factory=list)
    decision_efficiency: List[DecisionEfficiencyInput] = Field(default_factory=list)
    tasks: List[TaskInput] = Field(default_factory=list)
    engagements: List[EngagementInput] = Field(default_factory=list)
    ai_efficiencies: List[AIEfficiencyInput] = Field(default_factory=list)
    impacts: List[ImpactInput] = Field(default_factory=list)
    efficiencies: List[EfficiencyInput] = Field(default_factory=list)
    revenue_scalings: List[RevenueScalingInput] = Field(default_factory=list)
    execution_speeds: List[ExecutionSpeedInput] = Field(default_factory=list)
    attention_values: List[AttentionValueInput] = Field(default_factory=list)
    engagement_rates: List[EngagementRateInput] = Field(default_factory=list)
    business_growths: List[BusinessGrowthInput] = Field(default_factory=list)
    monetization_efficiencies: List[MonetizationEfficiencyInput] = Field(default_factory=list)
