from __future__ import annotations

from datetime import datetime
import uuid

from db.models.author_model import AuthorDB
from db.models.drop import DropPointDB, PingDB
from db.models.user import User
from services.auth_service import hash_password


def test_dashboard_requires_auth(client):
    response = client.get("/dashboard/overview")

    assert response.status_code == 401


def test_dashboard_overview_returns_real_db_snapshot(
    client,
    db_session,
    test_user,
    auth_headers,
):
    other_user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    db_session.add(
        User(
            id=other_user_id,
            email="other@aindy.test",
            username="other_user",
            hashed_password=hash_password("Passw0rd!123"),
            is_active=True,
        )
    )
    db_session.commit()
    db_session.add(
        AuthorDB(
            id="author-1",
            name="Primary Author",
            platform="x",
            notes="visible",
            joined_at=datetime.utcnow(),
            last_seen=datetime.utcnow(),
            user_id=test_user.id,
        )
    )
    db_session.add(
        AuthorDB(
            id="author-2",
            name="Hidden Author",
            platform="x",
            notes="other tenant",
            joined_at=datetime.utcnow(),
            last_seen=datetime.utcnow(),
            user_id=other_user_id,
        )
    )
    db_session.add(
        DropPointDB(
            id="drop-1",
            title="Visible Drop",
            platform="x",
            date_dropped=datetime.utcnow(),
            user_id=test_user.id,
        )
    )
    db_session.add(
        DropPointDB(
            id="drop-2",
            title="Hidden Drop",
            platform="x",
            date_dropped=datetime.utcnow(),
            user_id=other_user_id,
        )
    )
    db_session.add(
        PingDB(
            id="ping-1",
            drop_point_id="drop-1",
            ping_type="mention",
            source_platform="x",
            date_detected=datetime.utcnow(),
            connection_summary="visible ripple",
            user_id=test_user.id,
            strength=1.0,
            connection_type="direct",
        )
    )
    db_session.add(
        PingDB(
            id="ping-2",
            drop_point_id="drop-2",
            ping_type="reply",
            source_platform="x",
            date_detected=datetime.utcnow(),
            connection_summary="other ripple",
            user_id=other_user_id,
            strength=1.0,
            connection_type="direct",
        )
    )
    db_session.commit()

    response = client.get("/dashboard/overview", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    overview = payload["overview"]
    assert overview["author_count"] == 1
    assert len(overview["recent_authors"]) == 1
    assert overview["recent_authors"][0]["id"] == "author-1"
    assert len(overview["recent_ripples"]) == 1
    assert overview["recent_ripples"][0]["summary"] == "visible ripple"
    assert "system_timestamp" in overview
