from __future__ import annotations

import uuid
from collections import deque
from typing import Any

from sqlalchemy import or_

from AINDY.db.models.ripple_edge import RippleEdge
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
        raise ValueError("Ripple edge requires exactly one target: event or memory node")

    existing = (
        db.query(RippleEdge)
        .filter(
            RippleEdge.source_event_id == source_uuid,
            RippleEdge.target_event_id == target_uuid,
            RippleEdge.target_memory_node_id == target_memory_uuid,
            RippleEdge.relationship_type == relationship_type,
        )
        .first()
    )
    if existing:
        return _serialize_edge(existing)

    edge = RippleEdge(
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
        db.query(RippleEdge)
        .filter(
            or_(
                RippleEdge.source_event_id.in_(event_ids),
                RippleEdge.target_event_id.in_(event_ids),
            )
        )
        .order_by(RippleEdge.created_at.asc())
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
        "nodes": [_serialize_event(row) for row in events] + [_serialize_memory_node(row) for row in memory_nodes],
        "edges": [_serialize_edge(row, resolved_memory_targets.get(row.id)) for row in edges],
    }


def get_downstream_effects(db, event_id: str | uuid.UUID) -> list[dict[str, Any]]:
    event_uuid = uuid.UUID(str(event_id))
    edges = (
        db.query(RippleEdge)
        .filter(RippleEdge.source_event_id == event_uuid)
        .order_by(RippleEdge.created_at.asc())
        .all()
    )
    resolved_memory_targets = _resolve_memory_targets(db, edges)
    return [_serialize_edge(row, resolved_memory_targets.get(row.id)) for row in edges]


def get_upstream_causes(db, event_id: str | uuid.UUID) -> list[dict[str, Any]]:
    event_uuid = uuid.UUID(str(event_id))
    edges = (
        db.query(RippleEdge)
        .filter(
            or_(
                RippleEdge.target_event_id == event_uuid,
                RippleEdge.target_memory_node_id == event_uuid,
            )
        )
        .order_by(RippleEdge.created_at.asc())
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
            queue.append((edge["target"], depth + 1))
    return max_depth


def calculate_ripple_span(db, trace_id: str) -> dict[str, int]:
    graph = build_trace_graph(db, trace_id)
    root = detect_root_event(db, trace_id)
    return {
        "node_count": len(graph["nodes"]),
        "edge_count": len(graph["edges"]),
        "depth": calculate_depth(db, root["id"]) if root else 0,
        "terminal_count": len(detect_terminal_events(db, trace_id)),
    }


def detect_dominant_path(db, trace_id: str) -> list[dict[str, Any]]:
    graph = build_trace_graph(db, trace_id)
    if not graph["nodes"]:
        return []
    node_map = {node["id"]: node for node in graph["nodes"]}
    outgoing: dict[str, list[dict[str, Any]]] = {}
    for edge in graph["edges"]:
        outgoing.setdefault(edge["source"], []).append(edge)
    root = detect_root_event(db, trace_id)
    if not root:
        return []

    best_path: list[str] = []

    def _walk(node_id: str, path: list[str]) -> None:
        nonlocal best_path
        next_path = path + [node_id]
        if len(next_path) > len(best_path):
            best_path = next_path
        candidates = sorted(
            outgoing.get(node_id, []),
            key=lambda edge: (float(edge.get("weight") or 0.0), edge.get("relationship_type") == "caused_by"),
            reverse=True,
        )
        for edge in candidates:
            target = edge["target"]
            if target in next_path:
                continue
            _walk(target, next_path)

    _walk(root["id"], [])
    return [node_map[node_id] for node_id in best_path if node_id in node_map]


def detect_failure_clusters(db, trace_id: str) -> list[dict[str, Any]]:
    graph = build_trace_graph(db, trace_id)
    failures = [
        node for node in graph["nodes"]
        if node.get("node_kind") == "system_event"
        and ("failed" in str(node.get("type") or "").lower() or "error" in str(node.get("type") or "").lower())
    ]
    clustered: dict[str, dict[str, Any]] = {}
    for node in failures:
        key = str(node.get("type") or "unknown_failure")
        bucket = clustered.setdefault(
            key,
            {"type": key, "count": 0, "events": [], "latest_timestamp": None},
        )
        bucket["count"] += 1
        bucket["events"].append(node)
        timestamp = node.get("timestamp")
        if timestamp and (bucket["latest_timestamp"] is None or timestamp > bucket["latest_timestamp"]):
            bucket["latest_timestamp"] = timestamp
    return sorted(clustered.values(), key=lambda item: item["count"], reverse=True)


def generate_trace_insights(db, trace_id: str) -> dict[str, Any]:
    root_event = detect_root_event(db, trace_id)
    terminal_events = detect_terminal_events(db, trace_id)
    dominant_path = detect_dominant_path(db, trace_id)
    failure_clusters = detect_failure_clusters(db, trace_id)
    ripple_span = calculate_ripple_span(db, trace_id)

    explanation_parts = []
    if root_event:
        explanation_parts.append(f"Root cause starts at {root_event.get('type')}.")
    if dominant_path:
        path_types = " -> ".join(node.get("type", node.get("id")) for node in dominant_path[:6])
        explanation_parts.append(f"Dominant path: {path_types}.")
    if failure_clusters:
        top_failure = failure_clusters[0]
        explanation_parts.append(
            f"Primary failure cluster is {top_failure['type']} with {top_failure['count']} events."
        )
    if terminal_events:
        explanation_parts.append(f"{len(terminal_events)} terminal effects were detected.")

    recommendations: list[str] = []
    if failure_clusters:
        recommendations.append(f"Stabilize {failure_clusters[0]['type']} before retrying downstream execution.")
    if ripple_span.get("depth", 0) >= 4:
        recommendations.append("Inspect the dominant causal chain for excessive propagation depth.")
    if root_event and "memory" in str(root_event.get("type") or "").lower():
        recommendations.append("Review upstream memory write/retrieval behavior for causality drift.")
    if not recommendations:
        recommendations.append("Monitor the dominant path and recent terminal events for the next similar run.")

    return {
        "root_cause": root_event,
        "dominant_path": dominant_path,
        "failure_clusters": failure_clusters,
        "summary": " ".join(explanation_parts) if explanation_parts else "No causal insight available for this trace.",
        "recommendations": recommendations,
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
            "causal_depth": row.causal_depth,
            "source_event_id": str(row.source_event_id) if row.source_event_id else None,
            "root_event_id": str(row.root_event_id) if row.root_event_id else None,
        },
    }


def _resolve_memory_targets(
    db,
    edges: list[RippleEdge],
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
    row: RippleEdge,
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

