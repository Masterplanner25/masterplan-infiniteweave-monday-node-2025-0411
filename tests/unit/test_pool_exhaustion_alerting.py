from __future__ import annotations

import importlib


def _counter_value(counter) -> float:
    return counter._value.get()


def _gauge_value(gauge) -> float:
    return gauge._value.get()


def test_update_db_pool_metrics_sets_pressure_gauge(monkeypatch):
    import AINDY.startup as startup
    from AINDY.platform_layer.metrics import db_pool_pressure

    monkeypatch.setattr(startup, "_pool_was_near_exhaustion", False)
    monkeypatch.setattr(
        importlib.import_module("AINDY.db.database"),
        "get_pool_status",
        lambda: {"pool_size": 10, "checkedout": 0, "overflow": 0, "checked_in": 10},
    )

    startup._update_db_pool_metrics()

    assert _gauge_value(db_pool_pressure) == 0.0

    monkeypatch.setattr(
        importlib.import_module("AINDY.db.database"),
        "get_pool_status",
        lambda: {"pool_size": 10, "checkedout": 26, "overflow": 16, "checked_in": 0},
    )

    startup._update_db_pool_metrics()

    assert round(_gauge_value(db_pool_pressure), 2) == 0.87


def test_rising_edge_only_increments_counter_once(monkeypatch):
    import AINDY.startup as startup
    from AINDY.platform_layer.metrics import db_pool_exhaustion_events_total

    db_database = importlib.import_module("AINDY.db.database")
    monkeypatch.setattr(startup, "_pool_was_near_exhaustion", False)
    start_value = _counter_value(db_pool_exhaustion_events_total)
    monkeypatch.setattr(
        db_database,
        "get_pool_status",
        lambda: {"pool_size": 10, "checkedout": 26, "overflow": 16, "checked_in": 0},
    )

    startup._update_db_pool_metrics()
    startup._update_db_pool_metrics()

    assert _counter_value(db_pool_exhaustion_events_total) == start_value + 1


def test_falling_edge_does_not_increment_counter(monkeypatch):
    import AINDY.startup as startup
    from AINDY.platform_layer.metrics import db_pool_exhaustion_events_total

    db_database = importlib.import_module("AINDY.db.database")
    monkeypatch.setattr(startup, "_pool_was_near_exhaustion", False)
    start_value = _counter_value(db_pool_exhaustion_events_total)
    statuses = iter(
        [
            {"pool_size": 10, "checkedout": 26, "overflow": 16, "checked_in": 0},
            {"pool_size": 10, "checkedout": 2, "overflow": 0, "checked_in": 8},
        ]
    )
    monkeypatch.setattr(db_database, "get_pool_status", lambda: next(statuses))

    startup._update_db_pool_metrics()
    startup._update_db_pool_metrics()

    assert _counter_value(db_pool_exhaustion_events_total) == start_value + 1
    assert startup._pool_was_near_exhaustion is False


def test_health_endpoint_includes_pressure_ratio(client, monkeypatch):
    health_router = importlib.import_module("AINDY.routes.health_router")

    monkeypatch.setattr(
        health_router,
        "get_pool_status",
        lambda: {"pool_size": 10, "checkedout": 2, "overflow": 0, "checked_in": 8},
    )

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert "pressure_ratio" in payload["db_pool"]
    assert payload["db_pool"]["pressure_ratio"] == 0.067
