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
