"""
Sprint N+9 Phase 2 — Request context propagation tests.

Groups:
  1. _request_id_ctx ContextVar defaults (2 tests)
  2. RequestContextFilter sets record.request_id (3 tests)
  3. log_requests middleware sets ContextVar before call_next (3 tests)
"""
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# Group 1 — ContextVar defaults
# ─────────────────────────────────────────────────────────────────────────────

class TestRequestIdContextVar:
    """_request_id_ctx should default to '-' when no request is active."""

    def test_default_is_dash(self):
        from AINDY.main import _request_id_ctx
        # In a fresh context with no set() call, default must be "-"
        assert _request_id_ctx.get() == "-"

    def test_set_then_get_returns_value(self):
        from AINDY.main import _request_id_ctx
        token = _request_id_ctx.set("test-req-id-123")
        try:
            assert _request_id_ctx.get() == "test-req-id-123"
        finally:
            _request_id_ctx.reset(token)


# ─────────────────────────────────────────────────────────────────────────────
# Group 2 — RequestContextFilter
# ─────────────────────────────────────────────────────────────────────────────

class TestRequestContextFilter:
    """RequestContextFilter must inject request_id into every LogRecord."""

    def test_filter_sets_request_id_from_ctx(self):
        from AINDY.main import RequestContextFilter, _request_id_ctx
        f = RequestContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hi", args=(), exc_info=None,
        )
        token = _request_id_ctx.set("abc-123")
        try:
            f.filter(record)
        finally:
            _request_id_ctx.reset(token)
        assert record.request_id == "abc-123"
        assert record.trace_id == "abc-123"

    def test_filter_uses_default_when_no_request(self):
        from AINDY.main import RequestContextFilter, _request_id_ctx
        f = RequestContextFilter()
        # Ensure no value is set (use a fresh token state)
        token = _request_id_ctx.set("-")
        try:
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="", lineno=0,
                msg="no request", args=(), exc_info=None,
            )
            f.filter(record)
            assert record.request_id == "-"
        finally:
            _request_id_ctx.reset(token)

    def test_filter_returns_true(self):
        from AINDY.main import RequestContextFilter
        f = RequestContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="check return", args=(), exc_info=None,
        )
        result = f.filter(record)
        assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# Group 3 — log_requests middleware
# ─────────────────────────────────────────────────────────────────────────────

class TestLogRequestsMiddleware:
    """log_requests must set _request_id_ctx before calling call_next."""

    @pytest.mark.asyncio
    async def test_sets_request_id_before_call_next(self):
        from AINDY.main import log_requests, _request_id_ctx

        captured_id: list[str] = []

        async def fake_call_next(req):
            # By the time call_next runs, request_id must already be set
            captured_id.append(_request_id_ctx.get())
            mock_resp = MagicMock()
            mock_resp.headers = {}
            mock_resp.status_code = 200
            return mock_resp

        mock_request = MagicMock()
        mock_request.method = "GET"
        mock_request.url.path = "/test"

        await log_requests(mock_request, fake_call_next)

        assert len(captured_id) == 1
        assert captured_id[0] != "-"  # a real UUID was set

    @pytest.mark.asyncio
    async def test_response_header_x_request_id_set(self):
        from AINDY.main import log_requests

        async def fake_call_next(req):
            mock_resp = MagicMock()
            mock_resp.headers = {}
            mock_resp.status_code = 200
            return mock_resp

        mock_request = MagicMock()
        mock_request.method = "GET"
        mock_request.url.path = "/ping"

        response = await log_requests(mock_request, fake_call_next)
        assert "X-Request-ID" in response.headers
        assert response.headers["X-Trace-ID"] == response.headers["X-Request-ID"]

    @pytest.mark.asyncio
    async def test_request_id_is_uuid_format(self):
        import re
        from AINDY.main import log_requests, _request_id_ctx

        UUID_PATTERN = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        captured_id: list[str] = []

        async def fake_call_next(req):
            captured_id.append(_request_id_ctx.get())
            mock_resp = MagicMock()
            mock_resp.headers = {}
            mock_resp.status_code = 200
            return mock_resp

        mock_request = MagicMock()
        mock_request.method = "POST"
        mock_request.url.path = "/apps/agent/run"

        await log_requests(mock_request, fake_call_next)

        assert UUID_PATTERN.match(captured_id[0])
