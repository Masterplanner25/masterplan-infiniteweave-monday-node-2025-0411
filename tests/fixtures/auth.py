from __future__ import annotations

import os
import uuid

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MONGO_URL", "")
os.environ.setdefault("AINDY_ALLOW_SQLITE", "1")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key-for-testing-only")
os.environ.setdefault("DEEPSEEK_API_KEY", "fake-deepseek-key")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("TEST_MODE", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-not-production")
os.environ.setdefault("AINDY_API_KEY", "test-api-key-for-pytest-only")
os.environ.setdefault("PERMISSION_SECRET", "test-permission-secret-for-pytest-only")
os.environ.setdefault("SKIP_MONGO_PING", "1")
os.environ.setdefault("AINDY_SKIP_MONGO_PING", "1")

from AINDY.services.auth_service import create_access_token, hash_password


TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_EMAIL = "test@aindy.test"
TEST_USERNAME = "test_user"
TEST_PASSWORD = "Passw0rd!123"


def build_access_token(
    *,
    user_id: uuid.UUID = TEST_USER_ID,
    email: str = TEST_USER_EMAIL,
    is_admin: bool = False,
) -> str:
    return create_access_token(
        {
            "sub": str(user_id),
            "email": email,
            "is_admin": is_admin,
        }
    )


@pytest.fixture
def auth_headers(test_user):
    return {
        "Authorization": (
            "Bearer "
            f"{build_access_token(user_id=test_user.id, email=test_user.email, is_admin=bool(getattr(test_user, 'is_admin', False)))}"
        )
    }


@pytest.fixture
def non_admin_auth_headers(non_admin_user):
    return {
        "Authorization": (
            "Bearer "
            f"{build_access_token(user_id=non_admin_user.id, email=non_admin_user.email, is_admin=False)}"
        )
    }


@pytest.fixture
def api_key_headers():
    return {"X-API-Key": "test-api-key-for-pytest-only"}
