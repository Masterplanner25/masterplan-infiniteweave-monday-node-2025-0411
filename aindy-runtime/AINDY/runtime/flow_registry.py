"""
flow_registry.py — Runtime-safe dynamic flow registration.

Wraps FLOW_REGISTRY with a threading.Lock so concurrent API requests
cannot corrupt the registry during validate-then-write sequences.

Only simple edges (node_name → [next_node_name]) are supported for
dynamically registered flows; condition functions cannot be serialised
over HTTP.  Conditional routing still requires a startup-registered flow.
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Protects all writes to FLOW_REGISTRY and _DYNAMIC_META.
_registry_lock = threading.Lock()

# Serialisable metadata for every dynamically registered flow.
# Keyed by flow name; never contains Python callables.
_DYNAMIC_META: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate(
    name: str,
    nodes: list[str],
    edges: dict[str, list[str]],
    start: str,
    end: list[str],
) -> list[str]:
    """
    Return a list of human-readable error strings.  Empty list == valid.

    Checks performed:
    - name non-empty
    - all node names exist in NODE_REGISTRY
    - start and all end nodes are in the declared nodes list
    - edge source and target nodes are in the declared nodes list
    - no unreachable nodes (no inbound edge and not the start node)
    """
    from AINDY.runtime.flow_engine import NODE_REGISTRY  # lazy — avoids circular import at module load

    errors: list[str] = []
    node_set = set(nodes)

    if not name or not name.strip():
        errors.append("name must be a non-empty string")

    if not nodes:
        errors.append("nodes list must not be empty")
        return errors  # nothing more to validate

    # All declared nodes must be registered
    unknown = sorted(n for n in nodes if n not in NODE_REGISTRY)
    if unknown:
        errors.append(f"nodes not found in NODE_REGISTRY: {unknown}")

    # start must be a declared node
    if start not in node_set:
        errors.append(f"start node {start!r} not in nodes list")

    # end must be non-empty and every entry declared
    if not end:
        errors.append("end list must not be empty")
    else:
        bad_end = sorted(n for n in end if n not in node_set)
        if bad_end:
            errors.append(f"end nodes not in nodes list: {bad_end}")

    # Edge sources must be declared nodes
    bad_keys = sorted(k for k in edges if k not in node_set)
    if bad_keys:
        errors.append(f"edge source nodes not in nodes list: {bad_keys}")

    # Edge targets must be declared nodes
    for src, targets in edges.items():
        bad_targets = sorted(t for t in targets if t not in node_set)
        if bad_targets:
            errors.append(f"edge {src!r} → unknown targets: {bad_targets}")

    # Unreachable nodes: not the start AND no inbound edge from any other node
    reachable: set[str] = {start}
    for targets in edges.values():
        reachable.update(targets)
    orphans = sorted(node_set - reachable)
    if orphans:
        errors.append(f"unreachable nodes (no inbound edge and not start): {orphans}")

    return errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register_dynamic_flow(
    name: str,
    nodes: list[str],
    edges: dict[str, list[str]],
    start: str,
    end: list[str],
    *,
    user_id: str | None = None,
    overwrite: bool = False,
    db: Session | None = None,
) -> dict[str, Any]:
    """
    Validate then register a flow at runtime.

    Thread-safe: acquires _registry_lock before any write.

    If *db* is provided the registration is also persisted to the
    dynamic_flows table so it survives server restarts.  Pass db=None
    when called from the startup loader (already reading from DB).

    Returns the stored metadata dict on success.
    Raises ValueError(list[str]) with validation errors if invalid.
    Raises ValueError(["flow already exists ..."]) if name taken and overwrite=False.
    """
    from AINDY.runtime.flow_engine import FLOW_REGISTRY, register_flow

    errors = _validate(name, nodes, edges, start, end)
    if errors:
        raise ValueError(errors)

    with _registry_lock:
        if name in FLOW_REGISTRY and not overwrite:
            raise ValueError([
                f"flow {name!r} already exists; set overwrite=true to replace"
            ])

        flow_def: dict[str, Any] = {
            "start": start,
            "edges": {src: list(targets) for src, targets in edges.items()},
            "end": list(end),
        }
        register_flow(name, flow_def)

        meta: dict[str, Any] = {
            "name": name,
            "nodes": list(nodes),
            "edges": {src: list(targets) for src, targets in edges.items()},
            "start": start,
            "end": list(end),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": user_id,
            "dynamic": True,
        }
        _DYNAMIC_META[name] = meta

    if db is not None:
        _persist_flow(name, nodes, edges, start, end, user_id=user_id, overwrite=overwrite, db=db)

    logger.info("platform: dynamic flow registered: %s (nodes=%d)", name, len(nodes))
    return meta


def _persist_flow(
    name: str,
    nodes: list[str],
    edges: dict[str, list[str]],
    start: str,
    end: list[str],
    *,
    user_id: str | None,
    overwrite: bool,
    db: Session,
) -> None:
    """Upsert the flow definition into the dynamic_flows table."""
    from AINDY.db.models.dynamic_flow import DynamicFlow

    definition = {
        "nodes": list(nodes),
        "edges": {src: list(targets) for src, targets in edges.items()},
        "start": start,
        "end": list(end),
    }
    now = datetime.now(timezone.utc)

    try:
        existing = db.query(DynamicFlow).filter(DynamicFlow.name == name).first()
        if existing:
            existing.definition_json = definition
            existing.is_active = True
            existing.updated_at = now
        else:
            db.add(DynamicFlow(
                id=uuid.uuid4(),
                name=name,
                definition_json=definition,
                created_by=str(user_id) if user_id else None,
                created_at=now,
                updated_at=now,
                is_active=True,
            ))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("platform: failed to persist flow %r: %s", name, exc)


def list_dynamic_flows() -> list[dict[str, Any]]:
    """Return a snapshot of all dynamically registered flow metadata."""
    return list(_DYNAMIC_META.values())


def get_dynamic_flow(name: str) -> dict[str, Any] | None:
    """Return metadata for one dynamic flow, or None if not found."""
    return _DYNAMIC_META.get(name)


def delete_dynamic_flow(name: str, *, db: Session | None = None) -> bool:
    """
    Remove a dynamic flow from FLOW_REGISTRY and _DYNAMIC_META.

    If *db* is provided, soft-deletes the row in dynamic_flows (is_active=False).

    Returns True if removed, False if name not found in _DYNAMIC_META.
    Static (startup-registered) flows cannot be deleted via this function.
    """
    from AINDY.runtime.flow_engine import FLOW_REGISTRY

    with _registry_lock:
        if name not in _DYNAMIC_META:
            return False
        FLOW_REGISTRY.pop(name, None)
        _DYNAMIC_META.pop(name, None)

    if db is not None:
        try:
            from AINDY.db.models.dynamic_flow import DynamicFlow
            row = db.query(DynamicFlow).filter(DynamicFlow.name == name).first()
            if row:
                row.is_active = False
                row.updated_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("platform: failed to soft-delete flow %r: %s", name, exc)

    logger.info("platform: dynamic flow deleted: %s", name)
    return True
