from __future__ import annotations


def _payload(*, delivery_type: str) -> dict:
    return {
        "client_name": "Acme Corp",
        "client_email": "client@example.com",
        "service_type": "copywriting",
        "project_details": "Landing page copy",
        "price": 250.0,
        "delivery_type": delivery_type,
        "auto_generate_delivery": False,
    }


def test_freelance_order_create_manual_succeeds(client, auth_headers):
    response = client.post(
        "/freelance/order",
        json=_payload(delivery_type="manual"),
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["delivery_type"] == "manual"
    assert payload["delivery_status"] == "pending"
    assert payload["execution_envelope"]["eu_id"] is not None


def test_freelance_order_create_payment_returns_422(client, auth_headers):
    response = client.post(
        "/freelance/order",
        json=_payload(delivery_type="payment"),
        headers=auth_headers,
    )

    assert response.status_code == 422
    body = response.json()
    assert "delivery_type 'payment' is not supported" in (body.get("detail") or body.get("message") or "")


def test_freelance_order_create_stripe_returns_422(client, auth_headers):
    response = client.post(
        "/freelance/order",
        json=_payload(delivery_type="stripe"),
        headers=auth_headers,
    )

    assert response.status_code == 422
    body = response.json()
    assert "delivery_type 'stripe' is not supported" in (body.get("detail") or body.get("message") or "")
