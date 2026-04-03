"""
Unit tests for Syscall Versioning and ABI Stability — Sprint Syscall Versioning

Groups
------
A  parse_syscall_name              (8 tests)
B  validate_payload / validate_input (10 tests)
C  validate_output                 (4 tests)
D  SyscallSpec                     (6 tests)
E  VersionedSyscallRegistry        (10 tests)
F  Dispatcher — input validation   (5 tests)
G  Dispatcher — deprecation        (5 tests)
H  Dispatcher — version in envelope (5 tests)
I  Dispatcher — version fallback   (4 tests)
J  GET /platform/syscalls          (6 tests)
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

# ── helpers ────────────────────────────────────────────────────────────────────

def _ctx(**kwargs):
    from kernel.syscall_registry import SyscallContext
    defaults = dict(
        execution_unit_id="eu-test",
        user_id="user-abc",
        capabilities=["memory.read", "memory.write", "memory.search",
                      "memory.list", "memory.tree", "memory.trace",
                      "event.emit", "flow.run", "test.cap"],
        trace_id="trace-test",
    )
    defaults.update(kwargs)
    return SyscallContext(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# A — parse_syscall_name
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseSyscallName:
    from kernel.syscall_versioning import parse_syscall_name

    def test_standard_name(self):
        from kernel.syscall_versioning import parse_syscall_name
        assert parse_syscall_name("sys.v1.memory.read") == ("v1", "memory.read")

    def test_v2_name(self):
        from kernel.syscall_versioning import parse_syscall_name
        assert parse_syscall_name("sys.v2.memory.read") == ("v2", "memory.read")

    def test_multi_dot_action(self):
        from kernel.syscall_versioning import parse_syscall_name
        v, a = parse_syscall_name("sys.v1.task.complete_full")
        assert v == "v1"
        assert a == "task.complete_full"

    def test_wrong_prefix_raises(self):
        from kernel.syscall_versioning import parse_syscall_name
        with pytest.raises(ValueError, match="must start with"):
            parse_syscall_name("bad.v1.memory.read")

    def test_missing_action_raises(self):
        from kernel.syscall_versioning import parse_syscall_name
        with pytest.raises(ValueError):
            parse_syscall_name("sys.v1")

    def test_missing_version_raises(self):
        from kernel.syscall_versioning import parse_syscall_name
        with pytest.raises(ValueError):
            parse_syscall_name("sys.")

    def test_event_emit(self):
        from kernel.syscall_versioning import parse_syscall_name
        assert parse_syscall_name("sys.v1.event.emit") == ("v1", "event.emit")

    def test_flow_run(self):
        from kernel.syscall_versioning import parse_syscall_name
        assert parse_syscall_name("sys.v1.flow.run") == ("v1", "flow.run")


# ═══════════════════════════════════════════════════════════════════════════════
# B — validate_payload / validate_input
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidatePayload:
    def test_empty_schema_always_valid(self):
        from kernel.syscall_versioning import validate_payload
        assert validate_payload({}, {"anything": "goes"}) == []

    def test_required_field_present(self):
        from kernel.syscall_versioning import validate_payload
        schema = {"required": ["content"]}
        assert validate_payload(schema, {"content": "hello"}) == []

    def test_required_field_missing(self):
        from kernel.syscall_versioning import validate_payload
        schema = {"required": ["content"]}
        errors = validate_payload(schema, {})
        assert len(errors) == 1
        assert "content" in errors[0]

    def test_multiple_required_missing(self):
        from kernel.syscall_versioning import validate_payload
        schema = {"required": ["a", "b", "c"]}
        errors = validate_payload(schema, {"a": 1})
        assert len(errors) == 2

    def test_type_check_string_ok(self):
        from kernel.syscall_versioning import validate_payload
        schema = {"properties": {"name": {"type": "string"}}}
        assert validate_payload(schema, {"name": "alice"}) == []

    def test_type_check_string_fail(self):
        from kernel.syscall_versioning import validate_payload
        schema = {"properties": {"limit": {"type": "int"}}}
        errors = validate_payload(schema, {"limit": "ten"})
        assert errors

    def test_type_check_list(self):
        from kernel.syscall_versioning import validate_payload
        schema = {"properties": {"tags": {"type": "list"}}}
        assert validate_payload(schema, {"tags": ["a", "b"]}) == []

    def test_optional_field_absent_is_ok(self):
        from kernel.syscall_versioning import validate_payload
        schema = {"properties": {"optional_field": {"type": "string"}}}
        assert validate_payload(schema, {}) == []

    def test_unknown_type_skipped(self):
        from kernel.syscall_versioning import validate_payload
        schema = {"properties": {"x": {"type": "uuid"}}}
        assert validate_payload(schema, {"x": "any-value"}) == []

    def test_validate_input_alias(self):
        from kernel.syscall_versioning import validate_input
        schema = {"required": ["query"]}
        assert validate_input(schema, {"query": "hello"}) == []


# ═══════════════════════════════════════════════════════════════════════════════
# C — validate_output
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateOutput:
    def test_valid_output(self):
        from kernel.syscall_versioning import validate_output
        schema = {"required": ["nodes", "count"]}
        assert validate_output(schema, {"nodes": [], "count": 0}) == []

    def test_missing_required_output_field(self):
        from kernel.syscall_versioning import validate_output
        schema = {"required": ["nodes", "count"]}
        errors = validate_output(schema, {"nodes": []})
        assert len(errors) == 1
        assert "count" in errors[0]

    def test_empty_schema_valid(self):
        from kernel.syscall_versioning import validate_output
        assert validate_output({}, {"anything": "works"}) == []

    def test_type_mismatch_detected(self):
        from kernel.syscall_versioning import validate_output
        schema = {"properties": {"count": {"type": "int"}}}
        errors = validate_output(schema, {"count": "five"})
        assert errors


# ═══════════════════════════════════════════════════════════════════════════════
# D — SyscallSpec
# ═══════════════════════════════════════════════════════════════════════════════

class TestSyscallSpec:
    def test_full_name_derived(self):
        from kernel.syscall_versioning import SyscallSpec
        spec = SyscallSpec(name="memory.read", version="v1")
        assert spec.full_name == "sys.v1.memory.read"

    def test_deprecation_message_none_if_not_deprecated(self):
        from kernel.syscall_versioning import SyscallSpec
        spec = SyscallSpec(name="memory.read", version="v1")
        assert spec.deprecation_message() is None

    def test_deprecation_message_with_replacement(self):
        from kernel.syscall_versioning import SyscallSpec
        spec = SyscallSpec(
            name="memory.read", version="v1",
            deprecated=True, deprecated_since="v1.3",
            replacement="sys.v2.memory.read",
        )
        msg = spec.deprecation_message()
        assert msg is not None
        assert "deprecated" in msg
        assert "sys.v2.memory.read" in msg

    def test_to_dict_contains_required_keys(self):
        from kernel.syscall_versioning import SyscallSpec
        spec = SyscallSpec(name="memory.read", version="v1", capability="memory.read")
        d = spec.to_dict()
        assert d["full_name"] == "sys.v1.memory.read"
        assert d["capability"] == "memory.read"
        assert "input_schema" in d
        assert "deprecated" in d

    def test_to_dict_deprecated_false_by_default(self):
        from kernel.syscall_versioning import SyscallSpec
        spec = SyscallSpec(name="flow.run", version="v1")
        assert spec.to_dict()["deprecated"] is False

    def test_stable_true_by_default(self):
        from kernel.syscall_versioning import SyscallSpec
        spec = SyscallSpec(name="event.emit", version="v1")
        assert spec.stable is True


# ═══════════════════════════════════════════════════════════════════════════════
# E — VersionedSyscallRegistry
# ═══════════════════════════════════════════════════════════════════════════════

class TestVersionedSyscallRegistry:
    def _make_entry(self, cap="test.cap"):
        from kernel.syscall_registry import SyscallEntry
        return SyscallEntry(handler=lambda p, c: {}, capability=cap)

    def test_flat_set_and_get(self):
        from kernel.syscall_registry import VersionedSyscallRegistry
        reg = VersionedSyscallRegistry()
        e = self._make_entry()
        reg["sys.v1.test.ping"] = e
        assert reg["sys.v1.test.ping"] is e

    def test_versioned_view_populated(self):
        from kernel.syscall_registry import VersionedSyscallRegistry
        reg = VersionedSyscallRegistry()
        e = self._make_entry()
        reg["sys.v1.test.ping"] = e
        assert "v1" in reg.versioned
        assert "test.ping" in reg.versioned["v1"]

    def test_multi_version_separation(self):
        from kernel.syscall_registry import VersionedSyscallRegistry
        reg = VersionedSyscallRegistry()
        e1 = self._make_entry("test.cap1")
        e2 = self._make_entry("test.cap2")
        reg["sys.v1.test.action"] = e1
        reg["sys.v2.test.action"] = e2
        assert reg.get_version("v1")["test.action"] is e1
        assert reg.get_version("v2")["test.action"] is e2

    def test_delete_removes_from_both_views(self):
        from kernel.syscall_registry import VersionedSyscallRegistry
        reg = VersionedSyscallRegistry()
        reg["sys.v1.test.del"] = self._make_entry()
        del reg["sys.v1.test.del"]
        assert "sys.v1.test.del" not in reg
        assert "test.del" not in reg.get_version("v1")

    def test_pop_removes_from_both_views(self):
        from kernel.syscall_registry import VersionedSyscallRegistry
        reg = VersionedSyscallRegistry()
        e = self._make_entry()
        reg["sys.v1.test.pop"] = e
        val = reg.pop("sys.v1.test.pop")
        assert val is e
        assert "sys.v1.test.pop" not in reg

    def test_contains_uses_flat_key(self):
        from kernel.syscall_registry import VersionedSyscallRegistry
        reg = VersionedSyscallRegistry()
        reg["sys.v1.test.contains"] = self._make_entry()
        assert "sys.v1.test.contains" in reg
        assert "sys.v9.test.contains" not in reg

    def test_versions_sorted(self):
        from kernel.syscall_registry import VersionedSyscallRegistry
        reg = VersionedSyscallRegistry()
        reg["sys.v2.x.y"] = self._make_entry()
        reg["sys.v1.x.y"] = self._make_entry()
        assert reg.versions() == ["v1", "v2"]

    def test_len_counts_flat_entries(self):
        from kernel.syscall_registry import VersionedSyscallRegistry
        reg = VersionedSyscallRegistry()
        reg["sys.v1.a.b"] = self._make_entry()
        reg["sys.v2.a.b"] = self._make_entry()
        assert len(reg) == 2

    def test_iter_yields_flat_keys(self):
        from kernel.syscall_registry import VersionedSyscallRegistry
        reg = VersionedSyscallRegistry()
        reg["sys.v1.a.b"] = self._make_entry()
        reg["sys.v1.a.c"] = self._make_entry()
        assert set(reg) == {"sys.v1.a.b", "sys.v1.a.c"}

    def test_non_sys_key_not_in_versioned(self):
        from kernel.syscall_registry import VersionedSyscallRegistry
        reg = VersionedSyscallRegistry()
        # Store an entry with a non-standard key (shouldn't happen in prod,
        # but the mapping must not crash)
        e = self._make_entry()
        reg["not_a_sys_key"] = e  # version parsing fails silently
        assert reg["not_a_sys_key"] is e
        assert "not_a_sys_key" not in reg.versioned


# ═══════════════════════════════════════════════════════════════════════════════
# F — Dispatcher — input validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestDispatcherInputValidation:
    def setup_method(self):
        from kernel.syscall_dispatcher import SyscallDispatcher
        from kernel.syscall_registry import SYSCALL_REGISTRY, SyscallEntry
        self.dispatcher = SyscallDispatcher()
        SYSCALL_REGISTRY["sys.v1.test.validated"] = SyscallEntry(
            handler=lambda p, c: {"ok": True},
            capability="test.cap",
            input_schema={
                "required": ["required_field"],
                "properties": {
                    "required_field": {"type": "string"},
                    "optional_int": {"type": "int"},
                },
            },
        )

    def teardown_method(self):
        from kernel.syscall_registry import SYSCALL_REGISTRY
        SYSCALL_REGISTRY.pop("sys.v1.test.validated", None)

    def test_valid_payload_passes(self):
        result = self.dispatcher.dispatch(
            "sys.v1.test.validated",
            {"required_field": "hello"},
            _ctx(),
        )
        assert result["status"] == "success"

    def test_missing_required_field_returns_error(self):
        result = self.dispatcher.dispatch(
            "sys.v1.test.validated",
            {},
            _ctx(),
        )
        assert result["status"] == "error"
        assert "Input validation failed" in result["error"]
        assert "required_field" in result["error"]

    def test_wrong_type_returns_error(self):
        result = self.dispatcher.dispatch(
            "sys.v1.test.validated",
            {"required_field": "ok", "optional_int": "not-an-int"},
            _ctx(),
        )
        assert result["status"] == "error"
        assert "optional_int" in result["error"]

    def test_no_schema_skips_validation(self):
        from kernel.syscall_registry import SYSCALL_REGISTRY, SyscallEntry
        SYSCALL_REGISTRY["sys.v1.test.noschema"] = SyscallEntry(
            handler=lambda p, c: {"ok": True},
            capability="test.cap",
        )
        result = self.dispatcher.dispatch("sys.v1.test.noschema", {}, _ctx())
        assert result["status"] == "success"
        SYSCALL_REGISTRY.pop("sys.v1.test.noschema", None)

    def test_version_in_error_envelope(self):
        result = self.dispatcher.dispatch(
            "sys.v1.test.validated",
            {},
            _ctx(),
        )
        assert result["version"] == "v1"


# ═══════════════════════════════════════════════════════════════════════════════
# G — Dispatcher — deprecation
# ═══════════════════════════════════════════════════════════════════════════════

class TestDispatcherDeprecation:
    def setup_method(self):
        from kernel.syscall_dispatcher import SyscallDispatcher
        from kernel.syscall_registry import SYSCALL_REGISTRY, SyscallEntry
        self.dispatcher = SyscallDispatcher()
        SYSCALL_REGISTRY["sys.v1.test.deprecated"] = SyscallEntry(
            handler=lambda p, c: {"result": "ok"},
            capability="test.cap",
            deprecated=True,
            deprecated_since="v1.2",
            replacement="sys.v2.test.replacement",
        )
        SYSCALL_REGISTRY["sys.v1.test.nodep"] = SyscallEntry(
            handler=lambda p, c: {"result": "ok"},
            capability="test.cap",
            deprecated=False,
        )

    def teardown_method(self):
        from kernel.syscall_registry import SYSCALL_REGISTRY
        SYSCALL_REGISTRY.pop("sys.v1.test.deprecated", None)
        SYSCALL_REGISTRY.pop("sys.v1.test.nodep", None)

    def test_deprecated_syscall_still_executes(self):
        result = self.dispatcher.dispatch("sys.v1.test.deprecated", {}, _ctx())
        assert result["status"] == "success"
        assert result["data"] == {"result": "ok"}

    def test_deprecated_sets_warning_in_envelope(self):
        result = self.dispatcher.dispatch("sys.v1.test.deprecated", {}, _ctx())
        assert result["warning"] is not None
        assert "deprecated" in result["warning"]

    def test_deprecated_warning_mentions_replacement(self):
        result = self.dispatcher.dispatch("sys.v1.test.deprecated", {}, _ctx())
        assert "sys.v2.test.replacement" in result["warning"]

    def test_non_deprecated_warning_is_none(self):
        result = self.dispatcher.dispatch("sys.v1.test.nodep", {}, _ctx())
        assert result["warning"] is None

    def test_deprecated_since_in_warning(self):
        result = self.dispatcher.dispatch("sys.v1.test.deprecated", {}, _ctx())
        assert "v1.2" in result["warning"]


# ═══════════════════════════════════════════════════════════════════════════════
# H — Dispatcher — version in envelope
# ═══════════════════════════════════════════════════════════════════════════════

class TestDispatcherVersionEnvelope:
    def setup_method(self):
        from kernel.syscall_dispatcher import SyscallDispatcher
        from kernel.syscall_registry import SYSCALL_REGISTRY, SyscallEntry
        self.dispatcher = SyscallDispatcher()
        for ver in ("v1", "v2"):
            SYSCALL_REGISTRY[f"sys.{ver}.test.versioned"] = SyscallEntry(
                handler=lambda p, c: {"ver": "set"},
                capability="test.cap",
            )

    def teardown_method(self):
        from kernel.syscall_registry import SYSCALL_REGISTRY
        SYSCALL_REGISTRY.pop("sys.v1.test.versioned", None)
        SYSCALL_REGISTRY.pop("sys.v2.test.versioned", None)

    def test_v1_version_in_success_envelope(self):
        result = self.dispatcher.dispatch("sys.v1.test.versioned", {}, _ctx())
        assert result["version"] == "v1"

    def test_v2_version_in_success_envelope(self):
        result = self.dispatcher.dispatch("sys.v2.test.versioned", {}, _ctx())
        assert result["version"] == "v2"

    def test_unknown_syscall_error_includes_version(self):
        result = self.dispatcher.dispatch("sys.v1.unknown.syscall", {}, _ctx())
        assert result["status"] == "error"
        assert result["version"] == "v1"

    def test_warning_none_on_success_non_deprecated(self):
        result = self.dispatcher.dispatch("sys.v1.test.versioned", {}, _ctx())
        assert result["warning"] is None

    def test_version_v2_in_builtin_registry(self):
        # sys.v2.memory.read is registered in the built-in registry
        from kernel.syscall_registry import SYSCALL_REGISTRY
        assert "sys.v2.memory.read" in SYSCALL_REGISTRY
        assert SYSCALL_REGISTRY.get_version("v2").get("memory.read") is not None


# ═══════════════════════════════════════════════════════════════════════════════
# I — Dispatcher — version fallback
# ═══════════════════════════════════════════════════════════════════════════════

class TestDispatcherVersionFallback:
    def setup_method(self):
        from kernel.syscall_dispatcher import SyscallDispatcher
        from kernel.syscall_registry import SYSCALL_REGISTRY, SyscallEntry
        self.dispatcher = SyscallDispatcher()
        SYSCALL_REGISTRY["sys.v1.test.fallback_target"] = SyscallEntry(
            handler=lambda p, c: {"fallback": True},
            capability="test.cap",
        )

    def teardown_method(self):
        from kernel.syscall_registry import SYSCALL_REGISTRY
        SYSCALL_REGISTRY.pop("sys.v1.test.fallback_target", None)

    def test_unknown_version_no_fallback_returns_error(self):
        """Default: SYSCALL_VERSION_FALLBACK=False → error on unknown version."""
        result = self.dispatcher.dispatch("sys.v9.test.fallback_target", {}, _ctx())
        assert result["status"] == "error"
        assert "version" in result["error"].lower() or "unknown" in result["error"].lower()

    def test_fallback_enabled_routes_to_latest_stable(self):
        """With fallback enabled, unknown version falls back to v1."""
        import kernel.syscall_dispatcher as _disp_mod
        original = _disp_mod.SYSCALL_VERSION_FALLBACK
        try:
            _disp_mod.SYSCALL_VERSION_FALLBACK = True
            # Re-import resolve_version with new constant from module
            import importlib
            import kernel.syscall_versioning as _ver_mod
            # Patch resolve_version to use fallback=True
            with patch.object(_ver_mod, "SYSCALL_VERSION_FALLBACK", True):
                with patch("kernel.syscall_dispatcher.SYSCALL_VERSION_FALLBACK", True):
                    result = self.dispatcher.dispatch(
                        "sys.v9.test.fallback_target", {}, _ctx()
                    )
                    # Fallback lands on v1 which has the handler
                    assert result["status"] == "success"
                    assert result["data"]["fallback"] is True
        finally:
            _disp_mod.SYSCALL_VERSION_FALLBACK = original

    def test_resolve_version_no_fallback(self):
        from kernel.syscall_versioning import resolve_version
        result = resolve_version("v9", frozenset({"v1"}), fallback=False)
        assert result is None

    def test_resolve_version_with_fallback(self):
        from kernel.syscall_versioning import resolve_version
        result = resolve_version("v9", frozenset({"v1"}), fallback=True)
        assert result == "v1"


# ═══════════════════════════════════════════════════════════════════════════════
# J — GET /platform/syscalls endpoint
# ═══════════════════════════════════════════════════════════════════════════════

def _make_headers():
    import os
    from jose import jwt
    secret = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
    token = jwt.encode({"sub": "test_user", "user_id": 1}, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


class TestSyscallsEndpoint:
    def _client(self):
        from fastapi.testclient import TestClient
        from main import app
        return TestClient(app, raise_server_exceptions=False)

    def _auth(self, client):
        return _make_headers()

    def test_endpoint_returns_200(self):
        client = self._client()
        headers = self._auth(client)
        resp = client.get("/platform/syscalls", headers=headers)
        assert resp.status_code == 200

    def test_response_has_versions_key(self):
        client = self._client()
        headers = self._auth(client)
        resp = client.get("/platform/syscalls", headers=headers)
        data = resp.json()
        assert "versions" in data
        assert "v1" in data["versions"]

    def test_response_has_syscalls_key(self):
        client = self._client()
        headers = self._auth(client)
        resp = client.get("/platform/syscalls", headers=headers)
        data = resp.json()
        assert "syscalls" in data
        assert "v1" in data["syscalls"]

    def test_memory_read_present_in_v1(self):
        client = self._client()
        headers = self._auth(client)
        resp = client.get("/platform/syscalls", headers=headers)
        data = resp.json()
        assert "memory.read" in data["syscalls"]["v1"]

    def test_v2_present(self):
        client = self._client()
        headers = self._auth(client)
        resp = client.get("/platform/syscalls", headers=headers)
        data = resp.json()
        assert "v2" in data["versions"]
        assert "memory.read" in data["syscalls"]["v2"]

    def test_version_filter(self):
        client = self._client()
        headers = self._auth(client)
        resp = client.get("/platform/syscalls?version=v1", headers=headers)
        data = resp.json()
        assert list(data["syscalls"].keys()) == ["v1"]

    def test_unknown_version_returns_404(self):
        client = self._client()
        headers = self._auth(client)
        resp = client.get("/platform/syscalls?version=v99", headers=headers)
        assert resp.status_code == 404
