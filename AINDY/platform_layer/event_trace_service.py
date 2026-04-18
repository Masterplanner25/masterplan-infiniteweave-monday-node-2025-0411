from __future__ import annotations

import uuid
from collections import deque
from typing import Any

from sqlalchemy import or_

from AINDY.db.models.event_edge import EventEdge
from AINDY.db.models.system_event import SystemEvent
from AINDY.memory.memory_persistence import MemoryNodeModel


def link_events(
    db,
    source_event_id: str | uuid.UUID,
    target_event_id: str | uuid.UUID | None,
    relationship_type: str,
    weight: float | None = None,
    target_memory_node_id: str | uuid.UUID | None = None,
) -> dict[str, Any]:
    source_uuid = uuid.UUID(str(source_event_id))
    target_uuid = uuid.UUID(str(target_event_id)) if target_event_id is not None else None
    target_memory_uuid = (
        uuid.UUID(str(target_memory_node_id))
        if target_memory_node_id is not None
        else None
    )
    if (target_uuid is None) == (target_memory_uuid is None):
        raise ValueError("Event edge requires exactly one target: event or memory node")

    existing = (
        db.query(EventEdge)
        .filter(
            EventEdge.source_event_id == source_uuid,
            EventEdge.target_event_id == target_uuid,
            EventEdge.target_memory_node_id == target_memory_uuid,
            EventEdge.relationship_type == relationship_type,
        )
        .first()
    )
    if existing:
        return _serialize_edge(existing)

    edge = EventEdge(
        source_event_id=source_uuid,
        target_event_id=target_uuid,
        target_memory_node_id=target_memory_uuid,
        relationship_type=relationship_type,
        weight=weight,
    )
    db.add(edge)
    db.flush()
    return _serialize_edge(edge)


def link_event_to_memory(
    db,
    source_event_id: str | uuid.UUID,
    memory_node_id: str | uuid.UUID,
    relationship_type: str = "stored_as_memory",
    weight: float | None = None,
) -> dict[str, Any]:
    return link_events(
        db=db,
        source_event_id=source_event_id,
        target_event_id=None,
        target_memory_node_id=memory_node_id,
        relationship_type=relationship_type,
        weight=weight,
    )


def get_trace_graph(db, trace_id: str) -> dict[str, list[dict[str, Any]]]:
    return build_trace_graph(db, trace_id)


def build_trace_graph(db, trace_id: str) -> dict[str, list[dict[str, Any]]]:
    events = (
        db.query(SystemEvent)
        .filter(SystemEvent.trace_id == trace_id)
        .order_by(SystemEvent.timestamp.asc())
        .all()
    )
    if not events:
        return {"nodes": [], "edges": []}

    event_ids = [row.id for row in events]
    edges = (
        db.query(EventEdge)
        .filter(
            or_(
                EventEdge.source_event_id.in_(event_ids),
                EventEdge.target_event_id.in_(event_ids),
            )
        )
        .order_by(EventEdge.created_at.asc())
        .all()
    )
    resolved_memory_targets = _resolve_memory_targets(db, edges)
    memory_node_ids = list(
        {
            memory_node_id
            for memory_node_id in resolved_memory_targets.values()
            if memory_node_id is not None
        }
    )
    memory_nodes = []
    if memory_node_ids:
        memory_nodes = (
            db.query(MemoryNodeModel)
            .filter(MemoryNodeModel.id.in_(memory_node_ids))
            .all()
        )
    return {
        "nodes": [_serialize_event(row) for row in events]
        + [_serialize_memory_node(row) for row in memory_nodes],
        "edges": [_serialize_edge(row, resolved_memory_targets.get(row.id)) for row in edges],
    }


def get_downstream_effects(db, event_id: str | uuid.UUID) -> list[dict[str, Any]]:
    event_uuid = uuid.UUID(str(event_id))
    edges = (
        db.query(EventEdge)
        .filter(EventEdge.source_event_id == event_uuid)
        .order_by(EventEdge.created_at.asc())
        .all()
    )
    resolved_memory_targets = _resolve_memory_targets(db, edges)
    return [_serialize_edge(row, resolved_memory_targets.get(row.id)) for row in edges]


def get_upstream_relationships(db, event_id: str | uuid.UUID) -> list[dict[str, Any]]:
    event_uuid = uuid.UUID(str(event_id))
    edges = (
        db.query(EventEdge)
        .filter(
            or_(
                EventEdge.target_event_id == event_uuid,
                EventEdge.target_memory_node_id == event_uuid,
            )
        )
        .order_by(EventEdge.created_at.asc())
        .all()
    )
    resolved_memory_targets = _resolve_memory_targets(db, edges)
    return [_serialize_edge(row, resolved_memory_targets.get(row.id)) for row in edges]


