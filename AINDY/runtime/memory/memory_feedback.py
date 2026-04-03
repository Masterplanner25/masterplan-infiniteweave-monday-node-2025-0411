from __future__ import annotations

import logging
import uuid

from sqlalchemy.exc import SQLAlchemyError

from memory.memory_persistence import MemoryNodeModel

logger = logging.getLogger(__name__)
from services.observability_events import emit_observability_event


class MemoryFeedbackEngine:
    def record_usage(self, memory_ids, success_score: float, db) -> None:
        if not memory_ids or not db:
            return

        try:
            for memory_id in memory_ids:
                try:
                    node_uuid = uuid.UUID(str(memory_id))
                except (TypeError, ValueError):
                    continue

                if hasattr(db, "get"):
                    node = db.get(MemoryNodeModel, node_uuid)
                else:
                    node = db.query(MemoryNodeModel).get(node_uuid)
                if not node:
                    continue

                node.usage_count = (node.usage_count or 0) + 1

                # Maintain success/failure counts based on score
                if success_score >= 0.6:
                    node.success_count = (node.success_count or 0) + 1
                elif success_score <= 0.4:
                    node.failure_count = (node.failure_count or 0) + 1

                total = (node.success_count or 0) + (node.failure_count or 0)
                success_rate = 0.5
                if total > 0:
                    success_rate = (node.success_count or 0) / total

                # Persist best-effort success_rate for diagnostics
                extra = node.extra or {}
                extra["success_rate"] = round(success_rate, 4)
                node.extra = extra

            db.commit()
        except SQLAlchemyError as exc:
            logger.warning("[MemoryFeedback] update failed: %s", exc)
            try:
                db.rollback()
            except Exception as rollback_exc:
                emit_observability_event(
                    logger,
                    event="memory_feedback_rollback_failed",
                    error=str(rollback_exc),
                )
        except Exception as exc:
            logger.warning("[MemoryFeedback] update failed: %s", exc)
