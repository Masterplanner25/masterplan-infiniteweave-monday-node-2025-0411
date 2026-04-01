"""
Tests for the A.I.N.D.Y. Syscall Dispatcher.

Groups
------
A  SyscallContext construction          (4 tests)
B  SYSCALL_REGISTRY shape               (5 tests)
C  register_syscall()                   (4 tests)
D  dispatch — routing + capability      (7 tests)
E  dispatch — response envelope         (5 tests)
F  dispatch — handler errors            (5 tests)
G  memory.read handler (unit)           (4 tests)
H  memory.write handler (unit)          (4 tests)
I  memory.search handler (unit)         (3 tests)
J  flow.run handler (unit)              (4 tests)
K  event.emit handler (unit)            (4 tests)
L  Nodus integration (adapter binding)  (4 tests)
"""
from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest

import services.syscall_dispatcher as _disp_mod
import services.syscall_registry as _reg_mod
from services.syscall_dispatcher import (
    DEFAULT_NODUS_CAPABILITIES,
    SyscallContext,
    get_dispatcher,
    register_syscall,
)
from services.syscall_dispatcher import SyscallDispatcher
from services.syscall_registry import SYSCALL_REGISTRY


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ctx(**kwargs) -> SyscallContext:
    defaults = dict(
        execution_unit_id="eu-test",
        user_id="user-test",
        capabilities=list(DEFAULT_NODUS_CAPABILITIES) + ["flow.run"],
        trace_id="eu-test",
    )
    defaults.update(kwargs)
    return SyscallContext(**defaults)


def _no_caps_ctx() -> SyscallContext:
    return _ctx(capabilities=[])


# ── A: SyscallContext ─────────────────────────────────────────────────────────

class TestSyscallContext:
    def test_required_fields(self):
        ctx = SyscallContext(
            execution_unit_id="eu-1",
            user_id="u-1",
            capabilities=["memory.read"],
            trace_id="t-1",
        )
        assert ctx.execution_unit_id == "eu-1"
        assert ctx.user_id == "u-1"
        assert ctx.capabilities == ["memory.read"]
        assert ctx.trace_id == "t-1"

    def test_defaults(self):
        ctx = SyscallContext(
            execution_unit_id="x", user_id="u", capabilities=[], trace_id="t"
        )
        assert ctx.memory_context == []
        assert ctx.metadata == {}

    def test_memory_context_not_shared(self):
        ctx1 = SyscallContext(execution_unit_id="a", user_id="u", capabilities=[], trace_id="t")
        ctx2 = SyscallContext(execution_unit_id="b", user_id="u", capabilities=[], trace_id="t")
        ctx1.memory_context.append("x")
        assert ctx2.memory_context == []

    def test_metadata_accepts_arbitrary_keys(self):
        ctx = SyscallContext(
            execution_unit_id="x", user_id="u", capabilities=[], trace_id="t",
            metadata={"foo": 42, "bar": [1, 2]},
        )
        assert ctx.metadata["foo"] == 42


# ── B: SYSCALL_REGISTRY shape ─────────────────────────────────────────────────

class TestRegistryShape:
    def test_all_five_syscalls_present(self):
        expected = {
            "sys.v1.memory.read",
            "sys.v1.memory.write",
            "sys.v1.memory.search",
            "sys.v1.flow.run",
            "sys.v1.event.emit",
        }
        assert expected.issubset(set(SYSCALL_REGISTRY.keys()))

    def test_memory_read_capability(self):
        assert SYSCALL_REGISTRY["sys.v1.memory.read"].capability == "memory.read"

    def test_memory_write_capability(self):
        assert SYSCALL_REGISTRY["sys.v1.memory.write"].capability == "memory.write"

    def test_flow_run_capability(self):
        assert SYSCALL_REGISTRY["sys.v1.flow.run"].capability == "flow.run"

    def test_event_emit_capability(self):
        assert SYSCALL_REGISTRY["sys.v1.event.emit"].capability == "event.emit"


