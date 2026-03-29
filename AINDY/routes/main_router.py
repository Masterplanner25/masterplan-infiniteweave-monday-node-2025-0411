import uuid

from fastapi import Depends, APIRouter, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from services.auth_service import get_current_user
from fastapi_cache.decorator import cache
from schemas.masterplan import MasterPlanInput
from db.models import MasterPlan
from db.models import CalculationResult
from schemas.analytics_inputs import (
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
    ViralityInput,
)
from schemas.batch import BatchInput
from services.calculations import process_batch
from services.calculation_services import (
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

router = APIRouter(dependencies=[Depends(get_current_user)])


def _legacy_twr_response(*, task: TaskInput, infinity_result: dict) -> dict:
    score = (infinity_result or {}).get("score") or {}
    adjustment = (infinity_result or {}).get("adjustment") or {}
    latest_adjustment = {
        "decision_type": adjustment.get("decision_type"),
        "applied_at": adjustment.get("applied_at"),
        "adjustment_payload": adjustment.get("adjustment_payload"),
    } if adjustment else None
    return {
        "task_name": task.task_name,
        "TWR": score.get("master_score"),
        "control_system": "infinity",
        "message": "Legacy TWR route now uses Infinity as the canonical scoring source.",
        "score": score,
        "next_action": (infinity_result or {}).get("next_action"),
        "latest_adjustment": latest_adjustment,
        "prior_evaluation": (infinity_result or {}).get("prior_evaluation"),
    }

@router.post("/calculate_twr")
@cache(expire=60)
async def process_task(
    task: TaskInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from services.infinity_orchestrator import execute as execute_infinity_orchestrator

    try:
        result = execute_infinity_orchestrator(
            user_id=uuid.UUID(str(current_user["sub"])),
            trigger_event="legacy_twr_route",
            db=db,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "infinity_scoring_failed",
                "message": "Infinity scoring failed for legacy TWR route",
                "details": str(exc),
            },
        ) from exc

    if not result:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "infinity_scoring_failed",
                "message": "Infinity scoring returned no result",
            },
        )

    return _legacy_twr_response(task=task, infinity_result=result)

