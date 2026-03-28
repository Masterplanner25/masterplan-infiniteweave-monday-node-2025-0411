from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from bridge import create_memory_node
from db.dao.memory_trace_dao import MemoryTraceDAO
from runtime.memory import MemoryOrchestrator
from runtime.memory.memory_feedback import MemoryFeedbackEngine
from runtime.memory.memory_learning import MemoryLearningEngine
from runtime.memory.memory_metrics import MemoryMetricsEngine
from runtime.memory.metrics_store import MemoryMetricsStore
from utils.uuid_utils import normalize_uuid

logger = logging.getLogger(__name__)


class ExecutionLoop:
    def __init__(self, orchestrator: MemoryOrchestrator, executor: Optional[Callable] = None):
        self.orchestrator = orchestrator
        self.executor = executor
        self.feedback = MemoryFeedbackEngine()
        self.learning = MemoryLearningEngine()
        self.metrics = MemoryMetricsEngine()
        self.metrics_store = MemoryMetricsStore()

    def run(self, task: Any, user_id: str, db):
        result, _ = self.run_with_context(task, user_id, db)
        return result

    def run_with_context(self, task: Any, user_id: str, db):
        normalized_user_id = normalize_uuid(user_id) if user_id is not None else None
        trace_id = None
        try:
            trace_id = self._resolve_trace_id(task, normalized_user_id, db)
        except Exception as exc:
            logger.warning("[ExecutionLoop] trace resolution failed: %s", exc)

        if trace_id and hasattr(task, "metadata") and isinstance(task.metadata, dict):
            task.metadata["trace_id"] = trace_id

        context = None
        try:
            context = self.orchestrator.get_context(
                user_id=normalized_user_id,
                task_type=getattr(task, "type", "analysis"),
                query=getattr(task, "input", ""),
                db=db,
            )
        except Exception as exc:
            logger.warning("[ExecutionLoop] recall failed: %s", exc)
            context = self.orchestrator.get_context(
                user_id=user_id,
                task_type="analysis",
                query="",
                db=db,
                metadata={"node_types": []},
            )

        result = self._execute(task, context)

        created_node = None
        try:
            created_node = create_memory_node(
                content=str(result),
                source=getattr(task, "source", "execution_loop"),
                tags=getattr(task, "tags", []),
                user_id=normalized_user_id,
                db=db,
                node_type=getattr(task, "node_type", None) or "outcome",
            )
        except Exception as exc:
            logger.warning("[ExecutionLoop] memory write failed: %s", exc)
            db.rollback()

        if trace_id and created_node and created_node.get("id"):
            try:
                trace_dao = MemoryTraceDAO(db)
                trace_dao.append_node(
                    trace_id=trace_id,
                    node_id=created_node["id"],
                    user_id=normalized_user_id,
                )
            except Exception as exc:
                logger.warning("[ExecutionLoop] trace append failed: %s", exc)
                db.rollback()

        try:
            success_score = self._score(result)
            self.feedback.record_usage(
                memory_ids=context.ids if context else [],
                success_score=success_score,
                db=db,
            )
            self.learning.update_after_execution(
                memory_ids=context.ids if context else [],
                result=result,
                user_id=normalized_user_id,
                db=db,
            )
        except Exception as exc:
            logger.warning("[ExecutionLoop] feedback failed: %s", exc)
            db.rollback()

        try:
            baseline = self._get_baseline_result(task)
            impact = self.metrics.compute_impact(baseline, result, context)
            avg_similarity = self.metrics.compute_relevance(context)
            # Canonical persistence path for memory metrics.
            self.metrics_store.record(
                user_id=normalized_user_id,
                task_type=getattr(task, "type", None),
                impact_score=impact,
                memory_count=len(context.items) if context else 0,
                avg_similarity=avg_similarity,
                db=db,
            )
        except Exception as exc:
            logger.warning("[ExecutionLoop] metrics failed: %s", exc)

        return result, context

    def _execute(self, task: Any, context):
        if self.executor:
            return self.executor(task, context)
        if callable(task):
            return task(context)
        if hasattr(task, "execute") and callable(task.execute):
            return task.execute(context)
        return task

    def _score(self, result: Any) -> float:
        if isinstance(result, dict):
            return float(result.get("success_score", result.get("score", 0.5)))
        if isinstance(result, (int, float)):
            return float(result)
        return 0.5

    def _resolve_trace_id(self, task: Any, user_id: str, db) -> Optional[str]:
        metadata = self._get_task_metadata(task)
        trace_id = getattr(task, "trace_id", None) or metadata.get("trace_id")
        if trace_id:
            return str(trace_id)

        trace_title = metadata.get("trace_title") or getattr(task, "trace_title", None)
        trace_enabled = metadata.get("trace_enabled", False) or getattr(task, "trace_enabled", False)
        if not trace_title and not trace_enabled:
            return None

        dao = MemoryTraceDAO(db)
        trace = dao.create_trace(
            user_id=normalize_uuid(user_id) if user_id is not None else None,
            title=trace_title or getattr(task, "type", "execution"),
            description=metadata.get("trace_description"),
            source=metadata.get("trace_source") or getattr(task, "source", "execution_loop"),
            extra=metadata.get("trace_extra"),
        )
        return trace.get("id") if trace else None

    def _get_task_metadata(self, task: Any) -> dict:
        if hasattr(task, "metadata") and isinstance(task.metadata, dict):
            return task.metadata
        if isinstance(task, dict):
            return task.get("metadata", {}) if isinstance(task.get("metadata"), dict) else {}
        return {}

    def _get_baseline_result(self, task: Any) -> Any:
        if isinstance(task, dict):
            return task.get("baseline_result") or task.get("previous_result")
        for attr in ("baseline_result", "previous_result"):
            if hasattr(task, attr):
                return getattr(task, attr)
        if hasattr(task, "metadata") and isinstance(task.metadata, dict):
            return task.metadata.get("baseline_result")
        return None


# ── Flow Engine re-exports ────────────────────────────────────────────────────
# PersistentFlowRunner and related symbols are the canonical execution backbone
# as of Flow Engine Phase B. Exported here for backwards-compatibility.

from services.flow_engine import (  # noqa: F401, E402
    PersistentFlowRunner,
    execute_intent,
    register_node,
    register_flow,
    route_event,
)
