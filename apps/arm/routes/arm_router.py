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
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from AINDY.core.execution_gate import to_envelope
from AINDY.core.execution_helper import execute_with_pipeline
from AINDY.db.database import get_db
from AINDY.services.auth_service import get_current_user
from AINDY.platform_layer.rate_limiter import limiter
from apps.arm.dao import arm_config_dao
from apps.arm.services.deepseek.config_manager_deepseek import DEFAULT_CONFIG, _UPDATABLE_KEYS


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


def _arm_config_to_dict(config) -> dict:
    if config is None:
        return DEFAULT_CONFIG.copy()
    return {
        key: getattr(config, key)
        for key in DEFAULT_CONFIG.keys()
    }


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
        # Removed: if async_heavy_execution_enabled(): submit_async_job(...)
        # Execution mode (INLINE vs ASYNC) is decided exclusively by
        # ExecutionDispatcher — not at the route level.
        from AINDY.runtime.flow_engine import run_flow
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
        data = result.get("data") or {}
        if not isinstance(data, dict):
            data = {"result": data}
        data.setdefault("execution_envelope", to_envelope(
            eu_id=result.get("run_id"),
            trace_id=result.get("trace_id"),
            status=str(result.get("status") or "UNKNOWN").upper(),
            output=None, error=result.get("error"), duration_ms=None, attempt_count=None,
        ))
        return data

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
        # Removed: if async_heavy_execution_enabled(): submit_async_job(...)
        # Execution mode (INLINE vs ASYNC) is decided exclusively by
        # ExecutionDispatcher — not at the route level.
        from AINDY.runtime.flow_engine import run_flow
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
        data = result.get("data") or {}
        if not isinstance(data, dict):
            data = {"result": data}
        data.setdefault("execution_envelope", to_envelope(
            eu_id=result.get("run_id"),
            trace_id=result.get("trace_id"),
            status=str(result.get("status") or "UNKNOWN").upper(),
            output=None, error=result.get("error"), duration_ms=None, attempt_count=None,
        ))
        return data

    return await execute_with_pipeline(
        request=request,
        route_name="arm.generate",
        handler=handler,
        user_id=str(current_user["sub"]),
        metadata={"db": db},
        input_payload=body.model_dump(),
    )


@router.get("/logs")
@limiter.limit("60/minute")
async def get_arm_logs(
    request: Request,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Fetch reasoning session logs for the current user."""
    user_id = str(current_user["sub"])

    def handler(ctx):
        from apps.arm.services.arm_service import get_arm_logs as svc_logs
        return svc_logs(db, user_id=user_id, limit=limit)

    return await execute_with_pipeline(
        request=request, route_name="arm.logs", handler=handler,
        user_id=user_id, metadata={"db": db},
    )


@router.get("/config")
@limiter.limit("60/minute")
async def get_config(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Read current ARM configuration."""
    def handler(ctx):
        data = _arm_config_to_dict(arm_config_dao.get_config(db))
        data.setdefault("execution_envelope", to_envelope(
            eu_id=None, trace_id=None,
            status="SUCCESS",
            output=None, error=None, duration_ms=None, attempt_count=None,
        ))
        return data

    return await execute_with_pipeline(
        request=request, route_name="arm.config.get", handler=handler,
        user_id=str(current_user["sub"]), metadata={"db": db},
    )


@router.put("/config")
@limiter.limit("30/minute")
async def update_config(
    request: Request,
    body: ConfigUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update ARM configuration parameters."""
    def handler(ctx):
        current = _arm_config_to_dict(arm_config_dao.get_config(db))
        filtered = {k: v for k, v in body.updates.items() if k in _UPDATABLE_KEYS}
        if filtered:
            current.update(filtered)
            updated = arm_config_dao.upsert_config(db, **current)
            config_payload = _arm_config_to_dict(updated)
        else:
            config_payload = current
        data = {"status": "updated", "config": config_payload}
        data.setdefault("execution_envelope", to_envelope(
            eu_id=None, trace_id=None,
            status="SUCCESS",
            output=None, error=None, duration_ms=None, attempt_count=None,
        ))
        return data

    return await execute_with_pipeline(
        request=request, route_name="arm.config.update", handler=handler,
        user_id=str(current_user["sub"]), metadata={"db": db}, input_payload=body.model_dump(),
    )


@router.get("/metrics")
@limiter.limit("60/minute")
async def get_arm_metrics(
    request: Request,
    window: int = 30,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get the full Thinking KPI report for this user's ARM sessions."""
    def handler(ctx):
        from AINDY.runtime.flow_engine import run_flow
        result = run_flow("arm_metrics", {"window": window}, db=db, user_id=str(current_user["sub"]))
        if result.get("status") == "error":
            raise RuntimeError("ARM metrics flow failed")
        data = result.get("data") or {}
        if not isinstance(data, dict):
            data = {"result": data}
        data.setdefault("execution_envelope", to_envelope(
            eu_id=result.get("run_id"), trace_id=result.get("trace_id"),
            status=str(result.get("status") or "UNKNOWN").upper(),
            output=None, error=result.get("error"), duration_ms=None, attempt_count=None,
        ))
        return data

    return await execute_with_pipeline(
        request=request, route_name="arm.metrics.get", handler=handler,
        user_id=str(current_user["sub"]), metadata={"db": db},
    )


@router.get("/config/suggest")
@limiter.limit("60/minute")
async def get_config_suggestions(
    request: Request,
    window: int = 30,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Analyze ARM performance metrics and suggest configuration improvements."""
    def handler(ctx):
        from AINDY.runtime.flow_engine import run_flow
        result = run_flow("arm_config_suggest", {"window": window}, db=db, user_id=str(current_user["sub"]))
        if result.get("status") == "error":
            raise RuntimeError("ARM config suggest flow failed")
        data = result.get("data") or {}
        if not isinstance(data, dict):
            data = {"result": data}
        data.setdefault("execution_envelope", to_envelope(
            eu_id=result.get("run_id"), trace_id=result.get("trace_id"),
            status=str(result.get("status") or "UNKNOWN").upper(),
            output=None, error=result.get("error"), duration_ms=None, attempt_count=None,
        ))
        return data

    return await execute_with_pipeline(
        request=request, route_name="arm.config.suggest", handler=handler,
        user_id=str(current_user["sub"]), metadata={"db": db},
    )

