from __future__ import annotations

from datetime import datetime
import uuid
from typing import List, Optional

from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Index, func, or_, event, Integer, Float, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from pgvector.sqlalchemy import Vector
from AINDY.utils import prepare_input_text
from AINDY.platform_layer.trace_context import get_current_trace_id
from AINDY.platform_layer.user_ids import parse_user_id

# import your project's Base (must exist)
from AINDY.db.database import Base

VALID_NODE_TYPES = {"decision", "outcome", "insight", "relationship"}
VALID_MEMORY_TYPES = {"decision", "outcome", "failure", "insight"}

class MemoryNodeModel(Base):
    __tablename__ = "memory_nodes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    tags = Column(JSONB, nullable=False, default=list)
    node_type = Column(String(50), nullable=False)
    source = Column(String(255), nullable=True)
    source_agent = Column(String, nullable=True, index=True)
    is_shared = Column(Boolean, nullable=False, default=False)
    visibility = Column(String(16), nullable=False, default="private", index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    source_event_id = Column(UUID(as_uuid=True), ForeignKey("system_events.id"), nullable=True, index=True)
    root_event_id = Column(UUID(as_uuid=True), ForeignKey("system_events.id"), nullable=True, index=True)
    causal_depth = Column(Integer, nullable=False, default=0)
    impact_score = Column(Float, nullable=False, default=0.0)
    memory_type = Column(String(32), nullable=False, default="insight", index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    extra = Column(JSONB, default=dict, nullable=False)
    embedding = Column(Vector(1536), nullable=True)
    embedding_pending = Column(Boolean, nullable=False, default=True, index=True)
    embedding_status = Column(String(16), nullable=False, default="pending", index=True)
    success_count = Column(Integer, nullable=False, default=0)
    failure_count = Column(Integer, nullable=False, default=0)
    usage_count = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    last_outcome = Column(String, nullable=True)
    weight = Column(Float, nullable=False, default=1.0)
    # Memory Address Space (MAS) path fields — added Sprint MAS
    path = Column(String(512), nullable=True, index=True)
    namespace = Column(String(128), nullable=True, index=True)
    addr_type = Column(String(128), nullable=True, index=True)
    parent_path = Column(String(512), nullable=True, index=True)


Index("ix_memory_nodes_tags_gin", MemoryNodeModel.tags, postgresql_using="gin")


@event.listens_for(MemoryNodeModel, "before_insert")
@event.listens_for(MemoryNodeModel, "before_update")
def validate_node_type(mapper, connection, target):
    if target.node_type is not None and target.node_type not in VALID_NODE_TYPES:
        raise ValueError(
            f"Invalid node_type '{target.node_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_NODE_TYPES))}"
        )
    if target.memory_type is not None and target.memory_type not in VALID_MEMORY_TYPES:
        raise ValueError(
            f"Invalid memory_type '{target.memory_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_MEMORY_TYPES))}"
        )


class MemoryLinkModel(Base):
    __tablename__ = "memory_links"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_node_id = Column(UUID(as_uuid=True), ForeignKey("memory_nodes.id", ondelete="CASCADE"), nullable=False)
    target_node_id = Column(UUID(as_uuid=True), ForeignKey("memory_nodes.id", ondelete="CASCADE"), nullable=False)
    link_type = Column(String(50), nullable=False)
    strength = Column(String(20), default="medium", nullable=False)
    weight = Column(Float, default=0.5, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


Index("ix_memory_links_source", MemoryLinkModel.source_node_id)
Index("ix_memory_links_target", MemoryLinkModel.target_node_id)
Index("uq_memory_links_unique", MemoryLinkModel.source_node_id, MemoryLinkModel.target_node_id, MemoryLinkModel.link_type, unique=True)


class MemoryNodeDAO:
    """Simple DAO - requires a SQLAlchemy Session"""

    def __init__(self, db: Session):
        self.db = db

    def _is_postgres(self) -> bool:
        bind = getattr(self.db, "bind", None)
        dialect = getattr(bind, "dialect", None)
        return getattr(dialect, "name", "").lower().startswith("postgres")

    @staticmethod
    def _tags_match(node_tags: list[str] | None, query_tags: list[str], mode: str) -> bool:
        current = {str(tag) for tag in (node_tags or []) if tag is not None}
        requested = {str(tag) for tag in (query_tags or []) if tag}
        if not requested:
            return True
        if mode.upper() == "OR":
            return bool(current & requested)
        return requested.issubset(current)

    def save_memory_node(self, memory_node) -> MemoryNodeModel:
        try:
            raw_id = getattr(memory_node, "id", None)
            node_id = uuid.uuid4() if not raw_id else (uuid.UUID(str(raw_id)) if raw_id else uuid.uuid4())

            db_node = MemoryNodeModel(
                id=node_id,
                content=str(getattr(memory_node, "content", "")),
                tags=list(getattr(memory_node, "tags", [])),
                node_type=getattr(memory_node, "node_type", None),
                memory_type=getattr(memory_node, "memory_type", getattr(memory_node, "node_type", "insight")),
                source=getattr(memory_node, "source", None),
                source_agent=getattr(memory_node, "source_agent", None),
                is_shared=bool(getattr(memory_node, "is_shared", False)),
                visibility=str(getattr(memory_node, "visibility", "shared" if getattr(memory_node, "is_shared", False) else "private")),
                user_id=getattr(memory_node, "user_id", None),
                source_event_id=getattr(memory_node, "source_event_id", None),
                root_event_id=getattr(memory_node, "root_event_id", None),
                causal_depth=getattr(memory_node, "causal_depth", 0),
                impact_score=getattr(memory_node, "impact_score", 0.0),
                embedding_pending=bool(getattr(memory_node, "embedding_pending", True)),
                embedding_status=getattr(memory_node, "embedding_status", "pending"),
                extra={
                    **(getattr(memory_node, "extra", {}) or {}),
                    **(
                        {"trace_id": get_current_trace_id()}
                        if get_current_trace_id()
                        and not (getattr(memory_node, "extra", {}) or {}).get("trace_id")
                        else {}
                    ),
                },
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
            "source": db_node.source,
            "user_id": str(db_node.user_id) if db_node.user_id else None,
            "source_event_id": str(db_node.source_event_id) if db_node.source_event_id else None,
            "root_event_id": str(db_node.root_event_id) if db_node.root_event_id else None,
            "causal_depth": db_node.causal_depth,
            "impact_score": db_node.impact_score,
            "memory_type": db_node.memory_type,
            "embedding_pending": db_node.embedding_pending,
            "embedding_status": db_node.embedding_status,
            "extra": db_node.extra,
            "created_at": db_node.created_at,
            "updated_at": db_node.updated_at,
        }

    def find_by_tags(self, tags: List[str], limit: int = 100, mode: str = "AND", user_id: Optional[str] = None):
        query = self.db.query(MemoryNodeModel)
        owner_user_id = parse_user_id(user_id)
        if owner_user_id:
            query = query.filter(MemoryNodeModel.user_id == owner_user_id)
        else:
            query = query.filter(MemoryNodeModel.visibility.in_(["shared", "global"]))
        tags = [t for t in (tags or []) if t]
        if tags:
            if self._is_postgres():
                if mode.upper() == "OR":
                    query = query.filter(or_(*[MemoryNodeModel.tags.contains([t]) for t in tags]))
                else:
                    for t in tags:
                        query = query.filter(MemoryNodeModel.tags.contains([t]))
                db_nodes = query.limit(limit).all()
            else:
                db_nodes = [
                    node for node in query.all()
                    if self._tags_match(getattr(node, "tags", []), tags, mode)
                ][:limit]
        else:
            db_nodes = query.limit(limit).all()
        return [
            {
                "id": str(n.id),
                "content": n.content,
                "tags": n.tags,
                "node_type": n.node_type,
                "source": n.source,
                "user_id": str(n.user_id) if n.user_id else None,
                "source_event_id": str(n.source_event_id) if n.source_event_id else None,
                "root_event_id": str(n.root_event_id) if n.root_event_id else None,
                "causal_depth": n.causal_depth,
                "impact_score": n.impact_score,
                "memory_type": n.memory_type,
                "embedding_pending": n.embedding_pending,
                "embedding_status": n.embedding_status,
                "extra": n.extra,
                "created_at": n.created_at,
                "updated_at": n.updated_at,
            }
            for n in db_nodes
        ]

    def create_link(self, source_id: str, target_id: str, link_type: str = "related", weight: float = 0.5):
        sid = uuid.UUID(str(source_id))
        tid = uuid.UUID(str(target_id))
        if sid == tid:
            raise ValueError("source_id and target_id cannot be the same")
        count = self.db.query(MemoryNodeModel.id).filter(MemoryNodeModel.id.in_([sid, tid])).count()
        if count != 2:
            raise ValueError("source and/or target node does not exist")
        link = MemoryLinkModel(source_node_id=sid, target_node_id=tid, link_type=link_type, weight=weight)
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
                "weight": link.weight,
                "created_at": link.created_at,
            }
        except SQLAlchemyError:
            self.db.rollback()
            raise
