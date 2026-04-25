from __future__ import annotations

import uuid

import pytest

from AINDY.db.models.user import User
from tests.fixtures.auth import TEST_PASSWORD, TEST_USER_EMAIL, TEST_USER_ID, TEST_USERNAME
from AINDY.services.auth_service import hash_password


def _get_or_create_user(
    session_factory,
    *,
    user_id,
    email: str,
    username: str,
    is_admin: bool = False,
) -> User:
    session = session_factory()
    try:
        user = session.get(User, user_id)
        if user is None:
            user = User(
                id=user_id,
                email=email,
                username=username,
                hashed_password=hash_password(TEST_PASSWORD),
                is_active=True,
                is_admin=is_admin,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        elif bool(getattr(user, "is_admin", False)) != bool(is_admin):
            user.is_admin = bool(is_admin)
            session.add(user)
            session.commit()
            session.refresh(user)
        session.expunge(user)
        return user
    finally:
        session.close()


@pytest.fixture
def test_user(testing_session_factory):
    return _get_or_create_user(
        testing_session_factory,
        user_id=TEST_USER_ID,
        email=TEST_USER_EMAIL,
        username=TEST_USERNAME,
        is_admin=True,
    )


@pytest.fixture
def non_admin_user(testing_session_factory):
    return _get_or_create_user(
        testing_session_factory,
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        email="non-admin@aindy.test",
        username="non_admin_user",
        is_admin=False,
    )


@pytest.fixture
def persisted_user(create_test_user):
    return create_test_user()


@pytest.fixture
def create_test_user(testing_session_factory):
    def _create(
        *,
        user_id: uuid.UUID | None = None,
        email: str | None = None,
        username: str | None = None,
        is_admin: bool = False,
    ) -> User:
        resolved_user_id = user_id or uuid.uuid4()
        resolved_email = email or f"{resolved_user_id.hex[:12]}@aindy.test"
        resolved_username = username or f"user_{resolved_user_id.hex[:12]}"
        return _get_or_create_user(
            testing_session_factory,
            user_id=resolved_user_id,
            email=resolved_email,
            username=resolved_username,
            is_admin=is_admin,
        )

    return _create
