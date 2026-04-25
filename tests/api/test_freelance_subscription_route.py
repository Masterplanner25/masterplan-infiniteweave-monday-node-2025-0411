from __future__ import annotations

from apps.freelance.models.freelance import FreelanceOrder


def _payload() -> dict:
    return {
        "client_name": "Acme Corp",
        "client_email": "client@example.com",
        "service_type": "retainer",
        "project_details": "Monthly strategy retainer",
        "price": 250.0,
        "delivery_type": "subscription",
        "auto_generate_delivery": False,
    }


def _seed_order(
    db_session,
    test_user,
    *,
    delivery_type: str = "subscription",
    subscription_status: str = "active",
    stripe_subscription_id: str | None = "sub_test",
) -> FreelanceOrder:
    order = FreelanceOrder(
        client_name="Acme Corp",
        client_email="client@example.com",
        service_type="retainer",
        project_details="Monthly strategy retainer",
        price=250.0,
        status="delivered",
        delivery_type=delivery_type,
        delivery_status="completed",
        payment_status="confirmed",
        subscription_status=subscription_status,
        stripe_subscription_id=stripe_subscription_id,
        user_id=test_user.id,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order


def test_freelance_order_create_subscription_succeeds(client, auth_headers):
    response = client.post("/freelance/order", json=_payload(), headers=auth_headers)

    assert response.status_code == 201
    payload = response.json()
    assert payload["delivery_type"] == "subscription"
    assert payload["execution_envelope"]["eu_id"] is not None


def test_cancel_subscription_route_returns_422_for_manual_order(client, auth_headers, db_session, test_user):
    order = _seed_order(db_session, test_user, delivery_type="manual")

    response = client.post(f"/freelance/subscription/{order.id}/cancel", json={}, headers=auth_headers)

    assert response.status_code == 422
    assert "not 'subscription'" in response.text


def test_cancel_subscription_route_returns_401_without_auth(client):
    response = client.post("/freelance/subscription/1/cancel", json={})

    assert response.status_code == 401
