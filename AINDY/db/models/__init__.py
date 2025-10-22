# db.models package initializer
# This allows clean imports like: from db.models import TaskInput

from .models import (
    TaskInput,
    CalculationResult,
    EfficiencyInput,
    EngagementInput,
    AIEfficiencyInput,
    ImpactInput,
    RevenueScalingInput,
    ExecutionSpeedInput,
    AttentionValueInput,
    EngagementRateInput,
    BusinessGrowthInput,
    MonetizationEfficiencyInput,
    AIProductivityBoostInput,
    LostPotentialInput,
    DecisionEfficiencyInput,
)

from .research_results import ResearchResult
from .research_results_schema import ResearchResultCreate, ResearchResultBase

__all__ = [
    "TaskInput",
    "CalculationResult",
    "EfficiencyInput",
    "EngagementInput",
    "AIEfficiencyInput",
    "ImpactInput",
    "RevenueScalingInput",
    "ExecutionSpeedInput",
    "AttentionValueInput",
    "EngagementRateInput",
    "BusinessGrowthInput",
    "MonetizationEfficiencyInput",
    "AIProductivityBoostInput",
    "LostPotentialInput",
    "DecisionEfficiencyInput",
    "ResearchResult",
    "ResearchResultCreate",
    "ResearchResultBase",
]

from .models import DropPointDB, PingDB
__all__.extend(["DropPointDB", "PingDB"])

from .freelance_models import FreelanceOrder, ClientFeedback, RevenueMetrics
from db.models.arm_models import ARMRun, ARMLog, ARMConfig
from .leadgen_model import LeadGenResult