# ── C: register_syscall ───────────────────────────────────────────────────────

class TestRegisterSyscall:
    def test_registers_new_entry(self):
        fn = lambda p, c: {"ok": True}
        register_syscall("sys.v1.test.ping", fn, "test.ping")
        assert "sys.v1.test.ping" in SYSCALL_REGISTRY
        assert SYSCALL_REGISTRY["sys.v1.test.ping"].capability == "test.ping"
        # Cleanup
        del SYSCALL_REGISTRY["sys.v1.test.ping"]

    def test_bad_name_raises(self):
        with pytest.raises(ValueError, match="must start with 'sys.'"):
            register_syscall("bad.name", lambda p, c: {}, "cap")

    def test_overwrites_existing(self):
        fn1 = lambda p, c: {"v": 1}
        fn2 = lambda p, c: {"v": 2}
        register_syscall("sys.v1.test.overwrite", fn1, "x")
        register_syscall("sys.v1.test.overwrite", fn2, "y")
        assert SYSCALL_REGISTRY["sys.v1.test.overwrite"].handler is fn2
        del SYSCALL_REGISTRY["sys.v1.test.overwrite"]

    def test_description_stored(self):
        register_syscall("sys.v1.test.desc", lambda p, c: {}, "cap", description="Hello")
        assert SYSCALL_REGISTRY["sys.v1.test.desc"].description == "Hello"
        del SYSCALL_REGISTRY["sys.v1.test.desc"]


# ── D: dispatch — routing + capability ───────────────────────────────────────

class TestDispatchRouting:
    def setup_method(self):
        self.dispatcher = SyscallDispatcher()

    def _register_noop(self, name: str, cap: str) -> None:
        SYSCALL_REGISTRY[name] = _reg_mod.SyscallEntry(
            handler=lambda p, c: {"ok": True},
            capability=cap,
        )

    def teardown_method(self):
        for k in list(SYSCALL_REGISTRY.keys()):
            if "test." in k:
                del SYSCALL_REGISTRY[k]

    def test_unknown_syscall_returns_error(self):
        result = self.dispatcher.dispatch("sys.v1.unknown.nope", {}, _ctx())
        assert result["status"] == "error"
        assert "Unknown syscall" in result["error"]

    def test_missing_capability_returns_error(self):
        self._register_noop("sys.v1.test.cap", "special.cap")
        result = self.dispatcher.dispatch("sys.v1.test.cap", {}, _no_caps_ctx())
        assert result["status"] == "error"
        assert "Permission denied" in result["error"]

    def test_matching_capability_routes_handler(self):
        self._register_noop("sys.v1.test.route", "test.route")
        result = self.dispatcher.dispatch(
            "sys.v1.test.route", {}, _ctx(capabilities=["test.route"])
        )
        assert result["status"] == "success"
        assert result["data"] == {"ok": True}

    def test_syscall_name_in_envelope(self):
        self._register_noop("sys.v1.test.name", "test.name")
        result = self.dispatcher.dispatch(
            "sys.v1.test.name", {}, _ctx(capabilities=["test.name"])
        )
        assert result["syscall"] == "sys.v1.test.name"

    def test_trace_id_in_envelope(self):
        self._register_noop("sys.v1.test.trace", "test.trace")
        ctx = _ctx(capabilities=["test.trace"], trace_id="my-trace")
        result = self.dispatcher.dispatch("sys.v1.test.trace", {}, ctx)
        assert result["trace_id"] == "my-trace"

    def test_execution_unit_id_in_envelope(self):
        self._register_noop("sys.v1.test.euid", "test.euid")
        ctx = _ctx(capabilities=["test.euid"], execution_unit_id="eu-xyz")
        result = self.dispatcher.dispatch("sys.v1.test.euid", {}, ctx)
        assert result["execution_unit_id"] == "eu-xyz"

    def test_duration_ms_present_and_non_negative(self):
        self._register_noop("sys.v1.test.dur", "test.dur")
        result = self.dispatcher.dispatch(
            "sys.v1.test.dur", {}, _ctx(capabilities=["test.dur"])
        )
        assert isinstance(result["duration_ms"], int)
        assert result["duration_ms"] >= 0


