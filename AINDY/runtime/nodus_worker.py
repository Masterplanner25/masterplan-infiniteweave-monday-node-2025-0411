from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import uuid
from typing import Any, Optional


class WorkerWaitSignal(Exception):
    def __init__(self, event_type: str) -> None:
        self.event_type = event_type
        super().__init__(f"nodus.wait:{event_type}")


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


class DeferredMemoryBuiltins:
    def __init__(self, memory_context: dict[str, Any], user_id: str, execution_unit_id: str) -> None:
        self._memory_context = memory_context
        self._user_id = user_id
        self._execution_unit_id = execution_unit_id
        self._writes: list[dict[str, Any]] = []

    def recall(self, tags: Any = None, limit: int = 5, *_args: Any) -> list[dict[str, Any]]:
        nodes = list(self._memory_context.values()) if isinstance(self._memory_context, dict) else []
        if isinstance(tags, str):
            tags = [tags]
        if tags:
            tag_set = set(tags)
            nodes = [n for n in nodes if tag_set.intersection(set((n or {}).get("tags") or []))]
        return [_json_safe(n) for n in nodes[: max(1, int(limit or 1))]]

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        if not query:
            return []
        lowered = str(query).lower()
        nodes = list(self._memory_context.values()) if isinstance(self._memory_context, dict) else []
        matches = [n for n in nodes if lowered in str((n or {}).get("content") or "").lower()]
        return [_json_safe(n) for n in matches[: max(1, int(limit or 1))]]

    def write(
        self,
        content: str,
        tags: Any = None,
        node_type: str = "execution",
        significance: float = 0.5,
    ) -> dict[str, Any]:
        tags_list = [tags] if isinstance(tags, str) else list(tags or [])
        result = {
            "id": f"deferred-memory-{uuid.uuid4()}",
            "content": content,
            "tags": tags_list,
            "node_type": node_type,
            "significance": significance,
            "source": "nodus_script",
            "memory_type": "deferred",
        }
        self._writes.append(
            {
                "kind": "memory.write",
                "execution_unit_id": self._execution_unit_id,
                "user_id": self._user_id,
                "content": content,
                "tags": tags_list,
                "node_type": node_type,
                "significance": significance,
                "result": result,
                "args": [content, tags_list, node_type, significance],
            }
        )
        return result


class DeferredEventBuiltins:
    def __init__(
        self,
        state: dict[str, Any],
        emitted_events: list[dict[str, Any]],
        user_id: str,
        execution_unit_id: str,
    ) -> None:
        self._state = state
        self._emitted_events = emitted_events
        self._user_id = user_id
        self._execution_unit_id = execution_unit_id

    def emit(self, event_type: str, payload: Optional[dict[str, Any]] = None) -> None:
        routed_payload = dict(payload or {})
        self._emitted_events.append(
            {
                "type": event_type,
                "event_type": event_type,
                "payload": _json_safe(routed_payload),
                "execution_unit_id": self._execution_unit_id,
                "user_id": self._user_id,
            }
        )

    def wait(self, event_type: str) -> dict[str, Any]:
        received = self._state.get("nodus_received_events") or {}
        if event_type in received:
            payload = received[event_type]
            return dict(payload) if isinstance(payload, dict) else {}
        self._state["nodus_wait_requested"] = True
        self._state["nodus_wait_event_type"] = event_type
        self.emit("nodus.event.wait_requested", {"wait_for": event_type})
        raise WorkerWaitSignal(event_type)


def _remember_factory(memory: DeferredMemoryBuiltins) -> Any:
    def _remember(*args: Any) -> dict[str, Any]:
        content = str(args[0]) if args else ""
        tags = args[1] if len(args) > 1 else None
        node_type = str(args[2]) if len(args) > 2 else "execution"
        significance = float(args[3]) if len(args) > 3 else 0.5
        result = memory.write(content, tags, node_type, significance)
        memory._writes[-1]["kind"] = "remember"
        memory._writes[-1]["args"] = [content, tags, node_type, significance]
        return result

    return _remember


