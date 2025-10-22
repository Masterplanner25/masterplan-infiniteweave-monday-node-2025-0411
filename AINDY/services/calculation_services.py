from sqlalchemy.orm import Session
from db.models import (
    TaskInput, EngagementInput, AIEfficiencyInput, ImpactInput, EfficiencyInput,
    RevenueScalingInput, ExecutionSpeedInput, AttentionValueInput, EngagementRateInput,
    BusinessGrowthInput, MonetizationEfficiencyInput, AIProductivityBoostInput,
    LostPotentialInput, DecisionEfficiencyInput, CalculationResult
)

def save_calculation(db: Session, metric_name: str, result_value: float):
    db_result = CalculationResult(metric_name=metric_name, result_value=result_value)
    db.add(db_result)
    db.commit()
    db.refresh(db_result)
    return db_result

def calculate_twr(task: TaskInput):
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
    score = (
        (data.likes * 2) + (data.shares * 3) + (data.comments * 1.5) +
        (data.clicks * 1) + (data.time_on_page * 0.5)
    ) / data.total_views
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
