from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


def check_or_create(
    db: Session,
    model_class,
    idempotency_key: str,
    create_fn: Callable[[], ModelT],
) -> tuple[ModelT, bool]:
    """
    Reserve or return a record for the given idempotency key.

    Returns `(record, was_created)`. When a concurrent insert wins the race,
    the existing record is re-fetched and returned with `was_created=False`.
    """
    existing = (
        db.query(model_class)
        .filter(model_class.idempotency_key == idempotency_key)
        .with_for_update()
        .first()
    )
    if existing is not None:
        return existing, False

    record = create_fn()
    setattr(record, "idempotency_key", idempotency_key)
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(model_class)
            .filter(model_class.idempotency_key == idempotency_key)
            .first()
        )
        if existing is None:
            raise
        return existing, False

    db.refresh(record)
    return record, True


def claim_webhook_event(
    db: Session,
    stripe_event_id: str,
    event_type: str,
    *,
    payload: dict | None = None,
) -> bool:
    """
    Claim a Stripe webhook event for processing.

    Returns True when this process won the claim, False when another process
    already created the row for the same Stripe event id.
    """
    from apps.freelance.models.freelance import WebhookEvent

    event = WebhookEvent(
        stripe_event_id=str(stripe_event_id),
        event_type=event_type,
        idempotency_key=str(stripe_event_id),
        payload=payload,
        processing_status="processing",
        outcome="processing",
    )
    db.add(event)
    try:
        db.commit()
        db.refresh(event)
        return True
    except IntegrityError:
        db.rollback()
        return False


def mark_webhook_outcome(
    db: Session,
    stripe_event_id: str,
    outcome: str,
    *,
    error: str | None = None,
) -> None:
    from datetime import datetime, timezone

    from apps.freelance.models.freelance import WebhookEvent

    row = (
        db.query(WebhookEvent)
        .filter(WebhookEvent.stripe_event_id == str(stripe_event_id))
        .first()
    )
    if row is None:
        return
    row.outcome = outcome
    row.error = error
    if outcome == "fulfilled":
        row.processing_status = "processed"
    elif outcome == "skipped":
        row.processing_status = "ignored"
    elif outcome == "failed":
        row.processing_status = "failed"
    else:
        row.processing_status = outcome
    row.processed_at = datetime.now(timezone.utc)
    db.commit()
