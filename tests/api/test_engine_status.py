from __future__ import annotations


def test_dag_engine_registers_nodes(client):
    """Engine A must have at least one non-nodus node after startup."""
    from AINDY.runtime import get_engine_status

    status = get_engine_status()
    assert status["dag_engine"]["registered_nodes"] > 0, (
        "Custom DAG engine registered no nodes at startup"
    )


def test_nodus_engine_status_key_present(client):
    """Engine B status must always be present in runtime diagnostics."""
    from AINDY.runtime import get_engine_status

    status = get_engine_status()
    assert "nodus_engine" in status
    assert "available" in status["nodus_engine"]


def test_health_reports_flow_engine_status(client):
    response = client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert "flow_engines" in data
    assert "dag_engine" in data["flow_engines"]
    assert "nodus_engine" in data["flow_engines"]


def test_health_reports_async_job_capacity(client):
    response = client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert "async_jobs" in data
    assert data["async_jobs"]["execution_mode"] in {"thread", "distributed"}
    assert "queue_max" in data["async_jobs"]


def test_health_reports_cache_configuration(client):
    response = client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert "cache" in data
    assert "backend" in data["cache"]
    assert "redis_configured" in data["cache"]
    assert "requires_redis" in data["cache"]


def test_health_reports_stuck_run_configuration(client):
    response = client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert "stuck_run" in data
    assert "threshold_minutes" in data["stuck_run"]
    assert "wait_timeout_minutes" in data["stuck_run"]
    assert "margin_minutes" in data["stuck_run"]
