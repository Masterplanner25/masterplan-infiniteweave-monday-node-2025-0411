"""
tests/unit/test_aindy_cli.py — Tests for the A.I.N.D.Y. Nodus CLI.

Coverage
========
A. Config helpers (_api_url, _api_token)        (4 tests)
B. HTTP helpers (_http_post, _http_get)         (6 tests)
C. Output formatters (_fmt_run_result, etc.)    (6 tests)
D. cmd_run — happy path + error cases           (10 tests)
E. cmd_trace                                    (5 tests)
F. cmd_upload                                   (5 tests)
G. Argument parsing / main() dispatch           (8 tests)

Total: 44 tests
"""
from __future__ import annotations

import json
import sys
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_response(body: dict, status: int = 200):
    """Build a mock object that behaves like urllib's http.client.HTTPResponse."""
    mock = MagicMock()
    mock.status = status
    mock.read.return_value = json.dumps(body).encode("utf-8")
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


# ===========================================================================
# A. Config helpers
# ===========================================================================

class TestConfigHelpers:
    def test_api_url_default(self, monkeypatch):
        monkeypatch.delenv("AINDY_API_URL", raising=False)
        from cli import _api_url
        assert _api_url() == "http://localhost:8000"

    def test_api_url_from_env(self, monkeypatch):
        monkeypatch.setenv("AINDY_API_URL", "http://my-server:9000")
        from cli import _api_url
        assert _api_url() == "http://my-server:9000"

    def test_api_url_override_wins(self, monkeypatch):
        monkeypatch.setenv("AINDY_API_URL", "http://env-server")
        from cli import _api_url
        assert _api_url("http://override-server") == "http://override-server"

    def test_api_url_trailing_slash_stripped(self, monkeypatch):
        monkeypatch.delenv("AINDY_API_URL", raising=False)
        from cli import _api_url
        assert _api_url("http://server:8000/") == "http://server:8000"

    def test_api_token_none_when_unset(self, monkeypatch):
        monkeypatch.delenv("AINDY_API_TOKEN", raising=False)
        from cli import _api_token
        assert _api_token() is None

    def test_api_token_from_env(self, monkeypatch):
        monkeypatch.setenv("AINDY_API_TOKEN", "my-secret-token")
        from cli import _api_token
        assert _api_token() == "my-secret-token"


# ===========================================================================
# B. HTTP helpers
# ===========================================================================

class TestHttpHelpers:
    def test_http_post_success(self):
        from cli import _http_post
        mock_resp = _make_mock_response({"status": "SUCCESS", "nodus_status": "success"})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            code, data = _http_post("http://server/run", {"script": "x"}, token="tok")
        assert code == 200
        assert data["nodus_status"] == "success"

    def test_http_post_sets_bearer_header(self):
        from cli import _http_post
        mock_resp = _make_mock_response({})
        captured = []

        def fake_urlopen(req, timeout=None):
            captured.append(req)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _http_post("http://server/run", {}, token="my-token")

        assert captured[0].get_header("Authorization") == "Bearer my-token"

    def test_http_post_http_error(self):
        from cli import _http_post
        err = urllib.error.HTTPError(
            url="http://server/run",
            code=422,
            msg="Unprocessable",
            hdrs=MagicMock(),
            fp=BytesIO(json.dumps({"detail": "bad script"}).encode()),
        )
        with patch("urllib.request.urlopen", side_effect=err):
            code, data = _http_post("http://server/run", {}, token=None)
        assert code == 422
        assert data["detail"] == "bad script"

    def test_http_get_success(self):
        from cli import _http_get
        mock_resp = _make_mock_response({"trace_id": "abc", "count": 3})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            code, data = _http_get("http://server/trace/abc", token=None)
        assert code == 200
        assert data["count"] == 3

    def test_http_get_404(self):
        from cli import _http_get
        err = urllib.error.HTTPError(
            url="http://server/trace/missing",
            code=404,
            msg="Not Found",
            hdrs=MagicMock(),
            fp=BytesIO(json.dumps({"detail": "not found"}).encode()),
        )
        with patch("urllib.request.urlopen", side_effect=err):
            code, data = _http_get("http://server/trace/missing", token=None)
        assert code == 404

    def test_http_post_no_token_omits_header(self):
        from cli import _http_post
        mock_resp = _make_mock_response({})
        captured = []

        def fake_urlopen(req, timeout=None):
            captured.append(req)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _http_post("http://server/run", {}, token=None)

        assert captured[0].get_header("Authorization") is None


