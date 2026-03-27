from __future__ import annotations


def test_async_heavy_execution_disabled_in_test_mode():
    from services.async_job_service import async_heavy_execution_enabled

    assert async_heavy_execution_enabled() is False


def test_test_user_uuid_identity(test_user, auth_headers):
    assert str(test_user.id) == "00000000-0000-0000-0000-000000000001"
    assert "Authorization" in auth_headers
