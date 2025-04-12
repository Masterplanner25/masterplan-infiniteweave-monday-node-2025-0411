from batch import BatchInput
from services import (  # Import your calculation functions from services.py
    calculate_twr,
    calculate_effort,
    calculate_productivity,
    calculate_virality,
    calculate_engagement_score,
    calculate_ai_efficiency,
    calculate_impact_score,
    income_efficiency,
    revenue_scaling,
    execution_speed,
    attention_value,
    engagement_rate,
    business_growth,
    monetization_efficiency,
    ai_productivity_boost,
    lost_potential,
    decision_efficiency,
)

def process_batch(batch_data: BatchInput):
    results = {}
    if batch_data.ai_productivity_boost:
        results["AI Productivity Boost"] = [ai_productivity_boost(data) for data in batch_data.ai_productivity_boost]
    if batch_data.lost_potential:
        results["Lost Potential"] = [lost_potential(data) for data in batch_data.lost_potential]
    if batch_data.decision_efficiency:
        results["Decision Efficiency"] = [decision_efficiency(data) for data in batch_data.decision_efficiency]
    if batch_data.tasks:
        results["Tasks"] = [calculate_twr(data) for data in batch_data.tasks] # Or other task calculations
    if batch_data.engagements:
        results["Engagements"] = [calculate_engagement_score(data) for data in batch_data.engagements]
    if batch_data.ai_efficiencies:
        results["AI Efficiencies"] = [calculate_ai_efficiency(data) for data in batch_data.ai_efficiencies]
    if batch_data.impacts:
        results["Impacts"] = [calculate_impact_score(data) for data in batch_data.impacts]
    if batch_data.efficiencies:
        results["Efficiencies"] = [income_efficiency(data) for data in batch_data.efficiencies]
    if batch_data.revenue_scalings:
        results["Revenue Scalings"] = [revenue_scaling(data) for data in batch_data.revenue_scalings]
    if batch_data.execution_speeds:
        results["Execution Speeds"] = [execution_speed(data) for data in batch_data.execution_speeds]
    if batch_data.attention_values:
        results["Attention Values"] = [attention_value(data) for data in batch_data.attention_values]
    if batch_data.engagement_rates:
        results["Engagement Rates"] = [engagement_rate(data) for data in batch_data.engagement_rates]
    if batch_data.business_growths:
        results["Business Growths"] = [business_growth(data) for data in batch_data.business_growths]
    if batch_data.monetization_efficiencies:
        results["Monetization Efficiencies"] = [monetization_efficiency(data) for data in batch_data.monetization_efficiencies]
    return results