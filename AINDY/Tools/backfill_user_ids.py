"""
Backfill user_id for legacy rows where ownership is missing.

Default behavior is dry-run. Use --apply to commit changes.
Optional: --assign-single-user to assign a single existing user to rows
that cannot be deterministically backfilled.
"""
from __future__ import annotations

import argparse
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from AINDY.db.database import SessionLocal
from AINDY.db.models import (
    AuthorDB,
    ClientFeedback,
    FreelanceOrder,
    LeadGenResult,
    ResearchResult,
    Task,
    User,
)


def _print(msg: str) -> None:
    print(msg)


def _get_single_user_id(db: Session):
    users = [row[0] for row in db.query(User.id).all()]
    if len(users) == 1:
        return users[0]
    return None


def _summarize(name: str, updated: int, skipped: int, total: int) -> None:
    _print(f"{name}: total_missing={total} updated={updated} skipped={skipped}")


def _backfill_client_feedback(db: Session, *, apply: bool) -> tuple[int, int, int]:
    rows = (
        db.query(ClientFeedback, FreelanceOrder.user_id)
        .join(FreelanceOrder, ClientFeedback.order_id == FreelanceOrder.id)
        .filter(ClientFeedback.user_id.is_(None))
        .filter(FreelanceOrder.user_id.is_not(None))
        .all()
    )
    updated = 0
    for feedback, order_user_id in rows:
        feedback.user_id = order_user_id
        updated += 1
    if apply:
        db.flush()
    return len(rows), updated, 0


def _backfill_simple(
    db: Session,
    model: Any,
    *,
    user_value: Any | None,
    apply: bool,
) -> tuple[int, int, int]:
    missing = db.query(model).filter(model.user_id.is_(None)).all()
    total = len(missing)
    if not total:
        return 0, 0, 0
    if user_value is None:
        return total, 0, total
    for row in missing:
        row.user_id = user_value
    if apply:
        db.flush()
    return total, total, 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill user_id columns safely.")
    parser.add_argument("--apply", action="store_true", help="Commit changes to DB.")
    parser.add_argument(
        "--assign-single-user",
        action="store_true",
        help="Assign the only user in the DB to rows that cannot be linked.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        single_user_id = _get_single_user_id(db) if args.assign_single_user else None
        if args.assign_single_user and single_user_id is None:
            _print("No single user found; --assign-single-user will not be applied.")

        _print("Backfill plan:")
        _print("- ClientFeedback.user_id <- FreelanceOrder.user_id (deterministic)")
        if args.assign_single_user:
            _print("- Remaining NULL user_id fields assigned to single user if exactly one exists")
        else:
            _print("- Remaining NULL user_id fields are reported but not modified")

        total_missing, updated, skipped = _backfill_client_feedback(db, apply=args.apply)
        _summarize("ClientFeedback", updated, skipped, total_missing)

        # String user_id columns
        fallback_str = str(single_user_id) if single_user_id else None
        total, updated, skipped = _backfill_simple(
            db,
            FreelanceOrder,
            user_value=fallback_str,
            apply=args.apply,
        )
        _summarize("FreelanceOrder", updated, skipped, total)

        total, updated, skipped = _backfill_simple(
            db,
            ResearchResult,
            user_value=fallback_str,
            apply=args.apply,
        )
        _summarize("ResearchResult", updated, skipped, total)

        # UUID user_id columns
        total, updated, skipped = _backfill_simple(
            db,
            Task,
            user_value=single_user_id,
            apply=args.apply,
        )
        _summarize("Task", updated, skipped, total)

        total, updated, skipped = _backfill_simple(
            db,
            LeadGenResult,
            user_value=single_user_id,
            apply=args.apply,
        )
        _summarize("LeadGenResult", updated, skipped, total)

        total, updated, skipped = _backfill_simple(
            db,
            AuthorDB,
            user_value=single_user_id,
            apply=args.apply,
        )
        _summarize("AuthorDB", updated, skipped, total)

        if args.apply:
            db.commit()
            _print("Backfill committed.")
        else:
            db.rollback()
            _print("Dry-run complete. Re-run with --apply to commit.")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