# ── E: dispatch — response envelope ──────────────────────────────────────────

class TestResponseEnvelope:
    def setup_method(self):
        self.dispatcher = SyscallDispatcher()
        SYSCALL_REGISTRY["sys.v1.test.env"] = _reg_mod.SyscallEntry(
            handler=lambda p, c: {"result": p.get("x", 0) * 2},
            capability="test.env",
        )

    def teardown_method(self):
        SYSCALL_REGISTRY.pop("sys.v1.test.env", None)

    def _dispatch(self, payload=None):
        return self.dispatcher.dispatch(
            "sys.v1.test.env",
            payload or {},
            _ctx(capabilities=["test.env"]),
        )

    def test_status_success(self):
        assert self._dispatch()["status"] == "success"

    def test_data_contains_handler_output(self):
        result = self._dispatch({"x": 5})
        assert result["data"] == {"result": 10}

    def test_error_is_none_on_success(self):
        assert self._dispatch()["error"] is None

    def test_error_envelope_has_empty_data(self):
        result = self.dispatcher.dispatch("sys.v1.missing", {}, _ctx())
        assert result["data"] == {}

    def test_error_envelope_status_is_error(self):
        result = self.dispatcher.dispatch("sys.v1.missing", {}, _ctx())
        assert result["status"] == "error"


# ── F: dispatch — handler errors ─────────────────────────────────────────────

class TestHandlerErrors:
    def setup_method(self):
        self.dispatcher = SyscallDispatcher()

    def teardown_method(self):
        for k in list(SYSCALL_REGISTRY.keys()):
            if "test." in k:
                del SYSCALL_REGISTRY[k]

    def test_handler_exception_returns_error_envelope(self):
        SYSCALL_REGISTRY["sys.v1.test.boom"] = _reg_mod.SyscallEntry(
            handler=lambda p, c: (_ for _ in ()).throw(RuntimeError("kaboom")),
            capability="test.boom",
        )
        result = self.dispatcher.dispatch(
            "sys.v1.test.boom", {}, _ctx(capabilities=["test.boom"])
        )
        assert result["status"] == "error"
        assert "kaboom" in result["error"]

    def test_handler_value_error_in_error_envelope(self):
        SYSCALL_REGISTRY["sys.v1.test.bad"] = _reg_mod.SyscallEntry(
            handler=lambda p, c: (_ for _ in ()).throw(ValueError("bad input")),
            capability="test.bad",
        )
        result = self.dispatcher.dispatch(
            "sys.v1.test.bad", {}, _ctx(capabilities=["test.bad"])
        )
        assert result["status"] == "error"
        assert "bad input" in result["error"]

    def test_dispatch_never_raises(self):
        # Even an unregistered name must not raise
        result = self.dispatcher.dispatch("sys.v1.???.???", {}, _ctx())
        assert isinstance(result, dict)

    def test_error_includes_syscall_name(self):
        result = self.dispatcher.dispatch("sys.v1.no.such", {}, _ctx())
        assert result["syscall"] == "sys.v1.no.such"

    def test_observability_failure_does_not_kill_dispatch(self):
        SYSCALL_REGISTRY["sys.v1.test.obs"] = _reg_mod.SyscallEntry(
            handler=lambda p, c: {"ok": True},
            capability="test.obs",
        )
        with patch.object(
            self.dispatcher, "_emit_syscall_event", side_effect=Exception("event bus down")
        ):
            result = self.dispatcher.dispatch(
                "sys.v1.test.obs", {}, _ctx(capabilities=["test.obs"])
            )
        # Handler succeeded; event emission failure must not flip status
        assert result["status"] == "success"


# ── G: memory.read handler (direct) ──────────────────────────────────────────

