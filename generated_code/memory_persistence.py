# memory_persistence.py
# ==========================================
# Durable memory persistence for Memory Bridge
# - Uses unified Base from base.py
# - JSONB + GIN for tag queries
# - Safe transactions, UUID validation
# - Reserved attr 'metadata' renamed to 'extra'
# ==========================================

from __future__ import annotations

from datetime import datetime
import uuid
from typing import List, Optional

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Text,
    ForeignKey,
    Index,
    func,
    or_,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from base import Base  # <- unify ORM Base with the rest of the project


# -------------------------
# ORM Models
# -------------------------
class MemoryNodeModel(Base):
    """Database model for memory nodes."""
    __tablename__ = "memory_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    # JSONB for efficient contains queries; GIN index created below
    tags = Column(JSONB, nullable=False, default=list)
    node_type = Column(String(50), nullable=False)
    # DB-side timestamps for consistency
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    # 'metadata' is a reserved attribute on mapped classes — use 'extra'
    extra = Column(JSONB, default=dict, nullable=False)


# GIN index on tags for fast membership checks
Index("ix_memory_nodes_tags_gin", MemoryNodeModel.tags, postgresql_using="gin")


class MemoryLinkModel(Base):
    """Database model for memory node relationships."""
    __tablename__ = "memory_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_node_id = Column(UUID(as_uuid=True), ForeignKey("memory_nodes.id", ondelete="CASCADE"), nullable=False)
    target_node_id = Column(UUID(as_uuid=True), ForeignKey("memory_nodes.id", ondelete="CASCADE"), nullable=False)
    link_type = Column(String(50), nullable=False)
    strength = Column(String(20), default="medium", nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

# Practical indexes/constraint for link lookups + dedupe
Index("ix_memory_links_source", MemoryLinkModel.source_node_id)
Index("ix_memory_links_target", MemoryLinkModel.target_node_id)
Index(
    "uq_memory_links_unique",
    MemoryLinkModel.source_node_id,
    MemoryLinkModel.target_node_id,
    MemoryLinkModel.link_type,
    unique=True,
)


# -------------------------
# DAO
# -------------------------
class MemoryNodeDAO:
    """Data Access Object for memory persistence operations."""

    def __init__(self, db: Session):
        self.db = db

    # -------- Save / Load --------
    def save_memory_node(self, memory_node: "MemoryNode") -> MemoryNodeModel:
        """
        Save a MemoryNode-ish object to DB.
        Expects attributes: id (optional), content, tags (list), node_type (opt), extra (opt).
        """
        try:
            # Validate or generate UUID
            node_id: uuid.UUID
            raw_id = getattr(memory_node, "id", None)
            if raw_id:
                try:
                    node_id = uuid.UUID(str(raw_id))
                except ValueError:
                    node_id = uuid.uuid4()
            else:
                node_id = uuid.uuid4()

            db_node = MemoryNodeModel(
                id=node_id,
                content=str(getattr(memory_node, "content", "")),
                tags=list(getattr(memory_node, "tags", [])),
                node_type=getattr(memory_node, "node_type", "generic"),
                extra=getattr(memory_node, "extra", {}),
            )

            self.db.add(db_node)
            self.db.commit()
            self.db.refresh(db_node)
            return db_node
        except SQLAlchemyError:
            self.db.rollback()
            raise

    def load_memory_node(self, node_id: str) -> Optional["MemoryNode"]:
        """
        Load a MemoryNode from DB and reconstruct it.
        If your MemoryNode class implements `from_dict`, it will be used.
        """
        try:
            db_node = (
                self.db.query(MemoryNodeModel)
                .filter(MemoryNodeModel.id == uuid.UUID(str(node_id)))
                .first()
            )
        except (ValueError, SQLAlchemyError):
            return None

        if not db_node:
            return None

        # Import here to avoid circular imports
        from bridge import MemoryNode  # type: ignore

        # Prefer a factory if available
        if hasattr(MemoryNode, "from_dict"):
            return MemoryNode.from_dict(
                {
                    "id": str(db_node.id),
                    "content": db_node.content,
                    "tags": db_node.tags,
                    "node_type": db_node.node_type,
                    "extra": db_node.extra,
                    "created_at": db_node.created_at,
                    "updated_at": db_node.updated_at,
                }
            )

        # Fallback: construct directly and set extras
        node = MemoryNode(content=db_node.content, tags=db_node.tags, id=str(db_node.id))
        node.node_type = db_node.node_type
        node.extra = db_node.extra
        node.created_at = db_node.created_at
        node.updated_at = db_node.updated_at
        return node

    # -------- Query --------
    def find_by_tags(self, tags: List[str], limit: int = 100, mode: str = "AND") -> List["MemoryNode"]:
        """
        Find memory nodes by tags.

        mode="AND" (default): requires all tags
        mode="OR": requires any tag
        """
        query = self.db.query(MemoryNodeModel)

        tags = [t for t in (tags or []) if t]
        if tags:
            if mode.upper() == "OR":
                query = query.filter(or_(*[MemoryNodeModel.tags.contains([t]) for t in tags]))
            else:
                # AND semantics (has all tags)
                for t in tags:
                    query = query.filter(MemoryNodeModel.tags.contains([t]))

        db_nodes = query.limit(limit).all()

        # Reconstruct in-process nodes without N+1 round-trips
        from bridge import MemoryNode  # type: ignore

        results: List["MemoryNode"] = []
        for n in db_nodes:
            if hasattr(MemoryNode, "from_dict"):
                node = MemoryNode.from_dict(
                    {
                        "id": str(n.id),
                        "content": n.content,
                        "tags": n.tags,
                        "node_type": n.node_type,
                        "extra": n.extra,
                        "created_at": n.created_at,
                        "updated_at": n.updated_at,
                    }
                )
            else:
                node = MemoryNode(content=n.content, tags=n.tags, id=str(n.id))
                node.node_type = n.node_type
                node.extra = n.extra
                node.created_at = n.created_at
                node.updated_at = n.updated_at
            results.append(node)

        return results

    # -------- Links --------
    def create_link(self, source_id: str, target_id: str, link_type: str = "related") -> MemoryLinkModel:
        """
        Create a relationship between two memory nodes.
        Prevents self-links and raises on FK/mutex violations.
        """
        sid = uuid.UUID(str(source_id))
        tid = uuid.UUID(str(target_id))
        if sid == tid:
            raise ValueError("source_id and target_id cannot be the same")

        # Optional existence check
        count = (
            self.db.query(MemoryNodeModel.id)
            .filter(MemoryNodeModel.id.in_([sid, tid]))
            .count()
        )
        if count != 2:
            raise ValueError("source and/or target node does not exist")

        link = MemoryLinkModel(
            source_node_id=sid,
            target_node_id=tid,
            link_type=link_type,
        )

        try:
            self.db.add(link)
            self.db.commit()
            self.db.refresh(link)
            return link
        except SQLAlchemyError:
            self.db.rollback()
            raise
