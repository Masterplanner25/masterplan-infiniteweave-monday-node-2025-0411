from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session


def get_arm_logs(db: Session, *, user_id: str, limit: int = 20) -> dict[str, Any]:
    """Return ARM analysis and code-generation logs for a user."""
    from AINDY.db.models.arm_models import AnalysisResult, CodeGeneration

    uid = UUID(str(user_id))
    analyses = (
        db.query(AnalysisResult)
        .filter(AnalysisResult.user_id == uid)
        .order_by(AnalysisResult.created_at.desc())
        .limit(limit)
        .all()
    )
    generations = (
        db.query(CodeGeneration)
        .filter(CodeGeneration.user_id == uid)
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
            "total_tokens_used": (
                sum((a.input_tokens or 0) + (a.output_tokens or 0) for a in analyses)
                + sum((g.input_tokens or 0) + (g.output_tokens or 0) for g in generations)
            ),
        },
    }
