from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from AINDY.memory.bridge import create_memory_node
from AINDY.db.dao.memory_trace_dao import MemoryTraceDAO
from AINDY.runtime.memory import MemoryOrchestrator
from AINDY.runtime.memory.memory_feedback import MemoryFeedbackEngine
from AINDY.runtime.memory.memory_learning import MemoryLearningEngine
from AINDY.runtime.memory.memory_metrics import MemoryMetricsEngine
from AINDY.runtime.memory.metrics_store import MemoryMetricsStore
from AINDY.utils.uuid_utils import normalize_uuid

logger = logging.getLogger(__name__)
_MISSING = object()


class ExecutionLoop:
    def __init__(self, orchestrator: MemoryOrchestrator, executor: Optional[Callable] = None):
        self.orchestrator = orchestrator
        self.executor = executor
        self.feedback = MemoryFeedbackEngine()
        self.learning = MemoryLearningEngine()
        self.metrics = MemoryMetricsEngine()
        self.metrics_store = MemoryMetricsStore()

    def run(self, operation: Any = _MISSING, user_id: str = None, db=None, **kwargs):
        operation = self._coerce_operation_argument(operation, kwargs)
        result, _ = self.run_with_context(operation, user_id, db)
        return result

    def run_with_context(self, operation: Any = _MISSING, user_id: str = None, db=None, **kwargs):
        operation = self._coerce_operation_argument(operation, kwargs)
        normalized_user_id = normalize_uuid(user_id) if user_id is not None else None
        trace_id = None
        try:
            trace_id = self._resolve_trace_id(operation, normalized_user_id, db)
        except Exception as exc:
            logger.warning("[ExecutionLoop] trace resolution failed: %s", exc)

        if trace_id and hasattr(operation, "metadata") and isinstance(operation.metadata, dict):
            operation.metadata["trace_id"] = trace_id

        context = None
        try:
            context = self.orchestrator.get_context(
                user_id=normalized_user_id,
                task_type=self._get_operation_field(operation, "operation_type", "type", "analysis"),
                query=self._get_operation_field(operation, "input", "input", ""),
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

        result = self._execute(operation, context)

        created_node = None
        try:
            created_node = create_memory_node(
                content=str(result),
                source=self._get_operation_field(operation, "source", "source", "execution_loop"),
                tags=self._get_operation_field(operation, "tags", "tags", []),
                user_id=normalized_user_id,
                db=db,
                node_type=self._get_operation_field(operation, "node_type", "node_type", None) or "outcome",
            )
        except Exception as exc:
            logger.warning("[ExecutionLoop] memory write failed: %s", exc)
            if hasattr(db, "rollback"):
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
                if hasattr(db, "rollback"):
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
            if hasattr(db, "rollback"):
                db.rollback()

        try:
            baseline = self._get_baseline_result(operation)
            impact = self.metrics.compute_impact(baseline, result, context)
            avg_similarity = self.metrics.compute_relevance(context)
            # Canonical persistence path for memory metrics.
            self.metrics_store.record(
                user_id=normalized_user_id,
                task_type=self._get_operation_field(operation, "operation_type", "type", None),
                impact_score=impact,
                memory_count=len(context.items) if context else 0,
                avg_similarity=avg_similarity,
                db=db,
            )
        except Exception as exc:
            logger.warning("[ExecutionLoop] metrics failed: %s", exc)

        return result, context

    def _execute(self, operation: Any, context):
        if self.executor:
            return self.executor(operation, context)
        if callable(operation):
            return operation(context)
        if hasattr(operation, "execute") and callable(operation.execute):
            return operation.execute(context)
        return operation

    def _score(self, result: Any) -> float:
        if isinstance(result, dict):
            return float(result.get("success_score", result.get("score", 0.5)))
        if isinstance(result, (int, float)):
            return float(result)
        return 0.5

    def _resolve_trace_id(self, operation: Any, user_id: str, db) -> Optional[str]:
        metadata = self._get_operation_metadata(operation)
        trace_id = self._get_operation_field(operation, "trace_id", "trace_id", None) or metadata.get("trace_id")
        if trace_id:
            return str(trace_id)

        trace_title = metadata.get("trace_title") or self._get_operation_field(
            operation, "trace_title", "trace_title", None
        )
        trace_enabled = metadata.get("trace_enabled", False) or self._get_operation_field(
            operation, "trace_enabled", "trace_enabled", False
        )
        if not trace_title and not trace_enabled:
            return None

        dao = MemoryTraceDAO(db)
        trace = dao.create_trace(
            user_id=normalize_uuid(user_id) if user_id is not None else None,
            title=trace_title or self._get_operation_field(operation, "operation_type", "type", "execution"),
            description=metadata.get("trace_description"),
            source=metadata.get("trace_source") or self._get_operation_field(
                operation, "source", "source", "execution_loop"
            ),
            extra=metadata.get("trace_extra"),
        )
        return trace.get("id") if trace else None

    def _get_operation_metadata(self, operation: Any) -> dict:
        if hasattr(operation, "metadata") and isinstance(operation.metadata, dict):
            return operation.metadata
        if isinstance(operation, dict):
            return operation.get("metadata", {}) if isinstance(operation.get("metadata"), dict) else {}
        return {}

    def _get_task_metadata(self, task: Any) -> dict:
        return self._get_operation_metadata(task)

    def _get_baseline_result(self, operation: Any) -> Any:
        if isinstance(operation, dict):
            return operation.get("baseline_result") or operation.get("previous_result")
        for attr in ("baseline_result", "previous_result"):
            if hasattr(operation, attr):
                return getattr(operation, attr)
        metadata = self._get_operation_metadata(operation)
        if metadata:
            return metadata.get("baseline_result")
        return None

    def _coerce_operation_argument(self, operation: Any, kwargs: dict) -> Any:
        if operation is _MISSING and "task" in kwargs:
            operation = kwargs.pop("task")
        if kwargs:
            unexpected = next(iter(kwargs))
            raise TypeError(f"Unexpected keyword argument: {unexpected}")
        if operation is _MISSING:
            raise TypeError("Missing required operation argument")
        return operation

    def _get_operation_field(self, operation: Any, neutral_attr: str, legacy_attr: str, default: Any) -> Any:
        if isinstance(operation, dict):
            if neutral_attr in operation:
                return operation[neutral_attr]
            if legacy_attr in operation:
                return operation[legacy_attr]
            return default
        if hasattr(operation, neutral_attr):
            return getattr(operation, neutral_attr)
        if hasattr(operation, legacy_attr):
            return getattr(operation, legacy_attr)
        return default


# ── Flow Engine re-exports ────────────────────────────────────────────────────
# PersistentFlowRunner and related symbols are the canonical execution backbone
# as of Flow Engine Phase B. Exported here for backwards-compatibility.

from AINDY.runtime.flow_engine import (  # noqa: F401, E402
    PersistentFlowRunner,
    execute_intent,
    register_node,
    register_flow,
    route_event,
)

