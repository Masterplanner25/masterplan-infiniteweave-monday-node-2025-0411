"""
nodus_trace_service.py — Query Nodus execution trace events.

Each Nodus execution records a NodusTraceEvent row per host-function call
(recall, remember, emit, set_state, …).  This service retrieves those rows
and produces a structured trace response for GET /platform/nodus/trace/{id}.

Lookup
======
The query key is the ``trace_id`` — which equals the ``execution_unit_id``
of the NodusExecutionContext used for that run.  For PersistentFlowRunner
executions this is the flow-engine run_id / trace_id that appears in
AutomationLog and FlowHistory records, so callers can correlate traces with
other observability surfaces.

Ownership
=========
Ownership is enforced: only rows where ``user_id == caller_user_id`` are
returned.  Admin routes that need cross-user access should query the model
directly.
"""
from __future__ import annotations

import logging
import os
import sys
from importlib import import_module
from typing import Any, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def __getattr__(name: str):
    if name == "flow_engine":
        module = import_module("AINDY.runtime.flow_engine")
        sys.modules.setdefault("runtime.flow_engine", module)
        globals()[name] = module
        return module
    raise AttributeError(name)


def _is_nodus_node(name: str) -> bool:
    return name == "nodus.execute" or name.startswith("nodus.")


def get_engine_status() -> dict:
    """Return registration status of the DAG and Nodus flow engines."""
    from AINDY.runtime.flow_engine import FLOW_REGISTRY, NODE_REGISTRY

    dag_nodes = sorted(name for name in NODE_REGISTRY if not _is_nodus_node(name))
    nodus_nodes = sorted(name for name in NODE_REGISTRY if _is_nodus_node(name))
    return {
        "dag_engine": {
            "registered_nodes": len(dag_nodes),
            "node_names": dag_nodes,
            "available": len(dag_nodes) > 0,
            "registered_flows": len(FLOW_REGISTRY),
        },
        "nodus_engine": {
            "registered_nodes": len(nodus_nodes),
            "node_names": nodus_nodes,
            "available": len(nodus_nodes) > 0,
            "configured": bool(os.environ.get("NODUS_SOURCE_PATH")),
        },
    }


def verify_engine_registration() -> dict:
    """Validate that the always-on DAG engine is initialized."""
    status = get_engine_status()
    if status["dag_engine"]["registered_nodes"] <= 0:
        raise RuntimeError("Custom DAG engine registered no nodes at startup")
    return status


def enforce_engine_boundary(
    *,
    entrypoint: str,
    flow_name: str | None = None,
    workflow_type: str | None = None,
) -> None:
    """Reject the wrong public entrypoint for a flow engine boundary."""
    label = str(flow_name or workflow_type or "")
    is_nodus_workflow = (
        label == "nodus_execute"
        or label.startswith("nodus")
        or label.startswith("memory_nodus")
    )
    if entrypoint in {"flow.run", "flow.execute_intent"} and is_nodus_workflow:
        raise ValueError(
            "Nodus workflows must use AINDY.runtime.nodus_execution_service."
            "run_nodus_script_via_flow(), not the generic DAG flow entrypoints."
        )
    if entrypoint == "nodus.run" and label and "nodus" not in label:
        raise ValueError(
            "run_nodus_script_via_flow() is reserved for Nodus-backed workflows; "
            "use AINDY.runtime.flow_engine.run_flow()/execute_intent() for "
            "Python-defined DAG flows."
        )


def query_nodus_trace(
    *,
    db: Session,
    trace_id: str,
    user_id: str,
    limit: int = 500,
) -> dict[str, Any]:
    """
    Return all NodusTraceEvent rows for a given trace_id owned by user_id.

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    trace_id:
        The execution trace identifier — equals the execution_unit_id / run_id
        from PersistentFlowRunner.  Passed as the path parameter in the API.
    user_id:
        Caller's user UUID string — enforces ownership.
    limit:
        Maximum rows returned (default 500).

    Returns
    -------
    dict
        ``{"trace_id": str, "execution_unit_id": str, "count": int,
           "steps": [...], "summary": {...}}``
    """
    from AINDY.db.models.nodus_trace_event import NodusTraceEvent
    from AINDY.utils.uuid_utils import normalize_uuid

    try:
        uid = normalize_uuid(user_id)
    except Exception:
        uid = None

    rows = (
        db.query(NodusTraceEvent)
        .filter(
            NodusTraceEvent.trace_id == trace_id,
            NodusTraceEvent.user_id == uid,
        )
        .order_by(NodusTraceEvent.sequence.asc())
        .limit(limit)
        .all()
    )

    steps = [_serialize_trace_event(r) for r in rows]

    return {
        "trace_id": trace_id,
        "execution_unit_id": trace_id,   # same value in standard runs
        "count": len(steps),
        "steps": steps,
        "summary": build_trace_summary(steps),
    }


def build_trace_summary(steps: list[dict]) -> dict[str, Any]:
    """
    Build aggregate statistics over a list of serialised trace steps.

    Returns
    -------
    dict
        ``{"total_calls": int, "total_duration_ms": int,
           "fn_counts": {fn_name: count}, "error_count": int,
           "fn_names": [distinct fn_names in call order]}``
    """
    if not steps:
        return {
            "total_calls": 0,
            "total_duration_ms": 0,
            "fn_counts": {},
            "error_count": 0,
            "fn_names": [],
        }

    fn_counts: dict[str, int] = {}
    total_duration = 0
    error_count = 0
    seen_fns: list[str] = []

    for step in steps:
        fn = step.get("fn_name", "unknown")
        fn_counts[fn] = fn_counts.get(fn, 0) + 1
        if fn not in seen_fns:
            seen_fns.append(fn)
        total_duration += step.get("duration_ms") or 0
        if step.get("status") == "error":
            error_count += 1

    return {
        "total_calls": len(steps),
        "total_duration_ms": total_duration,
        "fn_counts": fn_counts,
        "error_count": error_count,
        "fn_names": seen_fns,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _serialize_trace_event(row: Any) -> dict[str, Any]:
    """Convert a NodusTraceEvent ORM row to a plain dict."""
    return {
        "id": str(row.id),
        "execution_unit_id": row.execution_unit_id,
        "trace_id": row.trace_id,
        "sequence": row.sequence,
        "fn_name": row.fn_name,
        "args_summary": row.args_summary,
        "result_summary": row.result_summary,
        "duration_ms": row.duration_ms,
        "status": row.status,
        "error": row.error,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
    }