@router.post("/calculate_effort")
@cache(expire=300)
async def process_effort(
    task: TaskInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    effort = calculate_effort(task)
    save_calculation(db, "Effort Score", effort, user_id=str(current_user["sub"]))
    return {"task_name": task.task_name, "Effort Score": effort}

@router.post("/calculate_productivity")
@cache(expire=300)
async def process_productivity(
    task: TaskInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    productivity = calculate_productivity(task)
    save_calculation(db, "Productivity Score", productivity, user_id=str(current_user["sub"]))
    return {"task_name": task.task_name, "Productivity Score": productivity}

@router.post("/calculate_virality")
async def process_virality(
    data: ViralityInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    virality_score = calculate_virality(
        data.share_rate,
        data.engagement_rate,
        data.conversion_rate,
        data.time_factor
    )
    save_calculation(db, "Virality Score", virality_score, user_id=str(current_user["sub"]))
    return {"Virality Score": virality_score}

@router.post("/calculate_engagement")
@cache(expire=300)
async def process_engagement(
    data: EngagementInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    engagement_score = calculate_engagement_score(data)
    save_calculation(db, "Engagement Score", engagement_score, user_id=str(current_user["sub"]))
    return {"Engagement Score": engagement_score}

@router.post("/calculate_ai_efficiency")
@cache(expire=300)
async def process_ai_efficiency(
    data: AIEfficiencyInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    efficiency = calculate_ai_efficiency(data)
    save_calculation(db, "AI Efficiency Score", efficiency, user_id=str(current_user["sub"]))
    return {"AI Efficiency Score": efficiency}

@router.post("/calculate_impact_score")
@cache(expire=300)
async def process_impact_score(
    data: ImpactInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    impact_score = calculate_impact_score(data)
    save_calculation(db, "Impact Score", impact_score, user_id=str(current_user["sub"]))
    return {"Impact Score": impact_score}

@router.post("/income_efficiency")
@cache(expire=300)
async def process_income_efficiency(
    eff: EfficiencyInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = income_efficiency(eff)
    save_calculation(db, "Income Efficiency", result, user_id=str(current_user["sub"]))
    return {"Income Efficiency": result}

@router.post("/revenue_scaling")
@cache(expire=300)
async def process_revenue_scaling(
    rs: RevenueScalingInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = revenue_scaling(rs)
    save_calculation(db, "Revenue Scaling", result, user_id=str(current_user["sub"]))
    return {"Revenue Scaling": result}

@router.post("/execution_speed")
@cache(expire=300)
async def process_execution_speed(
    es: ExecutionSpeedInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = execution_speed(es)
    save_calculation(db, "Execution Speed", result, user_id=str(current_user["sub"]))
    return {"Execution Speed": result}

@router.post("/attention_value")
@cache(expire=300)
async def process_attention_value(
    data: AttentionValueInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = attention_value(data)
    save_calculation(db, "Attention Value", result, user_id=str(current_user["sub"]))
    return {"Attention Value": result}

@router.post("/engagement_rate")
@cache(expire=300)
async def process_engagement_rate(
    data: EngagementRateInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = engagement_rate(data)
    save_calculation(db, "Engagement Rate", result, user_id=str(current_user["sub"]))
    return {"Engagement Rate": result}

@router.post("/business_growth")
@cache(expire=300)
async def process_business_growth(
    data: BusinessGrowthInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = business_growth(data)
    save_calculation(db, "Business Growth", result, user_id=str(current_user["sub"]))
    return {"Business Growth": result}

@router.post("/monetization_efficiency")
@cache(expire=300)
async def process_monetization_efficiency(
    data: MonetizationEfficiencyInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = monetization_efficiency(data)
    save_calculation(db, "Monetization Efficiency", result, user_id=str(current_user["sub"]))
    return {"Monetization Efficiency": result}

@router.post("/ai_productivity_boost")
@cache(expire=300)
async def process_ai_productivity_boost(
    data: AIProductivityBoostInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = ai_productivity_boost(data)
    saved_result = save_calculation(
        db,
        "AI Productivity Boost",
        result,
        user_id=str(current_user["sub"]),
    )
    return {"AI Productivity Boost": saved_result.result_value}

@router.post("/lost_potential")
@cache(expire=300)
async def process_lost_potential(
    data: LostPotentialInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = lost_potential(data)
    save_calculation(db, "Lost Potential", result, user_id=str(current_user["sub"]))
    return {"Lost Potential": result}

@router.post("/decision_efficiency")
@cache(expire=300)
async def process_decision_efficiency(
    data: DecisionEfficiencyInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = decision_efficiency(data)
    save_calculation(db, "Decision Efficiency", result, user_id=str(current_user["sub"]))
    return {"Decision Efficiency": result}

@router.post("/batch_calculations")
async def process_batch_calculations(
    batch_data: BatchInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = process_batch(batch_data)

    for metric_name, value in result.items():
        save_calculation(db, metric_name, value, user_id=str(current_user["sub"]))

    return result


@router.get("/results")
async def get_results(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    results = db.query(CalculationResult).filter(
        CalculationResult.user_id == uuid.UUID(str(current_user["sub"]))
    ).all()
    return results

@router.get("/masterplans")
async def get_masterplans(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Legacy unauthenticated endpoint ? kept for backward compatibility
    plans = db.query(MasterPlan).filter(
        MasterPlan.user_id == uuid.UUID(str(current_user["sub"]))
    ).all()
    return plans

@router.post("/create_masterplan")
async def create_masterplan(
    data: MasterPlanInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    plan = MasterPlan(**data.dict())
    plan.user_id = uuid.UUID(str(current_user["sub"]))
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan




