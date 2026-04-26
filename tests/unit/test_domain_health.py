from __future__ import annotations

from AINDY.platform_layer.domain_health import DomainHealthRegistry


def test_register_and_check_all_returns_statuses():
    registry = DomainHealthRegistry()
    registry.register("analytics", lambda: True)
    registry.register("automation", lambda: True)

    statuses = registry.check_all()

    assert set(statuses) == {"analytics", "automation"}
    assert statuses["analytics"].healthy is True
    assert statuses["automation"].healthy is True
    assert statuses["analytics"].error is None


def test_failing_check_fn_marks_domain_unhealthy():
    registry = DomainHealthRegistry()
    registry.register("analytics", lambda: False)

    status = registry.check_one("analytics")

    assert status.healthy is False
    assert status.error == "health check returned false"


def test_check_all_swallows_exceptions_from_check_fn():
    registry = DomainHealthRegistry()

    def _fail() -> bool:
        raise RuntimeError("analytics unavailable")

    registry.register("analytics", _fail)

    statuses = registry.check_all()

    assert statuses["analytics"].healthy is False
    assert statuses["analytics"].error == "analytics unavailable"
