from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from AINDY.config import settings
from AINDY.db.database import SessionLocal
from AINDY.db.models.flow_run import FlowRun
from AINDY.db.models.waiting_flow_run import WaitingFlowRun

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


async def _flush(db: AsyncSession) -> None:
    if isinstance(db, AsyncSession):
        await db.flush()
        return
    db.flush()


def _normalize_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _emit_wait_timeout_system_event(
    *,
    db,
    flow_run: FlowRun | None,
    waiting_row: WaitingFlowRun,
    elapsed_seconds: int,
) -> None:
    from AINDY.core.system_event_service import emit_system_event
    from AINDY.core.system_event_types import SystemEventTypes

    event_db = SessionLocal() if isinstance(db, AsyncSession) else db
    try:
        emit_system_event(
            db=event_db,
            event_type=SystemEventTypes.WAIT_TIMEOUT,
            user_id=getattr(flow_run, "user_id", None),
            trace_id=getattr(flow_run, "trace_id", None) or waiting_row.correlation_id,
            source="recovery",
            payload={
                "flow_run_id": str(getattr(flow_run, "id", None) or waiting_row.run_id),
                "elapsed_seconds": elapsed_seconds,
                "max_wait_seconds": waiting_row.max_wait_seconds,
                "waiting_for": waiting_row.event_type,
            },
        )
    except Exception as exc:
        logger.warning(
            "WAIT timeout event emission failed for run=%s (non-fatal): %s",
            waiting_row.run_id,
            exc,
        )
    finally:
        if event_db is not db:
            event_db.close()


async def expire_timed_out_waits(db: AsyncSession) -> int:
    """
    Fail expired waiting FlowRuns.

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

    expired_count = 0
    try:
        for flow_run in expired_runs:
            deadline = flow_run.wait_deadline
            flow_run.status = "failed"
            flow_run.waiting_for = None
            flow_run.wait_deadline = None
            flow_run.error_message = "WAIT_TIMEOUT"
            flow_run.error_detail = {
                "reason": "wait_timeout",
                "deadline": deadline.isoformat() if deadline else None,
            }
            flow_run.completed_at = now
            expired_count += 1
        if expired_count:
            await _commit(db)
    except Exception:
        await _rollback(db)
        raise
    return expired_count


async def expire_timed_out_wait_flows(db: AsyncSession) -> int:
    """
    Fail WaitingFlowRun-backed waits that exceeded their configured max wait.

    Rows with ``max_wait_seconds IS NULL`` preserve legacy behavior and are
    ignored by this scan.
    """
    now = _run_now()
    waiting_rows = await _select_flow_runs(
        db,
        select(WaitingFlowRun).where(WaitingFlowRun.max_wait_seconds.is_not(None)),
    )
    expired_count = 0
    try:
        for waiting_row in waiting_rows:
            waited_since = _normalize_utc(waiting_row.waited_since)
            if waited_since is None or waiting_row.max_wait_seconds is None:
                continue

            elapsed_seconds = int((now - waited_since).total_seconds())
            if elapsed_seconds <= int(waiting_row.max_wait_seconds):
                continue

            flow_run = await _select_flow_runs(
                db,
                select(FlowRun).where(FlowRun.id == waiting_row.run_id),
            )
            flow_run = flow_run[0] if flow_run else None

            _emit_wait_timeout_system_event(
                db=db,
                flow_run=flow_run,
                waiting_row=waiting_row,
                elapsed_seconds=elapsed_seconds,
            )

            if flow_run is not None:
                flow_run.status = "failed"
                flow_run.waiting_for = None
                flow_run.wait_deadline = None
                flow_run.error_message = "WAIT_TIMEOUT"
                flow_run.error_detail = {
                    "reason": "wait_timeout",
                    "elapsed_seconds": elapsed_seconds,
                    "max_wait_seconds": waiting_row.max_wait_seconds,
                    "waiting_for": waiting_row.event_type,
                }
                flow_run.completed_at = now

            if isinstance(db, AsyncSession):
                await db.delete(waiting_row)
            else:
                db.delete(waiting_row)
            expired_count += 1

        if expired_count:
            await _flush(db)
        await _commit(db)
    except Exception:
        await _rollback(db)
        raise

    return expired_count


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


def run_expire_timed_out_wait_flows_job() -> int:
    """Scheduler wrapper for WaitingFlowRun max-wait enforcement."""
    db = SessionLocal()
    try:
        expired = asyncio.run(expire_timed_out_wait_flows(db))
        if expired:
            logger.warning("Expired %d timed-out WaitingFlowRun(s)", expired)
        return expired
    except Exception as exc:
        logger.warning("WAIT flow timeout recovery job failed (non-fatal): %s", exc)
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
