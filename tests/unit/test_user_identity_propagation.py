from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

import AINDY.main as main_module
from AINDY.db.models.job_log import JobLog
from AINDY.services.auth_service import create_access_token
from AINDY.services.auth_service import get_current_user


def test_get_current_user_rejects_invalid_token_in_test_mode():
    with pytest.raises(Exception) as exc_info:
        get_current_user(
            credentials=type("Creds", (), {"credentials": "not-a-token"})(),
            platform_key=None,
            db=None,
        )

    assert getattr(exc_info.value, "status_code", None) == 401


def test_get_current_user_rejects_valid_token_for_missing_user(db_session):
    missing_user_id = uuid.uuid4()
    token = create_access_token({"sub": str(missing_user_id), "email": "missing@aindy.test"})

    with pytest.raises(Exception) as exc_info:
        get_current_user(
            credentials=type("Creds", (), {"credentials": token})(),
            platform_key=None,
            db=db_session,
        )

    assert getattr(exc_info.value, "status_code", None) == 401


def test_async_root_execution_event_uses_job_user_id(db_session, monkeypatch):
    import AINDY.platform_layer.async_job_service as async_job_service

    user_id = uuid.uuid4()
    log_id = str(uuid.uuid4())
    db_session.add(
        JobLog(
            id=log_id,
            source="unit",
            task_name="unit.job",
            payload={},
            status="pending",
            max_attempts=1,
            user_id=user_id,
            trace_id=log_id,
        )
    )
    db_session.commit()

    captured: dict[str, object] = {}

    def _fake_emit(**kwargs):
        captured.update(kwargs)
        return uuid.uuid4()

    monkeypatch.setattr(async_job_service, "_emit_async_system_event", _fake_emit)

    root_event_id = async_job_service._ensure_root_execution_event_id(db_session, log_id)

    assert root_event_id is not None
    assert captured["event_type"] == "execution.started"
    assert captured["trace_id"] == log_id
    assert captured["user_id"] == user_id


def test_request_user_extraction_prefers_authenticated_request_state():
    authenticated_user_id = uuid.uuid4()
    token_user_id = uuid.uuid4()
    request = SimpleNamespace(
        state=SimpleNamespace(user_id=str(authenticated_user_id)),
        headers={
            "Authorization": f"Bearer {create_access_token({'sub': str(token_user_id), 'email': 'token@aindy.test'})}"
        },
    )

    extracted = main_module._extract_user_id_from_request(request)

    assert extracted == authenticated_user_id
