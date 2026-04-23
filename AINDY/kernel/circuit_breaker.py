from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open and calls are rejected."""


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout_secs: int = 60,
    ):
        self.name = name
        self.failure_threshold = int(failure_threshold)
        self.recovery_timeout_secs = int(recovery_timeout_secs)
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: datetime | None = None
        self._half_open_in_flight = False
        self._lock = Lock()

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _transition_to(self, new_state: CircuitState, *, now: datetime) -> None:
        previous_state = self._state
        if previous_state != new_state:
            logger.warning(
                "[CircuitBreaker:%s] %s -> %s",
                self.name,
                previous_state.value,
                new_state.value,
            )
        self._state = new_state
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._opened_at = None
            self._half_open_in_flight = False
        elif new_state == CircuitState.OPEN:
            self._opened_at = now
            self._half_open_in_flight = False
        try:
            from AINDY.platform_layer.metrics import ai_circuit_breaker_state

            state_value = {"closed": 0, "half_open": 1, "open": 2}.get(new_state.value, -1)
            ai_circuit_breaker_state.labels(provider=self.name).set(state_value)
        except Exception:
            pass

    def _enter_call(self) -> str:
        with self._lock:
            now = self._now()
            if self._state == CircuitState.CLOSED:
                return "closed"

            if self._state == CircuitState.OPEN:
                if self._opened_at is not None:
                    elapsed = (now - self._opened_at).total_seconds()
                    if elapsed >= self.recovery_timeout_secs:
                        self._transition_to(CircuitState.HALF_OPEN, now=now)
                        self._half_open_in_flight = True
                        return "half_open"
                raise CircuitOpenError(
                    f"Circuit '{self.name}' is open; rejecting call"
                )

            if self._half_open_in_flight:
                raise CircuitOpenError(
                    f"Circuit '{self.name}' is half-open; probe already in flight"
                )

            self._half_open_in_flight = True
            return "half_open"

    def _record_success(self, phase: str) -> None:
        with self._lock:
            if phase == "half_open" or self._state != CircuitState.CLOSED:
                self._transition_to(CircuitState.CLOSED, now=self._now())
            else:
                self._failure_count = 0

    def _record_failure(self, phase: str) -> None:
        with self._lock:
            now = self._now()
            if phase == "half_open" or self._state == CircuitState.HALF_OPEN:
                self._failure_count = self.failure_threshold
                self._transition_to(CircuitState.OPEN, now=now)
                return

            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                self._transition_to(CircuitState.OPEN, now=now)

    def call(self, func: Callable[..., Any], *args, **kwargs):
        """
        Execute func(*args, **kwargs) with circuit breaker protection.
        - If CLOSED: call normally, track failures
        - If OPEN and recovery timeout not elapsed: raise CircuitOpenError immediately
        - If OPEN and recovery timeout elapsed: transition to HALF_OPEN, try once
        - If HALF_OPEN succeeds: transition to CLOSED
        - If HALF_OPEN fails: transition back to OPEN, reset timer
        """
        phase = self._enter_call()
        try:
            result = func(*args, **kwargs)
        except Exception:
            self._record_failure(phase)
            raise
        self._record_success(phase)
        return result

    async def async_call(self, coro_func: Callable[..., Awaitable[Any]], *args, **kwargs):
        """Async version of call() for async OpenAI clients."""
        phase = self._enter_call()
        try:
            result = await coro_func(*args, **kwargs)
        except Exception:
            self._record_failure(phase)
            raise
        self._record_success(phase)
        return result

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count

    @property
    def opened_at(self) -> datetime | None:
        with self._lock:
            return self._opened_at

    def reset(self) -> None:
        with self._lock:
            self._transition_to(CircuitState.CLOSED, now=self._now())


_openai_circuit_breaker = CircuitBreaker(
    name="openai",
    failure_threshold=3,
    recovery_timeout_secs=60,
)

_deepseek_circuit_breaker = CircuitBreaker(
    name="deepseek",
    failure_threshold=3,
    recovery_timeout_secs=60,
)


def get_openai_circuit_breaker() -> CircuitBreaker:
    return _openai_circuit_breaker


def get_deepseek_circuit_breaker() -> CircuitBreaker:
    return _deepseek_circuit_breaker
