from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch


def test_get_pool_status_returns_expected_keys():
    from AINDY.db.database import get_pool_status

    status = get_pool_status()

    assert set(status.keys()) == {"pool_size", "checkedout", "overflow", "checked_in"}


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


def test_metrics_registry_contains_db_pool_gauges():
    from AINDY.platform_layer.metrics import REGISTRY

    metric_names = {metric.name for metric in REGISTRY.collect()}

    assert "aindy_db_pool_checkedout" in metric_names


def test_metrics_endpoint_includes_db_pool_checkedout_gauge(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "aindy_db_pool_checkedout" in response.text
