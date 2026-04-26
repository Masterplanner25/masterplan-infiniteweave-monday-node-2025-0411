from __future__ import annotations

import threading
import uuid
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from AINDY.db.database import Base
from AINDY.db.models.user import User
from apps.freelance.models.freelance import FreelanceOrder, PaymentRecord, RefundRecord, WebhookEvent
from apps.freelance.schemas.freelance import FreelanceOrderCreate


def _order_payload(*, delivery_type: str = "manual") -> dict:
    return {
        "client_name": "Acme Corp",
        "client_email": "client@example.com",
        "service_type": "copywriting",
        "project_details": "Landing page copy",
        "price": 250.0,
        "delivery_type": delivery_type,
        "auto_generate_delivery": False,
    }


def _build_session_factory(tmp_path):
    import AINDY.db.model_registry  # noqa: F401
    import AINDY.memory.memory_persistence  # noqa: F401
    import apps.bootstrap

    apps.bootstrap.bootstrap_models()
    engine = create_engine(
        f"sqlite:///{tmp_path / 'freelance_idempotency.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=engine,
    )


def _seed_user(session_factory) -> str:
    user_id = uuid.uuid4()
    session = session_factory()
    try:
        session.add(
            User(
                id=user_id,
                email=f"{user_id}@example.com",
                hashed_password="test",
                is_active=True,
            )
        )
        session.commit()
    finally:
        session.close()
    return str(user_id)


