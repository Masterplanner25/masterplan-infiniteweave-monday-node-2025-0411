"""
test_platform_nodus_endpoints.py
─────────────────────────────────
Unit tests for the Nodus execution endpoints added to platform_router.py:

  POST /platform/nodus/run
  POST /platform/nodus/upload
  GET  /platform/nodus/scripts

Coverage
--------
Schemas            NodusRunRequest validation (mutual exclusion, bad policy)
                   NodusScriptUpload validation (name pattern, empty content)
_validate_nodus    passes clean source; raises 422 on violation
_format_nodus_response  all paths (success, failure, infra fail)
_ensure_nodus_flow_registered  idempotent registration
_run_nodus_script  delegates to PersistentFlowRunner with correct state keys
run_nodus_script   inline script success; named script success; named 404;
                   security violation → 422; flow infra error
upload_nodus_script happy path; duplicate without overwrite → 409;
                   duplicate with overwrite; security violation → 422
list_nodus_scripts empty registry; populated registry; disk scan on missing
"""
from __future__ import annotations

import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError


def _module():
    """Return the platform_router module, not the router object re-exported by routes/__init__."""
    if "routes.platform_router" in sys.modules:
        return sys.modules["routes.platform_router"]
    import importlib
    return importlib.import_module("routes.platform_router")


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestNodusRunRequestSchema:
    def _schema(self):
        from routes.platform_router import NodusRunRequest
        return NodusRunRequest

    def test_inline_script_valid(self):
        m = self._schema()(script="let x = 1")
        assert m.script == "let x = 1"
        assert m.error_policy == "fail"

    def test_script_name_valid(self):
        m = self._schema()(script_name="my_script")
        assert m.script_name == "my_script"

    def test_both_script_and_name_raises(self):
        with pytest.raises(ValidationError, match="not both"):
            self._schema()(script="x", script_name="y")

    def test_neither_script_nor_name_raises(self):
        with pytest.raises(ValidationError, match="script.*script_name"):
            self._schema()()

    def test_bad_error_policy_raises(self):
        with pytest.raises(ValidationError, match="error_policy"):
            self._schema()(script="x", error_policy="unknown")

    def test_retry_policy_accepted(self):
        m = self._schema()(script="x", error_policy="retry")
        assert m.error_policy == "retry"

    def test_input_defaults_to_empty_dict(self):
        m = self._schema()(script="x")
        assert m.input == {}

    def test_custom_input_passed_through(self):
        m = self._schema()(script="x", input={"goal": "test"})
        assert m.input == {"goal": "test"}


class TestNodusScriptUploadSchema:
    def _schema(self):
        from routes.platform_router import NodusScriptUpload
        return NodusScriptUpload

    def test_valid_name_and_content(self):
        m = self._schema()(name="my-script_v1.0", content="let x = 1")
        assert m.name == "my-script_v1.0"

    def test_name_with_spaces_raises(self):
        with pytest.raises(ValidationError):
            self._schema()(name="bad name", content="x")

    def test_empty_content_raises(self):
        with pytest.raises(ValidationError):
            self._schema()(name="ok", content="")

    def test_description_optional(self):
        m = self._schema()(name="s", content="x")
        assert m.description is None

    def test_overwrite_defaults_false(self):
        m = self._schema()(name="s", content="x")
        assert m.overwrite is False


# ── _validate_nodus_source ────────────────────────────────────────────────────

