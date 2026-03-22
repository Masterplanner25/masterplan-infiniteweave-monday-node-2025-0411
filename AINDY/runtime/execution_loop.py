from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from bridge import create_memory_node
from runtime.memory import MemoryOrchestrator
from runtime.memory.memory_feedback import MemoryFeedbackEngine
from runtime.memory.memory_learning import MemoryLearningEngine

logger = logging.getLogger(__name__)


class ExecutionLoop:
    def __init__(self, orchestrator: MemoryOrchestrator, executor: Optional[Callable] = None):
        self.orchestrator = orchestrator
        self.executor = executor
        self.feedback = MemoryFeedbackEngine()
        self.learning = MemoryLearningEngine()

    def run(self, task: Any, user_id: str, db):
        context = None
        try:
            context = self.orchestrator.get_context(
                user_id=user_id,
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

        try:
            create_memory_node(
                content=str(result),
                source=getattr(task, "source", "execution_loop"),
                tags=getattr(task, "tags", []),
                user_id=user_id,
                db=db,
                node_type=getattr(task, "node_type", None),
            )
        except Exception as exc:
            logger.warning("[ExecutionLoop] memory write failed: %s", exc)

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
                user_id=user_id,
                db=db,
            )
        except Exception as exc:
            logger.warning("[ExecutionLoop] feedback failed: %s", exc)

        return result

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
