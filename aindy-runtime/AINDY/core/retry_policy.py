"""
Retry Policy - central definition of retry semantics for all execution types.

This module defines how many attempts each execution type makes and under what
conditions. It also centralizes the shared backoff calculation so retry delays
stay consistent across execution paths.

Current system defaults (preserved exactly):
  Flow nodes    -> max_attempts=3  (global POLICY["max_retries"] in flow_engine.py)
  Agent low/med -> max_attempts=3  (MAX_STEP_RETRIES in nodus_adapter.py)
  Agent high    -> max_attempts=1  (immediate fail; no retry)
  AsyncJob      -> max_attempts=1  (default in async_job_service.py)
  Nodus sched.  -> max_attempts=3  (NodusScheduledJob.max_retries default)
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, TypeVar


_T = TypeVar("_T")
_MAX_BACKOFF_SECONDS = 10.0
_MAX_JITTER_MS = 50


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetryPolicy:
    """Immutable retry policy for one execution unit."""

    max_attempts: int
    """Total attempts allowed (1 = no retry)."""

    backoff_ms: int = 0
    """Base delay between attempts in milliseconds."""

    exponential_backoff: bool = False
    """If True, multiply backoff_ms by 2^attempt between retries."""

    high_risk_immediate_fail: bool = False
    """If True, any failure on the first attempt is terminal regardless of
    max_attempts. Matches nodus_adapter high-risk no-retry rule."""


# ---------------------------------------------------------------------------
# Well-known policies (named constants for documentation and future adoption)
# ---------------------------------------------------------------------------

# Mirrors flow_engine.POLICY["max_retries"] = 3 with exponential backoff
FLOW_NODE_DEFAULT = RetryPolicy(max_attempts=3, backoff_ms=200, exponential_backoff=True)

# Mirrors nodus_adapter.MAX_STEP_RETRIES = 3 for low/medium risk
AGENT_LOW_MEDIUM = RetryPolicy(max_attempts=3, backoff_ms=200, exponential_backoff=True)

# Mirrors nodus_adapter high-risk rule: 1 attempt, immediate fail on error
AGENT_HIGH_RISK = RetryPolicy(
    max_attempts=1,
    backoff_ms=0,
    exponential_backoff=False,
    high_risk_immediate_fail=True,
)

# Mirrors async_job_service default max_attempts=1
ASYNC_JOB_DEFAULT = RetryPolicy(max_attempts=1, backoff_ms=500, exponential_backoff=True)

# Mirrors NodusScheduledJob.max_retries default = 3 via nodus_schedule_service
NODUS_SCHEDULED_DEFAULT = RetryPolicy(max_attempts=3, backoff_ms=300, exponential_backoff=True)

# Used when a node explicitly opts out of retry (e.g. task_orchestrate RETRY->FAILURE)
NO_RETRY = RetryPolicy(max_attempts=1, backoff_ms=0, exponential_backoff=False)


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

_RISK_TO_AGENT_POLICY: dict[str, RetryPolicy] = {
    "low": AGENT_LOW_MEDIUM,
    "medium": AGENT_LOW_MEDIUM,
    "high": AGENT_HIGH_RISK,
}

# Error strings that indicate a non-retryable failure regardless of policy.
# Callers may check is_retryable_error() before honouring max_attempts.
_NON_RETRYABLE_SUBSTRINGS: tuple[str, ...] = (
    "permission",
    "unauthorized",
    "forbidden",
    "not found",
    "404",
    "401",
    "403",
    "invalid",
    "blocked by policy",
)


def resolve_retry_policy(
    *,
    execution_type: str,
    risk_level: Optional[str] = None,
    node_max_retries: Optional[int] = None,
    job_max_retries: Optional[int] = None,
) -> RetryPolicy:
    """
    Return the RetryPolicy that applies to one execution unit.

    Parameters
    ----------
    execution_type:
        One of ``"flow"``, ``"agent"``, ``"job"``, ``"nodus"``.
        Unknown types fall back to NO_RETRY (fail-safe).

    risk_level:
        Agent step risk level: ``"low"``, ``"medium"``, or ``"high"``.
        Only meaningful when execution_type == ``"agent"``.

    node_max_retries:
        Per-node override from node config (e.g. a flow node that declares
        its own ``max_retries`` value). When present this overrides the
        flow default. Has no effect for non-flow types.

    job_max_retries:
        Per-job override from ``NodusScheduledJob.max_retries``. Only
        meaningful when execution_type == ``"nodus"``.

    Returns
    -------
    RetryPolicy
        Frozen dataclass; never raises.
    """
    etype = (execution_type or "").lower().strip()

    if etype == "flow":
        if node_max_retries is not None:
            return RetryPolicy(
                max_attempts=max(1, node_max_retries),
                backoff_ms=FLOW_NODE_DEFAULT.backoff_ms,
                exponential_backoff=FLOW_NODE_DEFAULT.exponential_backoff,
            )
        return FLOW_NODE_DEFAULT

    if etype == "agent":
        risk = (risk_level or "high").lower().strip()
        return _RISK_TO_AGENT_POLICY.get(risk, AGENT_HIGH_RISK)

    if etype == "job":
        return ASYNC_JOB_DEFAULT

    if etype == "nodus":
        # Nodus scripts run inside a flow wrapper; inherit from there.
        # If a scheduled job supplies its own max_retries, honour that.
        if job_max_retries is not None:
            return RetryPolicy(
                max_attempts=max(1, job_max_retries),
                backoff_ms=NODUS_SCHEDULED_DEFAULT.backoff_ms,
                exponential_backoff=NODUS_SCHEDULED_DEFAULT.exponential_backoff,
            )
        return NODUS_SCHEDULED_DEFAULT

    # Unknown type -> safest default: no retry
    return NO_RETRY


# ---------------------------------------------------------------------------
# Retry execution helpers
# ---------------------------------------------------------------------------

def _retry_delay_seconds(policy: RetryPolicy, attempt_number: int) -> float:
    """
    Return the delay before the next retry attempt.

    ``attempt_number`` is 1-based for retries only: after the first failed
    attempt pass ``1``, so the first execution attempt is never delayed.
    """
    if attempt_number <= 0 or policy.backoff_ms <= 0:
        return 0.0

    multiplier = 2 ** attempt_number if policy.exponential_backoff else 1
    delay_ms = (policy.backoff_ms * multiplier) + random.randint(0, _MAX_JITTER_MS)
    return min(delay_ms / 1000.0, _MAX_BACKOFF_SECONDS)


def _sleep_before_retry(policy: RetryPolicy, attempt_number: int) -> None:
    delay_seconds = _retry_delay_seconds(policy, attempt_number)
    if delay_seconds > 0:
        time.sleep(delay_seconds)


async def _sleep_before_retry_async(policy: RetryPolicy, attempt_number: int) -> None:
    delay_seconds = _retry_delay_seconds(policy, attempt_number)
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)


# ---------------------------------------------------------------------------
# Error classification helper
# ---------------------------------------------------------------------------

def is_retryable_error(error: Optional[str]) -> bool:
    """
    Return False when an error string signals a non-retryable failure.

    Callers can use this to short-circuit retry loops even when the policy
    allows more attempts. Current system does not use this - it is here as
    the central place to add the check when callers adopt it.
    """
    if not error:
        return True
    lower = error.lower()
    return not any(substr in lower for substr in _NON_RETRYABLE_SUBSTRINGS)


def execute_with_retry(
    operation: Callable[[], _T],
    *,
    policy: RetryPolicy,
    retryable_error_checker: Callable[[Optional[str]], bool] = is_retryable_error,
) -> _T:
    """Run a synchronous operation under the supplied retry policy."""
    for attempt_index in range(policy.max_attempts):
        try:
            return operation()
        except Exception as exc:
            if policy.high_risk_immediate_fail or attempt_index + 1 >= policy.max_attempts:
                raise

            if not retryable_error_checker(str(exc)):
                raise

            _sleep_before_retry(policy, attempt_index + 1)

    raise RuntimeError("retry loop exhausted unexpectedly")


async def _execute_with_retry(
    operation: Callable[[], Awaitable[_T]],
    *,
    policy: RetryPolicy,
    retryable_error_checker: Callable[[Optional[str]], bool] = is_retryable_error,
) -> _T:
    """Run an async operation under the supplied retry policy."""
    for attempt_index in range(policy.max_attempts):
        try:
            return await operation()
        except Exception as exc:
            if policy.high_risk_immediate_fail or attempt_index + 1 >= policy.max_attempts:
                raise

            if not retryable_error_checker(str(exc)):
                raise

            await _sleep_before_retry_async(policy, attempt_index + 1)

    raise RuntimeError("retry loop exhausted unexpectedly")
