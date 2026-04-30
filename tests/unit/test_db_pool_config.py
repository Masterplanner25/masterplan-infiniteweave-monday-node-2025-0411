from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import prometheus_client as _prom
import pytest

# test_metrics_endpoint_includes_db_pool_checkedout_gauge needs real prometheus output.
# Mark only that test; the others work with the stub.
_needs_real_prometheus = pytest.mark.skipif(
    getattr(_prom, "_is_stub", False),
    reason="requires real prometheus_client: pip install -r AINDY/requirements.txt",
)


def test_get_pool_status_returns_expected_keys():
    from AINDY.db.database import get_pool_status

    status = get_pool_status()

    assert set(status.keys()) == {
        "pool_size",
        "checkedout",
        "overflow",
        "checked_in",
        "statement_timeout_ms",
        "idle_in_transaction_timeout_ms",
    }


def test_db_statement_timeout_default_is_30000():
    from AINDY.config import settings

    assert settings.DB_STATEMENT_TIMEOUT_MS == 30000


def test_db_idle_in_transaction_timeout_default_is_30000():
    from AINDY.config import settings

    assert settings.DB_IDLE_IN_TRANSACTION_TIMEOUT_MS == 30000


def test_get_pool_status_includes_statement_timeout_key():
    from AINDY.db.database import get_pool_status

    status = get_pool_status()

    assert "statement_timeout_ms" in status


def test_get_pool_status_includes_idle_in_transaction_timeout_key():
    from AINDY.db.database import get_pool_status

    status = get_pool_status()

    assert "idle_in_transaction_timeout_ms" in status


def test_health_response_includes_db_pool_key(client, monkeypatch):
    import importlib

    health_router = importlib.import_module("AINDY.routes.health_router")

    monkeypatch.setattr(
        health_router,
        "get_pool_status",
        lambda: {"pool_size": 10, "checkedout": 2, "overflow": 0, "checked_in": 8},
    )

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert "db_pool" in payload
    assert payload["db_pool"]["pool_size"] == 10


def test_engine_creation_uses_configured_db_pool_size(monkeypatch):
    import AINDY.config as config_module
    import AINDY.db.database as database_module
    from sqlalchemy import create_engine as real_create_engine

    monkeypatch.setattr(config_module.settings, "DATABASE_URL", "postgresql://user:pass@localhost/testdb")
    monkeypatch.setattr(config_module.settings, "DB_POOL_SIZE", 20)
    monkeypatch.setattr(config_module.settings, "DB_MAX_OVERFLOW", 7)
    monkeypatch.setattr(config_module.settings, "DB_POOL_TIMEOUT", 11)
    monkeypatch.setattr(config_module.settings, "DB_POOL_RECYCLE", 123)
    monkeypatch.setattr(config_module.settings, "TESTING", False)
    monkeypatch.setattr(config_module.settings, "TEST_MODE", False)
    captured: dict = {}

    def _fake_create_engine(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return real_create_engine("sqlite:///:memory:")

    with patch("sqlalchemy.create_engine", side_effect=_fake_create_engine), patch(
        "sqlalchemy.event.listens_for",
        lambda *args, **kwargs: (lambda fn: fn),
    ):
        importlib.reload(database_module)

    kwargs = captured["kwargs"]
    assert kwargs["pool_size"] == 20
    assert kwargs["max_overflow"] == 7
    assert kwargs["pool_timeout"] == 11
    assert kwargs["pool_recycle"] == 123
    assert kwargs["pool_pre_ping"] is True

    monkeypatch.setattr(config_module.settings, "DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setattr(config_module.settings, "TESTING", True)
    monkeypatch.setattr(config_module.settings, "TEST_MODE", True)
    importlib.reload(database_module)


@_needs_real_prometheus
def test_metrics_registry_contains_db_pool_gauges():
    from AINDY.platform_layer.metrics import REGISTRY

    metric_names = {metric.name for metric in REGISTRY.collect()}

    assert "aindy_db_pool_checkedout" in metric_names


@_needs_real_prometheus
def test_metrics_endpoint_includes_db_pool_checkedout_gauge(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "aindy_db_pool_checkedout" in response.text
