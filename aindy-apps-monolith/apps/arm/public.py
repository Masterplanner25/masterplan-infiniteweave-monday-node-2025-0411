"""Public interface for the ARM app. Other apps must only import from this file."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from AINDY.platform_layer.user_ids import parse_user_id


def _analysis_result_to_dict(result) -> dict:
    return {
        "id": str(result.id),
        "session_id": str(result.session_id),
        "user_id": str(result.user_id),
        "file_path": result.file_path,
        "file_type": result.file_type,
        "analysis_type": result.analysis_type,
        "prompt_used": result.prompt_used,
        "model_used": result.model_used,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "execution_seconds": result.execution_seconds,
        "result_summary": result.result_summary,
        "result_full": result.result_full,
        "task_priority": result.task_priority,
        "status": result.status,
        "error_message": result.error_message,
        "created_at": result.created_at.isoformat() if result.created_at else None,
    }


def get_analysis_result(result_id: str, db: Session) -> dict | None:
    from apps.arm.models import AnalysisResult

    result = db.query(AnalysisResult).filter(AnalysisResult.id == result_id).first()
    return _analysis_result_to_dict(result) if result else None


def list_analysis_results(
    user_id: str,
    db: Session,
    *,
    created_at_gte: datetime | None = None,
    status: str | None = None,
    ascending: bool = False,
) -> list[dict]:
    from apps.arm.models import AnalysisResult

    user_db_id = parse_user_id(user_id)
    if user_db_id is None:
        return []
    query = db.query(AnalysisResult).filter(AnalysisResult.user_id == user_db_id)
    if created_at_gte is not None:
        query = query.filter(AnalysisResult.created_at >= created_at_gte)
    if status is not None:
        query = query.filter(AnalysisResult.status == status)
    order_col = AnalysisResult.created_at.asc() if ascending else AnalysisResult.created_at.desc()
    return [_analysis_result_to_dict(row) for row in query.order_by(order_col).all()]


__all__ = [
    "get_analysis_result",
    "list_analysis_results",
]
