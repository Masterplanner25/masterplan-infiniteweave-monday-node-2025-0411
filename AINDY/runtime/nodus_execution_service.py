from __future__ import annotations

import os
import sys
import logging
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.execution_record_service import build_execution_record as build_canonical_execution_record
from runtime.nodus_runtime_adapter import NodusExecutionContext
from runtime.nodus_runtime_adapter import NodusRuntimeAdapter
from runtime.nodus_security import (
    ALLOWED_OPERATION_CAPABILITIES,
    NodusSecurityError,
    authorize_nodus_execution,
)
from utils.user_ids import parse_user_id
from utils.user_ids import require_user_id

logger = logging.getLogger(__name__)


def build_nodus_execution_summary(nodus_result) -> dict[str, Any]:
    """
    Normalize a Nodus runtime result into the shared summary shape used by flow
    execution, platform formatting, and direct route helpers.
    """
    return {
        "status": getattr(nodus_result, "status", None),
        "output_state": getattr(nodus_result, "output_state", {}) or {},
        "events_emitted": len(getattr(nodus_result, "emitted_events", []) or []),
        "memory_writes": len(getattr(nodus_result, "memory_writes", []) or []),
        "error": getattr(nodus_result, "error", None),
    }


def build_nodus_execution_record(
    *,
    flow_status: str | None = None,
    trace_id: str | None = None,
    run_id: str | None = None,
    nodus_summary: dict[str, Any] | None = None,
    nodus_status: str | None = None,
    output_state: dict[str, Any] | None = None,
    events: list[Any] | None = None,
    memory_writes: list[Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """
    Build the canonical Nodus execution record used across flow-backed and
    direct runtime entrypoints. Callers can wrap this record in route-specific
    envelopes without re-deriving execution metadata.
    """
    summary = dict(nodus_summary or {})
    normalized_output = output_state
    if normalized_output is None:
        normalized_output = summary.get("output_state") or {}
    normalized_events = list(events or [])
    normalized_writes = list(memory_writes or [])
    normalized_status = nodus_status or summary.get("status")
    normalized_error = error
    if normalized_error is None:
        normalized_error = summary.get("error")

    return {
        "status": flow_status,
        "trace_id": trace_id,
        "run_id": run_id,
        "nodus_status": normalized_status,
        "output_state": normalized_output,
        "events": normalized_events,
        "memory_writes": normalized_writes,
        "events_emitted": summary.get("events_emitted", len(normalized_events)),
        "memory_writes_count": summary.get("memory_writes", len(normalized_writes)),
        "error": normalized_error,
        "execution_record": build_canonical_execution_record(
            run_id=run_id,
            trace_id=trace_id or run_id or normalized_status,
            execution_unit_id=run_id or trace_id,
            workflow_type="nodus_execute",
            status=flow_status or normalized_status,
            error=normalized_error,
            actor="nodus",
            source="nodus",
            result_summary=summary,
            correlation_id=trace_id or run_id,
        ),
    }


def ensure_nodus_script_flow_registered() -> None:
    """
    Register the canonical Nodus script flow and its nodes exactly once.
    """
    import runtime.nodus_adapter  # noqa: F401
    from runtime.flow_engine import FLOW_REGISTRY, register_flow
    from runtime.nodus_runtime_adapter import NODUS_SCRIPT_FLOW

    if "nodus_execute" not in FLOW_REGISTRY:
        register_flow("nodus_execute", NODUS_SCRIPT_FLOW)


def _run_nodus_via_flow_direct(
    *,
    script: str,
    input_payload: dict[str, Any],
    error_policy: str,
    db: Session,
    user_id: str,
    workflow_type: str = "nodus_execute",
    trace_id: str | None = None,
    extra_initial_state: dict[str, Any] | None = None,
    node_max_retries: Optional[int] = None,
) -> dict[str, Any]:
    """
    Internal Nodus execution implementation.

    Called by the sys.v1.nodus.execute syscall handler and by
    run_nodus_script_via_flow() when user_id is absent.
    Do not call directly from new code — use run_nodus_script_via_flow() or
    dispatch sys.v1.nodus.execute through the SyscallDispatcher.

    node_max_retries
        When provided, overrides the default flow-node retry limit for the
        ``nodus.execute`` node in this run.  The value is injected as
        ``flow["node_configs"]["nodus.execute"]["max_retries"]`` so the flow
        engine's retry gate can resolve the correct RetryPolicy per-run without
        touching the shared NODUS_SCRIPT_FLOW constant.

        None (default) → the flow-engine default (3 attempts) applies unchanged.
    """
    from runtime.flow_engine import FLOW_REGISTRY, PersistentFlowRunner
    from utils.uuid_utils import normalize_uuid

    ensure_nodus_script_flow_registered()

    # Build a per-run flow dict.  When node_max_retries is supplied we inject
    # node_configs so the retry gate in PersistentFlowRunner can honour it.
    # The shared NODUS_SCRIPT_FLOW constant is never mutated.
    flow = FLOW_REGISTRY["nodus_execute"]
    if node_max_retries is not None:
        flow = {
            **flow,
            "node_configs": {"nodus.execute": {"max_retries": node_max_retries}},
        }

    runner = PersistentFlowRunner(
        flow=flow,
        db=db,
        user_id=normalize_uuid(user_id) if user_id else None,
        workflow_type=workflow_type,
    )
    initial_state = {
        "nodus_script": script,
        "nodus_input_payload": input_payload,
        "nodus_error_policy": error_policy,
    }
    if trace_id is not None:
        initial_state["trace_id"] = trace_id
    if extra_initial_state:
        initial_state.update(extra_initial_state)
    return runner.start(
        initial_state=initial_state,
        flow_name="nodus_execute",
    )


def run_nodus_script_via_flow(
    *,
    script: str,
    input_payload: dict[str, Any],
    error_policy: str,
    db: Session,
    user_id: str,
    workflow_type: str = "nodus_execute",
    trace_id: str | None = None,
    extra_initial_state: dict[str, Any] | None = None,
    node_max_retries: Optional[int] = None,
) -> dict[str, Any]:
    """
    Execute a Nodus script through the canonical flow-backed orchestration path.

    Routes through sys.v1.nodus.execute for unified capability enforcement,
    quota tracking, and observability. Falls back to _run_nodus_via_flow_direct()
    for anonymous/system calls (user_id absent).
    """
    if not user_id:
        logger.debug(
            "[run_nodus_script_via_flow] no user_id — executing directly "
            "(syscall layer requires identity)"
        )
        return _run_nodus_via_flow_direct(
            script=script,
            input_payload=input_payload,
            error_policy=error_policy,
            db=db,
            user_id=user_id,
            workflow_type=workflow_type,
            trace_id=trace_id,
            extra_initial_state=extra_initial_state,
            node_max_retries=node_max_retries,
        )

    import uuid as _uuid
    from kernel.syscall_dispatcher import get_dispatcher, SyscallContext

    _trace_id = trace_id or str(_uuid.uuid4())
    ctx = SyscallContext(
        execution_unit_id=_trace_id,
        user_id=str(user_id),
        capabilities=["nodus.execute", "flow.run"],
        trace_id=_trace_id,
        metadata={"_db": db, "_extra_initial_state": extra_initial_state},
    )
    _nodus_payload: dict[str, Any] = {
        "script": script,
        "input_payload": input_payload or {},
        "error_policy": error_policy,
        "workflow_type": workflow_type,
    }
    if trace_id is not None:
        _nodus_payload["trace_id"] = trace_id
    if node_max_retries is not None:
        _nodus_payload["node_max_retries"] = node_max_retries
    result = get_dispatcher().dispatch("sys.v1.nodus.execute", _nodus_payload, ctx)
    if result["status"] == "error":
        raise RuntimeError(
            f"sys.v1.nodus.execute failed: {result.get('error', '')}"
        )
    return result["data"]["nodus_result"]


def format_nodus_flow_result(flow_result: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a flow-backed Nodus execution result into the stable route shape.
    """
    final_state = flow_result.get("state") or {}
    nodus_result = flow_result.get("data") or {}
    if not isinstance(nodus_result, dict) or "status" not in nodus_result:
        nodus_result = final_state.get("nodus_execute_result") or {}

    return build_nodus_execution_record(
        flow_status=flow_result.get("status"),
        trace_id=flow_result.get("trace_id"),
        run_id=flow_result.get("run_id"),
        nodus_summary=nodus_result,
        nodus_status=final_state.get("nodus_status") or nodus_result.get("status"),
        output_state=nodus_result.get("output_state") or final_state.get("nodus_output_state") or {},
        events=final_state.get("nodus_events") or [],
        memory_writes=final_state.get("nodus_memory_writes") or [],
        error=(
            nodus_result.get("error")
            or final_state.get("nodus_handled_error")
            or (None if flow_result.get("status") != "FAILED" else flow_result.get("error"))
        ),
    )

def execute_agent_flow_orchestration(
    *,
    run_id: str,
    plan: dict[str, Any],
    user_id: str,
    db: Session,
    correlation_id: str | None = None,
    execution_token: dict[str, Any] | None = None,
    capability_token: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Canonical flow-backed agent execution path.

    The adapter remains import-compatible, but actual flow orchestration lives
    here so agent_runtime and any compatibility wrappers converge on one
    runtime-owned execution shell.
    """
    from datetime import datetime, timezone

    from agents.capability_service import check_execution_capability
    from core.execution_signal_helper import queue_system_event, record_agent_event
    from db.models.agent_run import AgentRun, AgentStep
    from runtime.flow_engine import PersistentFlowRunner
    from runtime.nodus_adapter import AGENT_FLOW, _db_run_id

    emit_system_event = queue_system_event

    try:
        steps = (plan or {}).get("steps", [])
        scoped_token = execution_token or capability_token
        flow_capability_check = {"ok": False, "error": "missing scoped capability token"}
        if scoped_token is not None:
            flow_capability_check = check_execution_capability(
                token=scoped_token,
                run_id=run_id,
                user_id=user_id,
                capability_name="execute_flow",
            )
        if not flow_capability_check["ok"]:
            agent_run = db.query(AgentRun).filter(AgentRun.id == _db_run_id(run_id)).first()
            if agent_run and agent_run.status == "executing":
                agent_run.status = "failed"
                agent_run.completed_at = datetime.now(timezone.utc)
                agent_run.error_message = flow_capability_check["error"]
                agent_run.result = {"steps": []}
            emit_system_event(
                db=db,
                event_type="capability.denied",
                user_id=user_id,
                trace_id=correlation_id,
                source="agent",
                payload={
                    "run_id": str(run_id),
                    "capability": "execute_flow",
                    "error": flow_capability_check["error"],
                },
                required=True,
            )
            record_agent_event(
                run_id=run_id,
                user_id=user_id,
                event_type="CAPABILITY_DENIED",
                db=db,
                correlation_id=correlation_id,
                payload={
                    "capability": "execute_flow",
                    "error": flow_capability_check["error"],
                },
                required=True,
            )
            logger.warning(
                "[NodusExecutionService] Flow capability denied for AgentRun %s: %s",
                run_id,
                flow_capability_check["error"],
            )
            return {"status": "FAILED", "error": flow_capability_check["error"]}
        emit_system_event(
            db=db,
            event_type="capability.allowed",
            user_id=user_id,
            trace_id=correlation_id,
            source="agent",
            payload={"run_id": str(run_id), "capability": "execute_flow"},
            required=True,
        )

        initial_state = {
            "agent_run_id": run_id,
            "user_id": user_id,
            "steps": steps,
            "memory_context": (plan or {}).get("memory_context", {}),
            "current_step_index": 0,
            "step_results": [],
            "correlation_id": correlation_id,
            "execution_token": scoped_token,
        }

        runner = PersistentFlowRunner(
            flow=AGENT_FLOW,
            db=db,
            user_id=user_id,
            workflow_type="agent_execution",
        )

        logger.info(
            "[NodusExecutionService] Starting flow for AgentRun %s (%d steps)",
            run_id,
            len(steps),
        )
        flow_result = runner.start(initial_state, flow_name="agent_execution")

        flow_run_id = flow_result.get("run_id")
        if flow_run_id:
            agent_run = db.query(AgentRun).filter(AgentRun.id == _db_run_id(run_id)).first()
            if agent_run:
                agent_run.flow_run_id = str(flow_run_id)
                db.commit()

        if flow_result.get("status") != "SUCCESS":
            agent_run = db.query(AgentRun).filter(AgentRun.id == _db_run_id(run_id)).first()
            if agent_run and agent_run.status == "executing":
                completed_steps = (
                    db.query(AgentStep)
                    .filter(AgentStep.run_id == _db_run_id(run_id))
                    .order_by(AgentStep.step_index.asc())
                    .all()
                )
                step_results = [
                    {
                        "step_index": s.step_index,
                        "tool": s.tool_name,
                        "status": s.status,
                        "result": s.result,
                        "error": s.error_message,
                    }
                    for s in completed_steps
                ]
                agent_run.status = "failed"
                agent_run.completed_at = datetime.now(timezone.utc)
                agent_run.result = {"steps": step_results}
                agent_run.error_message = flow_result.get("error", "Flow execution failed")
                db.commit()

        return flow_result
    except Exception as exc:
        logger.warning("[NodusExecutionService] execute_agent_flow_orchestration failed: %s", exc)
        return {"status": "FAILED", "error": str(exc)}


def execute_agent_run_via_nodus(
    *,
    run_id: str,
    plan: dict[str, Any],
    user_id: str,
    db: Session,
    correlation_id: str | None = None,
    execution_token: dict[str, Any] | None = None,
    capability_token: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Canonical Nodus/runtime entrypoint for agent execution.

    Agentics still relies on flow orchestration for retry and checkpoint
    semantics, but agent_runtime should enter that execution path through this
    runtime service instead of importing the adapter directly.

    Retry policy: no custom retry logic here — retry decisions are owned by
    the flow wrapper (flow_engine._FLOW_RETRY_POLICY) and the per-step adapter
    (_step_policy in nodus_adapter._execute_agent_step). This function executes
    exactly once per invocation; the flow engine controls whether it is retried.
    """
    from runtime.nodus_adapter import NodusAgentAdapter

    adapter_entrypoint = NodusAgentAdapter.execute_with_flow
    if not getattr(adapter_entrypoint, "__aindy_compat_wrapper__", False):
        return adapter_entrypoint(
            run_id=run_id,
            plan=plan,
            user_id=user_id,
            db=db,
            correlation_id=correlation_id,
            execution_token=execution_token,
            capability_token=capability_token,
        )

    return execute_agent_flow_orchestration(
        run_id=run_id,
        plan=plan,
        user_id=user_id,
        db=db,
        correlation_id=correlation_id,
        execution_token=execution_token,
        capability_token=capability_token,
    )


def execute_nodus_runtime(
    *,
    db: Session,
    user_id: str,
    execution_unit_id: str,
    script: str | None = None,
    file_path: str | None = None,
    memory_context: dict[str, Any] | None = None,
    input_payload: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    allowed_operations: Optional[list[str]] = None,
    event_sink=None,
    max_execution_ms: Optional[int] = None,
    adapter_cls=None,
    context_cls=None,
):
    """
    Canonical Nodus runtime entrypoint used by both route helpers and flow nodes.

    Legacy call sites may still shape the response differently, but actual VM
    execution should converge through this helper so adapter wiring, context
    injection, and file/script dispatch live in one place.
    """
    if not script and not file_path:
        raise ValueError("Provide either script or file_path")

    parsed_user_id = parse_user_id(user_id)
    normalized_user_id = str(parsed_user_id) if parsed_user_id is not None else str(user_id)
    if adapter_cls is None or context_cls is None:
        from runtime.nodus_runtime_adapter import NodusExecutionContext as _RuntimeExecutionContext
        from runtime.nodus_runtime_adapter import NodusRuntimeAdapter as _RuntimeAdapter

        adapter_cls = adapter_cls or _RuntimeAdapter
        context_cls = context_cls or _RuntimeExecutionContext

    execution_context = context_cls(
        user_id=normalized_user_id,
        execution_unit_id=execution_unit_id,
        memory_context=memory_context or {},
        input_payload=input_payload or {},
        state=state or {},
        allowed_operations=allowed_operations,
        event_sink=event_sink,
        max_execution_ms=max_execution_ms,
    )
    adapter = adapter_cls(db=db)
    if script is not None:
        return adapter.run_script(script, execution_context)
    return adapter.run_file(file_path, execution_context)


def execute_nodus_task_payload(
    *,
    task_name: str,
    task_code: str,
    db: Session,
    user_id: str,
    session_tags: Optional[list[str]] = None,
    allowed_operations: Optional[list[str]] = None,
    execution_id: Optional[str] = None,
    capability_token: Optional[dict] = None,
    logger=None,
) -> dict[str, Any]:
    normalized_user_id = str(require_user_id(user_id))
    eu_id = execution_id or f"memory.nodus.{task_name}"

    # Gate: ensure a DB-backed ExecutionUnit exists BEFORE the VM starts so the
    # run is always recoverable even if the process dies mid-execution.
    _pre_eu = None
    try:
        from core.execution_gate import require_execution_unit as _require_eu
        _pre_eu = _require_eu(
            db=db,
            eu_type="job",
            user_id=normalized_user_id,
            source_type="memory_nodus_execute",
            source_id=eu_id,
            correlation_id=eu_id,
            extra={"task_name": task_name, "workflow_type": "memory_nodus_execute"},
        )
    except Exception:
        pass  # EU gate is non-fatal; execution proceeds regardless

    try:
        security_context = authorize_nodus_execution(
            task_code=task_code,
            allowed_operations=allowed_operations,
            capability_token=capability_token,
            execution_id=execution_id,
            user_id=normalized_user_id,
        )

        nodus_path = os.environ.get(
            "NODUS_SOURCE_PATH",
            r"C:\dev\Coding Language\src",
        )
        if nodus_path not in sys.path:
            sys.path.insert(0, nodus_path)

        from nodus.runtime.embedding import NodusRuntime  # noqa: F401

        from db.dao.memory_node_dao import MemoryNodeDAO
        from runtime.memory import MemoryOrchestrator
        from runtime.memory.memory_feedback import MemoryFeedbackEngine
        from bridge import create_memory_node

        orchestrator = MemoryOrchestrator(MemoryNodeDAO)
        feedback_engine = MemoryFeedbackEngine()

        memory_context = orchestrator.get_context(
            user_id=normalized_user_id,
            query=task_name or "",
            task_type="nodus_execution",
            db=db,
            max_tokens=800,
            metadata={
                "tags": session_tags or [],
                "node_types": [],
                "limit": 3,
            },
        )

        nodus_result = execute_nodus_runtime(
            db=db,
            user_id=normalized_user_id,
            execution_unit_id=eu_id,
            script=task_code,
            memory_context=memory_context.formatted,
            input_payload={
                "task_name": task_name,
                "memory_ids": memory_context.ids,
                "allowed_operations": security_context["allowed_operations"],
                "required_capabilities": security_context["required_capabilities"],
                "restricted_operations": security_context["restricted_operations"],
            },
            state={
                "memory_ids": memory_context.ids,
                "allowed_operations": security_context["allowed_operations"],
            },
            allowed_operations=security_context["allowed_operations"],
            adapter_cls=NodusRuntimeAdapter,
            context_cls=NodusExecutionContext,
        )
        try:
            if _pre_eu is not None:
                from core.execution_unit_service import ExecutionUnitService
                ExecutionUnitService(db).update_status(
                    _pre_eu.id,
                    "completed" if nodus_result.status == "success" else "failed",
                )
        except Exception:
            pass

        summary = build_nodus_execution_summary(nodus_result)
        result = build_nodus_execution_record(
            flow_status="executed" if nodus_result.status == "success" else "failed",
            trace_id=eu_id,
            run_id=eu_id,
            nodus_summary=summary,
            nodus_status=nodus_result.status,
            output_state=nodus_result.output_state,
            events=nodus_result.emitted_events,
            memory_writes=nodus_result.memory_writes,
            error=nodus_result.error,
        )
        result["ok"] = nodus_result.status == "success"
        result["allowed_operations"] = security_context["allowed_operations"]

        try:
            result_preview = result.get("output_state") or result.get("error") or result.get("status")
            create_memory_node(
                content=f"Nodus task '{task_name}' executed: {str(result_preview)[:500]}",
                source="nodus_task",
                tags=(session_tags or []) + ["nodus", "task_execution"],
                user_id=normalized_user_id,
                db=db,
                node_type="outcome",
            )
        except Exception as exc:
            if logger:
                logger.warning("nodus_memory_capture_failed task=%s user=%s: %s", task_name, normalized_user_id, exc)

        try:
            success_score = 1.0 if result.get("ok") else 0.0
            feedback_engine.record_usage(
                memory_ids=memory_context.ids,
                success_score=success_score,
                db=db,
            )
        except Exception as exc:
            if logger:
                logger.warning(
                    "nodus_feedback_failed task=%s user=%s memory_ids=%s: %s",
                    task_name,
                    normalized_user_id,
                    memory_context.ids,
                    exc,
                )

        return {
            "task_name": task_name,
            "status": "executed" if result.get("ok") else "failed",
            "memory_bridge": "restricted",
            "session_tags": session_tags,
            "allowed_operations": security_context["allowed_operations"],
            "required_capabilities": security_context["required_capabilities"],
            "restricted_operations": security_context["restricted_operations"],
            "result": result,
        }

    except ImportError:
        return {
            "task_name": task_name,
            "status": "bridge_ready",
            "message": (
                "Nodus runtime not found. Memory Bridge is available for "
                "direct API calls."
            ),
            "allowed_operations": allowed_operations or sorted(ALLOWED_OPERATION_CAPABILITIES.keys()),
            "available_operations": [
                "POST /memory/recall/v3",
                "POST /memory/suggest",
                "POST /memory/nodes/{id}/feedback",
            ],
        }
    except NodusSecurityError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "nodus_security_violation",
                "message": str(exc),
            },
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "nodus_execute_failed", "message": "Task execution failed", "details": str(exc)},
        ) from exc

