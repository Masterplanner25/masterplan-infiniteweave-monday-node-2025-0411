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
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session
from AINDY.utils.user_ids import parse_user_id

logger = logging.getLogger(__name__)

_ORCHESTRATOR_ACTIVE: ContextVar[bool] = ContextVar(
    "infinity_orchestrator_active",
    default=False,
)


def _db_user_id(user_id: str):
    parsed = parse_user_id(user_id)
    return parsed if parsed is not None else user_id


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
            "Infinity score updates must be executed via domain.infinity_orchestrator.execute()"
        )

# ── KPI Weights ──────────────────────────────────────────────────────────────
from AINDY.db.models.user_score import KPI_WEIGHTS

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
        from AINDY.db.models.task import Task

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=SCORING_WINDOW_DAYS)

        # Current window velocity
        recent = db.query(Task).filter(
            Task.user_id == user_id,
            Task.status == "completed",
            Task.end_time >= window_start,
        ).count()

        current_velocity = recent / SCORING_WINDOW_DAYS

        # Historical baseline — first completed task
        first_task = db.query(Task).filter(
            Task.user_id == user_id,
            Task.status == "completed",
        ).order_by(Task.end_time.asc()).first()

        if not first_task or not first_task.end_time:
            return 50.0, recent

        # Days active since first completed task
        first_end = first_task.end_time
        if first_end.tzinfo is None:
            first_end = first_end.replace(tzinfo=timezone.utc)
        days_active = max(1, (now - first_end).days)

        total_completed = db.query(Task).filter(
            Task.user_id == user_id,
            Task.status == "completed",
        ).count()

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
        from AINDY.db.models.task import Task
        from AINDY.db.models.arm_models import AnalysisResult

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=SCORING_WINDOW_DAYS)

        # Task completion rate
        completed = db.query(Task).filter(
            Task.user_id == user_id,
            Task.status == "completed",
        ).count()

        pending = db.query(Task).filter(
            Task.user_id == user_id,
            Task.status.in_(["pending", "in_progress"]),
        ).count()

        total = completed + pending
        completion_rate = completed / total if total > 0 else 0.5

        # ARM quality trend — parse result_full JSON
        arm_score = 5.0
        arm_results = db.query(AnalysisResult).filter(
            AnalysisResult.user_id == user_id,
            AnalysisResult.created_at >= window_start,
            AnalysisResult.status == "success",
        ).all()

        data_points = len(arm_results)

        if arm_results:
            scores = []
            for r in arm_results:
                try:
                    result_data = json.loads(r.result_full) if r.result_full else {}
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
        from AINDY.db.models.arm_models import AnalysisResult

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=SCORING_WINDOW_DAYS)

        arm_results = db.query(AnalysisResult).filter(
            AnalysisResult.user_id == user_id,
            AnalysisResult.created_at >= window_start,
            AnalysisResult.status == "success",
        ).order_by(AnalysisResult.created_at.asc()).all()

        usage_count = len(arm_results)
        usage_score = _sigmoid_score(usage_count, 5.0, steepness=0.5)

        trend_score = 50.0

        if len(arm_results) >= 2:
            def _extract_avg(r):
                try:
                    result_data = json.loads(r.result_full) if r.result_full else {}
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
        from AINDY.db.models.watcher_signal import WatcherSignal

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=SCORING_WINDOW_DAYS)

        sessions = db.query(WatcherSignal).filter(
            WatcherSignal.signal_type == "session_ended",
            WatcherSignal.user_id == user_id,
            WatcherSignal.received_at >= window_start,
        ).all()

        if not sessions:
            return 50.0, 0

        # Average session duration
        durations = [s.duration_seconds or 0 for s in sessions]
        avg_duration_minutes = sum(durations) / len(durations) / 60
        duration_score = _sigmoid_score(avg_duration_minutes, 30.0, steepness=0.1)

        # Average distractions: count distraction_detected signals per session
        distraction_signals = db.query(WatcherSignal).filter(
            WatcherSignal.signal_type == "distraction_detected",
            WatcherSignal.user_id == user_id,
            WatcherSignal.received_at >= window_start,
        ).count()

        avg_distractions = distraction_signals / len(sessions)
        distraction_score = max(0.0, 100.0 - (avg_distractions * 10))

        # Focus achievement rate
        focus_achieved = db.query(WatcherSignal).filter(
            WatcherSignal.signal_type == "focus_achieved",
            WatcherSignal.user_id == user_id,
            WatcherSignal.received_at >= window_start,
        ).count()

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
        from AINDY.db.models.masterplan import MasterPlan
        from AINDY.db.models.task import Task

        plan = db.query(MasterPlan).filter(
            MasterPlan.user_id == user_id,
            MasterPlan.is_active.is_(True),
        ).first()

        if not plan:
            return 50.0, 0

        total = db.query(Task).filter(Task.user_id == user_id).count()
        completed = db.query(Task).filter(
            Task.user_id == user_id,
            Task.status == "completed",
        ).count()

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
        from AINDY.db.models.user_score import UserScore

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
        from AINDY.db.models.user_score import UserScore, ScoreHistory
        user_db_id = _db_user_id(user_id)

        now = datetime.now(timezone.utc)

        # Calculate all 5 KPIs
        exec_speed, dp1 = calculate_execution_speed(user_id, db)
        decision_eff, dp2 = calculate_decision_efficiency(user_id, db)
        ai_boost, dp3 = calculate_ai_productivity_boost(user_id, db)
        focus_qual, dp4 = calculate_focus_quality(user_id, db)
        plan_progress, dp5 = calculate_masterplan_progress(user_id, db)

        total_data_points = dp1 + dp2 + dp3 + dp4 + dp5

        # Master score (weighted average)
        master = round(
            exec_speed   * KPI_WEIGHTS["execution_speed"] +
            decision_eff * KPI_WEIGHTS["decision_efficiency"] +
            ai_boost     * KPI_WEIGHTS["ai_productivity_boost"] +
            focus_qual   * KPI_WEIGHTS["focus_quality"] +
            plan_progress * KPI_WEIGHTS["masterplan_progress"],
            2
        )

        # Confidence based on data density
        if total_data_points >= 50:
            confidence = "high"
        elif total_data_points >= 10:
            confidence = "medium"
        else:
            confidence = "low"

        # Upsert user_scores
        existing = db.query(UserScore).filter(
            UserScore.user_id == user_db_id
        ).first()

        previous_master = existing.master_score if existing else 0.0
        score_delta = master - previous_master

        if existing:
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
            db.add(existing)
        else:
            new_score = UserScore(
                user_id=user_db_id,
                master_score=master,
                execution_speed_score=exec_speed,
                decision_efficiency_score=decision_eff,
                ai_productivity_boost_score=ai_boost,
                focus_quality_score=focus_qual,
                masterplan_progress_score=plan_progress,
                data_points_used=total_data_points,
                confidence=confidence,
                trigger_event=trigger_event,
                calculated_at=now,
            )
            db.add(new_score)

        # Append to score_history
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
        db.commit()

        logger.info(
            "Infinity score for %s: %.1f (Δ%+.1f, trigger=%s)",
            user_id, master, score_delta, trigger_event
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
            "weights": KPI_WEIGHTS,
            "metadata": {
                "confidence": confidence,
                "data_points_used": total_data_points,
                "trigger_event": trigger_event,
                "score_delta": round(score_delta, 2),
                "calculated_at": now.isoformat(),
            },
        }

    except Exception as e:
        logger.warning("Infinity score calculation failed for %s: %s", user_id, e)
        return None


