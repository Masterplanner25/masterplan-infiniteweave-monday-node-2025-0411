"""
SDK unit tests — all network calls are mocked via unittest.mock.

These tests verify:
  A. AINDYClient construction and header selection
  B. request() success and error paths
  C. Syscalls.call() and Syscalls.list()
  D. MemoryAPI (read / write / search / list / tree / trace)
  E. FlowAPI.run()
  F. EventAPI.emit()
  G. ExecutionAPI.get()
  H. NodusAPI (run_script / upload_script / list_scripts)
  I. Exception mapping (_raise_for_status)
  J. Integration — client.memory.write → client.flow.run pipeline
"""
from __future__ import annotations

import json
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

from AINDY.sdk.aindy_sdk import AINDYClient
from AINDY.sdk.aindy_sdk.exceptions import (
    AINDYError,
    AuthenticationError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    ResourceLimitError,
    ServerError,
    ValidationError,
    _raise_for_status,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_client(api_key: str = "aindy_test_key") -> AINDYClient:
    return AINDYClient(base_url="http://localhost:8000", api_key=api_key)


def _ok_response(data: dict) -> dict:
    return {
        "status": "success",
        "data": data,
        "version": "v1",
        "warning": None,
        "trace_id": "trace-1",
        "execution_unit_id": "eu-1",
        "syscall": "sys.v1.test",
        "duration_ms": 5,
        "error": None,
    }


def _mock_urlopen(response_body: dict):
    """Return a context-manager mock that yields a fake HTTP response."""
    raw = json.dumps(response_body).encode()
    resp = MagicMock()
    resp.read.return_value = raw
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ── Group A: AINDYClient construction ────────────────────────────────────────

class TestClientConstruction(unittest.TestCase):

    def test_platform_key_uses_x_platform_key_header(self):
        c = _make_client("aindy_abc123")
        headers = c._auth_headers()
        self.assertEqual(headers, {"X-Platform-Key": "aindy_abc123"})

    def test_jwt_uses_bearer_header(self):
        c = _make_client("eyJhbGciOiJIUzI1NiJ9.xxx.yyy")
        headers = c._auth_headers()
        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("Bearer "))

    def test_base_url_strips_trailing_slash(self):
        c = AINDYClient(base_url="http://localhost:8000/", api_key="aindy_x")
        self.assertEqual(c.base_url, "http://localhost:8000")

    def test_sub_apis_are_attached(self):
        c = _make_client()
        self.assertIsNotNone(c.syscalls)
        self.assertIsNotNone(c.memory)
        self.assertIsNotNone(c.flow)
        self.assertIsNotNone(c.events)
        self.assertIsNotNone(c.execution)
        self.assertIsNotNone(c.nodus)

    def test_default_timeout(self):
        c = _make_client()
        self.assertEqual(c.timeout, 30)

    def test_custom_timeout(self):
        c = AINDYClient("http://localhost:8000", "aindy_x", timeout=60)
        self.assertEqual(c.timeout, 60)


# ── Group B: request() transport ─────────────────────────────────────────────

