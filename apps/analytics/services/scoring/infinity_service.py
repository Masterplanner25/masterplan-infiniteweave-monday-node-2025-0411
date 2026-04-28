"""
Infinity Algorithm Service — execution scoring engine.

Calculates five KPI scores from live data sources and rolls them
into a master score (0-100).

Score sources:
┌─────────────────────────┬────────────────────────────────────┐
│ KPI                     │ Data Sources                       │
├─────────────────────────┼────────────────────────────────────┤
│ execution_speed         │ task velocity, 14-day rolling avg  │
├─────────────────────────┼────────────────────────────────────┤
│ decision_efficiency     │ task completion rate,              │
│                         │ ARM analysis quality trend         │
├─────────────────────────┼────────────────────────────────────┤
│ ai_productivity_boost   │ ARM usage frequency,               │
│                         │ code quality improvement trend     │
├─────────────────────────┼────────────────────────────────────┤
│ focus_quality           │ watcher session data,              │
│                         │ distraction ratio                  │
├─────────────────────────┼────────────────────────────────────┤
│ masterplan_progress     │ % tasks complete,                  │
│                         │ days ahead/behind target           │
└─────────────────────────┴────────────────────────────────────┘

Master score = weighted KPI average:
  execution_speed       × 0.25
  decision_efficiency   × 0.25
  ai_productivity_boost × 0.20
  focus_quality         × 0.15
  masterplan_progress   × 0.15

Called by:
- Task completion hook
- Watcher session_ended signal
- ARM analysis completion
- APScheduler daily recalculation (7am)
- Manual recalculation via API

All calculations are wrapped in try/except —
score failure never crashes parent workflows.
"""
import json
import logging
import math
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session
from AINDY.core.system_event_types import SystemEventTypes
from AINDY.platform_layer.registry import emit_event, get_symbol
from AINDY.platform_layer.user_ids import parse_user_id
from ..orchestration.concurrency import supports_managed_transactions, transaction_scope

logger = logging.getLogger(__name__)
_SCORE_WRITE_RETRY_LIMIT = 5


class _ConcurrentScoreWrite(RuntimeError):
    """Raised when a version-checked score write loses a concurrent update race."""

_ORCHESTRATOR_ACTIVE: ContextVar[bool] = ContextVar(
    "infinity_orchestrator_active",
    default=False,
)


def _db_user_id(user_id: str):
    parsed = parse_user_id(user_id)
    return parsed if parsed is not None else user_id


def _dispatch_task_syscall(user_id: str, db: Session) -> dict:
    from AINDY.kernel.syscall_dispatcher import SyscallContext, get_dispatcher

    ctx = SyscallContext(
        execution_unit_id=str(uuid.uuid4()),
        user_id=str(user_id),
        capabilities=["task.read"],
        trace_id="",
        metadata={"_db": db},
    )
    result = get_dispatcher().dispatch(
        "sys.v1.task.get_user_tasks",
        {"user_id": str(user_id)},
        ctx,
    )
    if result["status"] == "error":
        logger.warning("task syscall failed for %s: %s", user_id, result["error"])
        return {"tasks": []}
    return result["data"]


def _parse_task_end_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _get_user_tasks_for_scoring(user_id: str, db: Session) -> list[dict]:
    return _dispatch_task_syscall(user_id, db).get("tasks", [])


@contextmanager
def orchestrator_score_context():
    token = _ORCHESTRATOR_ACTIVE.set(True)
    try:
        yield
    finally:
        _ORCHESTRATOR_ACTIVE.reset(token)


def _ensure_orchestrated() -> None:
    if not _ORCHESTRATOR_ACTIVE.get():
        raise RuntimeError(
            "Infinity score updates must be executed via apps.analytics.services.orchestration.infinity_orchestrator.execute()"
        )

# ── KPI Weights ──────────────────────────────────────────────────────────────

# ── Scoring window ───────────────────────────────────────────────────────────
SCORING_WINDOW_DAYS = 14