def _build_syscall(
    memory: DeferredMemoryBuiltins,
    event: DeferredEventBuiltins,
) -> Any:
    def _syscall(name: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        routed = dict(payload or {})
        if name == "sys.v1.event.emit":
            event_type = str(routed.get("event_type") or "")
            if not event_type:
                raise ValueError("sys.v1.event.emit requires 'event_type'")
            event.emit(event_type, routed.get("payload") or {})
            return {"ok": True, "deferred": True}
        if name == "sys.v1.memory.write":
            result = memory.write(
                str(routed.get("content") or ""),
                routed.get("tags") or [],
                str(routed.get("node_type") or "execution"),
                float(routed.get("significance") or 0.5),
            )
            return {"ok": True, "deferred": True, "result": result}
        if name == "sys.v1.memory.read":
            tags = routed.get("tags") or []
            limit = int(routed.get("limit") or 5)
            return {"ok": True, "nodes": memory.recall(tags, limit)}
        raise RuntimeError(f"Unsupported syscall in worker: {name}")

    return _syscall


def main() -> int:
    raw = sys.stdin.read()
    payload = json.loads(raw or "{}")

    script = str(payload.get("script") or "")
    state = dict(payload.get("state") or {})
    memory_context = dict(payload.get("memory_context") or {})
    input_payload = dict(payload.get("input_payload") or {})
    allowed_operations = list(payload.get("allowed_operations") or [])
    ctx = dict(payload.get("context") or {})
    user_id = str(ctx.get("user_id") or "")
    execution_unit_id = str(ctx.get("execution_unit_id") or "")
    filename = str(ctx.get("filename") or f"<nodus:eu:{execution_unit_id}>")

    nodus_path = os.environ.get("NODUS_SOURCE_PATH")
    if not nodus_path:
        print(
            json.dumps(
                {
                    "status": "failure",
                    "output_state": {},
                    "emitted_events": [],
                    "memory_writes": [],
                    "error": "NODUS_SOURCE_PATH is not set. Nodus VM cannot be loaded.",
                }
            )
        )
        sys.exit(1)
    if nodus_path not in sys.path:
        sys.path.insert(0, nodus_path)

    from AINDY.nodus.runtime.embedding import NodusRuntime  # type: ignore[import]

    emitted_events: list[dict[str, Any]] = []
    memory = DeferredMemoryBuiltins(memory_context, user_id, execution_unit_id)
    event = DeferredEventBuiltins(state, emitted_events, user_id, execution_unit_id)
    remember = _remember_factory(memory)
    stdout_buffer = io.StringIO()

    def _set_state(key: str, value: Any) -> None:
        state[key] = _json_safe(value)

    def _get_state(key: str, default: Any = None) -> Any:
        return state.get(key, default)

    initial_globals = {
        "memory_context": memory_context,
        "input_payload": input_payload,
        "allowed_operations": allowed_operations,
        "state": dict(state),
        "execution_unit_id": execution_unit_id,
        "user_id": user_id,
        "memory": memory,
        "event": event,
        "emit": event.emit,
        "remember": remember,
        "set_state": _set_state,
        "get_state": _get_state,
        "sys": _build_syscall(memory, event),
        "recall": memory.recall,
        "recall_tool": memory.recall,
        "recall_from": memory.recall,
        "recall_all": memory.recall,
        "suggest": memory.search,
        "record_outcome": remember,
        "share": remember,
    }

    result_payload: dict[str, Any]
    with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stdout_buffer):
        try:
            runtime = NodusRuntime()
            raw_result = runtime.run_source(
                script,
                filename=filename,
                initial_globals=initial_globals,
                host_globals=initial_globals,
            )
            if state.get("nodus_wait_requested"):
                wait_for = str(state.get("nodus_wait_event_type") or "unknown")
                state.pop("nodus_wait_requested", None)
                result_payload = {
                    "status": "waiting",
                    "output_state": _json_safe(state),
                    "emitted_events": _json_safe(emitted_events),
                    "memory_writes": _json_safe(memory._writes),
                    "error": None,
                    "stdout_log": stdout_buffer.getvalue(),
                    "wait_for": wait_for,
                    "raw_result": _json_safe(raw_result),
                }
            else:
                ok = bool((raw_result or {}).get("ok", False))
                result_payload = {
                    "status": "success" if ok else "failure",
                    "output_state": _json_safe(state),
                    "emitted_events": _json_safe(emitted_events),
                    "memory_writes": _json_safe(memory._writes),
                    "error": None if ok else str((raw_result or {}).get("error") or "Nodus execution failed"),
                    "stdout_log": stdout_buffer.getvalue(),
                    "raw_result": _json_safe(raw_result),
                }
        except WorkerWaitSignal as exc:
            state.pop("nodus_wait_requested", None)
            result_payload = {
                "status": "waiting",
                "output_state": _json_safe(state),
                "emitted_events": _json_safe(emitted_events),
                "memory_writes": _json_safe(memory._writes),
                "error": None,
                "stdout_log": stdout_buffer.getvalue(),
                "wait_for": exc.event_type,
            }
        except Exception as exc:
            result_payload = {
                "status": "failure",
                "output_state": _json_safe(state),
                "emitted_events": _json_safe(emitted_events),
                "memory_writes": _json_safe(memory._writes),
                "error": str(exc),
                "stdout_log": stdout_buffer.getvalue(),
            }

    sys.stdout.write(json.dumps(result_payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