class TestClientRequest(unittest.TestCase):

    def test_successful_post_returns_json(self):
        c = _make_client()
        mock_resp = _mock_urlopen({"status": "success", "data": {"x": 1}})
        with patch("AINDY.sdk.aindy_sdk.client.urlopen", return_value=mock_resp):
            result = c.post("/platform/syscall", {"name": "sys.v1.test", "payload": {}})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["x"], 1)

    def test_get_with_params_builds_query_string(self):
        c = _make_client()
        mock_resp = _mock_urlopen({"versions": ["v1"], "syscalls": {}, "total_count": 0})
        with patch("AINDY.sdk.aindy_sdk.client.urlopen", return_value=mock_resp) as mock_open:
            c.get("/platform/syscalls", params={"version": "v1"})
        req = mock_open.call_args[0][0]
        self.assertIn("version=v1", req.full_url)

    def test_network_error_raises_NetworkError(self):
        from urllib.error import URLError
        c = _make_client()
        with patch("AINDY.sdk.aindy_sdk.client.urlopen", side_effect=URLError("Connection refused")):
            with self.assertRaises(NetworkError):
                c.post("/platform/syscall", {})

    def test_http_401_raises_AuthenticationError(self):
        from urllib.error import HTTPError
        c = _make_client()
        err = HTTPError(
            url="http://localhost:8000/platform/syscall",
            code=401,
            msg="Unauthorized",
            hdrs={},  # type: ignore[arg-type]
            fp=BytesIO(json.dumps({"detail": "Invalid API key"}).encode()),
        )
        with patch("AINDY.sdk.aindy_sdk.client.urlopen", side_effect=err):
            with self.assertRaises(AuthenticationError):
                c.post("/platform/syscall", {})

    def test_http_403_raises_PermissionDeniedError(self):
        from urllib.error import HTTPError
        c = _make_client()
        err = HTTPError(
            url="http://localhost:8000/platform/syscall",
            code=403, msg="Forbidden", hdrs={},  # type: ignore[arg-type]
            fp=BytesIO(json.dumps({"detail": "Permission denied"}).encode()),
        )
        with patch("AINDY.sdk.aindy_sdk.client.urlopen", side_effect=err):
            with self.assertRaises(PermissionDeniedError):
                c.post("/platform/syscall", {})

    def test_http_422_raises_ValidationError(self):
        from urllib.error import HTTPError
        c = _make_client()
        err = HTTPError(
            url="http://localhost:8000/platform/syscall",
            code=422, msg="Unprocessable", hdrs={},  # type: ignore[arg-type]
            fp=BytesIO(json.dumps({"detail": "Missing field"}).encode()),
        )
        with patch("AINDY.sdk.aindy_sdk.client.urlopen", side_effect=err):
            with self.assertRaises(ValidationError):
                c.post("/platform/syscall", {})

    def test_http_500_raises_ServerError(self):
        from urllib.error import HTTPError
        c = _make_client()
        err = HTTPError(
            url="http://localhost:8000/platform/syscall",
            code=500, msg="Internal Server Error", hdrs={},  # type: ignore[arg-type]
            fp=BytesIO(json.dumps({"detail": "Unhandled exception"}).encode()),
        )
        with patch("AINDY.sdk.aindy_sdk.client.urlopen", side_effect=err):
            with self.assertRaises(ServerError):
                c.post("/platform/syscall", {})


# ── Group C: Syscalls ─────────────────────────────────────────────────────────

