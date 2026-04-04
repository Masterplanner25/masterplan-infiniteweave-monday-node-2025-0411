"""
ARM Metrics Service

Calculates Infinity Algorithm performance metrics from
ARM session history. These metrics form the "Thinking KPI
System" — A.I.N.D.Y. grading its own reasoning cycles.

Metrics:
- Execution Speed: tokens processed per second
- Decision Efficiency: successful sessions as % of total
- AI Productivity Boost: output quality relative to token cost
- Lost Potential: quantified cost of failures and truncations
- Learning Efficiency: improvement trend over time

Gap notes:
- Decision Efficiency and Lost Potential use analysis_results only:
  CodeGeneration has no status column.
- AI Productivity Boost uses output/input token ratio as a proxy
  for result quality (richer JSON responses = more output tokens).
"""
import statistics
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from db.models.arm_models import AnalysisResult, CodeGeneration
from utils.user_ids import require_user_id


class ARMMetricsService:

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = require_user_id(user_id)

    def get_all_metrics(self, window: int = 30) -> dict:
        """
        Calculate all Infinity Algorithm metrics for this user's
        ARM sessions within the given time window.
        Returns the full Thinking KPI System report.
        """
        analyses = self._get_recent_analyses(window)
        generations = self._get_recent_generations(window)

        if not analyses and not generations:
            return self._empty_metrics()

        return {
            "window_days": window,
            "total_sessions": len(analyses) + len(generations),
            "execution_speed": self._execution_speed(analyses, generations),
            "decision_efficiency": self._decision_efficiency(analyses),
            "ai_productivity_boost": self._ai_productivity_boost(
                analyses, generations
            ),
            "lost_potential": self._lost_potential(analyses),
            "learning_efficiency": self._learning_efficiency(analyses),
            "summary": self._generate_summary(analyses, generations),
        }

    # ── DB queries ────────────────────────────────────────────────────────────

    def _get_recent_analyses(self, window_days: int) -> list:
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        return (
            self.db.query(AnalysisResult)
            .filter(
                AnalysisResult.user_id == self.user_id,
                AnalysisResult.created_at >= cutoff,
            )
            .order_by(AnalysisResult.created_at.asc())
            .all()
        )

    def _get_recent_generations(self, window_days: int) -> list:
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        return (
            self.db.query(CodeGeneration)
            .filter(
                CodeGeneration.user_id == self.user_id,
                CodeGeneration.created_at >= cutoff,
            )
            .order_by(CodeGeneration.created_at.asc())
            .all()
        )

    # ── Metric calculations ───────────────────────────────────────────────────

    def _execution_speed(self, analyses: list, generations: list) -> dict:
        """
        Execution Speed = total tokens / total seconds elapsed.
        Higher = more efficient reasoning per unit time.
        """
        all_sessions = []

        for a in analyses:
            tokens = (a.input_tokens or 0) + (a.output_tokens or 0)
            secs = a.execution_seconds or 0
            if secs > 0 and tokens > 0:
                all_sessions.append(
                    {
                        "speed": tokens / secs,
                        "tokens": tokens,
                        "seconds": secs,
                        "created_at": a.created_at,
                    }
                )

        for g in generations:
            tokens = (g.input_tokens or 0) + (g.output_tokens or 0)
            secs = g.execution_seconds or 0
            if secs > 0 and tokens > 0:
                all_sessions.append(
                    {
                        "speed": tokens / secs,
                        "tokens": tokens,
                        "seconds": secs,
                        "created_at": g.created_at,
                    }
                )

        if not all_sessions:
            return {"current": 0, "average": 0, "unit": "tokens/sec"}

        speeds = [s["speed"] for s in all_sessions]
        return {
            "current": round(speeds[-1], 1),
            "average": round(statistics.mean(speeds), 1),
            "peak": round(max(speeds), 1),
            "unit": "tokens/sec",
            "total_tokens": sum(s["tokens"] for s in all_sessions),
            "total_seconds": round(
                sum(s["seconds"] for s in all_sessions), 2
            ),
        }

    def _decision_efficiency(self, analyses: list) -> dict:
        """
        Decision Efficiency = (successful sessions / total) × 100.
        Measures how reliably ARM produces valid output.
        Uses analysis_results only — CodeGeneration has no status column.
        """
        if not analyses:
            return {
                "score": 0,
                "successful": 0,
                "total": 0,
                "failed": 0,
                "unit": "%",
            }

        total = len(analyses)
        successful = sum(1 for a in analyses if a.status == "success")
        failed = total - successful
        score = (successful / total) * 100

        return {
            "score": round(score, 1),
            "successful": successful,
            "failed": failed,
            "total": total,
            "unit": "%",
        }

    def _ai_productivity_boost(
        self, analyses: list, generations: list
    ) -> dict:
        """
        AI Productivity Boost = output tokens / input tokens.
        Measures how much insight/code is generated per token spent.
        Ratio > 0.5 = efficient; < 0.2 = token-heavy prompting.
        """
        total_input = sum(
            (a.input_tokens or 0) for a in analyses
        ) + sum((g.input_tokens or 0) for g in generations)

        total_output = sum(
            (a.output_tokens or 0) for a in analyses
        ) + sum((g.output_tokens or 0) for g in generations)

        if total_input == 0:
            return {
                "ratio": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "rating": "no data",
            }

        ratio = total_output / total_input

        if ratio >= 0.5:
            rating = "excellent"
        elif ratio >= 0.3:
            rating = "good"
        elif ratio >= 0.15:
            rating = "moderate"
        else:
            rating = "low — prompts may be too verbose"

        return {
            "ratio": round(ratio, 3),
            "input_tokens": total_input,
            "output_tokens": total_output,
            "rating": rating,
        }

    def _lost_potential(self, analyses: list) -> dict:
        """
        Lost Potential = cost of failed or truncated runs.
        Quantifies model inefficiency in token-economic terms.
        A failed session consumed tokens but produced no value.
        Uses analysis_results only — CodeGeneration has no status column.
        """
        failed = [a for a in analyses if a.status == "failed"]

        failed_tokens = sum(
            (a.input_tokens or 0) + (a.output_tokens or 0) for a in failed
        )
        failed_time = sum(a.execution_seconds or 0 for a in failed)

        total_tokens = sum(
            (a.input_tokens or 0) + (a.output_tokens or 0)
            for a in analyses
        )

        waste_pct = (
            (failed_tokens / total_tokens * 100) if total_tokens > 0 else 0
        )

        return {
            "failed_sessions": len(failed),
            "wasted_tokens": failed_tokens,
            "wasted_seconds": round(failed_time, 2),
            "waste_percentage": round(waste_pct, 1),
            "rating": (
                "excellent"
                if waste_pct < 5
                else "good"
                if waste_pct < 15
                else "moderate"
                if waste_pct < 30
                else "high — investigate failure causes"
            ),
        }

    def _learning_efficiency(self, analyses: list) -> dict:
        """
        Learning Efficiency = improvement trend in execution speed.
        Compares first-half vs second-half of session history.
        Positive delta = system is getting faster/more efficient.
        Phase 2 note: When self-tuning is active, this metric
        directly measures the feedback loop effectiveness.
        """
        if len(analyses) < 4:
            return {
                "trend": "insufficient data",
                "delta": 0,
                "sessions_needed": 4 - len(analyses),
            }

        speeds = []
        for a in analyses:
            tokens = (a.input_tokens or 0) + (a.output_tokens or 0)
            secs = a.execution_seconds or 0.001
            if tokens > 0:
                speeds.append(tokens / secs)

        if len(speeds) < 4:
            return {"trend": "insufficient data", "delta": 0}

        midpoint = len(speeds) // 2
        early_avg = statistics.mean(speeds[:midpoint])
        recent_avg = statistics.mean(speeds[midpoint:])

        delta = recent_avg - early_avg
        delta_pct = (delta / early_avg * 100) if early_avg > 0 else 0

        return {
            "trend": (
                "improving"
                if delta_pct > 5
                else "stable"
                if abs(delta_pct) <= 5
                else "declining"
            ),
            "delta_tokens_per_sec": round(delta, 1),
            "delta_percentage": round(delta_pct, 1),
            "early_avg_speed": round(early_avg, 1),
            "recent_avg_speed": round(recent_avg, 1),
        }

    def _generate_summary(self, analyses: list, generations: list) -> str:
        """Plain-language summary of the Thinking KPI report."""
        total = len(analyses) + len(generations)
        if total == 0:
            return "No ARM sessions recorded yet."

        successful = sum(1 for a in analyses if a.status == "success")
        efficiency = (
            (successful / len(analyses) * 100) if analyses else 0
        )

        return (
            f"ARM processed {total} sessions "
            f"({len(analyses)} analyses, {len(generations)} "
            f"generations) with {efficiency:.0f}% success rate."
        )

    def _empty_metrics(self) -> dict:
        return {
            "window_days": 30,
            "total_sessions": 0,
            "execution_speed": {
                "current": 0,
                "average": 0,
                "unit": "tokens/sec",
            },
            "decision_efficiency": {"score": 0, "unit": "%"},
            "ai_productivity_boost": {"ratio": 0, "rating": "no data"},
            "lost_potential": {
                "failed_sessions": 0,
                "waste_percentage": 0,
            },
            "learning_efficiency": {"trend": "insufficient data"},
            "summary": "No ARM sessions recorded yet.",
        }


