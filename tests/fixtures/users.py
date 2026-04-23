from __future__ import annotations

import uuid

import pytest

from AINDY.db.models.user import User
from tests.fixtures.auth import TEST_PASSWORD, TEST_USER_EMAIL, TEST_USER_ID, TEST_USERNAME
from AINDY.services.auth_service import hash_password


@pytest.fixture
def test_user(db_session):
    user = db_session.get(User, TEST_USER_ID)
    if user is None:
        user = User(
            id=TEST_USER_ID,
            email=TEST_USER_EMAIL,
            username=TEST_USERNAME,
            hashed_password=hash_password(TEST_PASSWORD),
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    return user


@pytest.fixture
def persisted_user(create_test_user):
    return create_test_user()


@pytest.fixture
def create_test_user(db_session):
    def _create(*, user_id: uuid.UUID | None = None, email: str | None = None, username: str | None = None) -> User:
        resolved_user_id = user_id or uuid.uuid4()
        resolved_email = email or f"{resolved_user_id.hex[:12]}@aindy.test"
        resolved_username = username or f"user_{resolved_user_id.hex[:12]}"
        user = db_session.get(User, resolved_user_id)
        if user is None:
            user = User(
                id=resolved_user_id,
                email=resolved_email,
                username=resolved_username,
                hashed_password=hash_password(TEST_PASSWORD),
                is_active=True,
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
        return user

    return _create
