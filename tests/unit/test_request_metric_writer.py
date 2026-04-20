from __future__ import annotations

import queue
from unittest.mock import MagicMock

import pytest


def test_enqueue_and_flush_writes_to_db(monkeypatch, testing_session_factory):
    from AINDY.core.request_metric_writer import PendingMetric, RequestMetricWriter
    from AINDY.db import database as db_module
    from AINDY.db.models.request_metric import RequestMetric

    monkeypatch.setattr(db_module, "SessionLocal", testing_session_factory, raising=False)
    writer = RequestMetricWriter()
    metric = PendingMetric(
        request_id="req-1",
        trace_id="t-1",
        user_id=None,
        method="GET",
        path="/health",
        status_code=200,
        duration_ms=5.0,
    )

    assert writer.enqueue(metric) is True
    writer._flush()

    db = testing_session_factory()
    try:
        row = db.query(RequestMetric).filter_by(request_id="req-1").first()
        assert row is not None
        assert row.path == "/health"
        assert row.status_code == 200
    finally:
        db.close()


def test_enqueue_returns_false_when_queue_full():
    from AINDY.core.request_metric_writer import PendingMetric, RequestMetricWriter

    writer = RequestMetricWriter()
    writer._queue = queue.Queue(maxsize=1)
    metric = PendingMetric(
        request_id="r",
        trace_id="t",
        user_id=None,
        method="GET",
        path="/",
        status_code=200,
        duration_ms=1.0,
    )

    assert writer.enqueue(metric) is True
    assert writer.enqueue(metric) is False


@pytest.mark.asyncio
async def test_log_requests_middleware_does_not_open_session_per_request(monkeypatch):
    from AINDY import main

    sessions_opened: list[int] = []

    def mock_session():
        sessions_opened.append(1)
        raise AssertionError("SessionLocal should not be called by log_requests")

    async def fake_call_next(_request):
        response = MagicMock()
        response.headers = {}
        response.status_code = 200
        return response

    request = MagicMock()
    request.method = "GET"
    request.url.path = "/health"
    request.headers.get.return_value = None
    request.state = MagicMock()

    monkeypatch.setattr(main, "SessionLocal", mock_session)

    response = await main.log_requests(request, fake_call_next)

    assert response.status_code == 200
    assert sessions_opened == []
