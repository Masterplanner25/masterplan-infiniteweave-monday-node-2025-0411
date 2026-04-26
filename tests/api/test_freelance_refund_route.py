from __future__ import annotations

from apps.freelance.models.freelance import FreelanceOrder


def _seed_order(
    db_session,
    test_user,
    *,
    delivery_type: str,
    payment_status: str,
    stripe_payment_intent_id: str | None = None,
) -> FreelanceOrder:
    order = FreelanceOrder(
        client_name="Acme Corp",
        client_email="client@example.com",
        service_type="copywriting",
        project_details="Landing page copy",
        price=250.0,
        status="payment_confirmed" if payment_status == "confirmed" else "pending",
        delivery_type=delivery_type,
        delivery_status="completed" if payment_status == "confirmed" else "pending",
        payment_status=payment_status,
        stripe_payment_intent_id=stripe_payment_intent_id,
        user_id=test_user.id,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order


def test_refund_route_returns_422_for_manual_order(client, auth_headers, db_session, test_user):
    order = _seed_order(db_session, test_user, delivery_type="manual", payment_status="confirmed", stripe_payment_intent_id="pi_test")

    response = client.post(
        f"/freelance/refund/{order.id}",
        json={},
        headers={**auth_headers, "Idempotency-Key": "refund-manual-1"},
    )

    assert response.status_code == 422
    assert "not 'payment'" in response.text


def test_refund_route_returns_422_for_unconfirmed_payment(client, auth_headers, db_session, test_user):
    order = _seed_order(db_session, test_user, delivery_type="payment", payment_status="none")

    response = client.post(
        f"/freelance/refund/{order.id}",
        json={},
        headers={**auth_headers, "Idempotency-Key": "refund-unconfirmed-1"},
    )

    assert response.status_code == 422
    assert "Refunds can only be issued for confirmed payments" in response.text


def test_refund_route_returns_401_without_auth(client):
    response = client.post("/freelance/refund/1", json={})

    assert response.status_code == 401
