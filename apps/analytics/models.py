"""Analytics app ORM models."""

from apps.analytics.calculation import CalculationResult
from apps.analytics.metrics_models import (
    AIEfficiency,
    AIProductivityBoost,
    AttentionValue,
    BusinessGrowth,
    CanonicalMetricDB,
    DecisionEfficiency,
    Efficiency,
    Engagement,
    EngagementRate,
    ExecutionSpeed,
    Impact,
    LostPotential,
    MonetizationEfficiency,
    RevenueScaling,
)
from apps.analytics.score_snapshot import ScoreSnapshotDB
from apps.analytics.user_score import (
    KPI_WEIGHTS,
    KPI_WEIGHT_LEARNING_RATE,
    KPI_WEIGHT_MAX,
    KPI_WEIGHT_MIN,
    KPI_WEIGHT_MIN_SAMPLES,
    ScoreHistory,
    UserKpiWeights,
    UserPolicyThresholds,
    UserScore,
)

__all__ = [
    "AIEfficiency",
    "AIProductivityBoost",
    "AttentionValue",
    "BusinessGrowth",
    "CalculationResult",
    "CanonicalMetricDB",
    "DecisionEfficiency",
    "Efficiency",
    "Engagement",
    "EngagementRate",
    "ExecutionSpeed",
    "Impact",
    "KPI_WEIGHTS",
    "KPI_WEIGHT_LEARNING_RATE",
    "KPI_WEIGHT_MAX",
    "KPI_WEIGHT_MIN",
    "KPI_WEIGHT_MIN_SAMPLES",
    "LostPotential",
    "MonetizationEfficiency",
    "RevenueScaling",
    "ScoreHistory",
    "ScoreSnapshotDB",
    "UserKpiWeights",
    "UserPolicyThresholds",
    "UserScore",
]


def register_models() -> None:
    return None
