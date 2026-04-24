from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt

from AINDY.db.models.user import User
from AINDY.services.auth_service import ALGORITHM, SECRET_KEY, hash_password


def _create_user(db_session, *, email: str, password: str = "Passw0rd!123", is_admin: bool = False) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        username=email.split("@", 1)[0],
        hashed_password=hash_password(password),
        is_active=True,
        is_admin=is_admin,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _extract_access_token(response) -> str:
    payload = response.json()
    data = payload.get("data", payload)
    return data["access_token"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client, *, email: str, password: str = "Passw0rd!123") -> str:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return _extract_access_token(response)


def test_token_without_tv_claim_is_accepted(client, db_session, monkeypatch):
    user = _create_user(db_session, email="legacy-token@aindy.test")
    monkeypatch.setattr("apps.tasks.services.task_service.list_tasks", lambda db, user_id: [])
    token = jwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    response = client.get("/tasks/list", headers=_bearer(token))

    assert response.status_code == 200, response.text


def test_logout_invalidates_current_token(client):
    email = "logout-user@aindy.test"
    password = "Passw0rd!123"

    register_response = client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    assert register_response.status_code == 201, register_response.text
    token_a = _extract_access_token(register_response)

    logout_response = client.post("/auth/logout", headers=_bearer(token_a))
    assert logout_response.status_code == 200, logout_response.text
    assert logout_response.json()["status"] == "logged_out"

    stale_response = client.get("/tasks/list", headers=_bearer(token_a))
    assert stale_response.status_code == 401, stale_response.text


def test_relogin_after_logout_issues_valid_token(client, monkeypatch):
    email = "relogin-user@aindy.test"
    password = "Passw0rd!123"
    monkeypatch.setattr("apps.tasks.services.task_service.list_tasks", lambda db, user_id: [])

    register_response = client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    assert register_response.status_code == 201, register_response.text
    token_a = _extract_access_token(register_response)

    logout_response = client.post("/auth/logout", headers=_bearer(token_a))
    assert logout_response.status_code == 200, logout_response.text

    token_b = _login(client, email=email, password=password)
    response = client.get("/tasks/list", headers=_bearer(token_b))

    assert response.status_code == 200, response.text


def test_admin_can_invalidate_another_users_sessions(client, db_session):
    user_a = _create_user(db_session, email="user-a@aindy.test")
    user_b = _create_user(db_session, email="admin-b@aindy.test", is_admin=True)

    token_a = _login(client, email=user_a.email)
    token_b = _login(client, email=user_b.email)

    response = client.post(
        f"/auth/admin/invalidate-sessions/{user_a.id}",
        headers=_bearer(token_b),
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "sessions_invalidated"
    assert response.json()["user_id"] == str(user_a.id)

    stale_response = client.get("/tasks/list", headers=_bearer(token_a))
    assert stale_response.status_code == 401, stale_response.text


def test_non_admin_cannot_invalidate_sessions(client, db_session):
    user_a = _create_user(db_session, email="non-admin@aindy.test")
    other_user = _create_user(db_session, email="target-user@aindy.test")

    token_a = _login(client, email=user_a.email)
    response = client.post(
        f"/auth/admin/invalidate-sessions/{other_user.id}",
        headers=_bearer(token_a),
    )

    assert response.status_code == 403, response.text


def test_stale_token_version_is_rejected(client, db_session):
    user = _create_user(db_session, email="stale-tv@aindy.test")
    token = _login(client, email=user.email)

    user.token_version = 1
    db_session.commit()

    response = client.get("/tasks/list", headers=_bearer(token))

    assert response.status_code == 401, response.text
    assert "invalidated" in response.text.lower()
