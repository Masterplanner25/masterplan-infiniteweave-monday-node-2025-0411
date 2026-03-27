from __future__ import annotations

import pytest

from db.models.user import User
from tests.fixtures.auth import TEST_PASSWORD, TEST_USER_EMAIL, TEST_USER_ID, TEST_USERNAME
from services.auth_service import hash_password


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
