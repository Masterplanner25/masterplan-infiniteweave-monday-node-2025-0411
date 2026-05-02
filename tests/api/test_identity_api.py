from __future__ import annotations

from datetime import datetime, timezone
import uuid

from AINDY.db.models import AgentRun
from AINDY.db.models.flow_run import FlowRun
from AINDY.db.models.system_event import SystemEvent
from AINDY.db.models.user import User
from AINDY.db.models.user_identity import UserIdentity
from apps.analytics.models import UserScore
from AINDY.services.auth_service import hash_password
from AINDY.memory.memory_persistence import MemoryNodeModel


def test_identity_requires_auth(client):
    response = client.get("/identity/")

    assert response.status_code == 401


def test_identity_profile_returns_real_db_profile(
    client,
    db_session,
    test_user,
    auth_headers,
):
    db_session.add(
        UserIdentity(
            user_id=test_user.id,
            tone="technical",
            communication_notes="Prefer direct answers",
            preferred_languages=["python"],
            preferred_tools=["pytest"],
            avoided_tools=["selenium"],
            risk_tolerance="moderate",
            speed_vs_quality="quality",
            decision_notes="Bias toward correctness",
            learning_style="examples",
            detail_preference="high_level",
            learning_notes="Use concise examples",
            observation_count=3,
            evolution_log=[{"dimension": "tone", "new_value": "technical"}],
            last_updated=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    response = client.get("/identity/", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]
    assert data["user_id"] == str(test_user.id)
    assert data["communication"]["tone"] == "technical"
    assert data["tools"]["preferred_languages"] == ["python"]
    assert data["decision_making"]["risk_tolerance"] == "moderate"
    assert data["learning"]["style"] == "examples"
    assert data["evolution"]["observation_count"] == 3


def test_identity_context_returns_personalized_context(
    client,
    db_session,
    test_user,
    auth_headers,
):
    db_session.add(
        UserIdentity(
            user_id=test_user.id,
            tone="technical",
            preferred_languages=["python", "sql"],
            risk_tolerance="moderate",
            learning_style="examples",
            detail_preference="high_level",
            evolution_log=[],
        )
    )
    db_session.commit()

    response = client.get("/identity/context", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]
    assert data["is_empty"] is False
    assert "Communication style: technical" in data["context"]
    assert "Preferred languages: python, sql" in data["context"]
    assert "Risk tolerance: moderate" in data["context"]


def test_identity_evolution_returns_real_summary(
    client,
    db_session,
    test_user,
    auth_headers,
):
    db_session.add(
        UserIdentity(
            user_id=test_user.id,
            preferred_languages=["python"],
            preferred_tools=["pytest"],
            observation_count=2,
            evolution_log=[
                {"dimension": "preferred_languages", "new_value": ["python"]},
                {"dimension": "preferred_tools", "new_value": ["pytest"]},
            ],
        )
    )
    db_session.commit()

    response = client.get("/identity/evolution", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]
    assert data["observation_count"] == 2
    assert data["total_changes"] == 2
    assert set(data["dimensions_evolved"]) == {
        "preferred_languages",
        "preferred_tools",
    }
    assert data["most_changed_dimension"] in {
        "preferred_languages",
        "preferred_tools",
    }


def test_identity_boot_returns_full_scoped_state_and_emits_event(
    client,
    db_session,
    test_user,
    auth_headers,
):
    other_user = User(
        id=uuid.uuid4(),
        email="other@aindy.test",
        username="other_user",
        hashed_password=hash_password("Passw0rd!123"),
        is_active=True,
    )
    db_session.add(other_user)
    db_session.flush()

    own_memory = MemoryNodeModel(
        user_id=test_user.id,
        content="Own memory node",
        tags=["alpha"],
        node_type="insight",
        source_agent="user",
        extra={"source": "test"},
    )
    other_memory = MemoryNodeModel(
        user_id=other_user.id,
        content="Other memory node",
        tags=["beta"],
        node_type="decision",
        source_agent="user",
        extra={"source": "test"},
    )
    own_run = AgentRun(
        user_id=test_user.id,
        agent_type="default",
        goal="Own run",
        status="completed",
        steps_total=1,
    )
    other_run = AgentRun(
        user_id=other_user.id,
        agent_type="default",
        goal="Other run",
        status="completed",
        steps_total=1,
    )
    own_flow = FlowRun(
        user_id=test_user.id,
        flow_name="Identity Flow",
        workflow_type="identity_boot_test",
        status="running",
        state={"phase": "active"},
    )
    other_flow = FlowRun(
        user_id=other_user.id,
        flow_name="Other Flow",
        workflow_type="identity_boot_test",
        status="running",
        state={"phase": "active"},
    )
    own_score = UserScore(
        user_id=test_user.id,
        master_score=88.0,
        execution_speed_score=80.0,
        decision_efficiency_score=82.0,
        ai_productivity_boost_score=85.0,
        focus_quality_score=90.0,
        masterplan_progress_score=83.0,
        confidence="high",
        data_points_used=42,
        trigger_event="manual",
    )

    db_session.add_all(
        [
            own_memory,
            other_memory,
            own_run,
            other_run,
            own_flow,
            other_flow,
            own_score,
        ]
    )
    db_session.commit()

    response = client.get("/identity/boot", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]
    assert data["user_id"] == str(test_user.id)
    assert data["system_state"]["memory_count"] == 1
    assert data["system_state"]["active_runs"] == 1
    assert data["system_state"]["score"] == 88.0
    assert data["system_state"]["active_flows"] == 1
    assert [node["content"] for node in data["memory"]] == ["Own memory node"]
    assert data["memory"][0]["context"] == "identity_boot"
    assert data["memory"][0]["extra"]["context"] == "identity_boot"
    assert [run["goal"] for run in data["runs"]] == ["Own run"]
    assert [flow["flow_name"] for flow in data["flows"]] == ["Identity Flow"]
    assert data["metrics"]["master_score"] == 88.0
    assert data["metrics"]["metadata"]["confidence"] == "high"

    event = (
        db_session.query(SystemEvent)
        .filter(
            SystemEvent.user_id == test_user.id,
            SystemEvent.type == "identity.boot",
        )
        .order_by(SystemEvent.timestamp.desc())
        .first()
    )
    assert event is not None
    assert event.payload["memory_loaded"] == 1
    assert event.payload["runs_loaded"] == 1
    assert event.payload["score"] == 88.0


def test_identity_boot_requires_auth(client):
    response = client.get("/identity/boot")

    assert response.status_code == 401