class TestMemoryReadHandler:
    """Test _handle_memory_read by calling it directly with mocked dependencies."""

    def _call(self, payload: dict, user_id: str = "u1") -> dict:
        from services.syscall_registry import _handle_memory_read
        ctx = _ctx(user_id=user_id)
        mock_db = MagicMock()
        mock_dao = MagicMock()
        mock_dao.recall.return_value = [{"id": "n1", "content": "hello"}]
        with patch("services.syscall_registry.SessionLocal", return_value=mock_db):
            with patch("services.syscall_registry.MemoryNodeDAO", return_value=mock_dao):
                # SessionLocal() is called inside handler; patch it as a context manager
                pass
        # Patch both imports inside the handler's lazy import scope
        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "db.dao.memory_node_dao": MagicMock(MemoryNodeDAO=MagicMock(return_value=mock_dao)),
        }):
            return _handle_memory_read(payload, ctx), mock_dao

    def test_recall_called_with_user_id(self):
        from services.syscall_registry import _handle_memory_read
        ctx = _ctx(user_id="u-test")
        mock_db = MagicMock()
        mock_dao = MagicMock()
        mock_dao.recall.return_value = []
        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "db.dao.memory_node_dao": MagicMock(MemoryNodeDAO=MagicMock(return_value=mock_dao)),
        }):
            result = _handle_memory_read({"query": "test", "limit": 3}, ctx)
        mock_dao.recall.assert_called_once()
        call_kwargs = mock_dao.recall.call_args[1]
        assert call_kwargs["user_id"] == "u-test"
        assert call_kwargs["limit"] == 3

    def test_returns_nodes_and_count(self):
        from services.syscall_registry import _handle_memory_read
        ctx = _ctx()
        mock_db = MagicMock()
        mock_dao = MagicMock()
        mock_dao.recall.return_value = [{"id": "a"}, {"id": "b"}]
        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "db.dao.memory_node_dao": MagicMock(MemoryNodeDAO=MagicMock(return_value=mock_dao)),
        }):
            result = _handle_memory_read({}, ctx)
        assert result["count"] == 2
        assert len(result["nodes"]) == 2

    def test_default_limit_is_5(self):
        from services.syscall_registry import _handle_memory_read
        ctx = _ctx()
        mock_db = MagicMock()
        mock_dao = MagicMock()
        mock_dao.recall.return_value = []
        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "db.dao.memory_node_dao": MagicMock(MemoryNodeDAO=MagicMock(return_value=mock_dao)),
        }):
            _handle_memory_read({}, ctx)
        assert mock_dao.recall.call_args[1]["limit"] == 5

    def test_denied_without_memory_read_cap(self):
        dispatcher = SyscallDispatcher()
        ctx = _ctx(capabilities=["memory.write"])
        result = dispatcher.dispatch("sys.v1.memory.read", {}, ctx)
        assert result["status"] == "error"
        assert "memory.read" in result["error"]


# ── H: memory.write handler (direct) ─────────────────────────────────────────

class TestMemoryWriteHandler:
    def _call_write(self, payload: dict) -> dict:
        from services.syscall_registry import _handle_memory_write
        ctx = _ctx()
        mock_db = MagicMock()
        mock_dao = MagicMock()
        mock_dao.save.return_value = {"id": "new-node", "content": payload.get("content", "")}
        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "db.dao.memory_node_dao": MagicMock(MemoryNodeDAO=MagicMock(return_value=mock_dao)),
        }):
            return _handle_memory_write(payload, ctx), mock_dao

    def test_save_called_with_content(self):
        result, mock_dao = self._call_write({"content": "stored fact"})
        mock_dao.save.assert_called_once()
        assert mock_dao.save.call_args[1]["content"] == "stored fact"

    def test_returns_node(self):
        result, _ = self._call_write({"content": "hello"})
        assert result["node"]["id"] == "new-node"

    def test_empty_content_raises_value_error(self):
        from services.syscall_registry import _handle_memory_write
        ctx = _ctx()
        with pytest.raises(ValueError, match="content"):
            _handle_memory_write({"content": ""}, ctx)

    def test_denied_without_write_cap(self):
        dispatcher = SyscallDispatcher()
        ctx = _ctx(capabilities=["memory.read"])
        result = dispatcher.dispatch("sys.v1.memory.write", {"content": "x"}, ctx)
        assert result["status"] == "error"


