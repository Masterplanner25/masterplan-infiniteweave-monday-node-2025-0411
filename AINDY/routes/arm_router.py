"""
ARM API Router

Exposes the Autonomous Reasoning Module via FastAPI.
All endpoints require JWT authentication.
Rate limited to 10 requests/minute to prevent cost runaway.

Endpoints:
  POST /arm/analyze  — analyze a code file
  POST /arm/generate — generate or refactor code
  GET  /arm/logs     — fetch reasoning session logs
  GET  /arm/config   — read current ARM configuration
  PUT  /arm/config   — update ARM configuration
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from core.execution_helper import execute_with_pipeline
from db.database import get_db
from services.auth_service import get_current_user
from platform_layer.rate_limiter import limiter


router = APIRouter(
    prefix="/arm",
    tags=["ARM — Autonomous Reasoning"],
    dependencies=[Depends(get_current_user)],
)

# ── Request schemas ───────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    file_path: str
    complexity: Optional[float] = None
    urgency: Optional[float] = None
    context: Optional[str] = ""


class GenerateRequest(BaseModel):
    prompt: str
    original_code: Optional[str] = ""
    language: Optional[str] = "python"
    generation_type: Optional[str] = "generate"
    analysis_id: Optional[str] = None
    complexity: Optional[float] = None
    urgency: Optional[float] = None


class ConfigUpdateRequest(BaseModel):
    updates: dict


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/analyze")
@limiter.limit("10/minute")
async def analyze_code(
    request: Request,
    body: AnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Analyze a code or logic file.

    Returns architectural insights, performance findings,
    and a prioritized improvement roadmap.

    Task Priority is calculated per request via the Infinity Algorithm:
        TP = (Complexity × Urgency) / Resource Cost
    """
    async def handler(ctx):
        from platform_layer.async_job_service import (
            async_heavy_execution_enabled,
            build_queued_response,
            submit_async_job,
        )

        if async_heavy_execution_enabled():
            log_id = submit_async_job(
                task_name="arm.analyze",
                payload={
                    "file_path": body.file_path,
                    "user_id": str(current_user["sub"]),
                    "complexity": body.complexity,
                    "urgency": body.urgency,
                    "context": body.context,
                },
                user_id=current_user["sub"],
                source="arm_router",
            )
            return JSONResponse(
                status_code=202,
                content=build_queued_response(
                    log_id,
                    task_name="arm.analyze",
                    source="arm_router",
                ),
            )

        from runtime.flow_engine import run_flow
        result = run_flow(
            "arm_analysis",
            {
                "file_path": body.file_path,
                "complexity": body.complexity,
                "urgency": body.urgency,
                "context": body.context,
            },
            db=db,
            user_id=str(current_user["sub"]),
        )
        if result.get("status") == "error":
            raise RuntimeError(
                (result.get("data") or {}).get("message", "ARM analysis flow failed")
            )
        return result.get("data")

    return await execute_with_pipeline(
        request=request,
        route_name="arm.analyze",
        handler=handler,
        user_id=str(current_user["sub"]),
        metadata={"db": db},
        input_payload=body.model_dump(),
    )


