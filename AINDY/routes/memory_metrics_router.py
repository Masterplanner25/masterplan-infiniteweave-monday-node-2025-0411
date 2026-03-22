from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.database import get_db
from runtime.memory.metrics_store import MemoryMetricsStore
from services.auth_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["Memory"])


@router.get("/metrics")
def get_memory_metrics(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    store = MemoryMetricsStore()
    summary = store.get_summary(user_id=user_id, db=db)
    return summary


@router.get("/metrics/detail")
def get_memory_metrics_detail(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    store = MemoryMetricsStore()
    return store.get_recent(user_id=user_id, db=db, limit=20)


@router.get("/metrics/dashboard")
def get_memory_metrics_dashboard(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    user_id = str(current_user["sub"])
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

    return {
        "summary": summary,
        "recent_runs": recent,
        "insights": insights,
    }
