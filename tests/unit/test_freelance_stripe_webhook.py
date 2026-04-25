from __future__ import annotations

import hashlib
import hmac
import json
import time
from unittest.mock import patch

from apps.freelance.models.freelance import FreelanceOrder


def _build_signature(payload: bytes, secret: str, timestamp: int) -> str:
    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    digest = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def _make_payment_order(db_session, test_user, **overrides) -> FreelanceOrder:
    order = FreelanceOrder(
        client_name="Acme Corp",
        client_email="client@example.com",
        service_type="copywriting",
        project_details="Landing page",
        price=250.0,
        status="delivered",
        delivery_type="payment",
        delivery_status="completed",
        payment_status="none",
        user_id=test_user.id,
        external_response={"payment_link_id": "plink_test"},
        **overrides,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order


def test_verify_stripe_signature_valid():
    from apps.freelance.services.freelance_service import verify_stripe_signature

    payload = b'{"type":"checkout.session.completed"}'
    secret = "whsec_test_secret"
    timestamp = int(time.time())
    header = _build_signature(payload, secret, timestamp)

    assert verify_stripe_signature(payload, header, secret) is True


def test_verify_stripe_signature_invalid():
    from apps.freelance.services.freelance_service import verify_stripe_signature

    payload = b'{"type":"checkout.session.completed"}'
    timestamp = int(time.time())
    header = _build_signature(payload, "whsec_right", timestamp)

    assert verify_stripe_signature(payload, header, "whsec_wrong") is False


def test_verify_stripe_signature_stale_timestamp():
    from apps.freelance.services.freelance_service import verify_stripe_signature

    payload = b'{"type":"checkout.session.completed"}'
    secret = "whsec_test_secret"
    timestamp = int(time.time()) - 301
    header = _build_signature(payload, secret, timestamp)

    assert verify_stripe_signature(payload, header, secret) is False


def test_verify_stripe_signature_malformed_header():
    from apps.freelance.services.freelance_service import verify_stripe_signature

    assert verify_stripe_signature(b"{}", "not-a-valid-sig-header", "whsec_test") is False


def test_process_webhook_checkout_completed_confirms_order(db_session, test_user):
    from apps.freelance.services.freelance_service import process_stripe_webhook

    order = _make_payment_order(db_session, test_user, stripe_payment_link_id="plink_test")

    with patch("apps.freelance.services.freelance_service.queue_system_event", return_value="evt-1"):
        result = process_stripe_webhook(
            db_session,
            "checkout.session.completed",
            {"object": {"payment_link": "plink_test", "payment_intent": "pi_test"}},
        )

    db_session.refresh(order)
    assert result == {"processed": True, "action": "payment_confirmed"}
    assert order.payment_status == "confirmed"
    assert order.status == "payment_confirmed"
    assert order.stripe_payment_intent_id == "pi_test"
    assert order.payment_confirmed_at is not None


def test_process_webhook_unknown_event_returns_not_processed(db_session):
    from apps.freelance.services.freelance_service import process_stripe_webhook

    result = process_stripe_webhook(db_session, "unknown.event", {"object": {}})

    assert result["processed"] is False


def test_process_webhook_idempotent(db_session, test_user):
    from apps.freelance.services.freelance_service import process_stripe_webhook

    order = _make_payment_order(db_session, test_user, stripe_payment_link_id="plink_test")

    with patch("apps.freelance.services.freelance_service.queue_system_event", return_value="evt-1") as mock_queue:
        first = process_stripe_webhook(
            db_session,
            "checkout.session.completed",
            {"object": {"payment_link": "plink_test", "payment_intent": "pi_test"}},
        )
        second = process_stripe_webhook(
            db_session,
            "payment_intent.succeeded",
            {"object": {"id": "pi_test"}},
        )

    db_session.refresh(order)
    assert first == {"processed": True, "action": "payment_confirmed"}
    assert second == {"processed": True, "action": "payment_confirmed"}
    assert order.payment_status == "confirmed"
    assert order.status == "payment_confirmed"
    assert mock_queue.call_count == 1


def test_stripe_webhook_route_rejects_missing_signature(client, monkeypatch):
    from AINDY.config import settings

    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test_secret")

    response = client.post(
        "/freelance/webhook/stripe",
        json={"type": "checkout.session.completed", "data": {"object": {}}},
    )

    assert response.status_code == 400
    assert "stripe-signature header missing" in response.text


def test_stripe_webhook_route_skips_verification_when_no_secret(client, monkeypatch):
    from AINDY.config import settings

    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", None)

    response = client.post(
        "/freelance/webhook/stripe",
        data=json.dumps({"type": "unknown.event", "data": {"object": {}}}),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json() == {"received": True, "processed": False}


def test_stripe_webhook_route_not_in_openapi_schema(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/freelance/webhook/stripe" not in (response.json().get("paths") or {})
