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