# ── Score normalization helpers ──────────────────────────────────────────────

def _normalize(value: float, min_val: float, max_val: float) -> float:
    """Normalize a value to 0-100 range, clamped."""
    if max_val <= min_val:
        return 50.0
    normalized = (value - min_val) / (max_val - min_val)
    return round(max(0.0, min(100.0, normalized * 100)), 2)


def _sigmoid_score(value: float, midpoint: float, steepness: float = 1.0) -> float:
    """
    Sigmoid-based scoring. Returns 0-100.
    At midpoint → ~50. Above midpoint → > 50. Below → < 50.
    Steepness controls how quickly score rises.
    """
    try:
        sig = 1 / (1 + math.exp(-steepness * (value - midpoint)))
        return round(sig * 100, 2)
    except (OverflowError, ZeroDivisionError):
        return 50.0


# ── KPI Calculators ──────────────────────────────────────────────────────────

def calculate_execution_speed(user_id: str, db: Session) -> tuple:
    """
    Execution Speed Score (0-100).

    Measures: task completion velocity vs the user's own historical baseline.

    Formula:
      current_velocity = tasks completed in 14 days / 14
      historical_avg = all completed tasks / days since first task
      score = sigmoid(current / historical ratio, midpoint=1.0, steepness=3.0)

      ratio > 1.0 = faster than usual → score > 50
      ratio < 1.0 = slower than usual → score < 50
      ratio = 1.0 = exactly on average → score = 50

    Returns (score: float, data_points_used: int)
    """
    try:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=SCORING_WINDOW_DAYS)
        tasks = _get_user_tasks_for_scoring(user_id, db)

        completed_tasks = [
            task for task in tasks
            if task.get("status") == "completed"
        ]

        recent = 0
        for task in completed_tasks:
            end_time = _parse_task_end_time(task.get("end_time"))
            if end_time is not None and end_time >= window_start:
                recent += 1

        current_velocity = recent / SCORING_WINDOW_DAYS

        completed_end_times = sorted(
            end_time
            for end_time in (
                _parse_task_end_time(task.get("end_time"))
                for task in completed_tasks
            )
            if end_time is not None
        )
        if not completed_end_times:
            return 50.0, recent

        first_end = completed_end_times[0]
        if first_end.tzinfo is None:
            first_end = first_end.replace(tzinfo=timezone.utc)
        days_active = max(1, (now - first_end).days)

        total_completed = len(completed_tasks)

        historical_avg = total_completed / days_active

        if historical_avg == 0:
            ratio = 1.0 if current_velocity == 0 else 2.0
        else:
            ratio = current_velocity / historical_avg

        score = _sigmoid_score(ratio, 1.0, steepness=3.0)
        return score, recent

    except Exception as e:
        logger.warning("execution_speed calc failed: %s", e)
        return 50.0, 0


def calculate_decision_efficiency(user_id: str, db: Session) -> tuple:
    """
    Decision Efficiency Score (0-100).

    Measures: task completion rate + ARM analysis quality trend.

    Formula:
      completion_rate = completed / (completed + pending + in_progress)
      arm_avg = average (architecture_score + integrity_score) / 2 in last 14 days
      arm_quality = arm_avg / 10  (0-1 scale)
      score = (completion_rate × 60) + (arm_quality × 40)

    Returns (score: float, data_points_used: int)
    """
    try:
        from apps.arm.public import list_analysis_results

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=SCORING_WINDOW_DAYS)
        tasks = _get_user_tasks_for_scoring(user_id, db)

        completed = sum(1 for task in tasks if task.get("status") == "completed")
        pending = sum(
            1 for task in tasks
            if task.get("status") in {"pending", "in_progress"}
        )

        total = completed + pending
        completion_rate = completed / total if total > 0 else 0.5

        # ARM quality trend — parse result_full JSON
        arm_score = 5.0
        arm_results = list_analysis_results(
            user_id,
            db,
            created_at_gte=window_start,
            status="success",
        )

        data_points = len(arm_results)

        if arm_results:
            scores = []
            for r in arm_results:
                try:
                    result_data = json.loads(r.get("result_full")) if r.get("result_full") else {}
                    arch = result_data.get("architecture_score", 5)
                    integrity = result_data.get("integrity_score", 5)
                    scores.append((arch + integrity) / 2)
                except (json.JSONDecodeError, TypeError):
                    scores.append(5.0)
            if scores:
                arm_score = sum(scores) / len(scores)

        arm_quality = arm_score / 10.0
        score = round((completion_rate * 60) + (arm_quality * 40), 2)
        return min(100.0, score), data_points + total

    except Exception as e:
        logger.warning("decision_efficiency calc failed: %s", e)
        return 50.0, 0


