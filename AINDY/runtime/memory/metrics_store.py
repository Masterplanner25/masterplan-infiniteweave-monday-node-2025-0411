from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import case, func

from db.models.memory_metrics import MemoryMetric
from utils.uuid_utils import normalize_uuid

logger = logging.getLogger(__name__)


class MemoryMetricsStore:
    def record(
        self,
        *,
        user_id: str,
        task_type: str | None,
        impact_score: float,
        memory_count: int,
        avg_similarity: float,
        db,
    ) -> None:
        try:
            metric = MemoryMetric(
                user_id=normalize_uuid(user_id) if user_id is not None else None,
                task_type=task_type,
                impact_score=float(impact_score),
                memory_count=int(memory_count),
                avg_similarity=float(avg_similarity),
            )
            db.add(metric)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("[MemoryMetricsStore] record failed: %s", exc)

    def get_summary(self, *, user_id: str, db) -> dict:
        try:
            summary = (
                db.query(
                    func.avg(MemoryMetric.impact_score),
                    func.sum(
                        case(
                            (MemoryMetric.impact_score > 0, 1),
                            else_=0,
                        )
                    ),
                    func.sum(
                        case(
                            (MemoryMetric.impact_score == 0, 1),
                            else_=0,
                        )
                    ),
                    func.sum(
                        case(
                            (MemoryMetric.impact_score < 0, 1),
                            else_=0,
                        )
                    ),
                    func.count(MemoryMetric.id),
                )
                .filter(
                    MemoryMetric.user_id
                    == (normalize_uuid(user_id) if user_id is not None else None)
                )
                .one()
            )

            avg_impact = self._to_number(summary[0], default=0.0)
            positive = self._to_int(summary[1], default=0)
            zero = self._to_int(summary[2], default=0)
            negative = self._to_int(summary[3], default=0)
            total = self._to_int(summary[4], default=0)

            if total == 0:
                return self._empty_summary()

            return {
                "avg_impact_score": round(avg_impact, 4),
                "positive_impact_rate": round(positive / total, 4),
                "zero_impact_rate": round(zero / total, 4),
                "negative_impact_rate": round(negative / total, 4),
                "total_runs": total,
            }
        except Exception as exc:
            logger.warning("[MemoryMetricsStore] summary failed: %s", exc)
            return self._empty_summary()

    def get_recent(self, *, user_id: str, db, limit: int = 20) -> list[dict]:
        try:
            rows = (
                db.query(MemoryMetric)
                .filter(
                    MemoryMetric.user_id
                    == (normalize_uuid(user_id) if user_id is not None else None)
                )
                .order_by(MemoryMetric.created_at.desc())
                .limit(limit)
                .all()
            )
        except Exception as exc:
            logger.warning("[MemoryMetricsStore] recent failed: %s", exc)
            return []

        return [
            {
                "impact_score": float(row.impact_score or 0.0),
                "memory_count": int(row.memory_count or 0),
                "avg_similarity": float(row.avg_similarity or 0.0),
                "task_type": row.task_type,
                "created_at": row.created_at.isoformat()
                if getattr(row, "created_at", None)
                else None,
            }
            for row in rows
        ]

    def _empty_summary(self) -> dict:
        return {
            "avg_impact_score": 0.0,
            "positive_impact_rate": 0.0,
            "zero_impact_rate": 0.0,
            "negative_impact_rate": 0.0,
            "total_runs": 0,
        }

    def _to_number(self, value: Any, default: float) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    def _to_int(self, value: Any, default: int) -> int:
        try:
            if value is None:
                return default
            return int(value)
        except Exception:
            return default
