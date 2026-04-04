from __future__ import annotations

import uuid

from db.dao.memory_node_dao import MemoryNodeDAO
from db.dao.memory_trace_dao import MemoryTraceDAO
from db.models.user import User
from services.auth_service import hash_password


def _create_other_user(db_session) -> User:
    other_user = User(
        id=uuid.UUID("00000000-0000-0000-0000-000000000005"),
        email="trace-other@aindy.test",
        username="trace_other_user",
        hashed_password=hash_password("Passw0rd!123"),
        is_active=True,
    )
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)
    return other_user


class TestMemoryTraceDAO:
    def test_create_trace_returns_persisted_trace(self, db_session, test_user):
        dao = MemoryTraceDAO(db_session)

        result = dao.create_trace(user_id=str(test_user.id), title="Trace")

        assert result["user_id"] == str(test_user.id)
        assert result["title"] == "Trace"
        assert result["id"]

    def test_append_node_missing_trace(self, db_session, test_user):
        dao = MemoryTraceDAO(db_session)

        result = dao.append_node(
            trace_id=str(uuid.uuid4()),
            node_id=str(uuid.uuid4()),
            user_id=str(test_user.id),
        )

        assert result is None


class TestMemoryTraceRoutes:
    def test_trace_routes_use_real_db_and_enforce_user_scope(
        self,
        client,
        db_session,
        test_user,
        auth_headers,
        monkeypatch,
    ):
        monkeypatch.setattr("memory.embedding_service.generate_embedding", lambda text: [0.0] * 1536)
        other_user = _create_other_user(db_session)

        create_trace_response = client.post(
            "/memory/traces",
            headers=auth_headers,
            json={"title": "Trace", "description": "Primary trace"},
        )
        assert create_trace_response.status_code == 201
        payload = create_trace_response.json()
        trace = payload.get("data", payload)

        create_node_response = client.post(
            "/memory/nodes",
            headers=auth_headers,
            json={"content": "node for trace", "node_type": "insight", "tags": ["trace"]},
        )
        assert create_node_response.status_code == 201
        payload = create_node_response.json()
        node = payload.get("data", payload)

        append_response = client.post(
            f"/memory/traces/{trace['id']}/append",
            headers=auth_headers,
            json={"node_id": node["id"]},
        )
        assert append_response.status_code == 201
        append_payload = append_response.json()
        append_data = append_payload.get("data", append_payload)
        assert append_data["node_id"] == node["id"]

        list_response = client.get("/memory/traces", headers=auth_headers)
        assert list_response.status_code == 200
        list_payload = list_response.json()
        list_data = list_payload.get("data", list_payload)
        assert list_data["count"] == 1

        get_response = client.get(f"/memory/traces/{trace['id']}", headers=auth_headers)
        assert get_response.status_code == 200
        get_payload = get_response.json()
        get_data = get_payload.get("data", get_payload)
        assert get_data["title"] == "Trace"

        nodes_response = client.get(
            f"/memory/traces/{trace['id']}/nodes?include_nodes=true",
            headers=auth_headers,
        )
        assert nodes_response.status_code == 200
        nodes_payload = nodes_response.json()
        nodes_data = nodes_payload.get("data", nodes_payload)
        assert nodes_data["count"] == 1
        assert nodes_data["nodes"][0]["node"]["id"] == node["id"]

        other_trace = MemoryTraceDAO(db_session).create_trace(
            user_id=str(other_user.id),
            title="Other trace",
        )
        hidden_node = MemoryNodeDAO(db_session).save(
            content="other tenant node",
            source="pytest",
            tags=["trace"],
            user_id=str(other_user.id),
            node_type="insight",
            generate_embedding=False,
        )
        MemoryTraceDAO(db_session).append_node(
            trace_id=other_trace["id"],
            node_id=hidden_node["id"],
            user_id=str(other_user.id),
        )

        hidden_trace_response = client.get(f"/memory/traces/{other_trace['id']}", headers=auth_headers)
        assert hidden_trace_response.status_code == 404

        hidden_nodes_response = client.get(
            f"/memory/traces/{other_trace['id']}/nodes",
            headers=auth_headers,
        )
        assert hidden_nodes_response.status_code == 200
        hidden_payload = hidden_nodes_response.json()
        hidden_data = hidden_payload.get("data", hidden_payload)
        assert hidden_data["count"] == 0
