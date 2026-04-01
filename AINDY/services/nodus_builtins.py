"""
nodus_builtins.py
─────────────────
Structured builtins exposed to Nodus scripts as namespaced objects:

  ``memory``  — read/write/search A.I.N.D.Y. memory (NodusMemoryBuiltins)
  ``event``   — emit events and pause execution awaiting an event (NodusEventBuiltins)

Nodus script usage
------------------
    # Memory namespace
    memories = memory.recall(["task", "goal"], 5)
    node     = memory.write("Completed planning step", ["step", "plan"])
    results  = memory.search("goal prioritization strategies")

    # Event namespace
    event.emit("step.completed", {step: "plan"})

    # Pause and resume on event
    payload = event.wait("approval.received")
    set_state("approved_by", payload["user"])

event.wait() protocol
---------------------
1. First call: sets wait flags on context.state, emits ``nodus.event.wait_requested``,
   raises ``NodusWaitSignal`` — halting the script immediately.
2. NodusRuntimeAdapter catches NodusWaitSignal → returns NodusExecutionResult(status="waiting").
3. nodus.execute flow node returns WAIT → flow engine persists FlowRun.waiting_for.
4. External ``route_event(event_type, payload)`` → injects state["event"], resumes flow.
5. nodus.execute detects resume: moves state["event"] → state["nodus_received_events"].
6. Script re-executes — event.wait("foo") finds payload in nodus_received_events → returns it.

Memory contract
---------------
* All methods are non-fatal: errors log a warning and return an empty
  result rather than raising.
* All operations are scoped to ``user_id``.
* Return values are plain dicts / lists of dicts — no ORM objects.
* ``memory.write()`` accumulates in ``_writes``; ``event.emit()`` accumulates
  in ``_emitted`` — both are merged into NodusExecutionResult after execution.

Relationship to existing primitives
------------------------------------
The flat builtins ``recall()``, ``remember()``, ``emit()`` etc. registered by
NodusRuntimeAdapter remain available for backward compatibility.  ``memory.*``
and ``event.*`` are additive, namespaced façades.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Maximum limit enforced on every query (protects VM heap from huge result sets)
_MAX_LIMIT = 50


# ── NodusWaitSignal ───────────────────────────────────────────────────────────

class NodusWaitSignal(Exception):
    """
    Raised by ``event.wait(event_type)`` to immediately halt Nodus script
    execution and request a flow-engine WAIT on the given event type.

    NodusRuntimeAdapter catches this exception before the generic handler and
    converts it to NodusExecutionResult(status="waiting").  If the Nodus VM
    intercepts the exception instead (returning ok=False), the adapter also
    checks ``context.state["nodus_wait_requested"]`` as a fallback — so both
    paths are covered regardless of VM exception-propagation behaviour.

    Parameters
    ----------
    event_type : str
        The system event type the script is waiting for, e.g. ``"approval.received"``.
    """

    def __init__(self, event_type: str) -> None:
        self.event_type = event_type
        super().__init__(f"nodus.wait:{event_type}")


class NodusMemoryBuiltins:
    """
    Structured memory namespace injected into Nodus scripts as ``memory``.

    Instantiated once per script execution by NodusRuntimeAdapter with the
    execution's DB session and user_id.  The instance is added to
    ``initial_globals`` so scripts can call ``memory.recall(...)``,
    ``memory.write(...)``, and ``memory.search(...)`` directly.

    Parameters
    ----------
    db : Session
        Active SQLAlchemy session — shared with the broader adapter lifetime.
    user_id : str
        Owner of this execution.  Every DAO call is scoped to this user.

    Attributes
    ----------
    _writes : list[dict]
        Record of every successful ``memory.write()`` call.  Read by
        NodusRuntimeAdapter after execution to merge into
        NodusExecutionResult.memory_writes alongside ``remember()`` captures.
    """

    def __init__(self, db: "Session", user_id: str) -> None:
        self._db = db
        self._user_id = user_id
        self._writes: list[dict[str, Any]] = []

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _dao(self):
        """Lazy DAO instantiation — keeps module imports DB/settings-free."""
        from db.dao.memory_node_dao import MemoryNodeDAO
        return MemoryNodeDAO(self._db)

    @staticmethod
    def _safe_node(node: Any) -> dict[str, Any]:
        """
        Convert a memory node (dict or ORM object) to a VM-safe plain dict.

        Only a curated field set is returned — no raw embeddings, no internal
        PKs beyond the public ``id``, and no mutable ORM state.
        """
        if isinstance(node, dict):
            return {
                "id": str(node.get("id") or ""),
                "content": node.get("content", ""),
                "tags": list(node.get("tags") or []),
                "node_type": node.get("node_type"),
                "significance": node.get("significance"),
                "resonance_score": node.get("resonance_score"),
                "created_at": (
                    str(node["created_at"]) if node.get("created_at") else None
                ),
                "source": node.get("source"),
                "memory_type": node.get("memory_type"),
            }
        # ORM object fallback (save() may return a model in some code paths)
        return {
            "id": str(getattr(node, "id", "") or ""),
            "content": getattr(node, "content", ""),
            "tags": list(getattr(node, "tags", None) or []),
            "node_type": getattr(node, "node_type", None),
            "significance": getattr(node, "significance", None),
            "resonance_score": getattr(node, "resonance_score", None),
            "created_at": (
                str(node.created_at)
                if getattr(node, "created_at", None)
                else None
            ),
            "source": getattr(node, "source", None),
            "memory_type": getattr(node, "memory_type", None),
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def recall(
        self,
        tags: "list[str] | str",
        limit: int = 5,
    ) -> "list[dict[str, Any]]":
        """
        Retrieve memories by tag match, ranked by resonance score.

        Uses ``MemoryNodeDAO.recall()`` which combines tag filtering with
        recency decay, success-rate weighting, and graph connectivity signals,
        returning the most contextually relevant nodes for the given tags.

        Parameters
        ----------
        tags : str | list[str]
            One tag or a list of tags.  A single string is wrapped in a list.
            Matching is OR-mode: a node is a candidate if it has *any* of the
            supplied tags.
        limit : int
            Maximum nodes to return.  Clamped to ``[1, 50]``.

        Returns
        -------
        list[dict]
            Each dict contains: id, content, tags, node_type, significance,
            resonance_score, created_at, source, memory_type.
            Returns ``[]`` on any error.

        Example
        -------
            memories = memory.recall(["task", "goal"], 5)
            for m in memories:
                emit("memory.loaded", {content: m["content"]})
        """
        if isinstance(tags, str):
            tags = [tags]
        limit = max(1, min(int(limit), _MAX_LIMIT))
        try:
            nodes = self._dao().recall(
                tags=list(tags),
                limit=limit,
                user_id=self._user_id,
            )
            return [self._safe_node(n) for n in (nodes or [])]
        except Exception as exc:
            logger.warning("[NodusMemoryBuiltins.recall] failed: %s", exc)
            return []

    def write(
        self,
        content: str,
        tags: "list[str] | str | None" = None,
        node_type: str = "execution",
        significance: float = 0.5,
    ) -> "dict[str, Any]":
        """
        Persist a new memory node scoped to the current user.

        Each call appends a record to ``_writes`` so the adapter can include
        it in NodusExecutionResult.memory_writes after execution completes.

        Parameters
        ----------
        content : str
            Text content to store.  Must be a non-empty string.
        tags : str | list[str] | None
            Tags for later retrieval.  A single string is wrapped in a list.
        node_type : str
            Semantic category (default ``"execution"``).
        significance : float
            Importance score 0.0–1.0, clamped (default 0.5).

        Returns
        -------
        dict
            Saved memory: {id, content, tags, node_type, significance,
            created_at, source, memory_type}.  Returns ``{}`` on failure so
            the script can guard with ``if node: ...``.

        Example
        -------
            node = memory.write("Resolved auth conflict", ["auth", "fix"])
            set_state("write_id", node["id"])
        """
        if not content or not isinstance(content, str):
            logger.warning("[NodusMemoryBuiltins.write] empty content, skipping")
            return {}
        if isinstance(tags, str):
            tags = [tags]
        tags_list = list(tags or [])
        significance = float(max(0.0, min(1.0, significance)))

        try:
            result = self._dao().save(
                content=content,
                tags=tags_list,
                user_id=self._user_id,
                node_type=node_type,
                source="nodus_script",
                extra={"significance": significance},
            )
            safe = self._safe_node(result)
            self._writes.append({
                "user_id": self._user_id,
                "content": content,
                "tags": tags_list,
                "node_type": node_type,
                "result": safe,
            })
            return safe
        except Exception as exc:
            logger.warning("[NodusMemoryBuiltins.write] failed: %s", exc)
            return {}

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> "list[dict[str, Any]]":
        """
        Semantic search over memory using a free-text query string.

        Uses ``MemoryNodeDAO.recall()`` with the ``query`` parameter, which
        generates an embedding, runs cosine similarity against all stored
        nodes, and applies resonance scoring.  Falls back to ILIKE full-text
        matching if the embedding service is unavailable.

        Parameters
        ----------
        query : str
            Free-text query string.  Must be non-empty.
        limit : int
            Maximum results.  Clamped to ``[1, 50]``.

        Returns
        -------
        list[dict]
            Each dict contains: id, content, tags, node_type, significance,
            resonance_score, created_at, source, memory_type.
            Returns ``[]`` on any error or empty query.

        Example
        -------
            results = memory.search("goal prioritization strategies")
            best = results[0]["content"] if results else ""
        """
        if not query or not isinstance(query, str):
            return []
        limit = max(1, min(int(limit), _MAX_LIMIT))
        try:
            nodes = self._dao().recall(
                query=query,
                limit=limit,
                user_id=self._user_id,
            )
            return [self._safe_node(n) for n in (nodes or [])]
        except Exception as exc:
            logger.warning("[NodusMemoryBuiltins.search] failed: %s", exc)
            return []


# ── NodusEventBuiltins ────────────────────────────────────────────────────────

class NodusEventBuiltins:
    """
    Event primitives injected into Nodus scripts as the ``event`` namespace.

    Provides two operations:

    ``event.emit(type, payload)``
        Emit a system event with full correlation context.  The event is
        captured in ``_emitted`` and routed through the caller-supplied
        ``event_sink`` (if any) or directly via ``queue_system_event()``.

    ``event.wait(type)``
        Pause execution until a system event of the given type arrives.

        * **Wait path** (event not yet received): sets wait flags on
          ``context_state``, emits ``nodus.event.wait_requested``, and raises
          ``NodusWaitSignal`` — halting the script immediately.
        * **Resume path** (event already delivered): reads the payload from
          ``context_state["nodus_received_events"]``, emits
          ``nodus.event.wait_resumed``, and returns the payload dict so the
          script can continue.

    Parameters
    ----------
    db
        Active SQLAlchemy session for system event persistence.
    user_id : str
        Owner of this execution — used for event attribution.
    execution_unit_id : str
        Correlates emitted events back to the ExecutionUnit row.
    trace_id : str
        Trace context for linking all events in a single flow execution.
    event_sink : callable | None
        Optional ``(event_type, payload) -> None`` callable supplied by the
        caller.  When present, ``event.emit()`` routes here instead of the
        default ``queue_system_event()`` path.
    context_state : dict
        **Mutable** reference to ``NodusExecutionContext.state``.  Used by
        ``event.wait()`` to set/read wait flags and received-event payloads.

    Attributes
    ----------
    _emitted : list[dict]
        Record of every ``event.emit()`` call in emission order.  Merged into
        ``NodusExecutionResult.emitted_events`` by NodusRuntimeAdapter after
        execution alongside the flat ``emit()`` captures.
    """

    def __init__(
        self,
        *,
        db: Any,
        user_id: str,
        execution_unit_id: str,
        trace_id: str,
        event_sink: Optional[Callable[[str, dict], None]],
        context_state: dict,
    ) -> None:
        self._db = db
        self._user_id = user_id
        self._execution_unit_id = execution_unit_id
        self._trace_id = trace_id
        self._event_sink = event_sink
        self._context_state = context_state
        self._emitted: list[dict[str, Any]] = []

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _queue(self, event_type: str, payload: dict) -> None:
        """Route a system event through event_sink or queue_system_event."""
        if self._event_sink is not None:
            try:
                self._event_sink(event_type, payload)
            except Exception as exc:
                logger.warning(
                    "[NodusEventBuiltins] event_sink raised for '%s': %s", event_type, exc
                )
        else:
            try:
                from core.execution_signal_helper import queue_system_event
                queue_system_event(
                    db=self._db,
                    event_type=event_type,
                    user_id=self._user_id,
                    trace_id=self._trace_id,
                    source="nodus",
                    payload={**payload, "execution_unit_id": self._execution_unit_id},
                    required=False,
                )
            except Exception as exc:
                logger.warning(
                    "[NodusEventBuiltins] queue_system_event failed for '%s': %s", event_type, exc
                )

    # ── Public API ────────────────────────────────────────────────────────────

    def emit(
        self,
        event_type: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Emit a system event with the given type and payload.

        The event is always captured in ``_emitted`` regardless of routing,
        so it appears in NodusExecutionResult.emitted_events.  It is then
        routed to the event_sink (if supplied) or persisted via
        ``queue_system_event()``.

        This mirrors the flat ``emit()`` builtin but uses the namespaced API
        and includes the correlation identifiers automatically.

        Parameters
        ----------
        event_type : str
            System event type string, e.g. ``"step.completed"``.
        payload : dict | None
            Arbitrary JSON-serialisable data.

        Example
        -------
            event.emit("step.completed", {step: "plan", status: "ok"})
        """
        routed_payload = dict(payload or {})
        record = {
            "event_type": event_type,
            "payload": routed_payload,
            "execution_unit_id": self._execution_unit_id,
            "user_id": self._user_id,
        }
        self._emitted.append(record)
        self._queue(event_type, routed_payload)

    def wait(self, event_type: str) -> dict[str, Any]:
        """
        Pause script execution until an event of the given type is delivered.

        Resume path
        -----------
        If ``context_state["nodus_received_events"][event_type]`` is already
        populated (i.e. the flow was resumed after a previous wait), the
        received payload is returned immediately and execution continues.

        Wait path
        ---------
        Otherwise the method:
        1. Sets ``context_state["nodus_wait_requested"] = True`` and
           ``context_state["nodus_wait_event_type"] = event_type``.
        2. Emits a ``nodus.event.wait_requested`` system event so observers
           know the flow is about to pause.
        3. Raises ``NodusWaitSignal(event_type)`` to immediately halt the
           script.  NodusRuntimeAdapter converts this into
           ``NodusExecutionResult(status="waiting")``.

        Parameters
        ----------
        event_type : str
            The system event type to wait for, e.g. ``"approval.received"``.

        Returns
        -------
        dict
            The payload of the received event (resume path only).  On the
            wait path this function never returns — it always raises.

        Example
        -------
            payload = event.wait("approval.received")
            set_state("approved_by", payload["user"])
        """
        received = self._context_state.get("nodus_received_events") or {}

        # ── Resume path ───────────────────────────────────────────────────────
        if event_type in received:
            payload = dict(received[event_type]) if isinstance(received[event_type], dict) else {}
            logger.info(
                "[NodusEventBuiltins.wait] resumed on '%s' eu=%s",
                event_type, self._execution_unit_id,
            )
            self._queue(
                "nodus.event.wait_resumed",
                {"wait_for": event_type, "payload": payload},
            )
            return payload

        # ── Wait path ─────────────────────────────────────────────────────────
        logger.info(
            "[NodusEventBuiltins.wait] requesting wait for '%s' eu=%s",
            event_type, self._execution_unit_id,
        )
        self._context_state["nodus_wait_requested"] = True
        self._context_state["nodus_wait_event_type"] = event_type

        try:
            self._queue(
                "nodus.event.wait_requested",
                {"wait_for": event_type},
            )
        except Exception as exc:
            logger.warning(
                "[NodusEventBuiltins.wait] wait_requested emit failed for '%s': %s",
                event_type, exc,
            )

        raise NodusWaitSignal(event_type)
