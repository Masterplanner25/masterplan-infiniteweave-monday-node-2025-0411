"""
AINDYMemoryBridge - adapts AINDY's MemoryNodeDAO to the Nodus VM bridge interface.

The Nodus VM calls bridge.recall(), bridge.remember(), bridge.get_suggestions()
etc. when scripts use the recall(), remember(), suggest() built-ins.
This class routes those calls to AINDY's memory subsystem (MemoryNodeDAO,
MemoryFeedbackEngine) scoped to the execution's user_id.

Phase 2 implements: recall, remember, get_suggestions, record_outcome, share.
Phase 3 will add: recall_from (cross-agent), recall_all_agents (federated).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_MAX_LIMIT = 50


class AINDYMemoryBridge:
    """Nodus VM memory bridge backed by AINDY's MemoryNodeDAO.

    One instance is created per script execution and injected via:
        host_globals={"memory_bridge": bridge}

    All operations are scoped to self._user_id. The bridge opens and
    closes its own DB session per operation to avoid holding long
    transactions during script execution.
    """

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id

    def _session(self):
        """Open a short-lived DB session. Caller is responsible for close()."""
        from AINDY.db.database import SessionLocal

        return SessionLocal()

    @staticmethod
    def _safe_node(node: Any) -> dict[str, Any]:
        """Convert a memory node to a VM-safe plain dict."""
        if isinstance(node, dict):
            return {
                "id": str(node.get("id") or ""),
                "content": node.get("content", ""),
                "tags": list(node.get("tags") or []),
                "node_type": node.get("node_type"),
                "significance": node.get("significance"),
                "resonance_score": node.get("resonance_score"),
                "created_at": str(node["created_at"]) if node.get("created_at") else None,
                "source": node.get("source"),
                "memory_type": node.get("memory_type"),
            }
        return {
            "id": str(getattr(node, "id", "") or ""),
            "content": getattr(node, "content", ""),
            "tags": list(getattr(node, "tags", None) or []),
            "node_type": getattr(node, "node_type", None),
            "significance": getattr(node, "significance", None),
            "resonance_score": getattr(node, "resonance_score", None),
            "created_at": str(node.created_at) if getattr(node, "created_at", None) else None,
            "source": getattr(node, "source", None),
            "memory_type": getattr(node, "memory_type", None),
        }

    def recall(
        self,
        query: Optional[str] = None,
        tags: Optional[list] = None,
        limit: int = 3,
    ) -> list[dict]:
        """Retrieve memories by tag match and/or semantic query."""
        limit = max(1, min(int(limit or 3), _MAX_LIMIT))
        db = self._session()
        try:
            from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

            dao = MemoryNodeDAO(db)
            nodes = dao.recall(
                query=query or "",
                tags=list(tags or []),
                limit=limit,
                user_id=self._user_id,
            )
            return [self._safe_node(n) for n in (nodes or [])]
        except Exception as exc:
            logger.warning("[AINDYMemoryBridge.recall] failed: %s", exc)
            return []
        finally:
            db.close()

    def remember(
        self,
        content: Optional[str] = None,
        node_type: Optional[str] = None,
        tags: Optional[list] = None,
    ) -> Optional[str]:
        """Persist a memory node and return its ID."""
        if not content or not isinstance(content, str):
            return None
        db = self._session()
        try:
            from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

            dao = MemoryNodeDAO(db)
            result = dao.save(
                content=content,
                tags=list(tags or []),
                user_id=self._user_id,
                node_type=node_type or "execution",
                source="nodus_script",
                extra={},
            )
            if isinstance(result, dict):
                return str(result.get("id") or "") or None
            return str(result.id) if result and hasattr(result, "id") else None
        except Exception as exc:
            logger.warning("[AINDYMemoryBridge.remember] failed: %s", exc)
            return None
        finally:
            db.close()

    def get_suggestions(
        self,
        query: Optional[str] = None,
        tags: Optional[list] = None,
        limit: int = 3,
    ) -> list[dict]:
        """Return suggestions from past successful outcomes."""
        if not query:
            return []
        limit = max(1, min(int(limit or 3), _MAX_LIMIT))
        db = self._session()
        try:
            from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

            dao = MemoryNodeDAO(db)
            nodes = dao.recall(
                query=query,
                tags=list(tags or []),
                limit=max(limit * 3, limit),
                user_id=self._user_id,
            )
            filtered = [
                n for n in (nodes or []) if str(getattr(n, "node_type", None) or (n.get("node_type") if isinstance(n, dict) else "")).lower() in {"outcome", "insight", "decision"}
            ]
            return [self._safe_node(n) for n in filtered[:limit]]
        except Exception as exc:
            logger.warning("[AINDYMemoryBridge.get_suggestions] failed: %s", exc)
            return []
        finally:
            db.close()

    def record_outcome(self, node_id: str, outcome: str) -> None:
        """Record whether a recalled memory was helpful."""
        db = self._session()
        try:
            from AINDY.runtime.memory.memory_feedback import MemoryFeedbackEngine

            engine = MemoryFeedbackEngine()
            success_score = 1.0 if str(outcome).lower() == "success" else 0.0
            engine.record_usage(
                memory_ids=[str(node_id)],
                success_score=success_score,
                db=db,
            )
        except Exception as exc:
            logger.warning("[AINDYMemoryBridge.record_outcome] failed: %s", exc)
        finally:
            db.close()

    def share(self, node_id: str) -> bool:
        """Promote a private memory node to shared visibility."""
        db = self._session()
        try:
            from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

            dao = MemoryNodeDAO(db)
            result = dao.share_memory(
                node_id=str(node_id),
                user_id=self._user_id,
            )
            return result is not None
        except Exception as exc:
            logger.warning("[AINDYMemoryBridge.share] failed: %s", exc)
            return False
        finally:
            db.close()

    def recall_from(
        self,
        agent_namespace: Optional[str] = None,
        query: Optional[str] = None,
        tags: Optional[list] = None,
        limit: int = 3,
    ) -> list[dict]:
        """Retrieve shared memories from a specific agent namespace.

        Routes to MemoryNodeDAO.recall() with the agent namespace added as
        a tag filter ("_agent:{namespace}") so cross-agent memories can be
        retrieved without a schema change. Returns nodes with visibility=shared
        tagged with the agent namespace.

        Called by the Nodus VM built-in recall_from(agent, query, tags, limit).
        """
        if not agent_namespace or not isinstance(agent_namespace, str):
            return []
        limit = max(1, min(int(limit or 3), _MAX_LIMIT))

        namespace_tag = f"_agent:{agent_namespace}"
        combined_tags = [namespace_tag] + list(tags or [])

        db = self._session()
        try:
            from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

            dao = MemoryNodeDAO(db)
            nodes = dao.recall(
                query=query or "",
                tags=combined_tags,
                limit=limit,
                user_id=self._user_id,
            )
            return [self._safe_node(n) for n in (nodes or [])]
        except Exception as exc:
            logger.warning("[AINDYMemoryBridge.recall_from] failed: %s", exc)
            return []
        finally:
            db.close()

    def recall_all_agents(
        self,
        query: Optional[str] = None,
        tags: Optional[list] = None,
        limit: int = 5,
    ) -> list[dict]:
        """Retrieve shared memories across all agent namespaces.

        Returns memories from any agent source for the current user,
        ordered by resonance score. Uses MemoryNodeDAO.recall() with
        the provided query and tags (no namespace restriction).

        Called by the Nodus VM built-in recall_all(query, tags, limit).
        """
        limit = max(1, min(int(limit or 5), _MAX_LIMIT))
        db = self._session()
        try:
            from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

            dao = MemoryNodeDAO(db)
            nodes = dao.recall(
                query=query or "",
                tags=list(tags or []),
                limit=limit,
                user_id=self._user_id,
            )
            return [self._safe_node(n) for n in (nodes or [])]
        except Exception as exc:
            logger.warning("[AINDYMemoryBridge.recall_all_agents] failed: %s", exc)
            return []
        finally:
            db.close()