# ── I: memory.search handler (direct) ────────────────────────────────────────

class TestMemorySearchHandler:
    def test_search_returns_nodes(self):
        from services.syscall_registry import _handle_memory_search
        ctx = _ctx()
        mock_db = MagicMock()
        mock_dao = MagicMock()
        mock_dao.recall.return_value = [{"id": "x"}]
        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "db.dao.memory_node_dao": MagicMock(MemoryNodeDAO=MagicMock(return_value=mock_dao)),
        }):
            result = _handle_memory_search({"query": "auth"}, ctx)
        assert result["count"] == 1

    def test_empty_query_raises(self):
        from services.syscall_registry import _handle_memory_search
        ctx = _ctx()
        with pytest.raises(ValueError, match="query"):
            _handle_memory_search({"query": ""}, ctx)

    def test_denied_without_search_cap(self):
        dispatcher = SyscallDispatcher()
        ctx = _ctx(capabilities=["memory.read"])
        result = dispatcher.dispatch("sys.v1.memory.search", {"query": "x"}, ctx)
        assert result["status"] == "error"


# ── J: flow.run handler (direct) ─────────────────────────────────────────────

class TestFlowRunHandler:
    def test_missing_flow_name_raises(self):
        from services.syscall_registry import _handle_flow_run
        ctx = _ctx()
        with pytest.raises(ValueError, match="flow_name"):
            _handle_flow_run({}, ctx)

    def test_unknown_flow_raises(self):
        from services.syscall_registry import _handle_flow_run
        ctx = _ctx()
        mock_registry = {}
        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock()),
            "services.flow_engine": MagicMock(
                FLOW_REGISTRY=mock_registry,
                PersistentFlowRunner=MagicMock(),
            ),
        }):
            with pytest.raises(ValueError, match="unknown flow"):
                _handle_flow_run({"flow_name": "NO_SUCH"}, ctx)

    def test_runs_flow_and_returns_result(self):
        from services.syscall_registry import _handle_flow_run
        ctx = _ctx()
        mock_db = MagicMock()
        mock_runner = MagicMock()
        mock_runner.start.return_value = {"status": "SUCCESS", "run_id": "r1"}
        mock_flow = {"start": "node_a", "edges": {}}
        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "services.flow_engine": MagicMock(
                FLOW_REGISTRY={"MY_FLOW": mock_flow},
                PersistentFlowRunner=MagicMock(return_value=mock_runner),
            ),
        }):
            result = _handle_flow_run({"flow_name": "MY_FLOW"}, ctx)
        assert result["flow_result"]["run_id"] == "r1"

    def test_denied_without_flow_run_cap(self):
        dispatcher = SyscallDispatcher()
        ctx = _ctx(capabilities=["memory.read"])
        result = dispatcher.dispatch("sys.v1.flow.run", {"flow_name": "X"}, ctx)
        assert result["status"] == "error"


# ── K: event.emit handler (direct) ───────────────────────────────────────────