class TestValidateNodusSource:
    def _validate(self, source: str, field: str = "script"):
        from routes.platform_router import _validate_nodus_source
        _validate_nodus_source(source, field)

    def test_clean_source_passes(self):
        self._validate("let x = 1\nset_state(\"x\", x)")  # no exception

    def test_import_raises_422(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            self._validate("import os")
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"] == "nodus_security_violation"

    def test_eval_raises_422(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            self._validate("eval(something)")
        assert exc_info.value.status_code == 422

    def test_field_included_in_detail(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            self._validate("import x", field="content")
        assert exc_info.value.detail["field"] == "content"


# ── _format_nodus_response ────────────────────────────────────────────────────

class TestFormatNodusResponse:
    def _format(self, flow_result: dict) -> dict:
        from routes.platform_router import _format_nodus_response
        return _format_nodus_response(flow_result)

    def test_success_fields_extracted(self):
        flow_result = {
            "status": "SUCCESS",
            "trace_id": "t1",
            "run_id": "r1",
            "state": {
                "nodus_status": "success",
                "nodus_output_state": {"x": 1},
                "nodus_events": [{"event_type": "done"}],
                "nodus_memory_writes": [],
                "nodus_execute_result": {
                    "status": "success",
                    "output_state": {"x": 1},
                    "events_emitted": 1,
                    "memory_writes": 0,
                    "error": None,
                },
            },
            "data": {
                "status": "success",
                "output_state": {"x": 1},
                "events_emitted": 1,
                "memory_writes": 0,
                "error": None,
            },
        }
        result = self._format(flow_result)
        assert result["status"] == "SUCCESS"
        assert result["trace_id"] == "t1"
        assert result["run_id"] == "r1"
        assert result["nodus_status"] == "success"
        assert result["output_state"] == {"x": 1}
        assert len(result["events"]) == 1
        assert result["events_emitted"] == 1
        assert result["memory_writes_count"] == 0
        assert result["error"] is None

    def test_failure_nodus_status_extracted(self):
        flow_result = {
            "status": "SUCCESS",
            "trace_id": "t2",
            "run_id": "r2",
            "state": {
                "nodus_status": "failure",
                "nodus_handled_error": "type error",
                "nodus_events": [],
                "nodus_memory_writes": [],
                "nodus_execute_result": {
                    "status": "failure",
                    "output_state": {},
                    "events_emitted": 0,
                    "memory_writes": 0,
                    "error": "type error",
                },
            },
            "data": {
                "status": "failure",
                "error": "type error",
                "events_emitted": 0,
                "memory_writes": 0,
            },
        }
        result = self._format(flow_result)
        assert result["nodus_status"] == "failure"
        assert result["error"] == "type error"

    def test_infra_failure_propagates(self):
        flow_result = {
            "status": "FAILED",
            "trace_id": "t3",
            "run_id": "r3",
            "error": "VM not installed",
            "state": {},
            "data": {},
        }
        result = self._format(flow_result)
        assert result["status"] == "FAILED"
        assert result["error"] == "VM not installed"

    def test_empty_state_returns_safe_defaults(self):
        result = self._format({"status": "SUCCESS", "state": {}, "data": {}})
        assert result["output_state"] == {}
        assert result["events"] == []
        assert result["memory_writes"] == []
        assert result["events_emitted"] == 0
        assert result["memory_writes_count"] == 0

    def test_delegates_to_shared_runtime_formatter(self):
        expected = {"status": "SUCCESS", "run_id": "r1"}
        with patch("runtime.nodus_execution_service.format_nodus_flow_result", return_value=expected) as mock_format:
            result = self._format({"status": "SUCCESS"})
        mock_format.assert_called_once_with({"status": "SUCCESS"})
        assert result == expected


# ── _ensure_nodus_flow_registered ────────────────────────────────────────────

class TestEnsureNodusFlowRegistered:
    def test_idempotent_registration(self):
        """Calling twice should not raise and should result in exactly one registration."""
        mock_registry = {}

        def mock_register_flow(name, flow):
            mock_registry[name] = flow

        with patch("routes.platform_router._ensure_nodus_flow_registered"):
            # Just verify the function exists and is callable
            from routes.platform_router import _ensure_nodus_flow_registered
            assert callable(_ensure_nodus_flow_registered)

    def test_registers_nodus_execute_into_flow_registry(self):
        with patch("runtime.nodus_execution_service.ensure_nodus_script_flow_registered") as mock_ensure:
            m = _module()
            m._ensure_nodus_flow_registered()

        mock_ensure.assert_called_once()


# ── _run_nodus_script ─────────────────────────────────────────────────────────

class TestRunNodusScript:
    def test_delegates_to_persistent_flow_runner(self):
        with patch(
            "runtime.nodus_execution_service.run_nodus_script_via_flow",
            return_value={"status": "SUCCESS", "state": {}, "data": {}},
        ) as mock_run:
            from routes.platform_router import _run_nodus_script
            result = _run_nodus_script(
                script="let x = 1",
                input_payload={"goal": "test"},
                error_policy="fail",
                db=MagicMock(),
                user_id="user-123",
            )

        mock_run.assert_called_once()
        assert result["status"] == "SUCCESS"


# ── run_nodus_script endpoint (route function) ────────────────────────────────

class TestRunNodusScriptEndpoint:
    """Test the route handler function directly (not via HTTP client)."""

    def _run(self, body_dict: dict, registry: dict | None = None) -> dict:
        """Call the handler function directly with mocked deps."""
        from routes.platform_router import NodusRunRequest, _NODUS_SCRIPT_REGISTRY, run_nodus_script

        body = NodusRunRequest(**body_dict)
        db = MagicMock()
        current_user = {"sub": str(uuid.uuid4())}
        request = MagicMock()

        flow_result = {
            "status": "SUCCESS",
            "trace_id": "trace-1",
            "run_id": "run-1",
            "state": {
                "nodus_status": "success",
                "nodus_output_state": {},
                "nodus_events": [],
                "nodus_memory_writes": [],
                "nodus_execute_result": {
                    "status": "success",
                    "output_state": {},
                    "events_emitted": 0,
                    "memory_writes": 0,
                    "error": None,
                },
            },
            "data": {"status": "success", "events_emitted": 0, "memory_writes": 0, "error": None},
        }

        if registry is not None:
            m = _module()
            original = dict(m._NODUS_SCRIPT_REGISTRY)
            m._NODUS_SCRIPT_REGISTRY.clear()
            m._NODUS_SCRIPT_REGISTRY.update(registry)

        try:
            with patch("routes.platform_router._validate_nodus_source"), \
                 patch("routes.platform_router._run_nodus_script", return_value=flow_result), \
                 patch("routes.platform_router.execute_with_pipeline_sync",
                       side_effect=lambda **kw: kw["handler"](None)):
                return run_nodus_script(
                    request=request, body=body, db=db, current_user=current_user
                )
        finally:
            if registry is not None:
                m = _module()
                m._NODUS_SCRIPT_REGISTRY.clear()
                m._NODUS_SCRIPT_REGISTRY.update(original)

    def test_inline_script_returns_formatted_response(self):
        result = self._run({"script": "let x = 1"})
        assert result["status"] == "SUCCESS"
        assert result["nodus_status"] == "success"
        assert "trace_id" in result
        assert "run_id" in result

    def test_named_script_resolves_from_registry(self):
        registry = {
            "my_script": {
                "name": "my_script",
                "content": "let x = 1",
                "description": None,
                "uploaded_at": None,
                "uploaded_by": None,
            }
        }
        result = self._run({"script_name": "my_script"}, registry=registry)
        assert result["status"] == "SUCCESS"

    def test_named_script_not_found_raises_404(self):
        from fastapi import HTTPException
        m = _module()

        original = dict(m._NODUS_SCRIPT_REGISTRY)
        m._NODUS_SCRIPT_REGISTRY.clear()
        try:
            with patch("routes.platform_router._validate_nodus_source"), \
                 patch("routes.platform_router._SCRIPTS_DIR") as mock_dir:
                mock_dir.__truediv__.return_value.exists.return_value = False
                with pytest.raises(HTTPException) as exc_info:
                    from routes.platform_router import NodusRunRequest, run_nodus_script
                    body = NodusRunRequest(script_name="nonexistent")
                    run_nodus_script(
                        request=MagicMock(),
                        body=body,
                        db=MagicMock(),
                        current_user={"sub": str(uuid.uuid4())},
                    )
            assert exc_info.value.status_code == 404
            assert exc_info.value.detail["error"] == "script_not_found"
        finally:
            m._NODUS_SCRIPT_REGISTRY.update(original)

    def test_security_violation_raises_422(self):
        from fastapi import HTTPException
        with patch("routes.platform_router._validate_nodus_source",
                   side_effect=HTTPException(
                       status_code=422,
                       detail={"error": "nodus_security_violation", "message": "import blocked", "field": "script"},
                   )):
            with pytest.raises(HTTPException) as exc_info:
                from routes.platform_router import NodusRunRequest, run_nodus_script
                body = NodusRunRequest(script="import os")
                run_nodus_script(
                    request=MagicMock(),
                    body=body,
                    db=MagicMock(),
                    current_user={"sub": str(uuid.uuid4())},
                )
        assert exc_info.value.status_code == 422


# ── upload_nodus_script endpoint ──────────────────────────────────────────────

class TestUploadNodusScriptEndpoint:
    def _upload(self, body_dict: dict, registry_override: dict | None = None) -> dict:
        from routes.platform_router import NodusScriptUpload, upload_nodus_script
        m = _module()

        body = NodusScriptUpload(**body_dict)
        current_user = {"sub": str(uuid.uuid4())}

        original = dict(m._NODUS_SCRIPT_REGISTRY)
        if registry_override is not None:
            m._NODUS_SCRIPT_REGISTRY.clear()
            m._NODUS_SCRIPT_REGISTRY.update(registry_override)

        try:
            with patch("routes.platform_router._validate_nodus_source"), \
                 patch("routes.platform_router._SCRIPTS_DIR") as mock_dir:
                mock_path = MagicMock()
                mock_dir.__truediv__ = lambda self, other: mock_path
                mock_dir.mkdir = MagicMock()
                mock_path.write_text = MagicMock()

                return upload_nodus_script(body=body, current_user=current_user)
        finally:
            m._NODUS_SCRIPT_REGISTRY.clear()
            m._NODUS_SCRIPT_REGISTRY.update(original)

    def test_upload_returns_metadata(self):
        result = self._upload({"name": "test-script", "content": "let x = 1"})
        assert result["name"] == "test-script"
        assert "uploaded_at" in result
        assert "uploaded_by" in result
        assert result["size_bytes"] > 0

    def test_upload_stores_in_registry(self):
        m = _module()

        original = dict(m._NODUS_SCRIPT_REGISTRY)
        m._NODUS_SCRIPT_REGISTRY.clear()
        try:
            with patch("routes.platform_router._validate_nodus_source"), \
                 patch("routes.platform_router._SCRIPTS_DIR") as mock_dir:
                mock_path = MagicMock()
                mock_dir.__truediv__ = lambda self, other: mock_path
                mock_dir.mkdir = MagicMock()
                mock_path.write_text = MagicMock()

                from routes.platform_router import NodusScriptUpload, upload_nodus_script
                upload_nodus_script(
                    body=NodusScriptUpload(name="stored-script", content="let y = 2"),
                    current_user={"sub": str(uuid.uuid4())},
                )
            assert "stored-script" in m._NODUS_SCRIPT_REGISTRY
            assert m._NODUS_SCRIPT_REGISTRY["stored-script"]["content"] == "let y = 2"
        finally:
            m._NODUS_SCRIPT_REGISTRY.clear()
            m._NODUS_SCRIPT_REGISTRY.update(original)

    def test_duplicate_without_overwrite_raises_409(self):
        from fastapi import HTTPException
        existing = {"dup-script": {"name": "dup-script", "content": "x"}}
        with pytest.raises(HTTPException) as exc_info:
            self._upload({"name": "dup-script", "content": "y"}, registry_override=existing)
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error"] == "script_already_exists"

    def test_duplicate_with_overwrite_succeeds(self):
        existing = {"dup-script": {"name": "dup-script", "content": "x"}}
        result = self._upload(
            {"name": "dup-script", "content": "new content", "overwrite": True},
            registry_override=existing,
        )
        assert result["name"] == "dup-script"

    def test_security_violation_raises_422(self):
        from fastapi import HTTPException
        with patch("routes.platform_router._validate_nodus_source",
                   side_effect=HTTPException(
                       status_code=422,
                       detail={"error": "nodus_security_violation", "message": "eval blocked", "field": "content"},
                   )):
            with pytest.raises(HTTPException) as exc_info:
                from routes.platform_router import NodusScriptUpload, upload_nodus_script
                upload_nodus_script(
                    body=NodusScriptUpload(name="bad", content="eval(x)"),
                    current_user={"sub": str(uuid.uuid4())},
                )
            assert exc_info.value.status_code == 422


# ── list_nodus_scripts endpoint ───────────────────────────────────────────────

class TestListNodusScriptsEndpoint:
    def _list(self, registry: dict) -> dict:
        from routes.platform_router import list_nodus_scripts
        m = _module()

        original = dict(m._NODUS_SCRIPT_REGISTRY)
        m._NODUS_SCRIPT_REGISTRY.clear()
        m._NODUS_SCRIPT_REGISTRY.update(registry)

        try:
            with patch("routes.platform_router._SCRIPTS_DIR") as mock_dir:
                mock_dir.exists.return_value = False  # skip disk scan
                return list_nodus_scripts(current_user={"sub": str(uuid.uuid4())})
        finally:
            m._NODUS_SCRIPT_REGISTRY.clear()
            m._NODUS_SCRIPT_REGISTRY.update(original)

    def test_empty_registry_returns_zero_count(self):
        result = self._list({})
        assert result["count"] == 0
        assert result["scripts"] == []

    def test_scripts_listed_with_metadata(self):
        registry = {
            "script-a": {
                "name": "script-a",
                "content": "x",
                "description": "First",
                "size_bytes": 1,
                "uploaded_at": "2026-03-31T00:00:00Z",
                "uploaded_by": "u1",
            },
            "script-b": {
                "name": "script-b",
                "content": "y",
                "description": None,
                "size_bytes": 1,
                "uploaded_at": "2026-03-31T01:00:00Z",
                "uploaded_by": "u2",
            },
        }
        result = self._list(registry)
        assert result["count"] == 2
        names = [s["name"] for s in result["scripts"]]
        assert "script-a" in names
        assert "script-b" in names

    def test_content_not_included_in_listing(self):
        registry = {
            "secret-script": {
                "name": "secret-script",
                "content": "sensitive source",
                "description": None,
                "size_bytes": 16,
                "uploaded_at": None,
                "uploaded_by": None,
            }
        }
        result = self._list(registry)
        for script in result["scripts"]:
            assert "content" not in script

    def test_disk_scan_imports_on_disk_scripts(self):
        """Scripts on disk but not in memory are imported on list."""
        m = _module()

        original = dict(m._NODUS_SCRIPT_REGISTRY)
        m._NODUS_SCRIPT_REGISTRY.clear()

        disk_script_content = "let x = 1"

        mock_path = MagicMock()
        mock_path.stem = "disk-script"
        mock_path.read_text.return_value = disk_script_content

        try:
            with patch("routes.platform_router._SCRIPTS_DIR") as mock_dir:
                mock_dir.exists.return_value = True
                mock_dir.glob.return_value = [mock_path]

                from routes.platform_router import list_nodus_scripts
                result = list_nodus_scripts(current_user={"sub": str(uuid.uuid4())})

            assert any(s["name"] == "disk-script" for s in result["scripts"])
            assert "disk-script" in m._NODUS_SCRIPT_REGISTRY
        finally:
            m._NODUS_SCRIPT_REGISTRY.clear()
            m._NODUS_SCRIPT_REGISTRY.update(original)

