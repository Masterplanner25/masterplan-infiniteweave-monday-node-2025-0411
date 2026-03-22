from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import func

from db.models.memory_trace import MemoryTrace
from db.models.memory_trace_node import MemoryTraceNode

logger = logging.getLogger(__name__)


class MemoryTraceDAO:
    def __init__(self, db):
        self.db = db

    def create_trace(
        self,
        *,
        user_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        source: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> dict:
        trace = MemoryTrace(
            user_id=user_id,
            title=title,
            description=description,
            source=source,
            extra=extra,
        )
        if trace.id is None:
            trace.id = uuid.uuid4()
        self.db.add(trace)
        self.db.commit()
        self.db.refresh(trace)
        return self._trace_to_dict(trace)

    def append_node(
        self,
        *,
        trace_id: str,
        node_id: str,
        user_id: str,
        position: Optional[int] = None,
    ) -> Optional[dict]:
        trace = self._get_trace_model(trace_id, user_id=user_id)
        if not trace:
            return None

        if position is None:
            position = self._next_position(trace.id)

        trace_node = MemoryTraceNode(
            trace_id=trace.id,
            node_id=uuid.UUID(str(node_id)),
            position=position,
        )
        if trace_node.id is None:
            trace_node.id = uuid.uuid4()

        self.db.add(trace_node)
        self.db.commit()
        self.db.refresh(trace_node)
        return self._trace_node_to_dict(trace_node)

    def get_trace(self, trace_id: str, *, user_id: str) -> Optional[dict]:
        trace = self._get_trace_model(trace_id, user_id=user_id)
        if not trace:
            return None
        return self._trace_to_dict(trace)

    def list_traces(self, *, user_id: str, limit: int = 50) -> list[dict]:
        rows = (
            self.db.query(MemoryTrace)
            .filter(MemoryTrace.user_id == user_id)
            .order_by(MemoryTrace.created_at.desc())
            .limit(limit)
            .all()
        )
        if not isinstance(rows, list):
            return []
        return [self._trace_to_dict(row) for row in rows]

    def get_trace_nodes(
        self,
        trace_id: str,
        *,
        user_id: str,
        limit: int = 200,
    ) -> list[dict]:
        trace = self._get_trace_model(trace_id, user_id=user_id)
        if not trace:
            return []

        rows = (
            self.db.query(MemoryTraceNode)
            .filter(MemoryTraceNode.trace_id == trace.id)
            .order_by(MemoryTraceNode.position.asc())
            .limit(limit)
            .all()
        )
        if not isinstance(rows, list):
            return []
        return [self._trace_node_to_dict(row) for row in rows]

    def _next_position(self, trace_id: uuid.UUID) -> int:
        current = (
            self.db.query(func.max(MemoryTraceNode.position))
            .filter(MemoryTraceNode.trace_id == trace_id)
            .scalar()
        )
        try:
            current = int(current) if current is not None else -1
        except Exception:
            current = -1
        return current + 1

    def _get_trace_model(self, trace_id: str, *, user_id: str) -> Optional[MemoryTrace]:
        try:
            trace_uuid = uuid.UUID(str(trace_id))
        except Exception:
            return None
        return (
            self.db.query(MemoryTrace)
            .filter(MemoryTrace.id == trace_uuid, MemoryTrace.user_id == user_id)
            .first()
        )

    def _trace_to_dict(self, trace: MemoryTrace) -> dict:
        return {
            "id": str(trace.id),
            "user_id": trace.user_id,
            "title": trace.title,
            "description": trace.description,
            "source": trace.source,
            "extra": trace.extra or {},
            "created_at": trace.created_at.isoformat() if trace.created_at else None,
            "updated_at": trace.updated_at.isoformat() if trace.updated_at else None,
        }

    def _trace_node_to_dict(self, trace_node: MemoryTraceNode) -> dict:
        return {
            "id": str(trace_node.id),
            "trace_id": str(trace_node.trace_id),
            "node_id": str(trace_node.node_id),
            "position": trace_node.position,
            "created_at": trace_node.created_at.isoformat() if trace_node.created_at else None,
        }
