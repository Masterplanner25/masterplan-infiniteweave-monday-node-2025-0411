"""
MemoryNodeDAO — canonical data-access object for memory_nodes and memory_links.

All memory persistence goes through this class. Import and use from routes and
services; do not instantiate MemoryNodeDAO from bridge.py (bridge calls are
routed through services.memory_persistence.MemoryNodeDAO for backward compat).
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from services.memory_persistence import MemoryNodeModel, MemoryLinkModel


class MemoryNodeDAO:
    """Canonical DAO for memory_nodes and memory_links tables."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _node_to_dict(self, n: MemoryNodeModel) -> dict:
        return {
            "id": str(n.id),
            "content": n.content,
            "tags": n.tags,
            "node_type": n.node_type,
            "source": n.source,
            "user_id": n.user_id,
            "extra": n.extra,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "updated_at": n.updated_at.isoformat() if n.updated_at else None,
        }

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def save(
        self,
        content: str,
        source: str = None,
        tags: List[str] = None,
        user_id: str = None,
        node_type: str = "generic",
        extra: dict = None,
    ) -> dict:
        """Insert a new memory node and return its dict representation."""
        db_node = MemoryNodeModel(
            content=content,
            tags=tags or [],
            node_type=node_type,
            source=source,
            user_id=user_id,
            extra=extra or {},
        )
        try:
            self.db.add(db_node)
            self.db.commit()
            self.db.refresh(db_node)
            return self._node_to_dict(db_node)
        except SQLAlchemyError:
            self.db.rollback()
            raise

    def get_by_id(self, node_id: str) -> Optional[dict]:
        """Return a node dict by UUID string, or None if not found."""
        try:
            node_uuid = uuid.UUID(str(node_id))
        except ValueError:
            return None
        db_node = self.db.query(MemoryNodeModel).filter(MemoryNodeModel.id == node_uuid).first()
        if not db_node:
            return None
        return self._node_to_dict(db_node)

    def get_by_tags(self, tags: List[str], limit: int = 50, mode: str = "AND") -> List[dict]:
        """
        Return nodes whose tags array contains the given tags.
        mode='AND'  — all tags must be present.
        mode='OR'   — any tag must be present.
        """
        query = self.db.query(MemoryNodeModel)
        clean_tags = [t for t in (tags or []) if t]
        if clean_tags:
            if mode.upper() == "OR":
                query = query.filter(
                    or_(*[MemoryNodeModel.tags.contains([t]) for t in clean_tags])
                )
            else:
                for t in clean_tags:
                    query = query.filter(MemoryNodeModel.tags.contains([t]))
        return [self._node_to_dict(n) for n in query.limit(limit).all()]

    # ------------------------------------------------------------------
    # Graph query: get nodes linked to a given node
    # ------------------------------------------------------------------

    def get_linked_nodes(self, node_id: str, direction: str = "both") -> List[dict]:
        """
        Return all nodes directly linked to node_id.

        direction='out'  — nodes this node points to (source → target)
        direction='in'   — nodes that point to this node (target ← source)
        direction='both' — union of both directions (default)
        """
        try:
            node_uuid = uuid.UUID(str(node_id))
        except ValueError:
            return []

        linked: List[dict] = []

        if direction in ("out", "both"):
            links = (
                self.db.query(MemoryLinkModel)
                .filter(MemoryLinkModel.source_node_id == node_uuid)
                .all()
            )
            target_ids = [lnk.target_node_id for lnk in links]
            if target_ids:
                nodes = (
                    self.db.query(MemoryNodeModel)
                    .filter(MemoryNodeModel.id.in_(target_ids))
                    .all()
                )
                linked.extend(self._node_to_dict(n) for n in nodes)

        if direction in ("in", "both"):
            links = (
                self.db.query(MemoryLinkModel)
                .filter(MemoryLinkModel.target_node_id == node_uuid)
                .all()
            )
            source_ids = [lnk.source_node_id for lnk in links]
            if source_ids:
                # deduplicate against already-added nodes
                seen_ids = {d["id"] for d in linked}
                nodes = (
                    self.db.query(MemoryNodeModel)
                    .filter(MemoryNodeModel.id.in_(source_ids))
                    .all()
                )
                linked.extend(
                    self._node_to_dict(n) for n in nodes if str(n.id) not in seen_ids
                )

        return linked

    # ------------------------------------------------------------------
    # Link operations
    # ------------------------------------------------------------------

    def create_link(
        self, source_id: str, target_id: str, link_type: str = "related"
    ) -> dict:
        """Create a directed link between two existing nodes."""
        sid = uuid.UUID(str(source_id))
        tid = uuid.UUID(str(target_id))
        if sid == tid:
            raise ValueError("source_id and target_id cannot be the same")
        count = (
            self.db.query(MemoryNodeModel.id)
            .filter(MemoryNodeModel.id.in_([sid, tid]))
            .count()
        )
        if count != 2:
            raise ValueError("source and/or target node does not exist")
        link = MemoryLinkModel(source_node_id=sid, target_node_id=tid, link_type=link_type)
        try:
            self.db.add(link)
            self.db.commit()
            self.db.refresh(link)
            return {
                "id": str(link.id),
                "source_node_id": str(link.source_node_id),
                "target_node_id": str(link.target_node_id),
                "link_type": link.link_type,
                "strength": link.strength,
                "created_at": link.created_at.isoformat() if link.created_at else None,
            }
        except SQLAlchemyError:
            self.db.rollback()
            raise
