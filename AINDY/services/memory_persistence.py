from __future__ import annotations

from datetime import datetime
import uuid
from typing import List, Optional

from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Index, func, or_
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from utils import prepare_input_text

# import your project's Base (must exist)
from db.database import Base

def save_memory_node(self, memory_node: 'MemoryNode'):
    cleaned_content = prepare_input_text(memory_node.content, limit=300)
    db_node = MemoryNodeModel(
        content=cleaned_content,
        tags=memory_node.tags,
        node_type=memory_node.node_type,
        metadata=getattr(memory_node, 'metadata', {})
    )

class MemoryNodeModel(Base):
    __tablename__ = "memory_nodes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    tags = Column(JSONB, nullable=False, default=list)
    node_type = Column(String(50), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    extra = Column(JSONB, default=dict, nullable=False)


Index("ix_memory_nodes_tags_gin", MemoryNodeModel.tags, postgresql_using="gin")


class MemoryLinkModel(Base):
    __tablename__ = "memory_links"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_node_id = Column(UUID(as_uuid=True), ForeignKey("memory_nodes.id", ondelete="CASCADE"), nullable=False)
    target_node_id = Column(UUID(as_uuid=True), ForeignKey("memory_nodes.id", ondelete="CASCADE"), nullable=False)
    link_type = Column(String(50), nullable=False)
    strength = Column(String(20), default="medium", nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


Index("ix_memory_links_source", MemoryLinkModel.source_node_id)
Index("ix_memory_links_target", MemoryLinkModel.target_node_id)
Index("uq_memory_links_unique", MemoryLinkModel.source_node_id, MemoryLinkModel.target_node_id, MemoryLinkModel.link_type, unique=True)


class MemoryNodeDAO:
    """Simple DAO — requires a SQLAlchemy Session"""

    def __init__(self, db: Session):
        self.db = db

    def save_memory_node(self, memory_node) -> MemoryNodeModel:
        try:
            raw_id = getattr(memory_node, "id", None)
            node_id = uuid.uuid4() if not raw_id else (uuid.UUID(str(raw_id)) if raw_id else uuid.uuid4())

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

    def load_memory_node(self, node_id: str):
        try:
            db_node = self.db.query(MemoryNodeModel).filter(MemoryNodeModel.id == uuid.UUID(str(node_id))).first()
        except Exception:
            return None
        if not db_node:
            return None
        # return a simple dict representation (keeps DTO simple)
        return {
            "id": str(db_node.id),
            "content": db_node.content,
            "tags": db_node.tags,
            "node_type": db_node.node_type,
            "extra": db_node.extra,
            "created_at": db_node.created_at,
            "updated_at": db_node.updated_at,
        }

    def find_by_tags(self, tags: List[str], limit: int = 100, mode: str = "AND"):
        query = self.db.query(MemoryNodeModel)
        tags = [t for t in (tags or []) if t]
        if tags:
            if mode.upper() == "OR":
                query = query.filter(or_(*[MemoryNodeModel.tags.contains([t]) for t in tags]))
            else:
                for t in tags:
                    query = query.filter(MemoryNodeModel.tags.contains([t]))
        db_nodes = query.limit(limit).all()
        return [
            {
                "id": str(n.id),
                "content": n.content,
                "tags": n.tags,
                "node_type": n.node_type,
                "extra": n.extra,
                "created_at": n.created_at,
                "updated_at": n.updated_at,
            }
            for n in db_nodes
        ]

    def create_link(self, source_id: str, target_id: str, link_type: str = "related"):
        sid = uuid.UUID(str(source_id))
        tid = uuid.UUID(str(target_id))
        if sid == tid:
            raise ValueError("source_id and target_id cannot be the same")
        count = self.db.query(MemoryNodeModel.id).filter(MemoryNodeModel.id.in_([sid, tid])).count()
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
                "created_at": link.created_at,
            }
        except SQLAlchemyError:
            self.db.rollback()
            raise
