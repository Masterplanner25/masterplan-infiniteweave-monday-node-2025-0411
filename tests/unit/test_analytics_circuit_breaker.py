from __future__ import annotations

from datetime import timedelta

import pytest

from AINDY.kernel.circuit_breaker import CircuitBreaker, CircuitState
from apps.analytics import public as analytics_public


def _fresh_breaker(name: str, *, recovery_timeout_secs: int = 60) -> CircuitBreaker:
    return CircuitBreaker(name=name, failure_threshold=1, recovery_timeout_secs=recovery_timeout_secs)


def test_open_circuit_returns_fallback_values(monkeypatch):
    breaker = _fresh_breaker("analytics.public.get_user_scores", recovery_timeout_secs=60)
    monkeypatch.setattr(analytics_public, "_get_circuit_breaker", lambda function_name: breaker)
    monkeypatch.setattr(analytics_public, "parse_user_id", lambda _user_id: (_ for _ in ()).throw(RuntimeError("db down")))

    with pytest.raises(RuntimeError):
        analytics_public.get_user_scores(["user-1"], db=None)

    result = analytics_public.get_user_scores(["user-1"], db=None)

    assert breaker.state == CircuitState.OPEN
    assert result == {}


def test_circuit_closes_again_after_success(monkeypatch):
    breaker = _fresh_breaker("analytics.public.get_user_kpi_snapshot", recovery_timeout_secs=60)
    monkeypatch.setattr(analytics_public, "_get_circuit_breaker", lambda function_name: breaker)

    monkeypatch.setattr(analytics_public, "_get_user_kpi_snapshot", lambda user_id, db: (_ for _ in ()).throw(RuntimeError("down")))

    with pytest.raises(RuntimeError):
        analytics_public.get_user_kpi_snapshot("user-1", db=None)

    fallback = analytics_public.get_user_kpi_snapshot("user-1", db=None)
    assert fallback is None
    assert breaker.state == CircuitState.OPEN

    breaker._opened_at = breaker._now() - timedelta(seconds=breaker.recovery_timeout_secs + 1)

    monkeypatch.setattr(
        analytics_public,
        "_get_user_kpi_snapshot",
        lambda user_id, db: {
            "master_score": 42.0,
            "execution_speed": 10.0,
            "decision_efficiency": 11.0,
            "ai_productivity_boost": 12.0,
            "focus_quality": 13.0,
            "masterplan_progress": 14.0,
            "confidence": "medium",
        },
    )

    result = analytics_public.get_user_kpi_snapshot("user-1", db=None)

    assert result is not None
    assert result["master_score"] == 42.0
    assert breaker.state == CircuitState.CLOSED
