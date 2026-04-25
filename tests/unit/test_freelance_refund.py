from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.freelance.events import FreelanceEventTypes
from apps.freelance.models.freelance import FreelanceOrder


def _make_order(
    db_session,
    test_user,
    *,
    delivery_type: str = "payment",
    payment_status: str = "confirmed",
    stripe_payment_intent_id: str | None = "pi_test",
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


def test_issue_refund_raises_on_wrong_delivery_type(db_session, test_user):
    from apps.freelance.services.freelance_service import issue_refund

    order = _make_order(db_session, test_user, delivery_type="manual")

    with pytest.raises(ValueError) as exc_info:
        issue_refund(db_session, order.id, user_id=str(test_user.id))

    assert "not 'payment'" in str(exc_info.value)


def test_issue_refund_raises_on_already_refunded(db_session, test_user):
    from apps.freelance.services.freelance_service import issue_refund

    order = _make_order(db_session, test_user, payment_status="refunded")

    with pytest.raises(ValueError) as exc_info:
        issue_refund(db_session, order.id, user_id=str(test_user.id))

    assert "already been refunded" in str(exc_info.value)


def test_issue_refund_raises_on_unconfirmed_payment(db_session, test_user):
    from apps.freelance.services.freelance_service import issue_refund

    order = _make_order(db_session, test_user, payment_status="none")

    with pytest.raises(ValueError) as exc_info:
        issue_refund(db_session, order.id, user_id=str(test_user.id))

    assert "Refunds can only be issued for confirmed payments" in str(exc_info.value)


def test_issue_refund_raises_on_missing_payment_intent(db_session, test_user):
    from apps.freelance.services.freelance_service import issue_refund

    order = _make_order(db_session, test_user, stripe_payment_intent_id=None)

    with pytest.raises(ValueError) as exc_info:
        issue_refund(db_session, order.id, user_id=str(test_user.id))

    assert "no stripe_payment_intent_id" in str(exc_info.value)


def test_issue_refund_raises_on_missing_stripe_key(db_session, test_user, monkeypatch):
    from AINDY.config import settings
    from apps.freelance.services.freelance_service import issue_refund

    order = _make_order(db_session, test_user)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", None)

    with pytest.raises(RuntimeError) as exc_info:
        issue_refund(db_session, order.id, user_id=str(test_user.id))

    assert "STRIPE_SECRET_KEY" in str(exc_info.value)


def test_issue_refund_calls_stripe_and_updates_order(db_session, test_user, monkeypatch):
    from AINDY.config import settings
    from apps.freelance.services.freelance_service import issue_refund

    order = _make_order(db_session, test_user)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")

    with patch(
        "apps.freelance.services.freelance_service._stripe_api_post",
        return_value={"id": "re_test"},
    ) as mock_post, patch(
        "apps.freelance.services.freelance_service.queue_system_event",
        return_value="evt-1",
    ):
        refunded = issue_refund(
            db_session,
            order.id,
            user_id=str(test_user.id),
            reason="Customer asked for refund",
        )

    db_session.refresh(order)
    assert refunded.id == order.id
    assert order.refund_id == "re_test"
    assert order.payment_status == "refunded"
    assert order.status == "refunded"
    assert order.refunded_at is not None
    mock_post.assert_called_once_with(
        "/v1/refunds",
        {
            "payment_intent": "pi_test",
            "reason": "requested_by_customer",
            "metadata[reason_text]": "Customer asked for refund",
        },
        stripe_key="sk_test_fake",
    )


def test_issue_refund_emits_failure_event_on_stripe_error(db_session, test_user, monkeypatch):
    from AINDY.config import settings
    from apps.freelance.services.freelance_service import issue_refund

    order = _make_order(db_session, test_user)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")

    with patch(
        "apps.freelance.services.freelance_service._stripe_api_post",
        side_effect=RuntimeError("stripe down"),
    ), patch(
        "apps.freelance.services.freelance_service.queue_system_event",
        return_value="evt-1",
    ) as mock_event:
        with pytest.raises(RuntimeError) as exc_info:
            issue_refund(db_session, order.id, user_id=str(test_user.id))

    assert "Stripe refund failed" in str(exc_info.value)
    assert mock_event.call_args.kwargs["event_type"] == FreelanceEventTypes.FREELANCE_REFUND_FAILED
