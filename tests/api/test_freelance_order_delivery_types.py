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
    headers = {**auth_headers, "Idempotency-Key": "order-manual-1"}
    response = client.post(
        "/freelance/order",
        json=_payload(delivery_type="manual"),
        headers=headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["delivery_type"] == "manual"
    assert payload["delivery_status"] == "pending"
    assert payload["execution_envelope"]["eu_id"] is not None


def test_freelance_order_create_payment_succeeds(client, auth_headers):
    headers = {**auth_headers, "Idempotency-Key": "order-payment-1"}
    response = client.post(
        "/freelance/order",
        json=_payload(delivery_type="payment"),
        headers=headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["delivery_type"] == "payment"
    assert payload["delivery_status"] == "pending"
    assert payload["execution_envelope"]["eu_id"] is not None


def test_freelance_order_create_stripe_returns_422(client, auth_headers):
    headers = {**auth_headers, "Idempotency-Key": "order-invalid-1"}
    response = client.post(
        "/freelance/order",
        json=_payload(delivery_type="stripe"),
        headers=headers,
    )

    assert response.status_code == 422
    body = response.json()
    assert "delivery_type 'stripe' is not supported" in (body.get("detail") or body.get("message") or "")
