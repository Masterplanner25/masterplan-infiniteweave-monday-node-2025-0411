"""
Nodus Memory Bridge

Connects the Nodus language runtime to A.I.N.D.Y.'s
Memory Bridge. Provides recall() and remember() as
callable functions from within Nodus task blocks.

Integration pattern:
  Nodus task executes
    → calls recall() / remember() via this bridge
    → bridge calls MemoryNodeDAO
    → results flow back into Nodus execution context

This makes memory a first-class primitive in Nodus —
tasks can retrieve and store knowledge as part of their
execution logic, not as an afterthought.
"""

from __future__ import annotations

import logging
from typing import Optional

from AINDY.core.execution_signal_helper import queue_memory_capture

logger = logging.getLogger(__name__)


class NodusMemoryBridge:
    """
    Bridge between Nodus task execution and A.I.N.D.Y.
    Memory Bridge.

    Instantiated once per Nodus session with a DB connection
    and user context. Provides the recall() and remember()
    functions that Nodus tasks call.
    """

    def __init__(
        self,
        db=None,
        user_id: str = None,
        session_tags: list[str] = None,
        agent_namespace: str = "nodus",
    ):
        self.db = db
        self.user_id = user_id
        self.session_tags = session_tags or []
        self.agent_namespace = agent_namespace
        self._dao = None
        self._engine = None

    @property
    def dao(self):
        if self._dao is None and self.db:
            from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
            self._dao = MemoryNodeDAO(self.db)
        return self._dao

    @property
    def engine(self):
        if self._engine is None and self.db:
            from AINDY.memory.memory_capture_engine import MemoryCaptureEngine
            self._engine = MemoryCaptureEngine(
                db=self.db,
                user_id=self.user_id,
                agent_namespace=self.agent_namespace,
            )
        return self._engine

    def recall(
        self,
        query: str = None,
        tags: list[str] = None,
        node_type: str = None,
        limit: int = 3,
    ) -> list[dict]:
        """
        Recall relevant memories from within a Nodus task.

        Usage in Nodus:
          let context = recall(["authentication"])
          let past = recall("how did we handle auth")

        Returns list of memory dicts with resonance scores.
        Returns [] if no DB connection or on any error.
        """
        if not self.db:
            logger.warning(
                "NodusMemoryBridge.recall() called without DB"
            )
            return []

        try:
            combined_tags = list(
                set((tags or []) + self.session_tags)
            )

            from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
            from AINDY.runtime.memory import MemoryOrchestrator, memory_items_to_dicts

            metadata = {
                "tags": combined_tags or None,
                "node_type": node_type,
                "limit": limit,
            }
            if node_type is None:
                metadata["node_types"] = []

            orchestrator = MemoryOrchestrator(MemoryNodeDAO)
            context = orchestrator.get_context(
                user_id=self.user_id,
                query=query or "",
                task_type="nodus_execution",
                db=self.db,
                max_tokens=800,
                metadata=metadata,
            )
            results = memory_items_to_dicts(context.items)
            return results[:limit]

        except Exception as exc:
            logger.warning(
                "NodusMemoryBridge.recall() failed: %s",
                exc,
            )
            return []

    def remember(
        self,
        content: str,
        outcome: str = "neutral",
        tags: list[str] = None,
        node_type: str = "outcome",
        significance: float = 0.6,
    ) -> Optional[str]:
        """
        Store a memory from within a Nodus task.

        Usage in Nodus:
          remember("implemented auth with JWT")
          remember("chose Redis for session storage", "success")

        Returns the node ID if stored, None if not significant
        enough or on error.
        """
        if not self.engine:
            logger.warning(
                "NodusMemoryBridge.remember() called without DB"
            )
            return None

        try:
            combined_tags = list(
                set((tags or []) + self.session_tags +
                    ["nodus", "task_execution"])
            )

            node = queue_memory_capture(
                db=self.db,
                user_id=self.user_id,
                agent_namespace=self.agent_namespace,
                event_type="task_completed",
                content=content,
                source="nodus_task",
                tags=combined_tags,
                node_type=node_type,
                context={"significance": significance, "outcome": outcome},
            )

            return node.get("id") if node else None

        except Exception as exc:
            logger.warning(
                "NodusMemoryBridge.remember() failed: %s",
                exc,
            )
            return None

    def recall_from(
        self,
        agent_namespace: str,
        query: str = None,
        tags: list[str] = None,
        limit: int = 3,
    ) -> list[dict]:
        """
        Query another agent's shared memory.
        """
        if not self.dao:
            return []

        try:
            return self.dao.recall_from_agent(
                agent_namespace=agent_namespace,
                query=query,
                tags=tags,
                limit=limit,
                user_id=self.user_id,
                include_private=False,
            )
        except Exception as exc:
            logger.warning(
                "NodusMemoryBridge.recall_from() failed: %s",
                exc,
            )
            return []

    def recall_all_agents(
        self,
        query: str = None,
        tags: list[str] = None,
        limit: int = 5,
    ) -> dict:
        """
        Federated query across all agents.
        """
        if not self.dao:
            return {"merged_results": [], "results_by_agent": {}}

        try:
            return self.dao.recall_federated(
                query=query,
                tags=tags,
                limit=limit,
                user_id=self.user_id,
            )
        except Exception as exc:
            logger.warning(
                "NodusMemoryBridge.recall_all_agents() failed: %s",
                exc,
            )
            return {"merged_results": [], "results_by_agent": {}}

    def share(self, node_id: str) -> bool:
        """
        Share a private memory with all agents.
        """
        if not self.dao or not node_id:
            return False

        try:
            result = self.dao.share_memory(
                node_id=node_id,
                user_id=self.user_id,
            )
            return result is not None
        except Exception:
            return False

    def get_suggestions(
        self,
        query: str = None,
        tags: list[str] = None,
        limit: int = 3,
    ) -> list[dict]:
        """
        Get suggestions from within a Nodus task.

        Usage in Nodus:
          let hints = suggest("optimize this function")

        Returns actionable suggestions based on past outcomes.
        """
        if not self.dao:
            return []

        try:
            combined_tags = list(
                set((tags or []) + self.session_tags)
            )
            result = self.dao.suggest(
                query=query,
                tags=combined_tags or None,
                user_id=self.user_id,
                limit=limit,
            )
            return result.get("suggestions", [])

        except Exception as exc:
            logger.warning(
                "NodusMemoryBridge.get_suggestions() failed: %s",
                exc,
            )
            return []

    def record_outcome(
        self,
        node_id: str,
        outcome: str,  # "success" | "failure" | "neutral"
    ) -> None:
        """
        Record the outcome of using a recalled memory.

        Usage in Nodus (after task completes):
          record_outcome(memory_id, "success")

        This closes the feedback loop — memories that
        helped get boosted, ones that misled get suppressed.
        """
        if not self.dao or not node_id:
            return

        try:
            self.dao.record_feedback(
                node_id=node_id,
                outcome=outcome,
                user_id=self.user_id,
            )
        except Exception as exc:
            logger.warning(
                "NodusMemoryBridge.record_outcome() failed: %s",
                exc,
            )

    def recall_tool(
        self,
        query: str = None,
        tags: list[str] = None,
        limit: int = 3,
        max_tokens: int = 800,
    ) -> dict:
        """
        Tool-style recall for Nodus runtime.

        Returns a JSON-safe dict with formatted context and ids.
        """
        if not self.db:
            return {
                "formatted": "",
                "items": [],
                "ids": [],
                "count": 0,
                "tokens": 0,
            }

        try:
            combined_tags = list(
                set((tags or []) + self.session_tags)
            )

            from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
            from AINDY.runtime.memory import MemoryOrchestrator, memory_items_to_dicts

            metadata = {
                "tags": combined_tags or None,
                "limit": limit,
                "node_types": [],
            }

            orchestrator = MemoryOrchestrator(MemoryNodeDAO)
            context = orchestrator.get_context(
                user_id=self.user_id,
                query=query or "",
                task_type="nodus_execution",
                db=self.db,
                max_tokens=max_tokens,
                metadata=metadata,
            )
            return {
                "formatted": context.formatted,
                "items": memory_items_to_dicts(context.items)[:limit],
                "ids": context.ids[:limit],
                "count": len(context.items),
                "tokens": context.total_tokens,
            }
        except Exception as exc:
            logger.warning(
                "NodusMemoryBridge.recall_tool() failed: %s",
                exc,
            )
            return {
                "formatted": "",
                "items": [],
                "ids": [],
                "count": 0,
                "tokens": 0,
            }


def create_nodus_bridge(
    db=None,
    user_id: str = None,
    session_tags: list[str] = None,
    agent_namespace: str = "nodus",
) -> NodusMemoryBridge:
    """
    Factory function for creating a Nodus memory bridge.
    """
    return NodusMemoryBridge(
        db=db,
        user_id=user_id,
        session_tags=session_tags or [],
        agent_namespace=agent_namespace,
    )