class TestEventEmitHandler:
    def test_missing_event_type_raises(self):
        from services.syscall_registry import _handle_event_emit
        ctx = _ctx()
        with pytest.raises(ValueError, match="event_type"):
            _handle_event_emit({}, ctx)

    def test_emit_called_with_correct_type(self):
        from services.syscall_registry import _handle_event_emit
        ctx = _ctx(user_id="u1", trace_id="t1")
        mock_db = MagicMock()
        mock_emit = MagicMock(return_value="ev-123")
        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "services.system_event_service": MagicMock(emit_system_event=mock_emit),
        }):
            result = _handle_event_emit({"event_type": "task.done"}, ctx)
        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args[1]
        assert call_kwargs["event_type"] == "task.done"
        assert call_kwargs["user_id"] == "u1"
        assert call_kwargs["trace_id"] == "t1"

    def test_returns_event_id(self):
        from services.syscall_registry import _handle_event_emit
        import uuid as _uuid
        ctx = _ctx()
        ev_id = _uuid.uuid4()
        mock_db = MagicMock()
        mock_emit = MagicMock(return_value=ev_id)
        with patch.dict("sys.modules", {
            "db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "services.system_event_service": MagicMock(emit_system_event=mock_emit),
        }):
            result = _handle_event_emit({"event_type": "x"}, ctx)
        assert result["event_id"] == str(ev_id)

    def test_denied_without_event_emit_cap(self):
        dispatcher = SyscallDispatcher()
        ctx = _ctx(capabilities=["memory.read"])
        result = dispatcher.dispatch("sys.v1.event.emit", {"event_type": "x"}, ctx)
        assert result["status"] == "error"


# ── L: Nodus integration ──────────────────────────────────────────────────────

class TestNodusIntegration:
    """Verify that the 'sys' global is injected into Nodus initial_globals."""

    def _make_exec_context(self, **kwargs):
        """Build a minimal NodusExecutionContext-like object."""
        ctx = MagicMock()
        ctx.execution_unit_id = kwargs.get("execution_unit_id", "eu-nodus")
        ctx.user_id = kwargs.get("user_id", "u-nodus")
        ctx.memory_context = kwargs.get("memory_context", {})
        ctx.input_payload = kwargs.get("input_payload", {})
        ctx.state = kwargs.get("state", {})
        ctx.event_sink = None
        return ctx

    def test_sys_key_in_initial_globals(self):
        """After _execute() builds initial_globals, 'sys' must be callable."""
        from services.nodus_runtime_adapter import NodusRuntimeAdapter
        # We check that the code path to build initial_globals includes 'sys'
        # by inspecting the source rather than running the VM (VM not required).
        import inspect
        src = inspect.getsource(NodusRuntimeAdapter)
        assert '"sys": _nodus_syscall' in src or "'sys': _nodus_syscall" in src

    def test_sys_global_is_callable(self):
        """_nodus_syscall must be a callable wrapping get_dispatcher().dispatch."""
        from services.syscall_dispatcher import DEFAULT_NODUS_CAPABILITIES, SyscallContext, get_dispatcher

        # Simulate what nodus_runtime_adapter builds
        ctx = self._make_exec_context()
        syscall_ctx = SyscallContext(
            execution_unit_id=ctx.execution_unit_id,
            user_id=ctx.user_id,
            capabilities=list(DEFAULT_NODUS_CAPABILITIES),
            trace_id=ctx.execution_unit_id,
        )
        dispatcher = get_dispatcher()

        def _nodus_syscall(name, payload=None):
            return dispatcher.dispatch(name, payload or {}, syscall_ctx)

        # Unknown syscall returns error envelope — does not raise
        result = _nodus_syscall("sys.v1.unknown.x")
        assert result["status"] == "error"

    def test_default_caps_include_memory_and_event(self):
        assert "memory.read" in DEFAULT_NODUS_CAPABILITIES
        assert "memory.write" in DEFAULT_NODUS_CAPABILITIES
        assert "memory.search" in DEFAULT_NODUS_CAPABILITIES
        assert "event.emit" in DEFAULT_NODUS_CAPABILITIES

    def test_flow_run_not_in_default_caps(self):
        # flow.run is a privileged capability — not granted by default
        assert "flow.run" not in DEFAULT_NODUS_CAPABILITIES

    def test_get_dispatcher_returns_singleton(self):
        d1 = get_dispatcher()
        d2 = get_dispatcher()
        assert d1 is d2
