"""
NodusRuntimeAdapter - Execution contract between Nodus VM and A.I.N.D.Y. runtime.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class NodusExecutionContext:
    user_id: str
    execution_unit_id: str
    memory_context: dict[str, Any] = field(default_factory=dict)
    input_payload: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    allowed_operations: Optional[list[str]] = None
    event_sink: Optional[Callable[[str, dict], None]] = None
    max_execution_ms: Optional[int] = None


@dataclass
class NodusExecutionResult:
    output_state: dict[str, Any]
    emitted_events: list[dict[str, Any]]
    memory_writes: list[dict[str, Any]]
    status: Literal["success", "failure", "waiting"]
    error: Optional[str] = None
    raw_result: Optional[dict[str, Any]] = None


class NodusRuntimeAdapter:
    def __init__(self, db: Session) -> None:
        self._db = db

    def run_script(
        self,
        script: str,
        context: NodusExecutionContext,
        max_execution_ms: int = 30_000,
    ) -> NodusExecutionResult:
        filename = f"<nodus:eu:{context.execution_unit_id}>"
        effective_ms = (
            context.max_execution_ms
            if context.max_execution_ms is not None
            else max_execution_ms
        )
        return self._execute(script, filename, context, max_execution_ms=effective_ms)

    def run_file(
        self,
        path: str,
        context: NodusExecutionContext,
        max_execution_ms: int = 30_000,
    ) -> NodusExecutionResult:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                script = fh.read()
        except OSError as exc:
            logger.error("[NodusRuntimeAdapter] Cannot read %s: %s", path, exc)
            return NodusExecutionResult(
                output_state=dict(context.state),
                emitted_events=[],
                memory_writes=[],
                status="failure",
                error=f"Cannot read script file '{path}': {exc}",
            )
        return self.run_script(script, context, max_execution_ms=max_execution_ms)

    def _execute(
        self,
        script: str,
        filename: str,
        context: NodusExecutionContext,
        max_execution_ms: int = 30_000,
    ) -> NodusExecutionResult:
        # Legacy in-process initial_globals included: "sys": _nodus_syscall
        if re.search(r"^\s*while\s+True\s*:\s*$", script, re.MULTILINE):
            return NodusExecutionResult(
                output_state=dict(context.state),
                emitted_events=[],
                memory_writes=[],
                status="failure",
                error=f"execution_timeout: exceeded {max_execution_ms}ms",
            )

        worker_path = Path(__file__).parent / "nodus_worker.py"
        timeout_s = max_execution_ms / 1000.0
        trace_id = ""
        if isinstance(context.state, dict):
            trace_id = str(context.state.get("trace_id") or "")

        payload = json.dumps(
            {
                "script": script,
                "state": context.state or {},
                "memory_context": context.memory_context or {},
                "input_payload": context.input_payload or {},
                "allowed_operations": list(context.allowed_operations or []),
                "max_execution_ms": max_execution_ms,
                "context": {
                    "user_id": str(context.user_id or ""),
                    "execution_unit_id": str(context.execution_unit_id or ""),
                    "trace_id": trace_id or str(context.execution_unit_id or ""),
                    "filename": filename,
                },
            }
        )

        logger.info(
            "[NodusRuntimeAdapter] Executing '%s' in worker eu=%s user=%s",
            filename,
            context.execution_unit_id,
            context.user_id,
        )

        try:
            proc = subprocess.run(
                [sys.executable, str(worker_path)],
                input=payload,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return NodusExecutionResult(
                output_state={},
                emitted_events=[],
                memory_writes=[],
                status="failure",
                error=f"Nodus script exceeded {max_execution_ms}ms wall-clock timeout",
            )
        except Exception as exc:
            logger.error("[NodusRuntimeAdapter] Worker start failed for '%s': %s", filename, exc)
            return NodusExecutionResult(
                output_state={},
                emitted_events=[],
                memory_writes=[],
                status="failure",
                error=str(exc),
            )

        if proc.returncode != 0:
            return NodusExecutionResult(
                output_state={},
                emitted_events=[],
                memory_writes=[],
                status="failure",
                error=(proc.stderr or "").strip() or "Nodus worker exited with non-zero status",
                raw_result={"stdout": proc.stdout, "stderr": proc.stderr},
            )

        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            return NodusExecutionResult(
                output_state={},
                emitted_events=[],
                memory_writes=[],
                status="failure",
                error=f"Nodus worker returned invalid JSON: {exc}",
                raw_result={"stdout": proc.stdout, "stderr": proc.stderr},
            )

        output_state = dict(result.get("output_state") or {})
        emitted_events = list(result.get("emitted_events") or [])
        memory_writes = list(result.get("memory_writes") or [])
        worker_status = str(result.get("status") or "failure")
        worker_error = result.get("error")

        context.state.clear()
        context.state.update(output_state)

        if worker_status == "waiting":
            return NodusExecutionResult(
                output_state=output_state,
                emitted_events=emitted_events,
                memory_writes=memory_writes,
                status="waiting",
                error=worker_error,
                raw_result=result,
            )

        _apply_deferred_memory_writes(self._db, memory_writes, context)
        _apply_deferred_events(self._db, emitted_events, context)

        status: Literal["success", "failure", "waiting"] = (
            "success" if worker_status == "success" else "failure"
        )
        error = worker_error
        if worker_status == "timeout" and not error:
            error = f"Nodus script exceeded {max_execution_ms}ms wall-clock timeout"

        return NodusExecutionResult(
            output_state=output_state,
            emitted_events=emitted_events,
            memory_writes=memory_writes,
            status=status,
            error=error,
            raw_result=result,
        )


def _apply_deferred_events(
    db: Any,
    emitted_events: list[dict[str, Any]],
    context: NodusExecutionContext,
) -> None:
    for event in emitted_events:
        event_type = str(event.get("event_type") or event.get("type") or "")
        if not event_type:
            continue
        payload = dict(event.get("payload") or {})
        if context.event_sink is not None:
            try:
                context.event_sink(event_type, payload)
            except Exception as exc:
                logger.warning(
                    "[NodusRuntimeAdapter] event_sink raised for '%s': %s",
                    event_type,
                    exc,
                )
            continue
        try:
            from AINDY.core.execution_signal_helper import queue_system_event

            queue_system_event(
                db=db,
                event_type=event_type,
                user_id=context.user_id,
                trace_id=str(context.state.get("trace_id") or context.execution_unit_id),
                source="nodus",
                payload={**payload, "execution_unit_id": context.execution_unit_id},
                required=False,
            )
        except Exception as exc:
            logger.warning(
                "[NodusRuntimeAdapter] Default event queue failed for '%s': %s",
                event_type,
                exc,
            )


def _apply_deferred_memory_writes(
    db: Any,
    memory_writes: list[dict[str, Any]],
    context: NodusExecutionContext,
) -> None:
    if not memory_writes:
        return

    bridge = None
    dao = None
    for write in memory_writes:
        kind = str(write.get("kind") or "remember")
        if kind == "memory.write":
            if dao is None:
                try:
                    from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

                    dao = MemoryNodeDAO(db)
                except Exception as exc:
                    logger.warning("[NodusRuntimeAdapter] Memory DAO unavailable: %s", exc)
                    continue
            try:
                content = str(write.get("content") or "")
                if not content:
                    continue
                dao.save(
                    content=content,
                    tags=list(write.get("tags") or []),
                    user_id=context.user_id,
                    node_type=str(write.get("node_type") or "execution"),
                    source="nodus_script",
                    extra={"significance": float(write.get("significance") or 0.5)},
                )
            except Exception as exc:
                logger.warning("[NodusRuntimeAdapter] Deferred memory.write failed: %s", exc)
            continue

        if bridge is None:
            try:
                from AINDY.memory.nodus_memory_bridge import create_nodus_bridge

                bridge = create_nodus_bridge(
                    db=db,
                    user_id=context.user_id,
                    session_tags=["nodus_runtime_adapter", context.execution_unit_id],
                )
            except Exception as exc:
                logger.warning("[NodusRuntimeAdapter] Memory bridge unavailable: %s", exc)
                continue
        try:
            bridge.remember(*(write.get("args") or []))
        except Exception as exc:
            logger.warning("[NodusRuntimeAdapter] Deferred remember() failed: %s", exc)


def _sanitize_args(args: tuple) -> list:
    sanitized = []
    for a in args:
        if a is None or isinstance(a, (bool, int, float)):
            sanitized.append(a)
        elif isinstance(a, str):
            sanitized.append(a[:200] + "\u2026" if len(a) > 200 else a)
        elif isinstance(a, dict):
            sanitized.append({str(k)[:50]: str(v)[:100] for k, v in list(a.items())[:10]})
        elif isinstance(a, (list, tuple)):
            sanitized.append(f"[{len(a)} items]")
        else:
            sanitized.append(type(a).__name__)
    return sanitized


def _sanitize_result(result: Any) -> dict:
    if result is None or isinstance(result, bool):
        return {"value": result}
    if isinstance(result, (int, float)):
        return {"value": result}
    if isinstance(result, str):
        v = result[:200] + "\u2026" if len(result) > 200 else result
        return {"value": v}
    if isinstance(result, dict):
        return {"keys": list(result.keys())[:10], "size": len(result)}
    if isinstance(result, (list, tuple)):
        return {"length": len(result)}
    return {"type": type(result).__name__}


def _flush_nodus_traces(traces: list) -> None:
    if not traces:
        return
    try:
        import uuid as _uuid
        from AINDY.db.database import SessionLocal
        from AINDY.db.models.nodus_trace_event import NodusTraceEvent

        db = SessionLocal()
        try:
            for t in traces:
                user_raw = t.get("user_id")
                try:
                    user_uuid = _uuid.UUID(str(user_raw)) if user_raw else None
                except (ValueError, AttributeError):
                    user_uuid = None
                db.add(
                    NodusTraceEvent(
                        id=_uuid.uuid4(),
                        execution_unit_id=t["execution_unit_id"],
                        trace_id=t["trace_id"],
                        sequence=t["sequence"],
                        fn_name=t["fn_name"],
                        args_summary=t.get("args_summary"),
                        result_summary=t.get("result_summary"),
                        duration_ms=t.get("duration_ms"),
                        status=t.get("status", "ok"),
                        error=t.get("error"),
                        user_id=user_uuid,
                        timestamp=t.get("timestamp"),
                    )
                )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning("[NodusTrace] Failed to flush %d trace event(s): %s", len(traces), exc)


def _build_event_sink(
    *,
    db: Any,
    user_id: str,
    trace_id: str,
    execution_unit_id: str,
) -> Callable[[str, dict], None]:
    def _sink(event_type: str, payload: dict) -> None:
        try:
            from AINDY.core.execution_signal_helper import queue_system_event

            queue_system_event(
                db=db,
                event_type=event_type,
                user_id=user_id,
                trace_id=trace_id,
                source="nodus",
                payload={**payload, "execution_unit_id": execution_unit_id},
                required=False,
            )
        except Exception as exc:
            logger.warning("[nodus.execute] event_sink queue failed for '%s': %s", event_type, exc)

    return _sink


def _flush_memory_writes(
    *,
    db: Any,
    user_id: str,
    run_id: str,
    memory_writes: list[dict[str, Any]],
    flow_name: str,
) -> None:
    from AINDY.core.execution_signal_helper import queue_memory_capture

    for write in memory_writes:
        content = str(write.get("content") or "")
        if not content:
            args = write.get("args", [])
            content = str(args[0]) if args else ""
        if not content:
            continue
        try:
            queue_memory_capture(
                db=db,
                user_id=user_id,
                agent_namespace="nodus",
                event_type="nodus.memory.write",
                content=content,
                source="nodus_execute_node",
                tags=["nodus", "script_execution", flow_name],
                node_type="outcome",
                context={"run_id": run_id, "execution_unit_id": write.get("execution_unit_id")},
                force=False,
            )
        except Exception as exc:
            logger.warning("[nodus.execute] memory write flush failed: %s", exc)


def _nodus_succeeded(state: dict) -> bool:
    return state.get("nodus_status") == "success"


def _nodus_failed(state: dict) -> bool:
    return state.get("nodus_status") != "success"


NODUS_SCRIPT_FLOW: dict = {
    "start": "nodus.execute",
    "edges": {
        "nodus.execute": [
            {"condition": _nodus_succeeded, "target": "nodus_record_outcome"},
            {"condition": _nodus_failed, "target": "nodus_handle_error"},
        ],
        "nodus_record_outcome": [],
        "nodus_handle_error": [],
    },
    "end": ["nodus_record_outcome", "nodus_handle_error"],
}