# ===========================================================================
# C. Output formatters
# ===========================================================================

class TestFormatters:
    def test_fmt_run_result_success(self):
        from cli import _fmt_run_result
        resp = {
            "status": "SUCCESS",
            "nodus_status": "success",
            "run_id": "aabbccdd-1234-5678-abcd-000000000000",
            "trace_id": "tttttttt-1234-5678-abcd-000000000000",
            "output_state": {"result": 42},
            "events": [{"event_type": "done"}],
            "memory_writes": [],
            "error": None,
        }
        out = _fmt_run_result(resp)
        assert "success" in out
        assert "result" in out
        assert "events_emitted: 1" in out

    def test_fmt_run_result_failure(self):
        from cli import _fmt_run_result
        resp = {
            "status": "FAILED",
            "nodus_status": "failure",
            "run_id": "aabbccdd-0000",
            "trace_id": None,
            "output_state": {},
            "events": [],
            "memory_writes": [],
            "error": "Script raised RuntimeError",
        }
        out = _fmt_run_result(resp)
        assert "failure" in out
        assert "Script raised RuntimeError" in out

    def test_fmt_trace_shows_steps(self):
        from cli import _fmt_trace
        resp = {
            "trace_id": "abc-123",
            "count": 2,
            "steps": [
                {"sequence": 1, "fn_name": "recall", "duration_ms": 10, "status": "ok", "error": None},
                {"sequence": 2, "fn_name": "emit", "duration_ms": 5, "status": "ok", "error": None},
            ],
            "summary": {
                "total_calls": 2,
                "total_duration_ms": 15,
                "fn_counts": {"recall": 1, "emit": 1},
                "error_count": 0,
                "fn_names": ["recall", "emit"],
            },
        }
        out = _fmt_trace(resp)
        assert "abc-123" in out
        assert "recall" in out
        assert "emit" in out
        assert "15ms total" in out

    def test_fmt_trace_empty(self):
        from cli import _fmt_trace
        resp = {
            "trace_id": "x",
            "count": 0,
            "steps": [],
            "summary": {
                "total_calls": 0,
                "total_duration_ms": 0,
                "fn_counts": {},
                "error_count": 0,
                "fn_names": [],
            },
        }
        out = _fmt_trace(resp)
        assert "0 steps" in out

    def test_fmt_upload_result(self):
        from cli import _fmt_upload_result
        resp = {
            "name": "my_script",
            "size_bytes": 128,
            "uploaded_at": "2026-04-01T12:00:00Z",
            "uploaded_by": "user-1",
        }
        out = _fmt_upload_result(resp)
        assert "my_script" in out
        assert "128B" in out

    def test_fmt_run_result_no_output_state(self):
        from cli import _fmt_run_result
        resp = {
            "status": "SUCCESS",
            "nodus_status": "success",
            "run_id": "x",
            "trace_id": "y",
            "output_state": {},
            "events": [],
            "memory_writes": [],
            "error": None,
        }
        out = _fmt_run_result(resp)
        assert "output_state" not in out


# ===========================================================================
# D. cmd_run
# ===========================================================================

