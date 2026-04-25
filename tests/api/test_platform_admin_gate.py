from __future__ import annotations


def test_platform_route_rejects_non_admin_jwt(client, non_admin_auth_headers):
    """Platform endpoints must return 403 for non-admin JWT holders."""
    response = client.get(
        "/platform/observability/scheduler/status",
        headers=non_admin_auth_headers,
    )
    assert response.status_code == 403, (
        f"Expected 403 for non-admin user on platform endpoint, got {response.status_code}"
    )