class TestSyscalls(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_call_posts_to_platform_syscall(self):
        envelope = _ok_response({"nodes": []})
        with patch.object(self.client, "post", return_value=envelope) as mock_post:
            result = self.client.syscalls.call("sys.v1.memory.read", {"query": "auth"})
        mock_post.assert_called_once_with(
            "/platform/syscall",
            {"name": "sys.v1.memory.read", "payload": {"query": "auth"}},
        )
        self.assertEqual(result["status"], "success")

    def test_list_calls_get_syscalls(self):
        response = {"versions": ["v1"], "syscalls": {"v1": {}}, "total_count": 0}
        with patch.object(self.client, "get", return_value=response) as mock_get:
            result = self.client.syscalls.list(version="v1")
        mock_get.assert_called_once_with("/platform/syscalls", params={"version": "v1"})
        self.assertEqual(result["versions"], ["v1"])

    def test_list_without_version_passes_no_params(self):
        response = {"versions": ["v1", "v2"], "syscalls": {}, "total_count": 0}
        with patch.object(self.client, "get", return_value=response) as mock_get:
            self.client.syscalls.list()
        mock_get.assert_called_once_with("/platform/syscalls", params=None)


# ── Group D: MemoryAPI ────────────────────────────────────────────────────────

class TestMemoryAPI(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()
        self._sys_call = patch.object(self.client.syscalls, "call")

    def test_read_calls_memory_read_syscall(self):
        envelope = _ok_response({"nodes": [{"content": "x"}]})
        with patch.object(self.client.syscalls, "call", return_value=envelope) as m:
            result = self.client.memory.read("/memory/shawn/**", query="auth", limit=5)
        m.assert_called_once_with(
            "sys.v1.memory.read",
            {"path": "/memory/shawn/**", "query": "auth", "limit": 5},
        )
        self.assertEqual(len(result["data"]["nodes"]), 1)

    def test_read_omits_query_when_none(self):
        envelope = _ok_response({"nodes": []})
        with patch.object(self.client.syscalls, "call", return_value=envelope) as m:
            self.client.memory.read("/memory/shawn/*")
        payload = m.call_args[0][1]
        self.assertNotIn("query", payload)

    def test_write_calls_memory_write_syscall(self):
        envelope = _ok_response({"node": {"id": "abc"}})
        with patch.object(self.client.syscalls, "call", return_value=envelope) as m:
            self.client.memory.write("/memory/shawn/insights/outcome", "content", tags=["t"])
        m.assert_called_once_with(
            "sys.v1.memory.write",
            {"path": "/memory/shawn/insights/outcome", "content": "content", "tags": ["t"]},
        )

    def test_write_defaults_tags_to_empty_list(self):
        envelope = _ok_response({"node": {}})
        with patch.object(self.client.syscalls, "call", return_value=envelope) as m:
            self.client.memory.write("/memory/shawn/insights/outcome", "content")
        payload = m.call_args[0][1]
        self.assertEqual(payload["tags"], [])

    def test_search_calls_memory_search(self):
        envelope = _ok_response({"nodes": []})
        with patch.object(self.client.syscalls, "call", return_value=envelope) as m:
            self.client.memory.search("auth flow", limit=3, min_similarity=0.8)
        m.assert_called_once_with(
            "sys.v1.memory.search",
            {"query": "auth flow", "limit": 3, "min_similarity": 0.8},
        )

    def test_list_calls_memory_list(self):
        envelope = _ok_response({"nodes": []})
        with patch.object(self.client.syscalls, "call", return_value=envelope) as m:
            self.client.memory.list("/memory/shawn/entities")
        m.assert_called_once_with(
            "sys.v1.memory.list",
            {"path": "/memory/shawn/entities", "limit": 100},
        )

    def test_tree_calls_memory_tree(self):
        envelope = _ok_response({"tree": {}, "flat": []})
        with patch.object(self.client.syscalls, "call", return_value=envelope) as m:
            self.client.memory.tree("/memory/shawn/sprint")
        m.assert_called_once_with(
            "sys.v1.memory.tree",
            {"path": "/memory/shawn/sprint", "limit": 100},
        )

    def test_trace_calls_memory_trace(self):
        envelope = _ok_response({"chain": []})
        with patch.object(self.client.syscalls, "call", return_value=envelope) as m:
            self.client.memory.trace("/memory/shawn/decisions/outcome/abc", depth=3)
        m.assert_called_once_with(
            "sys.v1.memory.trace",
            {"path": "/memory/shawn/decisions/outcome/abc", "depth": 3},
        )


# ── Group E: FlowAPI ──────────────────────────────────────────────────────────

class TestFlowAPI(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_run_calls_flow_run_syscall(self):
        envelope = _ok_response({"summary": "done"})
        with patch.object(self.client.syscalls, "call", return_value=envelope) as m:
            result = self.client.flow.run("analyze_entities", {"nodes": []})
        m.assert_called_once_with(
            "sys.v1.flow.run",
            {"flow_name": "analyze_entities", "input": {"nodes": []}},
        )
        self.assertEqual(result["data"]["summary"], "done")

    def test_run_defaults_input_to_empty_dict(self):
        envelope = _ok_response({})
        with patch.object(self.client.syscalls, "call", return_value=envelope) as m:
            self.client.flow.run("my_flow")
        payload = m.call_args[0][1]
        self.assertEqual(payload["input"], {})


# ── Group F: EventAPI ─────────────────────────────────────────────────────────

class TestEventAPI(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_emit_calls_event_emit_syscall(self):
        envelope = _ok_response({"event_id": "ev-1"})
        with patch.object(self.client.syscalls, "call", return_value=envelope) as m:
            self.client.events.emit("entity.updated", {"entity_id": "42"})
        m.assert_called_once_with(
            "sys.v1.event.emit",
            {"type": "entity.updated", "payload": {"entity_id": "42"}},
        )

    def test_emit_defaults_payload_to_empty_dict(self):
        envelope = _ok_response({"event_id": "ev-2"})
        with patch.object(self.client.syscalls, "call", return_value=envelope) as m:
            self.client.events.emit("ping")
        payload = m.call_args[0][1]
        self.assertEqual(payload["payload"], {})


# ── Group G: ExecutionAPI ─────────────────────────────────────────────────────

class TestExecutionAPI(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_get_calls_execution_get_syscall(self):
        envelope = _ok_response({"status": "success", "syscall_count": 3})
        with patch.object(self.client.syscalls, "call", return_value=envelope) as m:
            result = self.client.execution.get("run-abc")
        m.assert_called_once_with(
            "sys.v1.execution.get",
            {"execution_id": "run-abc"},
        )
        self.assertEqual(result["data"]["syscall_count"], 3)


# ── Group H: NodusAPI ────────────────────────────────────────────────────────

class TestNodusAPI(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_run_script_inline_posts_to_nodus_run(self):
        nodus_response = {"status": "SUCCESS", "nodus_status": "success", "output_state": {"x": 1}}
        with patch.object(self.client, "post", return_value=nodus_response) as m:
            self.client.nodus.run_script(script='set_state("x", 1)')
        m.assert_called_once()
        call_args = m.call_args[0]
        self.assertEqual(call_args[0], "/platform/nodus/run")
        self.assertEqual(call_args[1]["script"], 'set_state("x", 1)')

    def test_run_script_named_passes_script_name(self):
        nodus_response = {"status": "SUCCESS", "nodus_status": "success", "output_state": {}}
        with patch.object(self.client, "post", return_value=nodus_response) as m:
            self.client.nodus.run_script(script_name="my_script")
        body = m.call_args[0][1]
        self.assertEqual(body["script_name"], "my_script")
        self.assertNotIn("script", body)

    def test_run_script_requires_script_or_name(self):
        with self.assertRaises(ValueError):
            self.client.nodus.run_script()

    def test_run_script_passes_input(self):
        nodus_response = {"status": "SUCCESS", "nodus_status": "success", "output_state": {}}
        with patch.object(self.client, "post", return_value=nodus_response) as m:
            self.client.nodus.run_script(script="x", input={"k": "v"})
        body = m.call_args[0][1]
        self.assertEqual(body["input"], {"k": "v"})

    def test_upload_script_posts_to_nodus_upload(self):
        response = {"name": "my_script", "size_bytes": 42, "created_at": "2026-04-01"}
        with patch.object(self.client, "post", return_value=response) as m:
            result = self.client.nodus.upload_script("my_script", 'set_state("x", 1)')
        m.assert_called_once_with(
            "/platform/nodus/upload",
            {"name": "my_script", "source": 'set_state("x", 1)', "overwrite": False},
        )
        self.assertEqual(result["name"], "my_script")

    def test_list_scripts_gets_nodus_scripts(self):
        response = {"scripts": [], "count": 0}
        with patch.object(self.client, "get", return_value=response) as m:
            self.client.nodus.list_scripts()
        m.assert_called_once_with("/platform/nodus/scripts")


# ── Group I: Exception mapping ────────────────────────────────────────────────

class TestExceptionMapping(unittest.TestCase):

    def _call(self, code: int, body: dict | None = None):
        _raise_for_status(code, body or {}, "http://localhost/test")

    def test_401_raises_AuthenticationError(self):
        with self.assertRaises(AuthenticationError):
            self._call(401)

    def test_403_raises_PermissionDeniedError(self):
        with self.assertRaises(PermissionDeniedError):
            self._call(403)

    def test_404_raises_NotFoundError(self):
        with self.assertRaises(NotFoundError):
            self._call(404)

    def test_422_raises_ValidationError(self):
        with self.assertRaises(ValidationError):
            self._call(422)

    def test_429_raises_ResourceLimitError(self):
        with self.assertRaises(ResourceLimitError):
            self._call(429)

    def test_500_raises_ServerError(self):
        with self.assertRaises(ServerError):
            self._call(500)

    def test_503_raises_ServerError(self):
        with self.assertRaises(ServerError):
            self._call(503)

    def test_400_raises_base_AINDYError(self):
        with self.assertRaises(AINDYError):
            self._call(400)

    def test_error_carries_status_code(self):
        try:
            self._call(404, {"detail": "not found"})
        except NotFoundError as e:
            self.assertEqual(e.status_code, 404)
            self.assertIn("not found", e.message)

    def test_error_carries_response_body(self):
        body = {"detail": "quota exceeded", "extra": "info"}
        try:
            self._call(429, body)
        except ResourceLimitError as e:
            self.assertEqual(e.response, body)

    def test_nested_detail_dict_extracted(self):
        body = {"detail": {"error": "inner message"}}
        try:
            self._call(422, body)
        except ValidationError as e:
            self.assertIn("inner message", e.message)


# ── Group J: Integration pipeline ─────────────────────────────────────────────

class TestIntegrationPipeline(unittest.TestCase):
    """Verify the read → flow.run → write pipeline composes correctly."""

    def test_read_flow_write_pipeline(self):
        client = _make_client()
        nodes = [{"id": "n1", "content": "Sprint objective"}]

        # Mock memory.read
        read_env = _ok_response({"nodes": nodes})
        # Mock flow.run
        flow_env = _ok_response({"summary": "Goals analyzed"})
        # Mock memory.write
        write_env = _ok_response({"node": {"id": "n2"}})

        call_results = [read_env, flow_env, write_env]

        with patch.object(client.syscalls, "call", side_effect=call_results) as m:
            mem_result = client.memory.read("/memory/shawn/entities/**")
            flow_result = client.flow.run("analyze_entities", {"data": mem_result["data"]["nodes"]})
            client.memory.write("/memory/shawn/insights", flow_result["data"]["summary"])

        self.assertEqual(m.call_count, 3)
        # First call: memory.read
        self.assertEqual(m.call_args_list[0][0][0], "sys.v1.memory.read")
        # Second call: flow.run
        self.assertEqual(m.call_args_list[1][0][0], "sys.v1.flow.run")
        # Third call: memory.write with the flow's summary
        write_payload = m.call_args_list[2][0][1]
        self.assertEqual(write_payload["content"], "Goals analyzed")
        self.assertEqual(write_payload["path"], "/memory/shawn/insights")


if __name__ == "__main__":
    unittest.main(verbosity=2)
