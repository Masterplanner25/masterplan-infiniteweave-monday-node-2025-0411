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
import threading

from db.database import get_db
from services.auth_service import get_current_user
from services.rate_limiter import limiter
from modules.deepseek.deepseek_code_analyzer import DeepSeekCodeAnalyzer
from modules.deepseek.config_manager_deepseek import ConfigManager
from services.arm_metrics_service import ARMMetricsService, ARMConfigSuggestionEngine
from db.models.arm_models import AnalysisResult, CodeGeneration
from db.models.user import User


router = APIRouter(
    prefix="/arm",
    tags=["ARM — Autonomous Reasoning"],
    dependencies=[Depends(get_current_user)],
)

# ── Singleton analyzer (loads config once per process) ───────────────────────

_analyzer: Optional[DeepSeekCodeAnalyzer] = None
_analyzer_lock = threading.Lock()


def get_analyzer() -> DeepSeekCodeAnalyzer:
    global _analyzer
    if _analyzer is None:
        with _analyzer_lock:
            if _analyzer is None:
                _analyzer = DeepSeekCodeAnalyzer()
    return _analyzer


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
    current_user: User = Depends(get_current_user),
):
    """
    Analyze a code or logic file.

    Returns architectural insights, performance findings,
    and a prioritized improvement roadmap.

    Task Priority is calculated per request via the Infinity Algorithm:
        TP = (Complexity × Urgency) / Resource Cost
    """
    analyzer = get_analyzer()
    return analyzer.run_analysis(
        file_path=body.file_path,
        user_id=str(current_user.id),
        db=db,
        complexity=body.complexity,
        urgency=body.urgency,
        additional_context=body.context,
    )


@router.post("/generate")
@limiter.limit("10/minute")
async def generate_code(
    request: Request,
    body: GenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate or refactor code based on a prompt.
    Optionally link to a previous analysis session via analysis_id.
    """
    analyzer = get_analyzer()
    return analyzer.generate_code(
        prompt=body.prompt,
        user_id=str(current_user.id),
        db=db,
        original_code=body.original_code,
        language=body.language,
        generation_type=body.generation_type,
        analysis_id=body.analysis_id,
        complexity=body.complexity,
        urgency=body.urgency,
    )


@router.get("/logs")
async def get_arm_logs(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fetch reasoning session logs for the current user.

    Returns analysis and generation history with Infinity Algorithm
    performance metrics (execution speed, task priority).
    """
    analyses = (
        db.query(AnalysisResult)
        .filter(AnalysisResult.user_id == str(current_user.id))
        .order_by(AnalysisResult.created_at.desc())
        .limit(limit)
        .all()
    )
    generations = (
        db.query(CodeGeneration)
        .filter(CodeGeneration.user_id == str(current_user.id))
        .order_by(CodeGeneration.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "analyses": [
            {
                "session_id": str(a.session_id),
                "file": a.file_path.split("/")[-1].split("\\")[-1] if a.file_path else "",
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
            "total_tokens_used": sum(
                (a.input_tokens or 0) + (a.output_tokens or 0) for a in analyses
            )
            + sum(
                (g.input_tokens or 0) + (g.output_tokens or 0) for g in generations
            ),
        },
    }


@router.get("/config")
async def get_config(
    current_user: User = Depends(get_current_user),
):
    """Read current ARM configuration."""
    return ConfigManager().get_all()


@router.put("/config")
async def update_config(
    body: ConfigUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Update ARM configuration parameters.

    Changes persist to deepseek_config.json.
    The analyzer singleton is reset so the next request picks up the new config.

    Phase 2: will also trigger the Infinity Algorithm self-tuning feedback loop.
    """
    updated = ConfigManager().update(body.updates)
    # Reset singleton so next request uses updated config
    global _analyzer
    _analyzer = None
    return {"status": "updated", "config": updated}


@router.get("/metrics")
async def get_arm_metrics(
    window: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get the full Thinking KPI report for this user's ARM sessions.

    Returns Infinity Algorithm metrics:
    - Execution Speed (tokens/sec)
    - Decision Efficiency (% successful sessions)
    - AI Productivity Boost (output/input token ratio)
    - Lost Potential (% wasted on failed sessions)
    - Learning Efficiency (speed trend over time)

    window: lookback period in days (default 30)
    """
    metrics_service = ARMMetricsService(db=db, user_id=str(current_user.id))
    return metrics_service.get_all_metrics(window=window)


@router.get("/config/suggest")
async def get_config_suggestions(
    window: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Analyze ARM performance metrics and suggest configuration
    improvements. Suggestions are advisory — apply via PUT /arm/config.

    Each suggestion includes:
    - The metric that triggered it
    - Current value vs threshold
    - Recommended config change
    - Expected impact
    - Risk level (low/medium/high)

    Low-risk suggestions can be auto-applied.
    Medium/high-risk suggestions require explicit approval.
    """
    # Get current metrics
    metrics_service = ARMMetricsService(db=db, user_id=str(current_user.id))
    metrics = metrics_service.get_all_metrics(window=window)

    # Get current config
    config_manager = ConfigManager()
    current_config = config_manager.get_all()

    # Generate suggestions
    suggestion_engine = ARMConfigSuggestionEngine(
        current_config=current_config,
        metrics=metrics,
    )
    suggestions = suggestion_engine.generate_suggestions()

    # Include current metrics summary for context
    suggestions["metrics_snapshot"] = {
        "decision_efficiency": metrics.get("decision_efficiency", {}).get(
            "score", 0
        ),
        "execution_speed_avg": metrics.get("execution_speed", {}).get(
            "average", 0
        ),
        "ai_productivity_ratio": metrics.get("ai_productivity_boost", {}).get(
            "ratio", 0
        ),
        "waste_percentage": metrics.get("lost_potential", {}).get(
            "waste_percentage", 0
        ),
        "learning_trend": metrics.get("learning_efficiency", {}).get(
            "trend", "insufficient data"
        ),
        "total_sessions": metrics.get("total_sessions", 0),
    }

    return suggestions
