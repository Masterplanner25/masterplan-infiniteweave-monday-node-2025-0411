from __future__ import annotations

import importlib
from datetime import timedelta

from AINDY.services.auth_service import create_access_token


def _admin_headers_for_user(user) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": str(user.id),
            "email": user.email,
            "is_admin": True,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def test_rotate_secret_key_with_admin_jwt_returns_200(client, test_user, monkeypatch):
    auth_service = importlib.import_module("AINDY.services.auth_service")

    ring = auth_service.KeyRing(active="a" * 32)
    monkeypatch.setattr(auth_service, "_key_ring", ring)
    monkeypatch.setattr(auth_service, "SECRET_KEY", "a" * 32)
    headers = _admin_headers_for_user(test_user)

    response = client.post(
        "/platform/ops/rotate-secret-key",
        headers=headers,
        json={"new_key": "b" * 32},
    )

    assert response.status_code == 200
    assert response.json()["rotated"] is True
    assert auth_service._key_ring.active_key == "b" * 32
    assert auth_service.SECRET_KEY == "b" * 32


def test_rotate_secret_key_with_non_admin_jwt_returns_403(client, non_admin_auth_headers):
    response = client.post(
        "/platform/ops/rotate-secret-key",
        headers=non_admin_auth_headers,
        json={"new_key": "b" * 32},
    )

    assert response.status_code == 403


def test_rotate_secret_key_rejects_short_key(client, auth_headers):
    response = client.post(
        "/platform/ops/rotate-secret-key",
        headers=auth_headers,
        json={"new_key": "short-key"},
    )

    assert response.status_code == 400
    assert "new_key must be at least 32 characters" in str(response.json())


def test_old_token_still_valid_after_rotation(client, test_user, monkeypatch):
    auth_service = importlib.import_module("AINDY.services.auth_service")

    ring = auth_service.KeyRing(active="a" * 32)
    monkeypatch.setattr(auth_service, "_key_ring", ring)
    monkeypatch.setattr(auth_service, "SECRET_KEY", "a" * 32)
    headers = _admin_headers_for_user(test_user)
    old_token = create_access_token(
        {
            "sub": str(test_user.id),
            "email": test_user.email,
            "is_admin": True,
        }
    )

    response = client.post(
        "/platform/ops/rotate-secret-key",
        headers=headers,
        json={"new_key": "b" * 32},
    )

    assert response.status_code == 200
    payload = auth_service.decode_access_token(old_token)
    assert payload["sub"] == str(test_user.id)


def test_new_token_valid_after_rotation(client, test_user, monkeypatch):
    auth_service = importlib.import_module("AINDY.services.auth_service")

    ring = auth_service.KeyRing(active="a" * 32)
    monkeypatch.setattr(auth_service, "_key_ring", ring)
    monkeypatch.setattr(auth_service, "SECRET_KEY", "a" * 32)
    headers = _admin_headers_for_user(test_user)

    response = client.post(
        "/platform/ops/rotate-secret-key",
        headers=headers,
        json={"new_key": "b" * 32},
    )

    assert response.status_code == 200

    new_token = create_access_token(
        {
            "sub": str(test_user.id),
            "email": test_user.email,
            "is_admin": True,
        },
        expires_delta=timedelta(minutes=5),
    )
    payload = auth_service.decode_access_token(new_token)
    assert payload["sub"] == str(test_user.id)
