from __future__ import annotations

import logging
import math
import uuid

from AINDY.memory.memory_persistence import MemoryNodeModel

logger = logging.getLogger(__name__)


class MemoryLearningEngine:
    def update_after_execution(
        self,
        *,
        memory_ids: list[str],
        result,
        user_id: str,
        db,
    ) -> None:
        if not memory_ids or not db:
            return

        try:
            score = evaluate_result(result)
            updated = []
            flagged = []

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
                if user_id and node.user_id and str(node.user_id) != str(user_id):
                    continue

                node.usage_count = (node.usage_count or 0) + 1
                usage = node.usage_count
                old_rate = self._get_success_rate(node)
                new_rate = ((old_rate * (usage - 1)) + score) / max(usage, 1)

                # Store success_rate and low_value flag in extra for now
                extra = node.extra or {}
                extra["success_rate"] = round(new_rate, 4)
                low_value = score < 0.3
                extra["low_value_flag"] = bool(low_value)
                node.extra = extra

                if low_value:
                    flagged.append(str(node.id))

                updated.append({"id": str(node.id), "success_rate": new_rate})

            if hasattr(db, "commit"):
                db.commit()

            logger.info(
                "[MemoryLearning] updated=%s score=%.3f flagged=%s",
                len(updated),
                score,
                len(flagged),
            )
        except Exception as exc:
            logger.warning("[MemoryLearning] update failed: %s", exc)
            if not hasattr(db, "rollback"):
                return
            try:
                db.rollback()
            except Exception as rollback_exc:
                logger.warning("[MemoryLearning] rollback failed: %s", rollback_exc)

    def _get_success_rate(self, node: MemoryNodeModel) -> float:
        extra = node.extra or {}
        value = extra.get("success_rate")
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.5
        total = (node.success_count or 0) + (node.failure_count or 0)
        if total == 0:
            return 0.5
        return (node.success_count or 0) / total


def evaluate_result(result) -> float:
    """
    Heuristic success scoring: returns 0.0 -> 1.0.
    """
    if isinstance(result, dict):
        if "success_score" in result:
            return _clamp(result.get("success_score"))
        if "score" in result:
            return _clamp(result.get("score"))
        if result.get("ok") is True:
            return 0.9
        if result.get("ok") is False:
            return 0.1
        if "error" in result or "exception" in result:
            return 0.1
        if result.get("status") in ("failed", "error"):
            return 0.1
        if result.get("status") in ("partial", "warning"):
            return 0.5
    if isinstance(result, (int, float)):
        return _clamp(result)
    if result is None:
        return 0.1
    return 0.6


def _clamp(value) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, v))

