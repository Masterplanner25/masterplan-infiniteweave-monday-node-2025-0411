"""Circuit breakers and shared state for RippleTrace engines."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from AINDY.kernel.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = logging.getLogger(__name__)

_BREAKERS: dict[str, CircuitBreaker] = {}


def get_engine_breaker(engine_name: str) -> CircuitBreaker:
    breaker = _BREAKERS.get(engine_name)
    if breaker is None:
        breaker = CircuitBreaker(
            name=f"rippletrace.{engine_name}",
            failure_threshold=3,
            recovery_timeout_secs=60,
        )
        _BREAKERS[engine_name] = breaker
    return breaker


def _metric_run(engine_name: str, status: str) -> None:
    try:
        from AINDY.platform_layer.metrics import rippletrace_engine_runs_total

        rippletrace_engine_runs_total.labels(engine=engine_name, status=status).inc()
    except Exception:
        pass


def _metric_duration(engine_name: str, duration_seconds: float) -> None:
    try:
        from AINDY.platform_layer.metrics import rippletrace_engine_duration_seconds

        rippletrace_engine_duration_seconds.labels(engine=engine_name).observe(
            duration_seconds
        )
    except Exception:
        pass


def call_with_engine_breaker(engine_name: str, fallback: Any, fn: Callable[[], Any]):
    breaker = get_engine_breaker(engine_name)
    started = time.monotonic()
    try:
        result = breaker.call(fn)
    except CircuitOpenError:
        _metric_run(engine_name, "circuit_open")
        logger.warning(
            "[rippletrace] %s circuit open - returning fallback",
            engine_name,
        )
        return fallback
    except Exception:
        _metric_run(engine_name, "failure")
        raise
    finally:
        _metric_duration(engine_name, time.monotonic() - started)
    _metric_run(engine_name, "success")
    return result
