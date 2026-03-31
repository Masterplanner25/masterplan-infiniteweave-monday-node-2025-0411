from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from core.execution_helper import execute_with_pipeline_sync
from db.database import get_db
from runtime.memory.metrics_store import MemoryMetricsStore
from services.auth_service import get_current_user
from utils.user_ids import require_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["Memory"])


def _execute_memory_metrics(request: Request, route_name: str, handler, *, db: Session, user_id: str):
    return execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        metadata={"db": db, "source": "memory_metrics_router"},
    )


@router.get("/metrics")
def get_memory_metrics(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    user_id = require_user_id(current_user["sub"])
    store = MemoryMetricsStore()
    summary = store.get_summary(user_id=user_id, db=db)
    def handler(_ctx):
        return summary
    return _execute_memory_metrics(request, "memory.metrics", handler, db=db, user_id=str(user_id))


@router.get("/metrics/detail")
def get_memory_metrics_detail(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    user_id = require_user_id(current_user["sub"])
    store = MemoryMetricsStore()
    def handler(_ctx):
        return store.get_recent(user_id=user_id, db=db, limit=20)
    return _execute_memory_metrics(request, "memory.metrics.detail", handler, db=db, user_id=str(user_id))


@router.get("/metrics/dashboard")
def get_memory_metrics_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    user_id = require_user_id(current_user["sub"])
    store = MemoryMetricsStore()
    summary = store.get_summary(user_id=user_id, db=db)
    recent = store.get_recent(user_id=user_id, db=db, limit=10)

    insights = []
    if summary["total_runs"] > 0:
        positive_pct = summary["positive_impact_rate"] * 100
        insights.append(
            f"Memory improves results {positive_pct:.0f}% of the time"
        )
        insights.append(
            f"Average impact score is {summary['avg_impact_score']:.2f}"
        )
        if summary["negative_impact_rate"] > 0:
            negative_pct = summary["negative_impact_rate"] * 100
            insights.append(
                f"Negative impact detected in {negative_pct:.0f}% of runs"
            )
    else:
        insights.append("No memory metrics recorded yet")

    def handler(_ctx):
        return {
            "summary": summary,
            "recent_runs": recent,
            "insights": insights,
        }
    return _execute_memory_metrics(request, "memory.metrics.dashboard", handler, db=db, user_id=str(user_id))
