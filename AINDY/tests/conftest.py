"""
Shared test fixtures for A.I.N.D.Y.

Test mode is enabled before the app imports so startup avoids schema checks,
background leadership, and async heavy execution.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres:test@localhost:5432/test_aindy")
os.environ.setdefault("PERMISSION_SECRET", "test-secret-for-pytest")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key-for-testing-only")
os.environ.setdefault("DEEPSEEK_API_KEY", "fake-deepseek-key")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-not-production")
os.environ.setdefault("AINDY_API_KEY", "test-api-key-for-pytest-only")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
os.environ.setdefault("AINDY_ASYNC_HEAVY_EXECUTION", "false")
os.environ.setdefault("AINDY_ENABLE_BACKGROUND_TASKS", "false")
os.environ.setdefault("AINDY_ENFORCE_SCHEMA", "false")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class MockSession(MagicMock):
    """Session-like MagicMock with working add/flush/commit/refresh semantics."""

    def __init__(self):
        super().__init__(spec_set=[])
        self._added_objects: list[object] = []
        self._query = MagicMock()
        self.query = MagicMock(return_value=self._query)
        self._query.filter.return_value = self._query
        self._query.filter_by.return_value = self._query
        self._query.order_by.return_value = self._query
        self._query.limit.return_value = self._query
        self._query.offset.return_value = self._query
        self._query.join.return_value = self._query
        self._query.outerjoin.return_value = self._query
        self._query.group_by.return_value = self._query
        self._query.scalar.return_value = 0.0
        self._query.count.return_value = 0
        self._query.first.return_value = None
        self._query.all.return_value = []
        self.add = MagicMock(side_effect=self._add)
        self.flush = MagicMock(side_effect=self._flush)
        self.commit = MagicMock(return_value=None)
        self.refresh = MagicMock(side_effect=self._refresh)
        self.rollback = MagicMock(return_value=None)
        self.close = MagicMock(return_value=None)

    def _assign_identity(self, obj: object) -> None:
        if hasattr(obj, "id") and getattr(obj, "id", None) is None:
            current = getattr(type(obj), "id", None)
            if current is not None and "UUID" in str(current):
                setattr(obj, "id", uuid.uuid4())
            else:
                setattr(obj, "id", str(uuid.uuid4()))
        if hasattr(obj, "timestamp") and getattr(obj, "timestamp", None) is None:
            setattr(obj, "timestamp", datetime.now(timezone.utc))
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            setattr(obj, "created_at", datetime.now(timezone.utc))

    def _add(self, obj: object) -> None:
        self._assign_identity(obj)
        self._added_objects.append(obj)

    def _flush(self) -> None:
        for obj in self._added_objects:
            self._assign_identity(obj)

    def _refresh(self, obj: object) -> None:
        self._assign_identity(obj)


@pytest.fixture(autouse=True)
def _test_runtime_isolation(monkeypatch):
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("AINDY_ASYNC_HEAVY_EXECUTION", "false")
    monkeypatch.setenv("AINDY_ENABLE_BACKGROUND_TASKS", "false")
    monkeypatch.setenv("AINDY_ENFORCE_SCHEMA", "false")
    from services.async_job_service import shutdown_async_jobs

    yield
    shutdown_async_jobs(wait=True)


@pytest.fixture(scope="session")
def app():
    from main import app as _app

    yield _app


@pytest.fixture(scope="session")
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def mock_db(app):
    from db.database import get_db

    db = MockSession()
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def mock_openai(mocker):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"reply": "test", "state_update": {}, "synthesis_ready": false}'
    mock_client.chat.completions.create.return_value = mock_response
    mocker.patch("openai.OpenAI", return_value=mock_client)
    return mock_client


@pytest.fixture
def auth_headers():
    from services.auth_service import create_access_token

    token = create_access_token(
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "email": "test@aindy.test",
        }
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def api_key_headers():
    return {"X-API-Key": os.getenv("AINDY_API_KEY", "test-api-key-for-pytest-only")}


@pytest.fixture
def sample_task_input():
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
    from schemas.analytics_inputs import EngagementInput

    return EngagementInput(
        likes=100,
        shares=50,
        comments=30,
        clicks=200,
        time_on_page=45.0,
        total_views=1000,
    )
