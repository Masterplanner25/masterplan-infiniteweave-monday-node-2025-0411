"""
tests/unit/test_nodus_trace.py — Tests for the Nodus execution trace system.

Coverage
========
A. _sanitize_args helper (5 tests)
B. _sanitize_result helper (5 tests)
C. _flush_nodus_traces (5 tests)
D. query_nodus_trace service (6 tests)
E. build_trace_summary (5 tests)
F. GET /platform/nodus/trace/{trace_id} endpoint (7 tests)
G. NodusTraceEvent model (4 tests)

Total: 37 tests
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest

# Pre-import lazy-loaded modules so patches resolve correctly
import db.models.nodus_trace_event
import db.database
import utils.uuid_utils
import services.nodus_trace_service
import services.nodus_runtime_adapter


# ===========================================================================
# A. _sanitize_args
# ===========================================================================

class TestSanitizeArgs:
    def test_none_passthrough(self):
        from services.nodus_runtime_adapter import _sanitize_args
        assert _sanitize_args((None,)) == [None]

    def test_numeric_passthrough(self):
        from services.nodus_runtime_adapter import _sanitize_args
        assert _sanitize_args((42, 3.14, True)) == [42, 3.14, True]

    def test_short_string_unchanged(self):
        from services.nodus_runtime_adapter import _sanitize_args
        assert _sanitize_args(("hello",)) == ["hello"]

    def test_long_string_truncated(self):
        from services.nodus_runtime_adapter import _sanitize_args
        long_str = "x" * 300
        result = _sanitize_args((long_str,))
        assert len(result) == 1
        assert result[0].endswith("\u2026")
        assert len(result[0]) == 201  # 200 chars + ellipsis

    def test_dict_summarised(self):
        from services.nodus_runtime_adapter import _sanitize_args
        d = {"key": "value", "num": 99}
        result = _sanitize_args((d,))
        assert isinstance(result[0], dict)
        assert "key" in result[0]

    def test_list_replaced_with_count(self):
        from services.nodus_runtime_adapter import _sanitize_args
        result = _sanitize_args(([1, 2, 3],))
        assert result == ["[3 items]"]

    def test_object_replaced_with_type_name(self):
        from services.nodus_runtime_adapter import _sanitize_args
        result = _sanitize_args((object(),))
        assert result == ["object"]

    def test_dict_truncated_to_ten_keys(self):
        from services.nodus_runtime_adapter import _sanitize_args
        d = {str(i): i for i in range(20)}
        result = _sanitize_args((d,))
        assert isinstance(result[0], dict)
        assert len(result[0]) == 10


# ===========================================================================
# B. _sanitize_result
# ===========================================================================

class TestSanitizeResult:
    def test_none(self):
        from services.nodus_runtime_adapter import _sanitize_result
        assert _sanitize_result(None) == {"value": None}

    def test_bool(self):
        from services.nodus_runtime_adapter import _sanitize_result
        assert _sanitize_result(True) == {"value": True}

    def test_int(self):
        from services.nodus_runtime_adapter import _sanitize_result
        assert _sanitize_result(42) == {"value": 42}

    def test_short_string(self):
        from services.nodus_runtime_adapter import _sanitize_result
        assert _sanitize_result("ok") == {"value": "ok"}

    def test_long_string_truncated(self):
        from services.nodus_runtime_adapter import _sanitize_result
        result = _sanitize_result("x" * 300)
        assert result["value"].endswith("\u2026")

    def test_dict(self):
        from services.nodus_runtime_adapter import _sanitize_result
        result = _sanitize_result({"a": 1, "b": 2})
        assert result["size"] == 2
        assert "keys" in result

    def test_list(self):
        from services.nodus_runtime_adapter import _sanitize_result
        assert _sanitize_result([1, 2, 3]) == {"length": 3}

    def test_unknown_type(self):
        from services.nodus_runtime_adapter import _sanitize_result
        result = _sanitize_result(object())
        assert result == {"type": "object"}


# ===========================================================================
# C. _flush_nodus_traces
# ===========================================================================

class TestFlushNodusTraces:
    def test_empty_list_is_noop(self):
        from services.nodus_runtime_adapter import _flush_nodus_traces
        with patch("db.database.SessionLocal") as mock_sl:
            _flush_nodus_traces([])
        mock_sl.assert_not_called()

    def test_single_trace_creates_row(self):
        from services.nodus_runtime_adapter import _flush_nodus_traces
        trace = {
            "execution_unit_id": "exec-1",
            "trace_id": "exec-1",
            "sequence": 1,
            "fn_name": "recall",
            "args_summary": ["goals"],
            "result_summary": {"length": 2},
            "duration_ms": 5,
            "status": "ok",
            "error": None,
            "user_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc),
        }
        mock_db = MagicMock()
        with patch("db.database.SessionLocal", return_value=mock_db), \
             patch("db.models.nodus_trace_event.NodusTraceEvent") as MockEvt:
            _flush_nodus_traces([trace])
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    def test_multiple_traces_all_added(self):
        from services.nodus_runtime_adapter import _flush_nodus_traces
        traces = [
            {
                "execution_unit_id": "exec-1",
                "trace_id": "exec-1",
                "sequence": i,
                "fn_name": "set_state",
                "args_summary": None,
                "result_summary": None,
                "duration_ms": i,
                "status": "ok",
                "error": None,
                "user_id": None,
                "timestamp": datetime.now(timezone.utc),
            }
            for i in range(3)
        ]
        mock_db = MagicMock()
        with patch("db.database.SessionLocal", return_value=mock_db), \
             patch("db.models.nodus_trace_event.NodusTraceEvent"):
            _flush_nodus_traces(traces)
        assert mock_db.add.call_count == 3

    def test_db_error_swallowed(self):
        from services.nodus_runtime_adapter import _flush_nodus_traces
        trace = {
            "execution_unit_id": "exec-1",
            "trace_id": "exec-1",
            "sequence": 1,
            "fn_name": "recall",
            "args_summary": None,
            "result_summary": None,
            "duration_ms": 1,
            "status": "ok",
            "error": None,
            "user_id": None,
            "timestamp": None,
        }
        with patch("db.database.SessionLocal", side_effect=RuntimeError("DB down")):
            # Must not raise
            _flush_nodus_traces([trace])

    def test_invalid_user_id_handled_gracefully(self):
        from services.nodus_runtime_adapter import _flush_nodus_traces
        trace = {
            "execution_unit_id": "exec-1",
            "trace_id": "exec-1",
            "sequence": 1,
            "fn_name": "emit",
            "args_summary": None,
            "result_summary": None,
            "duration_ms": 1,
            "status": "ok",
            "error": None,
            "user_id": "not-a-uuid",
            "timestamp": None,
        }
        mock_db = MagicMock()
        with patch("db.database.SessionLocal", return_value=mock_db), \
             patch("db.models.nodus_trace_event.NodusTraceEvent"):
            _flush_nodus_traces([trace])
        mock_db.add.assert_called_once()


# ===========================================================================
# D. query_nodus_trace
# ===========================================================================

class TestQueryNodusTrace:
    def _make_row(self, sequence: int = 1, fn_name: str = "recall") -> MagicMock:
        row = MagicMock()
        row.id = uuid.uuid4()
        row.execution_unit_id = "exec-1"
        row.trace_id = "exec-1"
        row.sequence = sequence
        row.fn_name = fn_name
        row.args_summary = ["goal"]
        row.result_summary = {"length": 1}
        row.duration_ms = 10
        row.status = "ok"
        row.error = None
        row.timestamp = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
        return row

    def test_returns_matching_events(self):
        from services.nodus_trace_service import query_nodus_trace
        db = MagicMock()
        row = self._make_row(sequence=1)
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [row]

        with patch("utils.uuid_utils.normalize_uuid", return_value=uuid.uuid4()):
            result = query_nodus_trace(db=db, trace_id="exec-1", user_id="user-1")

        assert result["count"] == 1
        assert result["trace_id"] == "exec-1"
        assert len(result["steps"]) == 1

    def test_empty_result(self):
        from services.nodus_trace_service import query_nodus_trace
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        with patch("utils.uuid_utils.normalize_uuid", return_value=uuid.uuid4()):
            result = query_nodus_trace(db=db, trace_id="missing", user_id="user-1")

        assert result["count"] == 0
        assert result["steps"] == []

    def test_summary_included(self):
        from services.nodus_trace_service import query_nodus_trace
        db = MagicMock()
        rows = [self._make_row(i, "recall") for i in range(3)]
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = rows

        with patch("utils.uuid_utils.normalize_uuid", return_value=uuid.uuid4()):
            result = query_nodus_trace(db=db, trace_id="exec-1", user_id="user-1")

        assert "summary" in result
        assert result["summary"]["total_calls"] == 3

    def test_limit_applied(self):
        from services.nodus_trace_service import query_nodus_trace
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        with patch("utils.uuid_utils.normalize_uuid", return_value=uuid.uuid4()):
            query_nodus_trace(db=db, trace_id="exec-1", user_id="user-1", limit=10)

        db.query.return_value.filter.return_value.order_by.return_value.limit.assert_called_once_with(10)

    def test_invalid_user_id_handled(self):
        from services.nodus_trace_service import query_nodus_trace
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        with patch("utils.uuid_utils.normalize_uuid", side_effect=ValueError("bad uuid")):
            result = query_nodus_trace(db=db, trace_id="exec-1", user_id="bad")

        assert result["count"] == 0

    def test_execution_unit_id_in_response(self):
        from services.nodus_trace_service import query_nodus_trace
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        with patch("utils.uuid_utils.normalize_uuid", return_value=uuid.uuid4()):
            result = query_nodus_trace(db=db, trace_id="exec-99", user_id="user-1")

        assert result["execution_unit_id"] == "exec-99"


# ===========================================================================
# E. build_trace_summary
# ===========================================================================

class TestBuildTraceSummary:
    def test_empty_steps(self):
        from services.nodus_trace_service import build_trace_summary
        result = build_trace_summary([])
        assert result == {
            "total_calls": 0,
            "total_duration_ms": 0,
            "fn_counts": {},
            "error_count": 0,
            "fn_names": [],
        }

    def test_counts_by_fn_name(self):
        from services.nodus_trace_service import build_trace_summary
        steps = [
            {"fn_name": "recall", "duration_ms": 5, "status": "ok"},
            {"fn_name": "recall", "duration_ms": 3, "status": "ok"},
            {"fn_name": "emit", "duration_ms": 2, "status": "ok"},
        ]
        result = build_trace_summary(steps)
        assert result["fn_counts"] == {"recall": 2, "emit": 1}

    def test_total_duration(self):
        from services.nodus_trace_service import build_trace_summary
        steps = [
            {"fn_name": "recall", "duration_ms": 10, "status": "ok"},
            {"fn_name": "set_state", "duration_ms": 5, "status": "ok"},
        ]
        result = build_trace_summary(steps)
        assert result["total_duration_ms"] == 15

    def test_error_count(self):
        from services.nodus_trace_service import build_trace_summary
        steps = [
            {"fn_name": "recall", "duration_ms": 5, "status": "ok"},
            {"fn_name": "remember", "duration_ms": 1, "status": "error"},
        ]
        result = build_trace_summary(steps)
        assert result["error_count"] == 1

    def test_fn_names_deduplicated_in_order(self):
        from services.nodus_trace_service import build_trace_summary
        steps = [
            {"fn_name": "recall", "duration_ms": 5, "status": "ok"},
            {"fn_name": "emit", "duration_ms": 2, "status": "ok"},
            {"fn_name": "recall", "duration_ms": 3, "status": "ok"},
        ]
        result = build_trace_summary(steps)
        assert result["fn_names"] == ["recall", "emit"]

    def test_none_duration_treated_as_zero(self):
        from services.nodus_trace_service import build_trace_summary
        steps = [{"fn_name": "get_state", "duration_ms": None, "status": "ok"}]
        result = build_trace_summary(steps)
        assert result["total_duration_ms"] == 0


# ===========================================================================
# F. GET /platform/nodus/trace/{trace_id} endpoint
# ===========================================================================

class TestNodusTraceEndpoint:
    def _make_app(self, db_override=None, user_override=None):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routes.platform_router import router
        from db.database import get_db
        from services.auth_service import get_current_user

        app = FastAPI()
        app.include_router(router)

        if db_override:
            app.dependency_overrides[get_db] = db_override
        if user_override:
            app.dependency_overrides[get_current_user] = user_override

        return TestClient(app)

    def test_returns_200_with_trace(self):
        db = MagicMock()
        user = {"sub": str(uuid.uuid4())}
        trace_result = {
            "trace_id": "exec-1",
            "execution_unit_id": "exec-1",
            "count": 2,
            "steps": [
                {"id": str(uuid.uuid4()), "sequence": 1, "fn_name": "recall",
                 "args_summary": [], "result_summary": {}, "duration_ms": 5,
                 "status": "ok", "error": None, "timestamp": "2026-04-01T12:00:00+00:00",
                 "execution_unit_id": "exec-1", "trace_id": "exec-1"},
            ],
            "summary": {"total_calls": 2, "total_duration_ms": 10,
                        "fn_counts": {"recall": 2}, "error_count": 0,
                        "fn_names": ["recall"]},
        }
        client = self._make_app(lambda: db, lambda: user)

        with patch("services.nodus_trace_service.query_nodus_trace", return_value=trace_result):
            resp = client.get("/platform/nodus/trace/exec-1")

        assert resp.status_code == 200
        body = resp.json()
        assert body["trace_id"] == "exec-1"
        assert body["count"] == 2

    def test_returns_404_when_empty(self):
        db = MagicMock()
        user = {"sub": str(uuid.uuid4())}
        empty = {
            "trace_id": "missing",
            "execution_unit_id": "missing",
            "count": 0,
            "steps": [],
            "summary": {"total_calls": 0, "total_duration_ms": 0,
                        "fn_counts": {}, "error_count": 0, "fn_names": []},
        }
        client = self._make_app(lambda: db, lambda: user)

        with patch("services.nodus_trace_service.query_nodus_trace", return_value=empty):
            resp = client.get("/platform/nodus/trace/missing")

        assert resp.status_code == 404
        assert resp.json()["detail"]["error"] == "trace_not_found"

    def test_requires_auth(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routes.platform_router import router
        from db.database import get_db

        app = FastAPI()
        app.include_router(router)
        db = MagicMock()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.get("/platform/nodus/trace/exec-1")
        assert resp.status_code in (401, 403, 422)

    def test_passes_trace_id_to_service(self):
        db = MagicMock()
        user = {"sub": str(uuid.uuid4())}
        result = {
            "trace_id": "my-trace",
            "execution_unit_id": "my-trace",
            "count": 1,
            "steps": [
                {"id": str(uuid.uuid4()), "sequence": 1, "fn_name": "emit",
                 "args_summary": [], "result_summary": {}, "duration_ms": 2,
                 "status": "ok", "error": None, "timestamp": "2026-04-01T12:00:00+00:00",
                 "execution_unit_id": "my-trace", "trace_id": "my-trace"},
            ],
            "summary": {"total_calls": 1, "total_duration_ms": 2,
                        "fn_counts": {"emit": 1}, "error_count": 0,
                        "fn_names": ["emit"]},
        }
        client = self._make_app(lambda: db, lambda: user)

        with patch("services.nodus_trace_service.query_nodus_trace", return_value=result) as mock_q:
            client.get("/platform/nodus/trace/my-trace")

        mock_q.assert_called_once()
        kwargs = mock_q.call_args.kwargs
        assert kwargs["trace_id"] == "my-trace"

    def test_default_limit_applied(self):
        db = MagicMock()
        user = {"sub": str(uuid.uuid4())}
        result = {
            "trace_id": "exec-1",
            "execution_unit_id": "exec-1",
            "count": 1,
            "steps": [
                {"id": str(uuid.uuid4()), "sequence": 1, "fn_name": "recall",
                 "args_summary": [], "result_summary": {}, "duration_ms": 1,
                 "status": "ok", "error": None, "timestamp": "2026-04-01T12:00:00+00:00",
                 "execution_unit_id": "exec-1", "trace_id": "exec-1"},
            ],
            "summary": {"total_calls": 1, "total_duration_ms": 1,
                        "fn_counts": {"recall": 1}, "error_count": 0,
                        "fn_names": ["recall"]},
        }
        client = self._make_app(lambda: db, lambda: user)

        with patch("services.nodus_trace_service.query_nodus_trace", return_value=result) as mock_q:
            client.get("/platform/nodus/trace/exec-1")

        kwargs = mock_q.call_args.kwargs
        assert kwargs["limit"] == 500

    def test_summary_in_response(self):
        db = MagicMock()
        user = {"sub": str(uuid.uuid4())}
        result = {
            "trace_id": "exec-1",
            "execution_unit_id": "exec-1",
            "count": 1,
            "steps": [
                {"id": str(uuid.uuid4()), "sequence": 1, "fn_name": "set_state",
                 "args_summary": [], "result_summary": {}, "duration_ms": 1,
                 "status": "ok", "error": None, "timestamp": "2026-04-01T12:00:00+00:00",
                 "execution_unit_id": "exec-1", "trace_id": "exec-1"},
            ],
            "summary": {"total_calls": 1, "total_duration_ms": 1,
                        "fn_counts": {"set_state": 1}, "error_count": 0,
                        "fn_names": ["set_state"]},
        }
        client = self._make_app(lambda: db, lambda: user)

        with patch("services.nodus_trace_service.query_nodus_trace", return_value=result):
            resp = client.get("/platform/nodus/trace/exec-1")

        body = resp.json()
        assert "summary" in body
        assert body["summary"]["fn_counts"]["set_state"] == 1

    def test_custom_limit_forwarded(self):
        db = MagicMock()
        user = {"sub": str(uuid.uuid4())}
        result = {
            "trace_id": "exec-1",
            "execution_unit_id": "exec-1",
            "count": 1,
            "steps": [
                {"id": str(uuid.uuid4()), "sequence": 1, "fn_name": "recall",
                 "args_summary": [], "result_summary": {}, "duration_ms": 1,
                 "status": "ok", "error": None, "timestamp": "2026-04-01T12:00:00+00:00",
                 "execution_unit_id": "exec-1", "trace_id": "exec-1"},
            ],
            "summary": {"total_calls": 1, "total_duration_ms": 1,
                        "fn_counts": {"recall": 1}, "error_count": 0,
                        "fn_names": ["recall"]},
        }
        client = self._make_app(lambda: db, lambda: user)

        with patch("services.nodus_trace_service.query_nodus_trace", return_value=result) as mock_q:
            client.get("/platform/nodus/trace/exec-1?limit=50")

        kwargs = mock_q.call_args.kwargs
        assert kwargs["limit"] == 50


# ===========================================================================
# G. NodusTraceEvent model
# ===========================================================================

class TestNodusTraceEventModel:
    def test_instantiation_with_required_fields(self):
        from db.models.nodus_trace_event import NodusTraceEvent
        evt = NodusTraceEvent(
            execution_unit_id="exec-1",
            trace_id="exec-1",
            sequence=1,
            fn_name="recall",
        )
        assert evt.fn_name == "recall"
        assert evt.execution_unit_id == "exec-1"

    def test_default_status_is_ok(self):
        from db.models.nodus_trace_event import NodusTraceEvent
        # SQLAlchemy column default is used at insert time; verify the column
        # definition carries the expected default value.
        col = NodusTraceEvent.__table__.c["status"]
        assert col.default.arg == "ok"

    def test_optional_fields_accept_none(self):
        from db.models.nodus_trace_event import NodusTraceEvent
        evt = NodusTraceEvent(
            execution_unit_id="exec-1",
            trace_id="exec-1",
            sequence=1,
            fn_name="get_state",
            args_summary=None,
            result_summary=None,
            duration_ms=None,
            error=None,
            user_id=None,
        )
        assert evt.error is None
        assert evt.duration_ms is None

    def test_tablename(self):
        from db.models.nodus_trace_event import NodusTraceEvent
        assert NodusTraceEvent.__tablename__ == "nodus_trace_events"
