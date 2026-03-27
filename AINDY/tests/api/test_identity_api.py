from __future__ import annotations

from datetime import datetime, timezone

from db.models.user_identity import UserIdentity


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
    assert payload["user_id"] == str(test_user.id)
    assert payload["communication"]["tone"] == "technical"
    assert payload["tools"]["preferred_languages"] == ["python"]
    assert payload["decision_making"]["risk_tolerance"] == "moderate"
    assert payload["learning"]["style"] == "examples"
    assert payload["evolution"]["observation_count"] == 3


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
    assert payload["is_empty"] is False
    assert "Communication style: technical" in payload["context"]
    assert "Preferred languages: python, sql" in payload["context"]
    assert "Risk tolerance: moderate" in payload["context"]


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
    assert payload["observation_count"] == 2
    assert payload["total_changes"] == 2
    assert set(payload["dimensions_evolved"]) == {
        "preferred_languages",
        "preferred_tools",
    }
    assert payload["most_changed_dimension"] in {
        "preferred_languages",
        "preferred_tools",
    }
