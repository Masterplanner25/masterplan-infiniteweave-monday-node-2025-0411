from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from apps.freelance.models.freelance import FreelanceOrder


def _make_subscription_order(
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
        project_details="Monthly retainer",
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


def test_subscription_delivery_type_accepted():
    from apps.freelance.services.freelance_service import _SUPPORTED_DELIVERY_TYPES

    assert "subscription" in _SUPPORTED_DELIVERY_TYPES


def test_execute_stripe_subscription_raises_on_missing_key():
    from apps.automation.services.automation_execution_service import _execute_stripe_subscription

    with pytest.raises(ValueError) as exc_info:
        _execute_stripe_subscription({"automation_config": {}}, {"customer_email": "client@example.com"})

    assert "stripe_secret_key not configured" in str(exc_info.value)


def test_execute_stripe_subscription_raises_on_invalid_interval():
    from apps.automation.services.automation_execution_service import _execute_stripe_subscription

    with pytest.raises(ValueError) as exc_info:
        _execute_stripe_subscription(
            {"task_name": "retainer"},
            {
                "stripe_secret_key": "sk_test_fake",
                "customer_email": "client@example.com",
                "amount": 5000,
                "interval": "biweekly",
            },
        )

    assert "Invalid billing interval" in str(exc_info.value)


def test_execute_stripe_subscription_raises_on_missing_customer_email():
    from apps.automation.services.automation_execution_service import _execute_stripe_subscription

    with pytest.raises(ValueError) as exc_info:
        _execute_stripe_subscription(
            {"task_name": "retainer"},
            {"stripe_secret_key": "sk_test_fake", "amount": 5000},
        )

    assert "customer_email required" in str(exc_info.value)


def test_execute_stripe_subscription_calls_stripe_create_customer():
    from apps.automation.services import automation_execution_service as svc

    call_log: list[str] = []

    def fake_urlopen(req, timeout=None):
        path = req.full_url
        call_log.append(path)
        resp = MagicMock()
        if "/v1/customers" in path:
            resp.read.return_value = json.dumps({"id": "cus_test"}).encode()
        elif "/v1/products" in path:
            resp.read.return_value = json.dumps({"id": "prod_test"}).encode()
        elif "/v1/prices" in path:
            resp.read.return_value = json.dumps({"id": "price_test"}).encode()
        elif "/v1/subscriptions" in path:
            resp.read.return_value = json.dumps(
                {
                    "id": "sub_test",
                    "status": "incomplete",
                    "current_period_end": 1760000000,
                }
            ).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    with patch.object(svc.urllib_request, "urlopen", side_effect=fake_urlopen):
        result = svc._execute_stripe_subscription(
            {"task_name": "retainer", "user_id": "user-1"},
            {
                "stripe_secret_key": "sk_test_fake",
                "customer_email": "client@example.com",
                "amount": 5000,
                "interval": "month",
                "metadata": {"order_id": 42},
            },
        )

    assert result["automation_type"] == "subscription"
    assert result["subscription_id"] == "sub_test"
    assert any("/v1/customers" in c for c in call_log)
    assert any("/v1/prices" in c for c in call_log)
    assert any("/v1/subscriptions" in c for c in call_log)


def test_webhook_subscription_cancelled_transitions_order(db_session, test_user):
    from apps.freelance.services.freelance_service import process_stripe_webhook

    order = _make_subscription_order(db_session, test_user)
    with patch("apps.freelance.services.freelance_service.queue_system_event", return_value="evt-1"):
        result = process_stripe_webhook(
            db_session,
            "customer.subscription.deleted",
            {"object": {"id": "sub_test"}},
        )

    db_session.refresh(order)
    assert result == {"processed": True, "action": "subscription_cancelled"}
    assert order.subscription_status == "cancelled"
    assert order.status == "subscription_cancelled"


def test_webhook_invoice_payment_succeeded_renews_order(db_session, test_user):
    from apps.freelance.services.freelance_service import process_stripe_webhook

    order = _make_subscription_order(db_session, test_user, subscription_status="incomplete")
    with patch("apps.freelance.services.freelance_service.queue_system_event", return_value="evt-1"):
        result = process_stripe_webhook(
            db_session,
            "invoice.payment_succeeded",
            {"object": {"subscription": "sub_test", "lines": {"data": [{"period": {"end": 1760000000}}]}}},
        )

    db_session.refresh(order)
    assert result == {"processed": True, "action": "subscription_renewed"}
    assert order.subscription_status == "active"
    assert int(order.subscription_period_end.replace(tzinfo=timezone.utc).timestamp()) == 1760000000


def test_webhook_invoice_payment_failed_marks_past_due(db_session, test_user):
    from apps.freelance.services.freelance_service import process_stripe_webhook

    order = _make_subscription_order(db_session, test_user, subscription_status="active")
    with patch("apps.freelance.services.freelance_service.queue_system_event", return_value="evt-1"):
        result = process_stripe_webhook(
            db_session,
            "invoice.payment_failed",
            {"object": {"subscription": "sub_test"}},
        )

    db_session.refresh(order)
    assert result == {"processed": True, "action": "subscription_payment_failed"}
    assert order.subscription_status == "past_due"


def test_cancel_subscription_raises_on_non_subscription_order(db_session, test_user):
    from apps.freelance.services.freelance_service import cancel_subscription

    order = _make_subscription_order(db_session, test_user, delivery_type="manual")

    with pytest.raises(ValueError) as exc_info:
        cancel_subscription(db_session, order.id, user_id=str(test_user.id))

    assert "not 'subscription'" in str(exc_info.value)


def test_cancel_subscription_raises_on_already_cancelled(db_session, test_user):
    from apps.freelance.services.freelance_service import cancel_subscription

    order = _make_subscription_order(db_session, test_user, subscription_status="cancelled")

    with pytest.raises(ValueError) as exc_info:
        cancel_subscription(db_session, order.id, user_id=str(test_user.id))

    assert "already cancelled" in str(exc_info.value)


def test_cancel_subscription_calls_stripe_delete(db_session, test_user, monkeypatch):
    from AINDY.config import settings
    from apps.freelance.services.freelance_service import cancel_subscription

    order = _make_subscription_order(db_session, test_user)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")

    with patch(
        "apps.freelance.services.freelance_service._stripe_api_delete",
        return_value={"status": "canceled"},
    ) as mock_delete, patch(
        "apps.freelance.services.freelance_service.queue_system_event",
        return_value="evt-1",
    ):
        cancelled = cancel_subscription(
            db_session,
            order.id,
            user_id=str(test_user.id),
            reason="Customer asked to cancel",
        )

    db_session.refresh(order)
    assert cancelled.id == order.id
    assert order.subscription_status == "cancelled"
    assert order.status == "subscription_cancelled"
    mock_delete.assert_called_once_with(
        "/v1/subscriptions/sub_test",
        stripe_key="sk_test_fake",
    )