class TestCmdRun:
    def _run_resp(self, **kwargs):
        defaults = {
            "status": "SUCCESS",
            "nodus_status": "success",
            "run_id": "run-1234-5678",
            "trace_id": "trace-1234-5678",
            "output_state": {},
            "events": [],
            "memory_writes": [],
            "events_emitted": 0,
            "memory_writes_count": 0,
            "error": None,
        }
        defaults.update(kwargs)
        return defaults

    def test_posts_script_content(self, tmp_path, capsys):
        from cli import cmd_run
        script_file = tmp_path / "test.nd"
        script_file.write_text("set_state('x', 1)", encoding="utf-8")

        posted = {}

        def fake_post(url, payload, *, token):
            posted.update(payload)
            return 200, self._run_resp()

        with patch("cli._http_post", side_effect=fake_post):
            rc = cmd_run(str(script_file), api_url="http://server", token=None)

        assert rc == 0
        assert posted["script"] == "set_state('x', 1)"

    def test_file_not_found(self, capsys):
        from cli import cmd_run
        rc = cmd_run("nonexistent.nd", api_url="http://server", token=None)
        assert rc == 1
        assert "not found" in capsys.readouterr().err.lower()

    def test_api_error_returns_1(self, tmp_path, capsys):
        from cli import cmd_run
        f = tmp_path / "t.nd"
        f.write_text("x", encoding="utf-8")
        with patch("cli._http_post", return_value=(422, {"detail": "bad"})):
            rc = cmd_run(str(f), api_url="http://server", token=None)
        assert rc == 1

    def test_nodus_failure_returns_1(self, tmp_path):
        from cli import cmd_run
        f = tmp_path / "t.nd"
        f.write_text("fail", encoding="utf-8")
        with patch("cli._http_post", return_value=(200, self._run_resp(nodus_status="failure"))):
            rc = cmd_run(str(f), api_url="http://server", token=None)
        assert rc == 1

    def test_passes_input_payload(self, tmp_path):
        from cli import cmd_run
        f = tmp_path / "t.nd"
        f.write_text("x", encoding="utf-8")
        posted = {}
        with patch("cli._http_post", side_effect=lambda url, p, **kw: (posted.update(p), (200, self._run_resp()))[1]):
            cmd_run(str(f), api_url="http://s", token=None, input_payload={"goal": "test"})
        assert posted["input"] == {"goal": "test"}

    def test_trace_flag_fetches_trace(self, tmp_path):
        from cli import cmd_run
        f = tmp_path / "t.nd"
        f.write_text("x", encoding="utf-8")
        trace_resp = {
            "trace_id": "trace-1234-5678",
            "execution_unit_id": "trace-1234-5678",
            "count": 1,
            "steps": [{"sequence": 1, "fn_name": "recall", "duration_ms": 5, "status": "ok", "error": None}],
            "summary": {"total_calls": 1, "total_duration_ms": 5, "fn_counts": {"recall": 1}, "error_count": 0, "fn_names": ["recall"]},
        }
        with patch("cli._http_post", return_value=(200, self._run_resp())), \
             patch("cli._http_get", return_value=(200, trace_resp)) as mock_get:
            cmd_run(str(f), api_url="http://s", token=None, trace=True)

        mock_get.assert_called_once()
        call_url = mock_get.call_args.args[0]
        assert "trace-1234-5678" in call_url

    def test_trace_404_warns_not_fails(self, tmp_path, capsys):
        from cli import cmd_run
        f = tmp_path / "t.nd"
        f.write_text("x", encoding="utf-8")
        with patch("cli._http_post", return_value=(200, self._run_resp())), \
             patch("cli._http_get", return_value=(404, {})):
            rc = cmd_run(str(f), api_url="http://s", token=None, trace=True)
        assert rc == 0
        assert "warn" in capsys.readouterr().err.lower()

    def test_dump_bytecode_warns_when_vm_unavailable(self, tmp_path, capsys):
        from cli import cmd_run
        f = tmp_path / "t.nd"
        f.write_text("x", encoding="utf-8")
        with patch("cli._local_disassemble", return_value=None), \
             patch("cli._http_post", return_value=(200, self._run_resp())):
            rc = cmd_run(str(f), api_url="http://s", token=None, dump_bytecode=True)
        assert rc == 0
        assert "warn" in capsys.readouterr().err.lower()

    def test_dump_bytecode_prints_disassembly(self, tmp_path, capsys):
        from cli import cmd_run
        f = tmp_path / "t.nd"
        f.write_text("x", encoding="utf-8")
        with patch("cli._local_disassemble", return_value="LOAD_CONST 1\nRETURN"), \
             patch("cli._http_post", return_value=(200, self._run_resp())):
            cmd_run(str(f), api_url="http://s", token=None, dump_bytecode=True)
        out = capsys.readouterr().out
        assert "LOAD_CONST" in out

    def test_json_flag_prints_raw(self, tmp_path, capsys):
        from cli import cmd_run
        f = tmp_path / "t.nd"
        f.write_text("x", encoding="utf-8")
        with patch("cli._http_post", return_value=(200, self._run_resp())):
            cmd_run(str(f), api_url="http://s", token=None, json_output=True)
        raw = capsys.readouterr().out
        parsed = json.loads(raw)
        assert parsed["nodus_status"] == "success"


