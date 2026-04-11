import logging
from sqlalchemy.orm import Session
from AINDY.db.models import CalculationResult

logger = logging.getLogger(__name__)

# C++ kernel — high-performance vector math for the Infinity Algorithm.
# Falls back to pure Python if the compiled extension is not available
# (e.g., fresh clone before maturin build, CI without Rust toolchain).
try:
    from memory_bridge_rs import (
        semantic_similarity,
        weighted_dot_product as _cpp_weighted_dot,
    )
    _USE_CPP_KERNEL = True
except ImportError:
    import math
    _USE_CPP_KERNEL = False

    def semantic_similarity(a, b):
        """Pure Python fallback for cosine similarity."""
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(y * y for y in b))
        denom = mag_a * mag_b
        return dot / denom if denom > 1e-15 else 0.0

    def _cpp_weighted_dot(values, weights):
        """Pure Python fallback for weighted dot product."""
        return sum(v * w for v, w in zip(values, weights))

# Pydantic schemas
from AINDY.schemas.analytics_inputs import (
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
    AIProductivityBoostInput,
    LostPotentialInput,
    DecisionEfficiencyInput,
)



def save_calculation(
    db: Session,
    metric_name: str,
    value: float,
    user_id: str = None,
):
    from datetime import datetime
    try:
        result = CalculationResult(
            metric_name=metric_name,
            result_value=value,
            user_id=user_id,
            created_at=datetime.utcnow(),
        )
        db.add(result)
        db.commit()
        db.refresh(result)
        logger.info("Saved metric: %s (ID: %s)", metric_name, result.id)
        return result
    except Exception as e:
        db.rollback()
        logger.warning("save_calculation failed for %s: %s", metric_name, e)
        return None

def calculate_twr(task: TaskInput):
    # Guard: task_difficulty=0 causes ZeroDivisionError.
    # Raise ValueError so the route can return 422 instead of 500.
    # See TECH_DEBT.md §9.
    if task.task_difficulty == 0:
        raise ValueError("task_difficulty must be greater than zero")
    LHI = (task.time_spent * task.task_complexity * task.skill_level)
    TWR = (LHI * task.ai_utilization * task.time_spent) / task.task_difficulty
    return TWR

def calculate_effort(task: TaskInput):
    return (task.time_spent * task.task_complexity) / (task.skill_level + task.ai_utilization + 1)

def calculate_productivity(task: TaskInput):
    return (task.ai_utilization * task.skill_level) / (task.time_spent + 1)

def calculate_virality(share_rate: float, engagement_rate: float, conversion_rate: float, time_factor: float):
    return (share_rate * engagement_rate * conversion_rate) / (time_factor + 1)

def calculate_engagement_score(data: EngagementInput):
    if data.total_views == 0:
        return 0
    # Infinity Algorithm engagement score is a weighted dot product:
    #   [likes, shares, comments, clicks, time_on_page] · [2, 3, 1.5, 1, 0.5]
    # Routed through C++ kernel when available.
    interactions = [float(data.likes), float(data.shares), float(data.comments),
                    float(data.clicks), float(data.time_on_page)]
    weights = [2.0, 3.0, 1.5, 1.0, 0.5]
    score = _cpp_weighted_dot(interactions, weights) / data.total_views
    return round(score, 2)

def calculate_ai_efficiency(data: AIEfficiencyInput):
    if data.total_tasks == 0:
        return 0
    score = (data.ai_contributions / (data.human_contributions + 1)) * (data.total_tasks / 10)
    return round(score, 2)

def calculate_impact_score(data: ImpactInput):
    if data.reach == 0:
        return 0
    score = (data.engagement / data.reach) * 100 + (data.conversion * 2)
    return round(score, 2)

def income_efficiency(eff: EfficiencyInput):
    return (eff.focused_effort * eff.ai_utilization) / (eff.time + eff.capital)

def revenue_scaling(rs: RevenueScalingInput):
    return ((rs.ai_leverage + rs.content_distribution) / rs.time) * rs.audience_engagement

def execution_speed(es: ExecutionSpeedInput):
    return (es.ai_automations + es.systemized_workflows) / es.decision_lag

def attention_value(input_data: AttentionValueInput):
    return (input_data.content_output * input_data.platform_presence) / input_data.time

def engagement_rate(input_data: EngagementRateInput):
    return input_data.total_interactions / input_data.total_views

def business_growth(input_data: BusinessGrowthInput):
    return (input_data.revenue - input_data.expenses) / input_data.scaling_friction

def monetization_efficiency(input_data: MonetizationEfficiencyInput):
    return input_data.total_revenue / input_data.audience_size

def ai_productivity_boost(input_data: AIProductivityBoostInput):
    return (input_data.tasks_with_ai - input_data.tasks_without_ai) / input_data.time_saved

def lost_potential(input_data: LostPotentialInput):
    return (input_data.missed_opportunities * input_data.time_delayed) - input_data.gains_from_action

def decision_efficiency(input_data: DecisionEfficiencyInput):
    return input_data.automated_decisions / (input_data.manual_decisions + input_data.processing_time)