def calculate_ai_productivity_boost(user_id: str, db: Session) -> tuple:
    """
    AI Productivity Boost Score (0-100).

    Measures: ARM usage frequency + code quality improvement trend.

    Formula:
      usage_freq = ARM analyses in 14 days
      quality_trend = latest ARM avg score - earliest ARM avg score (in window)
      score = sigmoid(usage_freq, midpoint=5) × 0.5 +
              normalized_trend(-5..+5 → 0..100) × 0.5

    Returns (score: float, data_points_used: int)
    """
    try:
        from apps.arm.public import list_analysis_results

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=SCORING_WINDOW_DAYS)

        arm_results = list_analysis_results(
            user_id,
            db,
            created_at_gte=window_start,
            status="success",
            ascending=True,
        )

        usage_count = len(arm_results)
        usage_score = _sigmoid_score(usage_count, 5.0, steepness=0.5)

        trend_score = 50.0

        if len(arm_results) >= 2:
            def _extract_avg(r):
                try:
                    result_data = json.loads(r.get("result_full")) if r.get("result_full") else {}
                    arch = result_data.get("architecture_score", 5)
                    integ = result_data.get("integrity_score", 5)
                    return (arch + integ) / 2
                except (json.JSONDecodeError, TypeError):
                    return 5.0

            earliest = _extract_avg(arm_results[0])
            latest = _extract_avg(arm_results[-1])
            trend = latest - earliest
            trend_score = _normalize(trend, -5.0, 5.0)

        score = round((usage_score * 0.5) + (trend_score * 0.5), 2)
        return min(100.0, score), usage_count

    except Exception as e:
        logger.warning("ai_productivity_boost calc failed: %s", e)
        return 50.0, 0


def calculate_focus_quality(user_id: str, db: Session) -> tuple:
    """
    Focus Quality Score (0-100).

    Measures: watcher session data — duration, distractions, focus achievement.

    Filters by user_id when available; falls back to neutral (50.0) when the
    user has no associated watcher signals.

    Formula:
      avg_duration_score = sigmoid(avg_session_minutes, midpoint=30, steepness=0.1)
      distraction_score = 100 - (avg_distractions_per_session × 10)
      achievement_rate = focus_achieved_signals / session_ended_signals

      score = (avg_duration_score × 0.4) +
              (distraction_score × 0.4) +
              (achievement_rate × 100 × 0.2)

    Returns (score: float, data_points_used: int)
    """
    try:
        from apps.automation.public import list_watcher_signals

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=SCORING_WINDOW_DAYS)

        sessions = [
            signal
            for signal in list_watcher_signals(
                db,
                user_id=user_id,
                signal_type="session_ended",
                limit=500,
            )
            if _parse_task_end_time(signal.get("received_at")) is None
            or _parse_task_end_time(signal.get("received_at")) >= window_start
        ]

        if not sessions:
            return 50.0, 0

        # Average session duration
        durations = [float(signal.get("duration_seconds") or 0) for signal in sessions]
        avg_duration_minutes = sum(durations) / len(durations) / 60
        duration_score = _sigmoid_score(avg_duration_minutes, 30.0, steepness=0.1)

        # Average distractions: count distraction_detected signals per session
        distraction_signals = len(
            [
                signal
                for signal in list_watcher_signals(
                    db,
                    user_id=user_id,
                    signal_type="distraction_detected",
                    limit=1000,
                )
                if _parse_task_end_time(signal.get("received_at")) is None
                or _parse_task_end_time(signal.get("received_at")) >= window_start
            ]
        )

        avg_distractions = distraction_signals / len(sessions)
        distraction_score = max(0.0, 100.0 - (avg_distractions * 10))

        # Focus achievement rate
        focus_achieved = len(
            [
                signal
                for signal in list_watcher_signals(
                    db,
                    user_id=user_id,
                    signal_type="focus_achieved",
                    limit=1000,
                )
                if _parse_task_end_time(signal.get("received_at")) is None
                or _parse_task_end_time(signal.get("received_at")) >= window_start
            ]
        )

        achievement_rate = focus_achieved / len(sessions)

        score = round(
            (duration_score * 0.4) +
            (distraction_score * 0.4) +
            (achievement_rate * 100 * 0.2),
            2
        )
        return min(100.0, score), len(sessions)

    except Exception as e:
        logger.warning("focus_quality calc failed: %s", e)
        return 50.0, 0


