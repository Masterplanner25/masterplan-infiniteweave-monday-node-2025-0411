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
from apps.analytics.user_score import KPI_WEIGHTS, ScoreHistory, UserScore

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
    "LostPotential",
    "MonetizationEfficiency",
    "RevenueScaling",
    "ScoreHistory",
    "ScoreSnapshotDB",
    "UserScore",
]


def register_models() -> None:
    return None
