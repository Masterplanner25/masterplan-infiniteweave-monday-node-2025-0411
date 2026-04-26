from __future__ import annotations

import importlib
import os
import signal
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt
from fastapi import HTTPException


def test_key_ring_rotate_promotes_active_to_previous():
    auth_service = importlib.import_module("AINDY.services.auth_service")

    ring = auth_service.KeyRing(active="a" * 32)
    ring.rotate("b" * 32)

    assert ring.active_key == "b" * 32
    assert ring.verify_keys() == ["b" * 32, "a" * 32]


def test_key_ring_verify_keys_expires_previous():
    auth_service = importlib.import_module("AINDY.services.auth_service")

    ring = auth_service.KeyRing(active="a" * 32, previous="b" * 32)
    assert ring.verify_keys() == ["a" * 32, "b" * 32]

    ring._previous_expires = datetime.now(timezone.utc) - timedelta(seconds=1)

    assert ring.verify_keys() == ["a" * 32]


def test_key_ring_rotate_noop_when_same_key():
    auth_service = importlib.import_module("AINDY.services.auth_service")

    ring = auth_service.KeyRing(active="a" * 32)
    ring.rotate("a" * 32)

    assert ring.active_key == "a" * 32
    assert ring.verify_keys() == ["a" * 32]


def test_decode_access_token_accepts_previous_key_during_grace(monkeypatch):
    auth_service = importlib.import_module("AINDY.services.auth_service")

    ring = auth_service.KeyRing(active="a" * 32)
    monkeypatch.setattr(auth_service, "_key_ring", ring)
    token = jwt.encode({"sub": "user-1"}, "a" * 32, algorithm=auth_service.ALGORITHM)

    ring.rotate("b" * 32)

    payload = auth_service.decode_access_token(token)

    assert payload["sub"] == "user-1"


def test_decode_access_token_rejects_previous_key_after_grace(monkeypatch):
    auth_service = importlib.import_module("AINDY.services.auth_service")

    ring = auth_service.KeyRing(active="a" * 32)
    monkeypatch.setattr(auth_service, "_key_ring", ring)
    token = jwt.encode({"sub": "user-1"}, "a" * 32, algorithm=auth_service.ALGORITHM)

    ring.rotate("b" * 32)
    ring._previous_expires = datetime.now(timezone.utc) - timedelta(seconds=1)

    with pytest.raises(HTTPException):
        auth_service.decode_access_token(token)


def test_reload_from_env_rotates(monkeypatch):
    auth_service = importlib.import_module("AINDY.services.auth_service")

    ring = auth_service.KeyRing(active="a" * 32)
    monkeypatch.setenv("SECRET_KEY", "b" * 32)

    changed = ring.reload_from_env()

    assert changed is True
    assert ring.active_key == "b" * 32
    assert ring.verify_keys() == ["b" * 32, "a" * 32]


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="SIGHUP not available on this platform")
def test_sighup_reload_updates_module_secret(monkeypatch):
    auth_service = importlib.import_module("AINDY.services.auth_service")

    ring = auth_service.KeyRing(active="a" * 32)
    monkeypatch.setattr(auth_service, "_key_ring", ring)
    monkeypatch.setattr(auth_service, "SECRET_KEY", "a" * 32)
    monkeypatch.setenv("SECRET_KEY", "b" * 32)

    auth_service._reload_key_on_sighup(signal.SIGHUP, None)

    assert auth_service.SECRET_KEY == "b" * 32
    assert auth_service._key_ring.active_key == "b" * 32