def calculate_masterplan_progress(user_id: str, db: Session) -> tuple:
    """
    MasterPlan Progress Score (0-100).

    Measures: % of tasks complete + days ahead/behind target.

    Formula:
      completion_pct = completed_tasks / total_tasks
      schedule_score = sigmoid(days_ahead_behind, midpoint=0, steepness=0.05)
        positive (ahead) → score > 50
        negative (behind) → score < 50

      score = (completion_pct × 100 × 0.6) + (schedule_score × 0.4)

    Returns 50.0 if no active MasterPlan.
    Returns (score: float, data_points_used: int)
    """
    try:
        MasterPlan = get_symbol("MasterPlan")
        if MasterPlan is None:
            return 50.0, 0

        plan = db.query(MasterPlan).filter(
            MasterPlan.user_id == user_id,
            MasterPlan.is_active.is_(True),
        ).first()

        if not plan:
            return 50.0, 0

        tasks = _get_user_tasks_for_scoring(user_id, db)
        total = len(tasks)
        completed = sum(1 for task in tasks if task.get("status") == "completed")

        completion_pct = completed / total if total > 0 else 0.0

        schedule_score = 50.0
        if plan.days_ahead_behind is not None:
            schedule_score = _sigmoid_score(
                float(plan.days_ahead_behind),
                0.0,
                steepness=0.05,
            )

        score = round((completion_pct * 100 * 0.6) + (schedule_score * 0.4), 2)
        return min(100.0, score), total

    except Exception as e:
        logger.warning("masterplan_progress calc failed: %s", e)
        return 50.0, 0


# ── KPI Snapshot ─────────────────────────────────────────────────────────────

def get_user_kpi_snapshot(user_id: str, db: Session) -> Optional[dict]:
    """
    Return the latest KPI snapshot for a user from user_scores.

    Returns a dict with master_score + individual KPI scores, or None
    if the user has no computed scores yet.

    Used by the agent planner to inject live context into the system prompt.
    Never raises.
    """
    try:
        user_db_id = _db_user_id(user_id)
        from apps.analytics.models import UserScore

        score = db.query(UserScore).filter(
            UserScore.user_id == user_db_id
        ).first()

        if not score:
            return None

        return {
            "master_score": score.master_score,
            "execution_speed": score.execution_speed_score,
            "decision_efficiency": score.decision_efficiency_score,
            "ai_productivity_boost": score.ai_productivity_boost_score,
            "focus_quality": score.focus_quality_score,
            "masterplan_progress": score.masterplan_progress_score,
            "confidence": score.confidence,
        }
    except Exception as exc:
        logger.warning("get_user_kpi_snapshot failed for %s: %s", user_id, exc)
        return None


# ── Master Calculator ────────────────────────────────────────────────────────