@router.post("/generate")
@limiter.limit("10/minute")
async def generate_code(
    request: Request,
    body: GenerateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Generate or refactor code based on a prompt.
    Optionally link to a previous analysis session via analysis_id.
    """
    async def handler(ctx):
        from platform_layer.async_job_service import (
            async_heavy_execution_enabled,
            build_queued_response,
            submit_async_job,
        )

        if async_heavy_execution_enabled():
            log_id = submit_async_job(
                task_name="arm.generate",
                payload={
                    "prompt": body.prompt,
                    "user_id": str(current_user["sub"]),
                    "original_code": body.original_code,
                    "language": body.language,
                    "generation_type": body.generation_type,
                    "analysis_id": body.analysis_id,
                    "complexity": body.complexity,
                    "urgency": body.urgency,
                },
                user_id=current_user["sub"],
                source="arm_router",
            )
            return JSONResponse(
                status_code=202,
                content=build_queued_response(
                    log_id,
                    task_name="arm.generate",
                    source="arm_router",
                ),
            )

        from runtime.flow_engine import run_flow
        result = run_flow(
            "arm_generate",
            {
                "prompt": body.prompt,
                "original_code": body.original_code,
                "language": body.language,
                "generation_type": body.generation_type,
                "analysis_id": str(body.analysis_id) if body.analysis_id else None,
                "complexity": body.complexity,
                "urgency": body.urgency,
            },
            db=db,
            user_id=str(current_user["sub"]),
        )
        if result.get("status") == "error":
            raise RuntimeError(
                (result.get("data") or {}).get("message", "ARM generate flow failed")
            )
        return result.get("data")

    return await execute_with_pipeline(
        request=request,
        route_name="arm.generate",
        handler=handler,
        user_id=str(current_user["sub"]),
        metadata={"db": db},
        input_payload=body.model_dump(),
    )


@router.get("/logs")
async def get_arm_logs(
    request: Request,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Fetch reasoning session logs for the current user."""
    def handler(ctx):
        from uuid import UUID
        from db.models.arm_models import AnalysisResult, CodeGeneration

        user_id = UUID(str(current_user["sub"]))
        analyses = (
            db.query(AnalysisResult)
            .filter(AnalysisResult.user_id == user_id)
            .order_by(AnalysisResult.created_at.desc())
            .limit(limit)
            .all()
        )
        generations = (
            db.query(CodeGeneration)
            .filter(CodeGeneration.user_id == user_id)
            .order_by(CodeGeneration.created_at.desc())
            .limit(limit)
            .all()
        )
        return {
            "analyses": [
                {
                    "session_id": str(a.session_id),
                    "file": (a.file_path or "").split("/")[-1].split("\\")[-1],
                    "status": a.status,
                    "execution_seconds": a.execution_seconds,
                    "input_tokens": a.input_tokens,
                    "output_tokens": a.output_tokens,
                    "task_priority": a.task_priority,
                    "execution_speed": round(
                        ((a.input_tokens or 0) + (a.output_tokens or 0))
                        / max(a.execution_seconds or 0.001, 0.001),
                        1,
                    ),
                    "summary": a.result_summary,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in analyses
            ],
            "generations": [
                {
                    "session_id": str(g.session_id),
                    "language": g.language,
                    "generation_type": g.generation_type,
                    "execution_seconds": g.execution_seconds,
                    "input_tokens": g.input_tokens,
                    "output_tokens": g.output_tokens,
                    "created_at": g.created_at.isoformat() if g.created_at else None,
                }
                for g in generations
            ],
            "summary": {
                "total_analyses": len(analyses),
                "total_generations": len(generations),
                "total_tokens_used": sum((a.input_tokens or 0) + (a.output_tokens or 0) for a in analyses)
                + sum((g.input_tokens or 0) + (g.output_tokens or 0) for g in generations),
            },
        }

    return await execute_with_pipeline(
        request=request, route_name="arm.logs", handler=handler,
        user_id=str(current_user["sub"]), metadata={"db": db},
    )


@router.get("/config")
async def get_config(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Read current ARM configuration."""
    def handler(ctx):
        from runtime.flow_engine import run_flow
        result = run_flow("arm_config_get", {}, user_id=str(current_user["sub"]))
        if result.get("status") == "error":
            raise RuntimeError("ARM config get flow failed")
        return result.get("data")

    return await execute_with_pipeline(
        request=request, route_name="arm.config.get", handler=handler,
        user_id=str(current_user["sub"]),
    )


@router.put("/config")
async def update_config(
    request: Request,
    body: ConfigUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update ARM configuration parameters."""
    def handler(ctx):
        from runtime.flow_engine import run_flow
        result = run_flow("arm_config_update", {"updates": body.updates}, user_id=str(current_user["sub"]))
        if result.get("status") == "error":
            raise RuntimeError("ARM config update flow failed")
        return result.get("data")

    return await execute_with_pipeline(
        request=request, route_name="arm.config.update", handler=handler,
        user_id=str(current_user["sub"]), input_payload=body.model_dump(),
    )


@router.get("/metrics")
async def get_arm_metrics(
    request: Request,
    window: int = 30,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get the full Thinking KPI report for this user's ARM sessions."""
    def handler(ctx):
        from runtime.flow_engine import run_flow
        result = run_flow("arm_metrics", {"window": window}, db=db, user_id=str(current_user["sub"]))
        if result.get("status") == "error":
            raise RuntimeError("ARM metrics flow failed")
        return result.get("data")

    return await execute_with_pipeline(
        request=request, route_name="arm.metrics.get", handler=handler,
        user_id=str(current_user["sub"]), metadata={"db": db},
    )


@router.get("/config/suggest")
async def get_config_suggestions(
    request: Request,
    window: int = 30,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Analyze ARM performance metrics and suggest configuration improvements."""
    def handler(ctx):
        from runtime.flow_engine import run_flow
        result = run_flow("arm_config_suggest", {"window": window}, db=db, user_id=str(current_user["sub"]))
        if result.get("status") == "error":
            raise RuntimeError("ARM config suggest flow failed")
        return result.get("data")

    return await execute_with_pipeline(
        request=request, route_name="arm.config.suggest", handler=handler,
        user_id=str(current_user["sub"]), metadata={"db": db},
    )

