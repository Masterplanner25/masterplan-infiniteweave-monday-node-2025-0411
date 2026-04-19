from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from AINDY.config import settings
from AINDY.db.database import SessionLocal
from AINDY.db.models.flow_run import FlowRun

logger = logging.getLogger(__name__)


def _run_now() -> datetime:
    return datetime.now(timezone.utc)


async def _select_flow_runs(db: AsyncSession, statement) -> list[FlowRun]:
    if isinstance(db, AsyncSession):
        result = await db.execute(statement)
        return list(result.scalars().all())
    return list(db.execute(statement).scalars().all())


async def _commit(db: AsyncSession) -> None:
    if isinstance(db, AsyncSession):
        await db.commit()
        return
    db.commit()


async def _rollback(db: AsyncSession) -> None:
    if isinstance(db, AsyncSession):
        await db.rollback()
        return
    db.rollback()


async def expire_timed_out_waits(db: AsyncSession) -> int:
    """
    Mark expired waiting FlowRuns as failed.

    A run expires only when ``status == "waiting"`` and ``wait_deadline`` is in
    the past. ``wait_deadline IS NULL`` means no deadline and is left untouched.
    """
    now = _run_now()
    expired_runs = await _select_flow_runs(
        db,
        select(FlowRun).where(
            FlowRun.status == "waiting",
            FlowRun.wait_deadline.is_not(None),
            FlowRun.wait_deadline < now,
        ),
    )
    if not expired_runs:
        return 0

    try:
        for flow_run in expired_runs:
            deadline = flow_run.wait_deadline
            flow_run.status = "failed"
            flow_run.waiting_for = None
            flow_run.wait_deadline = None
            flow_run.error_message = "Flow wait deadline expired"
            flow_run.error_detail = {
                "reason": "wait_timeout",
                "deadline": deadline.isoformat() if deadline else None,
            }
            flow_run.completed_at = now
        await _commit(db)
    except Exception:
        await _rollback(db)
        raise
    return len(expired_runs)


async def recover_stuck_runs(db: AsyncSession) -> int:
    """
    Mark stale running FlowRuns as failed.

    The scan is idempotent because only rows still in ``status == "running"``
    and older than the configured threshold are updated.
    """
    now = _run_now()
    threshold = now - timedelta(minutes=settings.STUCK_RUN_THRESHOLD_MINUTES)
    stuck_runs = await _select_flow_runs(
        db,
        select(FlowRun).where(
            FlowRun.status == "running",
            FlowRun.updated_at < threshold,
        ),
    )
    if not stuck_runs:
        return 0

    try:
        for flow_run in stuck_runs:
            flow_run.status = "failed"
            flow_run.waiting_for = None
            flow_run.wait_deadline = None
            flow_run.error_message = "Stuck FlowRun recovered by periodic scan"
            flow_run.error_detail = {
                "reason": "stuck_run_recovered",
                "detected_at": now.isoformat(),
            }
            flow_run.completed_at = now
        await _commit(db)
    except Exception:
        await _rollback(db)
        raise
    return len(stuck_runs)


def run_expire_timed_out_waits_job() -> int:
    """Scheduler wrapper for WAIT timeout enforcement."""
    db = SessionLocal()
    try:
        expired = asyncio.run(expire_timed_out_waits(db))
        if expired:
            logger.warning("Expired %d timed-out waiting FlowRun(s)", expired)
        return expired
    except Exception as exc:
        logger.warning("WAIT timeout recovery job failed (non-fatal): %s", exc)
        return 0
    finally:
        db.close()


def run_recover_stuck_runs_job() -> int:
    """Scheduler wrapper for periodic stuck-run recovery."""
    db = SessionLocal()
    try:
        recovered = asyncio.run(recover_stuck_runs(db))
        if recovered:
            logger.warning("Recovered %d stuck FlowRun(s)", recovered)
        return recovered
    except Exception as exc:
        logger.warning("Stuck-run recovery job failed (non-fatal): %s", exc)
        return 0
    finally:
        db.close()
