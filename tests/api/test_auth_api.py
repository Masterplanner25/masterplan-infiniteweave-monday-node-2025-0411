from __future__ import annotations

import uuid

from AINDY.db.models.system_event import SystemEvent
from AINDY.db.models.user import User
from AINDY.services.auth_service import decode_access_token
from AINDY.memory.memory_persistence import MemoryNodeModel


def test_register_seeds_signup_state_and_supports_immediate_boot(client, db_session):
    register_response = client.post(
        "/auth/register",
        json={
            "email": "signup@aindy.test",
            "password": "Passw0rd!123",
        },
    )

    assert register_response.status_code == 201
    register_payload = register_response.json()
    register_data = register_payload.get("data", register_payload)
    token = register_data["access_token"]
    claims = decode_access_token(token)
    user_id = uuid.UUID(claims["sub"])

    user = db_session.query(User).filter(User.id == user_id).first()
    assert user is not None
    assert user.email == "signup@aindy.test"
    assert user.username == "signup"

    memory = (
        db_session.query(MemoryNodeModel)
        .filter(
            MemoryNodeModel.user_id == user.id,
            MemoryNodeModel.content == "User account created",
        )
        .first()
    )
    assert memory is not None
    assert memory.extra["type"] == "identity"
    assert memory.extra["context"] == "identity_init"

    created_event = (
        db_session.query(SystemEvent)
        .filter(
            SystemEvent.user_id == user.id,
            SystemEvent.type == "identity.created",
        )
        .order_by(SystemEvent.timestamp.desc())
        .first()
    )
    assert created_event is not None
    assert created_event.payload["email"] == "signup@aindy.test"

    login_response = client.post(
        "/auth/login",
        json={
            "email": "signup@aindy.test",
            "password": "Passw0rd!123",
        },
    )
    assert login_response.status_code == 200
    login_token = login_response.json()["access_token"]

    boot_response = client.get(
        "/identity/boot",
        headers={"Authorization": f"Bearer {login_token}"},
    )
    assert boot_response.status_code == 200
    boot_payload = boot_response.json()
    boot_data = boot_payload["data"]
    assert boot_data["system_state"]["memory_count"] >= 1
    assert boot_data["system_state"]["active_runs"] == 1
    assert boot_data["system_state"]["score"] == 0.0
    assert any(m["content"] == "User account created" for m in boot_data["memory"])
    assert boot_data["metrics"]["trajectory"] == "baseline"


def test_register_derives_unique_username_when_email_local_part_collides(client, db_session):
    db_session.add(
        User(
            email="signup@aindy.existing",
            username="signup",
            hashed_password="hashed",
            is_active=True,
        )
    )
    db_session.commit()

    response = client.post(
        "/auth/register",
        json={
            "email": "signup@aindy.test",
            "password": "Passw0rd!123",
        },
    )

    assert response.status_code == 201
    claims = decode_access_token(response.json()["access_token"])
    created_user = db_session.query(User).filter(User.id == uuid.UUID(claims["sub"])).first()
    assert created_user is not None
    assert created_user.username == "signup_2"