# ===========================================================================
# E. cmd_trace
# ===========================================================================

class TestCmdTrace:
    def _trace_resp(self):
        return {
            "trace_id": "abc-123",
            "execution_unit_id": "abc-123",
            "count": 2,
            "steps": [
                {"sequence": 1, "fn_name": "recall", "duration_ms": 5, "status": "ok", "error": None},
                {"sequence": 2, "fn_name": "emit", "duration_ms": 3, "status": "ok", "error": None},
            ],
            "summary": {
                "total_calls": 2,
                "total_duration_ms": 8,
                "fn_counts": {"recall": 1, "emit": 1},
                "error_count": 0,
                "fn_names": ["recall", "emit"],
            },
        }

    def test_returns_0_on_success(self):
        from cli import cmd_trace
        with patch("cli._http_get", return_value=(200, self._trace_resp())):
            rc = cmd_trace("abc-123", api_url="http://s", token=None)
        assert rc == 0

    def test_returns_1_on_404(self, capsys):
        from cli import cmd_trace
        with patch("cli._http_get", return_value=(404, {})):
            rc = cmd_trace("missing", api_url="http://s", token=None)
        assert rc == 1
        assert "not found" in capsys.readouterr().err.lower()

    def test_prints_trace_summary(self, capsys):
        from cli import cmd_trace
        with patch("cli._http_get", return_value=(200, self._trace_resp())):
            cmd_trace("abc-123", api_url="http://s", token=None)
        out = capsys.readouterr().out
        assert "abc-123" in out
        assert "recall" in out

    def test_json_flag_prints_raw(self, capsys):
        from cli import cmd_trace
        with patch("cli._http_get", return_value=(200, self._trace_resp())):
            cmd_trace("abc-123", api_url="http://s", token=None, json_output=True)
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["trace_id"] == "abc-123"

    def test_api_error_returns_1(self, capsys):
        from cli import cmd_trace
        with patch("cli._http_get", return_value=(500, {"detail": "server error"})):
            rc = cmd_trace("abc-123", api_url="http://s", token=None)
        assert rc == 1


# ===========================================================================
# F. cmd_upload
# ===========================================================================

