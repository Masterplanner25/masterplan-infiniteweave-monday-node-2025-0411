from fastapi import Depends
from sqlalchemy.orm import Session
from config import SessionLocal
from fastapi import APIRouter
from fastapi_cache.decorator import cache


from config import SessionLocal
from models import (
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
    CalculationResult
)
from batch import BatchInput
from calculations import process_batch
from services.calculation_services import (
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
    save_calculation
)

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/calculate_twr")
@cache(expire=60)
async def process_task(task: TaskInput, db: Session = Depends(get_db)):
    twr = calculate_twr(task)
    save_calculation(db, "Time-to-Wealth Ratio", twr)
    return {"task_name": task.task_name, "TWR": twr}

@router.post("/calculate_effort")
@cache(expire=300)
async def process_effort(task: TaskInput, db: Session = Depends(get_db)):
    effort = calculate_effort(task)
    save_calculation(db, "Effort Score", effort)
    return {"task_name": task.task_name, "Effort Score": effort}

@router.post("/calculate_productivity")
@cache(expire=300)
async def process_productivity(task: TaskInput, db: Session = Depends(get_db)):
    productivity = calculate_productivity(task)
    save_calculation(db, "Productivity Score", productivity)
    return {"task_name": task.task_name, "Productivity Score": productivity}

@router.post("/calculate_virality")
@cache(expire=300)
async def process_virality(share_rate: float, engagement_rate: float, conversion_rate: float, time_factor: float, db: Session = Depends(get_db)):
    virality_score = calculate_virality(share_rate, engagement_rate, conversion_rate, time_factor)
    save_calculation(db, "Virality Score", virality_score)
    return {"Virality Score": virality_score}

@router.post("/calculate_engagement")
@cache(expire=300)
async def process_engagement(data: EngagementInput, db: Session = Depends(get_db)):
    engagement_score = calculate_engagement_score(data)
    save_calculation(db, "Engagement Score", engagement_score)
    return {"Engagement Score": engagement_score}

@router.post("/calculate_ai_efficiency")
@cache(expire=300)
async def process_ai_efficiency(data: AIEfficiencyInput, db: Session = Depends(get_db)):
    efficiency = calculate_ai_efficiency(data)
    save_calculation(db, "AI Efficiency Score", efficiency)
    return {"AI Efficiency Score": efficiency}

@router.post("/calculate_impact_score")
@cache(expire=300)
async def process_impact_score(data: ImpactInput, db: Session = Depends(get_db)):
    impact_score = calculate_impact_score(data)
    save_calculation(db, "Impact Score", impact_score)
    return {"Impact Score": impact_score}

@router.post("/income_efficiency")
@cache(expire=300)
async def process_income_efficiency(eff: EfficiencyInput, db: Session = Depends(get_db)):
    result = income_efficiency(eff)
    save_calculation(db, "Income Efficiency", result)
    return {"Income Efficiency": result}

@router.post("/revenue_scaling")
@cache(expire=300)
async def process_revenue_scaling(rs: RevenueScalingInput, db: Session = Depends(get_db)):
    result = revenue_scaling(rs)
    save_calculation(db, "Revenue Scaling", result)
    return {"Revenue Scaling": result}

@router.post("/execution_speed")
@cache(expire=300)
async def process_execution_speed(es: ExecutionSpeedInput, db: Session = Depends(get_db)):
    result = execution_speed(es)
    save_calculation(db, "Execution Speed", result)
    return {"Execution Speed": result}

@router.post("/attention_value")
@cache(expire=300)
async def process_attention_value(data: AttentionValueInput, db: Session = Depends(get_db)):
    result = attention_value(data)
    save_calculation(db, "Attention Value", result)
    return {"Attention Value": result}

@router.post("/engagement_rate")
@cache(expire=300)
async def process_engagement_rate(data: EngagementRateInput, db: Session = Depends(get_db)):
    result = engagement_rate(data)
    save_calculation(db, "Engagement Rate", result)
    return {"Engagement Rate": result}

@router.post("/business_growth")
@cache(expire=300)
async def process_business_growth(data: BusinessGrowthInput, db: Session = Depends(get_db)):
    result = business_growth(data)
    save_calculation(db, "Business Growth", result)
    return {"Business Growth": result}

@router.post("/monetization_efficiency")
@cache(expire=300)
async def process_monetization_efficiency(data: MonetizationEfficiencyInput, db: Session = Depends(get_db)):
    result = monetization_efficiency(data)
    save_calculation(db, "Monetization Efficiency", result)
    return {"Monetization Efficiency": result}

@router.post("/ai_productivity_boost")
@cache(expire=300)
async def process_ai_productivity_boost(data: AIProductivityBoostInput, db: Session = Depends(get_db)):
    result = ai_productivity_boost(data)
    saved_result = save_calculation(db, "AI Productivity Boost", result)
    return {"AI Productivity Boost": saved_result.result_value}

@router.post("/lost_potential")
@cache(expire=300)
async def process_lost_potential(data: LostPotentialInput, db: Session = Depends(get_db)):
    result = lost_potential(data)
    save_calculation(db, "Lost Potential", result)
    return {"Lost Potential": result}

@router.post("/decision_efficiency")
@cache(expire=300)
async def process_decision_efficiency(data: DecisionEfficiencyInput, db: Session = Depends(get_db)):
    result = decision_efficiency(data)
    save_calculation(db, "Decision Efficiency", result)
    return {"Decision Efficiency": result}

@router.post("/batch_calculations")
async def process_batch_calculations(batch_data: BatchInput, db: Session = Depends(get_db)):
    result = process_batch(batch_data)

    for metric_name, value in result.items():
        save_calculation(db, metric_name, value)

    return result


@router.get("/results")
async def get_results(db: Session = Depends(get_db)):
    results = db.query(CalculationResult).all()
    return results