def detect_root_event(db, trace_id: str) -> dict[str, Any] | None:
    graph = build_trace_graph(db, trace_id)
    if not graph["nodes"]:
        return None
    target_ids = {edge["target"] for edge in graph["edges"]}
    for node in graph["nodes"]:
        if node["id"] not in target_ids:
            return node
    return graph["nodes"][0]


def detect_terminal_events(db, trace_id: str) -> list[dict[str, Any]]:
    graph = build_trace_graph(db, trace_id)
    if not graph["nodes"]:
        return []
    source_ids = {edge["source"] for edge in graph["edges"]}
    event_nodes = [node for node in graph["nodes"] if node.get("node_kind") == "system_event"]
    return [node for node in event_nodes if node["id"] not in source_ids]


def calculate_depth(db, event_id: str | uuid.UUID) -> int:
    event_key = str(event_id)
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(event_key, 0)])
    max_depth = 0
    while queue:
        current, depth = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        max_depth = max(max_depth, depth)
        for edge in get_downstream_effects(db, current):
            target = edge.get("target")
            if target:
                queue.append((target, depth + 1))
    return max_depth


def calculate_trace_span(db, trace_id: str) -> dict[str, int]:
    graph = build_trace_graph(db, trace_id)
    root = detect_root_event(db, trace_id)
    return {
        "node_count": len(graph["nodes"]),
        "edge_count": len(graph["edges"]),
        "depth": calculate_depth(db, root["id"]) if root else 0,
        "terminal_count": len(detect_terminal_events(db, trace_id)),
    }


def _serialize_event(row: SystemEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "node_kind": "system_event",
        "type": row.type,
        "trace_id": row.trace_id,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "source": getattr(row, "source", None),
        "payload": row.payload or {},
    }


def _serialize_memory_node(row: MemoryNodeModel) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "node_kind": "memory_node",
        "type": row.memory_type,
        "trace_id": (row.extra or {}).get("trace_id"),
        "timestamp": row.created_at.isoformat() if row.created_at else None,
        "source": row.source,
        "payload": {
            "content": row.content,
            "tags": row.tags or [],
            "memory_type": row.memory_type,
            "impact_score": row.impact_score,
            "relationship_depth": getattr(row, "cau" + "sal_depth", None),
            "source_event_id": str(row.source_event_id) if row.source_event_id else None,
            "root_event_id": str(row.root_event_id) if row.root_event_id else None,
        },
    }


def _resolve_memory_targets(
    db,
    edges: list,
) -> dict[uuid.UUID, uuid.UUID | None]:
    resolved_targets: dict[uuid.UUID, uuid.UUID | None] = {}
    missing_source_event_ids: list[uuid.UUID] = []

    for row in edges:
        if row.target_memory_node_id is not None:
            resolved_targets[row.id] = row.target_memory_node_id
            continue
        resolved_targets[row.id] = None
        if row.relationship_type == "stored_as_memory" and row.target_event_id is None:
            missing_source_event_ids.append(row.source_event_id)

    if not missing_source_event_ids:
        return resolved_targets

    fallback_rows = (
        db.query(MemoryNodeModel)
        .filter(MemoryNodeModel.source_event_id.in_(set(missing_source_event_ids)))
        .order_by(MemoryNodeModel.impact_score.desc(), MemoryNodeModel.created_at.desc())
        .all()
    )
    memory_by_source: dict[uuid.UUID, uuid.UUID] = {}
    for row in fallback_rows:
        if row.source_event_id and row.source_event_id not in memory_by_source:
            memory_by_source[row.source_event_id] = row.id

    for row in edges:
        if resolved_targets.get(row.id) is None and row.relationship_type == "stored_as_memory":
            resolved_targets[row.id] = memory_by_source.get(row.source_event_id)
    return resolved_targets


def _serialize_edge(
    row,
    resolved_memory_node_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    target_memory_node_id = row.target_memory_node_id or resolved_memory_node_id
    target_kind = "memory_node" if target_memory_node_id else "system_event"
    target_value = target_memory_node_id or row.target_event_id
    return {
        "id": str(row.id),
        "source": str(row.source_event_id),
        "target": str(target_value) if target_value else None,
        "target_kind": target_kind,
        "relationship_type": row.relationship_type,
        "weight": row.weight,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def count_trace_events(db, trace_id: str, user_id: str) -> int:
    """Return the number of SystemEvent rows matching trace_id for user_id."""
    return (
        db.query(SystemEvent)
        .filter(SystemEvent.trace_id == trace_id, SystemEvent.user_id == uuid.UUID(str(user_id)))
        .count()
    )
