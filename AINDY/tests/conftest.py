"""
conftest.py — Shared fixtures for A.I.N.D.Y. diagnostic test suite.

IMPORTANT: env vars are set before any app import to prevent config.py from
failing on missing DATABASE_URL / PERMISSION_SECRET.

DB startup events are patched out so unit/route tests run without a live DB.
"""
import os
import sys

# ── Set env vars BEFORE importing anything from the application ──────────────
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres:test@localhost:5432/test_aindy")
os.environ.setdefault("PERMISSION_SECRET", "test-secret-for-pytest")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key-for-testing-only")
os.environ.setdefault("DEEPSEEK_API_KEY", "fake-deepseek-key")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-not-production")
os.environ.setdefault("AINDY_API_KEY", "test-api-key-for-pytest-only")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")

# Make sure the AINDY root is on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest
from unittest.mock import MagicMock, patch


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    """
    Create the FastAPI application for the test session.
    The DB startup event is patched out so no real Postgres connection is needed.
    """
    # Patch all DB-touching startup code before importing the app
    with patch("db.database.engine") as mock_engine, \
         patch("db.database.SessionLocal") as mock_session_local, \
         patch("services.task_services.get_mongo_client", return_value=None):

        # Make SessionLocal return a mock session
        mock_session = MagicMock()
        mock_session.query.return_value = mock_session
        mock_session.filter.return_value = mock_session
        mock_session.filter_by.return_value = mock_session
        mock_session.first.return_value = None
        mock_session.add.return_value = None
        mock_session.commit.return_value = None
        mock_session.close.return_value = None
        mock_session_local.return_value = mock_session

        from main import app as _app
        yield _app


@pytest.fixture(scope="session")
def client(app):
    """
    HTTP test client (synchronous) wrapping the FastAPI app.
    Startup events that touch DB are patched out.
    """
    from fastapi.testclient import TestClient

    # We need to patch the startup events that try to connect to DB
    with patch("db.database.SessionLocal") as mock_sl, \
         patch("services.task_services.get_mongo_client", return_value=None):

        mock_session = MagicMock()
        mock_session.query.return_value = mock_session
        mock_session.filter.return_value = mock_session
        mock_session.filter_by.return_value = mock_session
        mock_session.first.return_value = None
        mock_session.add.return_value = None
        mock_session.commit.return_value = None
        mock_session.close.return_value = None
        mock_sl.return_value = mock_session

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


@pytest.fixture
def mock_db():
    """
    A MagicMock standing in for a SQLAlchemy Session.
    Used by unit tests that call service functions directly.
    """
    db = MagicMock()
    db.query.return_value = db
    db.filter.return_value = db
    db.filter_by.return_value = db
    db.first.return_value = None
    db.all.return_value = []
    db.add.return_value = None
    db.commit.return_value = None
    db.refresh.return_value = None
    db.rollback.return_value = None
    return db


@pytest.fixture
def mock_openai(mocker):
    """Patches openai.OpenAI so no real API calls are made."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"reply": "test", "state_update": {}, "synthesis_ready": false}'
    mock_client.chat.completions.create.return_value = mock_response
    mocker.patch("openai.OpenAI", return_value=mock_client)
    return mock_client


@pytest.fixture
def auth_headers():
    """Valid JWT auth headers for protected route tests."""
    from services.auth_service import create_access_token
    token = create_access_token({
        "sub": "00000000-0000-0000-0000-000000000001",
        "email": "test@aindy.test",
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def api_key_headers():
    """Valid API key headers for service-to-service routes."""
    return {"X-API-Key": os.getenv("AINDY_API_KEY", "test-api-key-for-pytest-only")}


@pytest.fixture
def sample_task_input():
    """A valid TaskInput instance for calculation tests."""
    from schemas.analytics_inputs import TaskInput
    return TaskInput(
        task_name="Test Task",
        time_spent=2.0,
        task_complexity=3,
        skill_level=4,
        ai_utilization=3,
        task_difficulty=2,
    )


@pytest.fixture
def sample_engagement_input():
    """A valid EngagementInput instance for engagement tests."""
    from schemas.analytics_inputs import EngagementInput
    return EngagementInput(
        likes=100,
        shares=50,
        comments=30,
        clicks=200,
        time_on_page=45.0,
        total_views=1000,
    )