def calculate_infinity_score(
    user_id: str,
    db: Session,
    trigger_event: str = "manual",
) -> Optional[dict]:
    """
    Calculate and persist the full Infinity score.

    Computes all 5 KPIs, rolls them into a master score, persists to
    user_scores (upsert) and score_history (append), and returns the result.

    Never raises — returns None on failure.

    trigger_event: "task_completion" | "session_ended" |
                   "arm_analysis" | "scheduled" | "manual"
    """
    try:
        _ensure_orchestrated()
        from apps.analytics.models import UserScore, ScoreHistory
        from .kpi_weight_service import get_effective_weights
        user_db_id = _db_user_id(user_id)
        for attempt in range(_SCORE_WRITE_RETRY_LIMIT):
            try:
                with transaction_scope(db):
                    now = datetime.now(timezone.utc)
                    if supports_managed_transactions(db):
                        existing = db.execute(
                            select(UserScore)
                            .where(UserScore.user_id == user_db_id)
                            .with_for_update()
                        ).scalar_one_or_none()
                    else:
                        existing = (
                            db.query(UserScore)
                            .filter(UserScore.user_id == user_db_id)
                            .first()
                        )

                    if existing is None:
                        existing = UserScore(
                            user_id=user_db_id,
                            master_score=0.0,
                            execution_speed_score=0.0,
                            decision_efficiency_score=0.0,
                            ai_productivity_boost_score=0.0,
                            focus_quality_score=0.0,
                            masterplan_progress_score=0.0,
                            confidence="baseline",
                            data_points_used=0,
                            trigger_event="baseline",
                            calculated_at=now,
                            updated_at=now,
                            lock_version=1,
                        )
                        db.add(existing)
                        db.flush()

                    previous_master = float(existing.master_score or 0.0)
                    previous_version = int(existing.lock_version or 0)

                    exec_speed, dp1 = calculate_execution_speed(user_id, db)
                    decision_eff, dp2 = calculate_decision_efficiency(user_id, db)
                    ai_boost, dp3 = calculate_ai_productivity_boost(user_id, db)
                    focus_qual, dp4 = calculate_focus_quality(user_id, db)
                    plan_progress, dp5 = calculate_masterplan_progress(user_id, db)
                    total_data_points = dp1 + dp2 + dp3 + dp4 + dp5
                    effective_weights = get_effective_weights(db, user_id)

                    master = round(
                        exec_speed * effective_weights["execution_speed"] +
                        decision_eff * effective_weights["decision_efficiency"] +
                        ai_boost * effective_weights["ai_productivity_boost"] +
                        focus_qual * effective_weights["focus_quality"] +
                        plan_progress * effective_weights["masterplan_progress"],
                        2,
                    )

                    if total_data_points >= 50:
                        confidence = "high"
                    elif total_data_points >= 10:
                        confidence = "medium"
                    else:
                        confidence = "low"

                    score_delta = master - previous_master
                    next_version = previous_version + 1

                    if supports_managed_transactions(db):
                        updated = (
                            db.query(UserScore)
                            .filter(
                                UserScore.id == existing.id,
                                UserScore.lock_version == previous_version,
                            )
                            .update(
                                {
                                    UserScore.master_score: master,
                                    UserScore.execution_speed_score: exec_speed,
                                    UserScore.decision_efficiency_score: decision_eff,
                                    UserScore.ai_productivity_boost_score: ai_boost,
                                    UserScore.focus_quality_score: focus_qual,
                                    UserScore.masterplan_progress_score: plan_progress,
                                    UserScore.data_points_used: total_data_points,
                                    UserScore.confidence: confidence,
                                    UserScore.trigger_event: trigger_event,
                                    UserScore.calculated_at: now,
                                    UserScore.updated_at: now,
                                    UserScore.lock_version: next_version,
                                },
                                synchronize_session=False,
                            )
                        )
                        if updated != 1:
                            raise _ConcurrentScoreWrite(f"Lost score update race for user {user_id}")
                    else:
                        existing.master_score = master
                        existing.execution_speed_score = exec_speed
                        existing.decision_efficiency_score = decision_eff
                        existing.ai_productivity_boost_score = ai_boost
                        existing.focus_quality_score = focus_qual
                        existing.masterplan_progress_score = plan_progress
                        existing.data_points_used = total_data_points
                        existing.confidence = confidence
                        existing.trigger_event = trigger_event
                        existing.calculated_at = now
                        existing.updated_at = now
                        existing.lock_version = next_version
                        db.add(existing)

                    history_entry = ScoreHistory(
                        user_id=user_db_id,
                        master_score=master,
                        execution_speed_score=exec_speed,
                        decision_efficiency_score=decision_eff,
                        ai_productivity_boost_score=ai_boost,
                        focus_quality_score=focus_qual,
                        masterplan_progress_score=plan_progress,
                        trigger_event=trigger_event,
                        score_delta=round(score_delta, 2),
                        calculated_at=now,
                    )
                    db.add(history_entry)
                    db.flush()
                break
            except _ConcurrentScoreWrite:
                db.rollback()
                if attempt == _SCORE_WRITE_RETRY_LIMIT - 1:
                    raise
                continue

        logger.info(
            "Infinity score for %s: %.1f (delta %+.1f, trigger=%s)",
            user_id, master, score_delta, trigger_event
        )
        emit_event(
            SystemEventTypes.ANALYTICS_SCORE_UPDATED,
            {
                "user_id": str(user_id),
                "score": float(master),
                "kpi_breakdown": {
                    "execution_speed": float(exec_speed),
                    "decision_efficiency": float(decision_eff),
                    "ai_productivity_boost": float(ai_boost),
                    "focus_quality": float(focus_qual),
                    "masterplan_progress": float(plan_progress),
                },
                "computed_at": now.isoformat(),
            },
        )

        return {
            "user_id": user_id,
            "master_score": master,
            "kpis": {
                "execution_speed": exec_speed,
                "decision_efficiency": decision_eff,
                "ai_productivity_boost": ai_boost,
                "focus_quality": focus_qual,
                "masterplan_progress": plan_progress,
            },
            "weights": effective_weights,
            "metadata": {
                "confidence": confidence,
                "data_points_used": total_data_points,
                "trigger_event": trigger_event,
                "score_delta": round(score_delta, 2),
                "lock_version": int(existing.lock_version or 0),
                "calculated_at": now.isoformat(),
            },
        }

    except _ConcurrentScoreWrite as e:
        reason = "concurrent_write"
        logger.error(
            "Infinity score write failed for user %s after %d attempts: %s",
            user_id,
            _SCORE_WRITE_RETRY_LIMIT,
            e,
        )
        try:
            from AINDY.platform_layer.metrics import infinity_score_write_failures_total

            infinity_score_write_failures_total.labels(reason=reason).inc()
        except Exception:
            pass
        try:
            from AINDY.core.system_event_service import emit_error_event
            from AINDY.db.database import SessionLocal

            _err_db = SessionLocal()
            try:
                emit_error_event(
                    db=_err_db,
                    error_type="infinity_score.concurrent_write_failure",
                    message=f"Score write failed after {_SCORE_WRITE_RETRY_LIMIT} retries",
                    user_id=_db_user_id(user_id) if user_id else None,
                    payload={
                        "retry_limit": _SCORE_WRITE_RETRY_LIMIT,
                        "trigger_event": trigger_event,
                    },
                    required=False,
                )
                _err_db.commit()
            finally:
                _err_db.close()
        except Exception:
            pass
        return None
    except Exception as e:
        logger.warning("Infinity score calculation failed for %s: %s", user_id, e)
        try:
            from AINDY.platform_layer.metrics import infinity_score_write_failures_total

            infinity_score_write_failures_total.labels(reason="unknown").inc()
        except Exception:
            pass
        return None