# ─────────────────────────────────────────────────────────────────────────────


class ARMConfigSuggestionEngine:
    """
    Analyzes ARM metrics and suggests configuration improvements.
    Suggestions are advisory — user must approve via PUT /arm/config.

    This is the self-tuning layer of the Infinity Algorithm feedback
    loop. Phase 3 will automate approval for low-risk changes.
    """

    # Thresholds that trigger suggestions
    EFFICIENCY_WARN_THRESHOLD = 80.0  # % success rate
    EFFICIENCY_CRITICAL_THRESHOLD = 60.0
    SPEED_SLOW_THRESHOLD = 50.0  # tokens/sec
    WASTE_WARN_THRESHOLD = 15.0  # % wasted tokens
    PRODUCTIVITY_LOW_THRESHOLD = 0.2  # output/input ratio

    def __init__(self, current_config: dict, metrics: dict):
        self.config = current_config
        self.metrics = metrics

    def generate_suggestions(self) -> dict:
        """
        Analyze metrics and produce prioritized config suggestions.
        Each suggestion includes:
        - metric that triggered it
        - current value vs threshold
        - recommended config change
        - expected impact
        - risk level (low/medium/high)
        """
        suggestions = []

        # Check Decision Efficiency
        efficiency = self.metrics.get("decision_efficiency", {}).get(
            "score", 100
        )

        if efficiency < self.EFFICIENCY_CRITICAL_THRESHOLD:
            suggestions.append(
                {
                    "priority": "critical",
                    "metric": "decision_efficiency",
                    "current_value": f"{efficiency:.1f}%",
                    "threshold": f"{self.EFFICIENCY_CRITICAL_THRESHOLD}%",
                    "issue": "High failure rate — ARM is producing "
                    "invalid or incomplete responses",
                    "suggestion": "Reduce temperature for more "
                    "deterministic outputs",
                    "config_change": {
                        "temperature": max(
                            0.1,
                            self.config.get("temperature", 0.2) - 0.1,
                        )
                    },
                    "expected_impact": "More consistent JSON output, "
                    "fewer parse failures",
                    "risk": "low",
                }
            )
        elif efficiency < self.EFFICIENCY_WARN_THRESHOLD:
            suggestions.append(
                {
                    "priority": "warning",
                    "metric": "decision_efficiency",
                    "current_value": f"{efficiency:.1f}%",
                    "threshold": f"{self.EFFICIENCY_WARN_THRESHOLD}%",
                    "issue": "Below-target success rate",
                    "suggestion": "Add retry attempts for resilience",
                    "config_change": {
                        "retry_limit": min(
                            5, self.config.get("retry_limit", 3) + 1
                        )
                    },
                    "expected_impact": "Fewer failed sessions from "
                    "transient API errors",
                    "risk": "low",
                }
            )

        # Check Execution Speed
        avg_speed = self.metrics.get("execution_speed", {}).get(
            "average", 0
        )

        if avg_speed > 0 and avg_speed < self.SPEED_SLOW_THRESHOLD:
            current_tokens = self.config.get("max_output_tokens", 2000)
            suggestions.append(
                {
                    "priority": "warning",
                    "metric": "execution_speed",
                    "current_value": f"{avg_speed:.1f} tokens/sec",
                    "threshold": f"{self.SPEED_SLOW_THRESHOLD} tokens/sec",
                    "issue": "Slow execution — responses may be "
                    "unnecessarily long",
                    "suggestion": "Reduce max_output_tokens to focus "
                    "ARM on concise insights",
                    "config_change": {
                        "max_output_tokens": max(
                            500, int(current_tokens * 0.8)
                        )
                    },
                    "expected_impact": "Faster responses, lower token "
                    "cost, more focused output",
                    "risk": "medium — may truncate detailed analyses",
                }
            )

        # Check AI Productivity Boost (output/input ratio)
        productivity = self.metrics.get("ai_productivity_boost", {}).get(
            "ratio", 0
        )

        if productivity > 0 and productivity < self.PRODUCTIVITY_LOW_THRESHOLD:
            current_chunk = self.config.get("max_chunk_tokens", 4000)
            suggestions.append(
                {
                    "priority": "warning",
                    "metric": "ai_productivity_boost",
                    "current_value": f"{productivity:.3f} ratio",
                    "threshold": f"{self.PRODUCTIVITY_LOW_THRESHOLD} ratio",
                    "issue": "High input-to-output ratio — prompts may "
                    "be sending more context than needed",
                    "suggestion": "Reduce chunk size to send more "
                    "focused context to the model",
                    "config_change": {
                        "max_chunk_tokens": max(
                            1000, int(current_chunk * 0.75)
                        )
                    },
                    "expected_impact": "Better output-per-token ratio, "
                    "lower analysis cost",
                    "risk": "medium — large files may lose context",
                }
            )

        # Check Lost Potential (waste %)
        waste_pct = self.metrics.get("lost_potential", {}).get(
            "waste_percentage", 0
        )

        if waste_pct > self.WASTE_WARN_THRESHOLD:
            suggestions.append(
                {
                    "priority": "warning",
                    "metric": "lost_potential",
                    "current_value": f"{waste_pct:.1f}% wasted tokens",
                    "threshold": f"{self.WASTE_WARN_THRESHOLD}%",
                    "issue": "High token waste from failed sessions",
                    "suggestion": "Add stricter input validation to "
                    "catch failures before API calls",
                    "config_change": {
                        "max_file_size_bytes": max(
                            50000,
                            int(
                                self.config.get(
                                    "max_file_size_bytes", 100000
                                )
                                * 0.8
                            ),
                        )
                    },
                    "expected_impact": "Fewer oversized file failures, "
                    "reduced wasted tokens",
                    "risk": "low",
                }
            )

        # Check Learning Efficiency trend
        learning = self.metrics.get("learning_efficiency", {})
        if learning.get("trend") == "declining":
            delta = learning.get("delta_percentage", 0)
            suggestions.append(
                {
                    "priority": "info",
                    "metric": "learning_efficiency",
                    "current_value": f"{delta:.1f}% speed decline",
                    "threshold": "stable or improving",
                    "issue": "Execution speed declining over time — "
                    "may indicate model latency increase or "
                    "growing file complexity",
                    "suggestion": "Switch to faster model for initial "
                    "analysis passes",
                    "config_change": {"analysis_model": "gpt-4o-mini"},
                    "expected_impact": "Faster analysis, lower cost — "
                    "use gpt-4o for generation only",
                    "risk": "medium — gpt-4o-mini may miss subtle issues",
                }
            )

        # All metrics green
        if not suggestions:
            suggestions.append(
                {
                    "priority": "info",
                    "metric": "all",
                    "issue": "All metrics within acceptable ranges",
                    "suggestion": "No config changes recommended",
                    "config_change": {},
                    "expected_impact": "Current configuration is "
                    "performing well",
                    "risk": "none",
                }
            )

        return {
            "suggestions": suggestions,
            "auto_apply_safe": [
                s
                for s in suggestions
                if s.get("risk") == "low" and s.get("config_change")
            ],
            "requires_approval": [
                s
                for s in suggestions
                if s.get("risk") in ["medium", "high"]
                and s.get("config_change")
            ],
            "combined_suggested_config": {
                k: v
                for s in suggestions
                for k, v in s.get("config_change", {}).items()
            },
            "apply_instruction": (
                "Review suggestions above. To apply, send "
                "PUT /arm/config with the combined_suggested_config "
                "or individual changes of your choice."
            ),
        }

