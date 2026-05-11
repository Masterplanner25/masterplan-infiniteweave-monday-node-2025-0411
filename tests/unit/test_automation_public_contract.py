from __future__ import annotations

import inspect
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-required-length-1234567890")

from AINDY.db.database import Base
from tests.helpers.app_profile import bootstrap_app_models
from tests.helpers.runtime import import_runtime_model_registry


pytestmark = pytest.mark.app_profile

automation_public = pytest.importorskip("apps.automation.public")


def _build_session():
    import_runtime_model_registry()
    bootstrap_app_models(required=True)

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=engine,
    )
    return engine, session_factory


def test_automation_public_contract_holds():
    assert automation_public.PUBLIC_API_VERSION == "1.0"
    assert automation_public.__all__

    for name in automation_public.__all__:
        exported = getattr(automation_public, name)
        assert callable(exported)
        assert inspect.get_annotations(exported)


def test_execute_automation_action_happy_path():
    engine, session_factory = _build_session()
    session = session_factory()
    try:
        result = automation_public.execute_automation_action(
            {
                "automation_type": "crm",
                "task_id": 7,
                "automation_config": {
                    "action": "record_follow_up",
                    "contact": "lead@example.com",
                    "details": "Follow up tomorrow",
                },
            },
            session,
        )

        assert result["automation_type"] == "crm"
        assert result["status"] == "completed"
        assert result["task_id"] == 7
    finally:
        session.close()
        engine.dispose()
