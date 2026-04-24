from unittest.mock import patch


def test_client_error_endpoint_returns_204(client):
    with patch("AINDY.routes.health_router.queue_system_event") as mock_event:
        resp = client.post("/client/error", json={
            "error_message": "ReferenceError: foo is not defined",
            "error_type": "boundary",
            "route": "/dashboard",
        })

    assert resp.status_code == 204
    mock_event.assert_called_once()


def test_client_vitals_endpoint_returns_204(client):
    with patch("AINDY.routes.health_router.queue_system_event") as mock_event:
        resp = client.post("/client/vitals", json={
            "lcp_ms": 1200,
            "cls_score": 0.05,
            "inp_ms": 80,
            "route": "/analytics",
        })

    assert resp.status_code == 204
    mock_event.assert_called_once()


def test_client_error_does_not_expose_server_internals(client):
    with patch(
        "AINDY.routes.health_router.queue_system_event",
        side_effect=Exception("DB is down"),
    ):
        resp = client.post("/client/error", json={"error_message": "test"})

    assert resp.status_code == 204
