import uuid
from datetime import datetime

from fastapi import Depends, APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from AINDY.core.execution_gate import to_envelope
from AINDY.core.execution_helper import execute_with_pipeline
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.services.auth_service import get_current_user
from fastapi_cache.decorator import cache
from apps.analytics.schemas.analytics_inputs import (
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
from apps.analytics.schemas.batch import BatchInput
from apps.analytics.services.calculations import process_batch
from apps.analytics.services.calculation_services import (
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

router = APIRouter(prefix="/compute", tags=["Compute"], dependencies=[Depends(get_current_user)])
legacy_router = APIRouter(tags=["Compute"])


class MasterPlanInput(BaseModel):
    name: str
    start_date: datetime
    duration_years: int
    wcu_target: float
    revenue_target: float
    books_required: int
    platform_required: bool
    studio_required: bool
    playbooks_required: int


async def _execute_main(
    request: Request,
    route_name: str,
    handler,
    *,
    db: Session,
    current_user: dict,
    input_payload=None,
):
    return await execute_with_pipeline(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=str(current_user["sub"]),
        metadata={"db": db},
        input_payload=input_payload,
    )


def _legacy_twr_response(*, task: TaskInput, infinity_result: dict) -> dict:
    score = (infinity_result or {}).get("score") or {}
    adjustment = (infinity_result or {}).get("adjustment") or {}
    memory_influence = (infinity_result or {}).get("memory_influence") or score.get("metadata", {}).get("memory_influence")
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
        "memory_influence": memory_influence,
        "learning_context": {
            "memory_context_count": (infinity_result or {}).get("memory_context_count", score.get("metadata", {}).get("memory_context_count", 0)),
            "memory_signal_count": (infinity_result or {}).get("memory_signal_count", score.get("metadata", {}).get("memory_signal_count", 0)),
            "has_memory_influence": bool(memory_influence),
        },
    }


def _with_execution_envelope(payload):
    envelope = to_envelope(
        eu_id=None,
        trace_id=None,
        status="SUCCESS",
        output=None,
        error=None,
        duration_ms=None,
        attempt_count=1,
    )
    if hasattr(payload, "status_code") and hasattr(payload, "body"):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data")
        result = dict(data) if isinstance(data, dict) else dict(payload)
        result.setdefault("execution_envelope", envelope)
        return result
    return {"data": payload, "execution_envelope": envelope}

@router.post("/calculate_twr")
@limiter.limit("30/minute")
@cache(expire=60)
async def process_task(
    request: Request,
    task: TaskInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        from apps.analytics.services.infinity_orchestrator import execute as execute_infinity_orchestrator

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

    result = await _execute_main(
        request,
        "main.calculate_twr",
        handler,
        db=db,
        current_user=current_user,
        input_payload=task.model_dump(),
    )
    return _with_execution_envelope(result)

@router.post("/calculate_effort")
@limiter.limit("30/minute")
@cache(expire=300)
async def process_effort(
    request: Request,
    task: TaskInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await _execute_main(
        request,
        "main.calculate_effort",
        lambda ctx: (
            lambda effort: (
                save_calculation(db, "Effort Score", effort, user_id=str(current_user["sub"])),
                {"task_name": task.task_name, "Effort Score": effort},
            )[1]
        )(calculate_effort(task)),
        db=db,
        current_user=current_user,
        input_payload=task.model_dump(),
    )
    return _with_execution_envelope(result)

@router.post("/calculate_productivity")
@limiter.limit("30/minute")
@cache(expire=300)
async def process_productivity(
    request: Request,
    task: TaskInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await _execute_main(
        request,
        "main.calculate_productivity",
        lambda ctx: (
            lambda productivity: (
                save_calculation(db, "Productivity Score", productivity, user_id=str(current_user["sub"])),
                {"task_name": task.task_name, "Productivity Score": productivity},
            )[1]
        )(calculate_productivity(task)),
        db=db,
        current_user=current_user,
        input_payload=task.model_dump(),
    )
    return _with_execution_envelope(result)

@router.post("/calculate_virality")
@limiter.limit("30/minute")
async def process_virality(
    request: Request,
    data: ViralityInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        virality_score = calculate_virality(
            data.share_rate,
            data.engagement_rate,
            data.conversion_rate,
            data.time_factor
        )
        save_calculation(db, "Virality Score", virality_score, user_id=str(current_user["sub"]))
        return {"Virality Score": virality_score}

    result = await _execute_main(request, "main.calculate_virality", handler, db=db, current_user=current_user, input_payload=data.model_dump())
    return _with_execution_envelope(result)

@router.post("/calculate_engagement")
@limiter.limit("30/minute")
@cache(expire=300)
async def process_engagement(
    request: Request,
    data: EngagementInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        engagement_score = calculate_engagement_score(data)
        save_calculation(db, "Engagement Score", engagement_score, user_id=str(current_user["sub"]))
        return {"Engagement Score": engagement_score}

    result = await _execute_main(request, "main.calculate_engagement", handler, db=db, current_user=current_user, input_payload=data.model_dump())
    return _with_execution_envelope(result)

@router.post("/calculate_ai_efficiency")
@limiter.limit("30/minute")
@cache(expire=300)
async def process_ai_efficiency(
    request: Request,
    data: AIEfficiencyInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        efficiency = calculate_ai_efficiency(data)
        save_calculation(db, "AI Efficiency Score", efficiency, user_id=str(current_user["sub"]))
        return {"AI Efficiency Score": efficiency}

    result = await _execute_main(request, "main.calculate_ai_efficiency", handler, db=db, current_user=current_user, input_payload=data.model_dump())
    return _with_execution_envelope(result)

@router.post("/calculate_impact_score")
@limiter.limit("30/minute")
@cache(expire=300)
async def process_impact_score(
    request: Request,
    data: ImpactInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        impact_score = calculate_impact_score(data)
        save_calculation(db, "Impact Score", impact_score, user_id=str(current_user["sub"]))
        return {"Impact Score": impact_score}

    result = await _execute_main(request, "main.calculate_impact_score", handler, db=db, current_user=current_user, input_payload=data.model_dump())
    return _with_execution_envelope(result)

@router.post("/income_efficiency")
@limiter.limit("30/minute")
@cache(expire=300)
async def process_income_efficiency(
    request: Request,
    eff: EfficiencyInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        result = income_efficiency(eff)
        save_calculation(db, "Income Efficiency", result, user_id=str(current_user["sub"]))
        return {"Income Efficiency": result}

    result = await _execute_main(request, "main.income_efficiency", handler, db=db, current_user=current_user, input_payload=eff.model_dump())
    return _with_execution_envelope(result)

@router.post("/revenue_scaling")
@limiter.limit("30/minute")
@cache(expire=300)
async def process_revenue_scaling(
    request: Request,
    rs: RevenueScalingInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        result = revenue_scaling(rs)
        save_calculation(db, "Revenue Scaling", result, user_id=str(current_user["sub"]))
        return {"Revenue Scaling": result}

    result = await _execute_main(request, "main.revenue_scaling", handler, db=db, current_user=current_user, input_payload=rs.model_dump())
    return _with_execution_envelope(result)

@router.post("/execution_speed")
@limiter.limit("30/minute")
@cache(expire=300)
async def process_execution_speed(
    request: Request,
    es: ExecutionSpeedInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        result = execution_speed(es)
        save_calculation(db, "Execution Speed", result, user_id=str(current_user["sub"]))
        return {"Execution Speed": result}

    result = await _execute_main(request, "main.execution_speed", handler, db=db, current_user=current_user, input_payload=es.model_dump())
    return _with_execution_envelope(result)

@router.post("/attention_value")
@limiter.limit("30/minute")
@cache(expire=300)
async def process_attention_value(
    request: Request,
    data: AttentionValueInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        result = attention_value(data)
        save_calculation(db, "Attention Value", result, user_id=str(current_user["sub"]))
        return {"Attention Value": result}

    result = await _execute_main(request, "main.attention_value", handler, db=db, current_user=current_user, input_payload=data.model_dump())
    return _with_execution_envelope(result)

@router.post("/engagement_rate")
@limiter.limit("30/minute")
@cache(expire=300)
async def process_engagement_rate(
    request: Request,
    data: EngagementRateInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        result = engagement_rate(data)
        save_calculation(db, "Engagement Rate", result, user_id=str(current_user["sub"]))
        return {"Engagement Rate": result}

    result = await _execute_main(request, "main.engagement_rate", handler, db=db, current_user=current_user, input_payload=data.model_dump())
    return _with_execution_envelope(result)

@router.post("/business_growth")
@limiter.limit("30/minute")
@cache(expire=300)
async def process_business_growth(
    request: Request,
    data: BusinessGrowthInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        result = business_growth(data)
        save_calculation(db, "Business Growth", result, user_id=str(current_user["sub"]))
        return {"Business Growth": result}

    result = await _execute_main(request, "main.business_growth", handler, db=db, current_user=current_user, input_payload=data.model_dump())
    return _with_execution_envelope(result)

@router.post("/monetization_efficiency")
@limiter.limit("30/minute")
@cache(expire=300)
async def process_monetization_efficiency(
    request: Request,
    data: MonetizationEfficiencyInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        result = monetization_efficiency(data)
        save_calculation(db, "Monetization Efficiency", result, user_id=str(current_user["sub"]))
        return {"Monetization Efficiency": result}

    result = await _execute_main(request, "main.monetization_efficiency", handler, db=db, current_user=current_user, input_payload=data.model_dump())
    return _with_execution_envelope(result)

@router.post("/ai_productivity_boost")
@limiter.limit("30/minute")
@cache(expire=300)
async def process_ai_productivity_boost(
    request: Request,
    data: AIProductivityBoostInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        result = ai_productivity_boost(data)
        saved_result = save_calculation(
            db,
            "AI Productivity Boost",
            result,
            user_id=str(current_user["sub"]),
        )
        return {"AI Productivity Boost": saved_result.result_value}

    result = await _execute_main(request, "main.ai_productivity_boost", handler, db=db, current_user=current_user, input_payload=data.model_dump())
    return _with_execution_envelope(result)

@router.post("/lost_potential")
@limiter.limit("30/minute")
@cache(expire=300)
async def process_lost_potential(
    request: Request,
    data: LostPotentialInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        result = lost_potential(data)
        save_calculation(db, "Lost Potential", result, user_id=str(current_user["sub"]))
        return {"Lost Potential": result}

    result = await _execute_main(request, "main.lost_potential", handler, db=db, current_user=current_user, input_payload=data.model_dump())
    return _with_execution_envelope(result)

@router.post("/decision_efficiency")
@limiter.limit("30/minute")
@cache(expire=300)
async def process_decision_efficiency(
    request: Request,
    data: DecisionEfficiencyInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        result = decision_efficiency(data)
        save_calculation(db, "Decision Efficiency", result, user_id=str(current_user["sub"]))
        return {"Decision Efficiency": result}

    result = await _execute_main(request, "main.decision_efficiency", handler, db=db, current_user=current_user, input_payload=data.model_dump())
    return _with_execution_envelope(result)

@router.post("/batch_calculations")
@limiter.limit("30/minute")
async def process_batch_calculations(
    request: Request,
    batch_data: BatchInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        result = process_batch(batch_data)
        for metric_name, value in result.items():
            save_calculation(db, metric_name, value, user_id=str(current_user["sub"]))
        return result

    result = await _execute_main(request, "main.batch_calculations", handler, db=db, current_user=current_user, input_payload=batch_data.model_dump())
    return _with_execution_envelope(result)


@router.get("/results")
@limiter.limit("60/minute")
async def get_results(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        from apps.analytics.services.compute_service import list_calculation_results
        return list_calculation_results(db, user_id=str(current_user["sub"]))

    return await _execute_main(request, "main.results.list", handler, db=db, current_user=current_user)

@router.get("/masterplans")
@limiter.limit("60/minute")
async def get_masterplans(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        from apps.analytics.services.compute_service import list_masterplans_compute
        return list_masterplans_compute(db, user_id=str(current_user["sub"]))

    return await _execute_main(request, "main.masterplans.list", handler, db=db, current_user=current_user)

@router.post("/create_masterplan")
@limiter.limit("30/minute")
async def create_masterplan(
    request: Request,
    data: MasterPlanInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        from apps.analytics.services.compute_service import create_masterplan_compute
        return create_masterplan_compute(db, data=data.dict(), user_id=str(current_user["sub"]))

    result = await _execute_main(request, "main.masterplan.create", handler, db=db, current_user=current_user, input_payload=data.model_dump())
    return _with_execution_envelope(result)


for _route in list(router.routes):
    _path = getattr(_route, "path", None)
    if not _path or not _path.startswith("/compute/"):
        continue
    legacy_router.add_api_route(
        _path.removeprefix("/compute"),
        _route.endpoint,
        methods=list(_route.methods or []),
        name=f"legacy_{_route.name}",
        include_in_schema=False,
    )





