from __future__ import annotations

import uuid

import pytest

from AINDY.services.auth_service import create_access_token, hash_password


TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_EMAIL = "test@aindy.test"
TEST_USERNAME = "test_user"
TEST_PASSWORD = "Passw0rd!123"


def build_access_token(
    *,
    user_id: uuid.UUID = TEST_USER_ID,
    email: str = TEST_USER_EMAIL,
) -> str:
    return create_access_token(
        {
            "sub": str(user_id),
            "email": email,
        }
    )


@pytest.fixture
def auth_headers(test_user):
    return {"Authorization": f"Bearer {build_access_token(user_id=test_user.id, email=test_user.email)}"}


@pytest.fixture
def api_key_headers():
    return {"X-API-Key": "test-api-key-for-pytest-only"}
