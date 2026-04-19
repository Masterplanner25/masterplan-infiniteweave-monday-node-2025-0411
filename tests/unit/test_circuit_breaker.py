from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta, timezone

import pytest

from AINDY.kernel.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


def test_circuit_starts_closed():
    breaker = CircuitBreaker("test")
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


def test_circuit_opens_after_threshold_failures():
    breaker = CircuitBreaker("test", failure_threshold=3)

    def _fail():
        raise RuntimeError("down")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            breaker.call(_fail)

    assert breaker.state == CircuitState.OPEN
    assert breaker.failure_count == 3
    assert breaker.opened_at is not None


def test_open_circuit_fails_fast_without_calling_func():
    breaker = CircuitBreaker("test", failure_threshold=1)
    called = {"count": 0}

    def _fail():
        called["count"] += 1
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        breaker.call(_fail)

    with pytest.raises(CircuitOpenError):
        breaker.call(_fail)

    assert called["count"] == 1


def test_open_circuit_transitions_to_half_open_after_timeout():
    breaker = CircuitBreaker("test", failure_threshold=1, recovery_timeout_secs=60)
    base_now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    timeline = {"now": base_now}
    breaker._now = lambda: timeline["now"]  # type: ignore[method-assign]
    seen_state = {"value": None}

    def _fail():
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        breaker.call(_fail)

    assert breaker.state == CircuitState.OPEN
    timeline["now"] = base_now + timedelta(seconds=61)

    def _probe():
        seen_state["value"] = breaker.state
        return "ok"

    assert breaker.call(_probe) == "ok"
    assert seen_state["value"] == CircuitState.HALF_OPEN
    assert breaker.state == CircuitState.CLOSED


def test_half_open_success_closes_circuit_and_resets_failure_count():
    breaker = CircuitBreaker("test", failure_threshold=1, recovery_timeout_secs=60)
    base_now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    timeline = {"now": base_now}
    breaker._now = lambda: timeline["now"]  # type: ignore[method-assign]

    def _fail():
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        breaker.call(_fail)

    timeline["now"] = base_now + timedelta(seconds=61)
    result = breaker.call(lambda: "ok")

    assert result == "ok"
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0
    assert breaker.opened_at is None


def test_half_open_failure_reopens_and_resets_timer():
    breaker = CircuitBreaker("test", failure_threshold=1, recovery_timeout_secs=60)
    base_now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    timeline = {"now": base_now}
    breaker._now = lambda: timeline["now"]  # type: ignore[method-assign]

    def _fail():
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        breaker.call(_fail)

    first_opened = breaker.opened_at
    timeline["now"] = base_now + timedelta(seconds=61)

    with pytest.raises(RuntimeError):
        breaker.call(_fail)

    assert breaker.state == CircuitState.OPEN
    assert breaker.opened_at == timeline["now"]
    assert breaker.opened_at != first_opened


def test_success_while_closed_resets_failure_count():
    breaker = CircuitBreaker("test", failure_threshold=3)

    def _fail():
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        breaker.call(_fail)
    with pytest.raises(RuntimeError):
        breaker.call(_fail)

    assert breaker.failure_count == 2
    assert breaker.call(lambda: "ok") == "ok"
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


def test_thread_safety_under_simultaneous_failures():
    breaker = CircuitBreaker("test", failure_threshold=2)
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def _fail():
        barrier.wait()
        raise RuntimeError("down")

    def _worker():
        try:
            breaker.call(_fail)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(errors) == 2
    assert breaker.state == CircuitState.OPEN
    assert breaker.failure_count == 2


def test_async_call_supports_async_functions():
    breaker = CircuitBreaker("test")

    async def _ok():
        return "ok"

    result = asyncio.run(breaker.async_call(_ok))
    assert result == "ok"
    assert breaker.state == CircuitState.CLOSED