def _seed_payment_order(db_session, test_user) -> FreelanceOrder:
    order = FreelanceOrder(
        client_name="Acme Corp",
        client_email="client@example.com",
        service_type="copywriting",
        project_details="Landing page copy",
        price=250.0,
        status="delivered",
        delivery_type="payment",
        delivery_status="completed",
        payment_status="none",
        stripe_payment_link_id="plink_test",
        user_id=test_user.id,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order


def _seed_refund_order(db_session, test_user) -> FreelanceOrder:
    order = FreelanceOrder(
        client_name="Acme Corp",
        client_email="client@example.com",
        service_type="copywriting",
        project_details="Landing page copy",
        price=250.0,
        status="payment_confirmed",
        delivery_type="payment",
        delivery_status="completed",
        payment_status="confirmed",
        stripe_payment_intent_id="pi_refund_test",
        user_id=test_user.id,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order


def test_create_order_idempotency_replays_existing_record(db_session, test_user):
    from apps.freelance.services.freelance_service import create_order

    payload = FreelanceOrderCreate(**_order_payload())

    first, first_created = create_order(
        db_session,
        payload,
        user_id=str(test_user.id),
        idempotency_key="order-key-1",
        return_created=True,
    )
    second, second_created = create_order(
        db_session,
        payload,
        user_id=str(test_user.id),
        idempotency_key="order-key-1",
        return_created=True,
    )

    assert first_created is True
    assert second_created is False
    assert first.id == second.id
    assert (
        db_session.query(FreelanceOrder)
        .filter(FreelanceOrder.idempotency_key == "order-key-1")
        .count()
        == 1
    )


def test_record_payment_idempotency_replays_existing_record(db_session, test_user):
    from apps.freelance.services.freelance_service import record_payment

    order = _seed_payment_order(db_session, test_user)

    with patch("apps.freelance.services.freelance_service.queue_system_event", return_value="evt-1") as mock_queue:
        first, first_created = record_payment(
            db_session,
            payment_intent_id="pi_test",
            payment_link_id="plink_test",
            idempotency_key="payment-key-1",
            return_created=True,
        )
        second, second_created = record_payment(
            db_session,
            payment_intent_id="pi_test",
            payment_link_id="plink_test",
            idempotency_key="payment-key-1",
            return_created=True,
        )

    db_session.refresh(order)
    assert first.id == second.id == order.id
    assert first_created is True
    assert second_created is False
    assert order.payment_status == "confirmed"
    assert db_session.query(PaymentRecord).filter(PaymentRecord.idempotency_key == "payment-key-1").count() == 1
    assert mock_queue.call_count == 1


def test_issue_refund_idempotency_replays_existing_record(db_session, test_user, monkeypatch):
    from AINDY.config import settings
    from apps.freelance.services.freelance_service import issue_refund

    order = _seed_refund_order(db_session, test_user)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")

    with patch(
        "apps.freelance.services.freelance_service._stripe_api_post",
        return_value={"id": "re_test"},
    ) as mock_post, patch(
        "apps.freelance.services.freelance_service.queue_system_event",
        return_value="evt-1",
    ):
        first, first_created = issue_refund(
            db_session,
            order.id,
            user_id=str(test_user.id),
            reason="Customer asked for refund",
            idempotency_key="refund-key-1",
            return_created=True,
        )
        second, second_created = issue_refund(
            db_session,
            order.id,
            user_id=str(test_user.id),
            reason="Customer asked for refund",
            idempotency_key="refund-key-1",
            return_created=True,
        )

    db_session.refresh(order)
    assert first.id == second.id == order.id
    assert first_created is True
    assert second_created is False
    assert order.payment_status == "refunded"
    assert db_session.query(RefundRecord).filter(RefundRecord.idempotency_key == "refund-key-1").count() == 1
    assert mock_post.call_count == 1


def test_concurrent_order_create_same_key_creates_single_record(tmp_path):
    from apps.freelance.services.freelance_service import create_order

    engine, session_factory = _build_session_factory(tmp_path)
    user_id = _seed_user(session_factory)
    payload = FreelanceOrderCreate(**_order_payload())
    barrier = threading.Barrier(2)
    results: list[tuple[int, bool]] = []

    def _worker():
        session = session_factory()
        try:
            barrier.wait()
            order, created = create_order(
                session,
                payload,
                user_id=user_id,
                idempotency_key="concurrent-order-key",
                return_created=True,
            )
            results.append((order.id, created))
        finally:
            session.close()

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    verification = session_factory()
    try:
        count = (
            verification.query(FreelanceOrder)
            .filter(FreelanceOrder.idempotency_key == "concurrent-order-key")
            .count()
        )
    finally:
        verification.close()
        engine.dispose()

    assert len(results) == 2
    assert len({order_id for order_id, _ in results}) == 1
    assert sum(1 for _, created in results if created) == 1
    assert count == 1


def test_order_route_requires_idempotency_key_header(client, auth_headers):
    response = client.post(
        "/freelance/order",
        json=_order_payload(),
        headers=auth_headers,
    )

    assert response.status_code == 400
    detail = response.json().get("detail") or response.json().get("message") or response.text
    assert "Idempotency-Key header is required" in detail


def test_order_route_returns_201_then_200_for_same_idempotency_key(client, auth_headers):
    headers = {**auth_headers, "Idempotency-Key": "route-order-key-1"}

    first = client.post("/freelance/order", json=_order_payload(), headers=headers)
    second = client.post("/freelance/order", json=_order_payload(), headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_refund_route_requires_idempotency_key_header(client, auth_headers, db_session, test_user):
    order = _seed_refund_order(db_session, test_user)

    response = client.post(
        f"/freelance/refund/{order.id}",
        json={},
        headers=auth_headers,
    )

    assert response.status_code == 400
    detail = response.json().get("detail") or response.json().get("message") or response.text
    assert "Idempotency-Key header is required" in detail


def test_webhook_event_id_processed_once(db_session, test_user):
    from apps.freelance.services.freelance_service import process_stripe_webhook

    _seed_payment_order(db_session, test_user)

    with patch("apps.freelance.services.freelance_service.record_payment", return_value=None) as mock_record:
        first = process_stripe_webhook(
            db_session,
            "checkout.session.completed",
            {"object": {"payment_link": "plink_test", "payment_intent": "pi_test"}},
            event_id="evt_123",
        )
        second = process_stripe_webhook(
            db_session,
            "checkout.session.completed",
            {"object": {"payment_link": "plink_test", "payment_intent": "pi_test"}},
            event_id="evt_123",
        )

    assert first == {"processed": True, "action": "payment_confirmed"}
    assert second == {"processed": False, "status": "already_processed"}
    assert mock_record.call_count == 1
    assert db_session.query(WebhookEvent).filter(WebhookEvent.idempotency_key == "evt_123").count() == 1
