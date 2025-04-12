from pydantic import BaseModel
from typing import List 
from models import (
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
    ai_productivity_boost: List[AIProductivityBoostInput] = []
    lost_potential: List[LostPotentialInput] = []
    decision_efficiency: List[DecisionEfficiencyInput] = []
    tasks: List[TaskInput] = []
    engagements: List[EngagementInput] = []
    ai_efficiencies: List[AIEfficiencyInput] = []
    impacts: List[ImpactInput] = []
    efficiencies: List[EfficiencyInput] = []
    revenue_scalings: List[RevenueScalingInput] = []
    execution_speeds: List[ExecutionSpeedInput] = []
    attention_values: List[AttentionValueInput] = []
    engagement_rates: List[EngagementRateInput] = []
    business_growths: List[BusinessGrowthInput] = []
    monetization_efficiencies: List[MonetizationEfficiencyInput] = []