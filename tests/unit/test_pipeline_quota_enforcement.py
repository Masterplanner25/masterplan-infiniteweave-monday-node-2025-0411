"""Unit tests for quota enforcement wired into ExecutionPipeline.run()."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from AINDY.core.execution_pipeline import ExecutionContext, ExecutionPipeline


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ctx(user_id: str = "user-1", eu_id: str | None = "eu-1") -> ExecutionContext:
    ctx = ExecutionContext(request_id="req-test", route_name="test.route")
    ctx.user_id = user_id
    if eu_id:
        ctx.metadata["eu_id"] = eu_id
    return ctx


def _run(pipeline: ExecutionPipeline, ctx: ExecutionContext, handler) -> object:
    return asyncio.run(pipeline.run(ctx, handler))


def _mock_rm(can_execute_rv=(True, None)) -> MagicMock:
    rm = MagicMock()
    rm.can_execute.return_value = can_execute_rv
    return rm


def _patch_rm(rm: MagicMock):
    return patch("AINDY.kernel.resource_manager.get_resource_manager", return_value=rm)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_quota_exceeded_returns_429():
    """When can_execute returns False the pipeline short-circuits with 429."""
    pipeline = ExecutionPipeline()
    ctx = _make_ctx()
    rm = _mock_rm(can_execute_rv=(False, "limit reached"))

    with _patch_rm(rm):
        result = _run(pipeline, ctx, lambda c: {"data": "ok"})

    assert result.success is False
    assert result.metadata["status_code"] == 429
    assert "limit" in result.error.lower() or "concurrency" in result.error.lower()
    # mark_started must NOT have been called — we never started
    rm.mark_started.assert_not_called()


def test_quota_ok_proceeds():
    """When can_execute returns True the handler is called normally."""
    pipeline = ExecutionPipeline()
    ctx = _make_ctx()
    rm = _mock_rm(can_execute_rv=(True, None))

    handler_called = []
    def handler(c):
        handler_called.append(True)
        return {"result": "ok"}

    with _patch_rm(rm):
        result = _run(pipeline, ctx, handler)

    assert result.success is True
    assert handler_called == [True]


def test_quota_rm_error_fails_open():
    """When can_execute raises the pipeline proceeds (fail open)."""
    pipeline = ExecutionPipeline()
    ctx = _make_ctx()
    rm = MagicMock()
    rm.can_execute.side_effect = RuntimeError("redis unavailable")

    handler_called = []
    def handler(c):
        handler_called.append(True)
        return {"result": "ok"}

    with _patch_rm(rm):
        result = _run(pipeline, ctx, handler)

    assert result.success is True
    assert handler_called == [True]


def test_mark_completed_called_on_success():
    """mark_completed is called exactly once after a successful handler."""
    pipeline = ExecutionPipeline()
    ctx = _make_ctx()
    rm = _mock_rm()

    with _patch_rm(rm):
        result = _run(pipeline, ctx, lambda c: {"result": "ok"})

    assert result.success is True
    rm.mark_completed.assert_called_once_with("user-1", "eu-1")


def test_mark_completed_called_on_handler_exception():
    """mark_completed is called even when the handler raises."""
    pipeline = ExecutionPipeline()
    ctx = _make_ctx()
    rm = _mock_rm()

    def bad_handler(c):
        raise ValueError("handler blew up")

    with _patch_rm(rm):
        result = _run(pipeline, ctx, bad_handler)

    assert result.success is False
    rm.mark_completed.assert_called_once_with("user-1", "eu-1")