class TestCmdUpload:
    def test_uploads_file_content(self, tmp_path):
        from cli import cmd_upload
        f = tmp_path / "script.nd"
        f.write_text("let x = 1", encoding="utf-8")
        posted = {}
        resp = {"name": "script", "size_bytes": 9, "uploaded_at": "2026-04-01", "uploaded_by": "u"}
        with patch("cli._http_post", side_effect=lambda url, p, **kw: (posted.update(p), (201, resp))[1]):
            rc = cmd_upload(str(f), api_url="http://s", token=None)
        assert rc == 0
        assert posted["content"] == "let x = 1"

    def test_uses_stem_as_name_when_not_given(self, tmp_path):
        from cli import cmd_upload
        f = tmp_path / "my_processor.nd"
        f.write_text("x", encoding="utf-8")
        posted = {}
        resp = {"name": "my_processor", "size_bytes": 1, "uploaded_at": "", "uploaded_by": ""}
        with patch("cli._http_post", side_effect=lambda url, p, **kw: (posted.update(p), (201, resp))[1]):
            cmd_upload(str(f), api_url="http://s", token=None)
        assert posted["name"] == "my_processor"

    def test_409_conflict_message(self, tmp_path, capsys):
        from cli import cmd_upload
        f = tmp_path / "s.nd"
        f.write_text("x", encoding="utf-8")
        with patch("cli._http_post", return_value=(409, {"detail": "already exists"})):
            rc = cmd_upload(str(f), api_url="http://s", token=None)
        assert rc == 1
        assert "already exists" in capsys.readouterr().err.lower()

    def test_file_not_found(self, capsys):
        from cli import cmd_upload
        rc = cmd_upload("nope.nd", api_url="http://s", token=None)
        assert rc == 1

    def test_overwrite_flag_forwarded(self, tmp_path):
        from cli import cmd_upload
        f = tmp_path / "s.nd"
        f.write_text("x", encoding="utf-8")
        posted = {}
        resp = {"name": "s", "size_bytes": 1, "uploaded_at": "", "uploaded_by": ""}
        with patch("cli._http_post", side_effect=lambda url, p, **kw: (posted.update(p), (201, resp))[1]):
            cmd_upload(str(f), api_url="http://s", token=None, overwrite=True)
        assert posted["overwrite"] is True


# ===========================================================================
# G. main() dispatch
# ===========================================================================

class TestMainDispatch:
    def test_no_args_prints_help(self, capsys):
        from cli import main
        rc = main(["cli.py"])
        assert rc == 0
        assert "Usage" in capsys.readouterr().out

    def test_help_flag(self, capsys):
        from cli import main
        rc = main(["cli.py", "--help"])
        assert rc == 0
        assert "run" in capsys.readouterr().out

    def test_unknown_command(self, capsys):
        from cli import main
        rc = main(["cli.py", "frobnicate"])
        assert rc == 1
        assert "Unknown" in capsys.readouterr().err

    def test_run_dispatches_to_cmd_run(self, tmp_path):
        from cli import main
        f = tmp_path / "t.nd"
        f.write_text("x", encoding="utf-8")
        with patch("cli.cmd_run", return_value=0) as mock_run:
            rc = main(["cli.py", "run", str(f)])
        assert rc == 0
        mock_run.assert_called_once()

    def test_trace_dispatches_to_cmd_trace(self):
        from cli import main
        with patch("cli.cmd_trace", return_value=0) as mock_trace:
            rc = main(["cli.py", "trace", "some-trace-id"])
        assert rc == 0
        mock_trace.assert_called_once()
        assert mock_trace.call_args.args[0] == "some-trace-id"

    def test_upload_dispatches_to_cmd_upload(self, tmp_path):
        from cli import main
        f = tmp_path / "t.nd"
        f.write_text("x", encoding="utf-8")
        with patch("cli.cmd_upload", return_value=0) as mock_up:
            rc = main(["cli.py", "upload", str(f)])
        assert rc == 0
        mock_up.assert_called_once()

    def test_invalid_input_json_returns_1(self, tmp_path, capsys):
        from cli import main
        f = tmp_path / "t.nd"
        f.write_text("x", encoding="utf-8")
        rc = main(["cli.py", "run", str(f), "--input", "not-json"])
        assert rc == 1
        assert "Invalid" in capsys.readouterr().err

    def test_invalid_error_policy_returns_1(self, tmp_path, capsys):
        from cli import main
        f = tmp_path / "t.nd"
        f.write_text("x", encoding="utf-8")
        rc = main(["cli.py", "run", str(f), "--error-policy", "explode"])
        assert rc == 1
        assert "error-policy" in capsys.readouterr().err
