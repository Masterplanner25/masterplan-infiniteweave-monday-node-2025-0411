from __future__ import annotations

import inspect
import os
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-required-length-1234567890")

from AINDY.db.database import Base
from AINDY.db.models.user import User
from apps.tasks import public as tasks_public
from apps.tasks.models import Task


def _build_session():
    import AINDY.db.model_registry  # noqa: F401
    import AINDY.memory.memory_persistence  # noqa: F401
    import apps.bootstrap

    apps.bootstrap.bootstrap_models()

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=engine,
    )
    return engine, session_factory


def test_tasks_public_contract_holds():
    assert tasks_public.PUBLIC_API_VERSION == "1.0"
    assert tasks_public.__all__

    for name in tasks_public.__all__:
        exported = getattr(tasks_public, name)
        assert callable(exported)
        assert inspect.get_annotations(exported)


def test_tasks_public_happy_paths(monkeypatch):
    engine, session_factory = _build_session()
    session = session_factory()
    try:
        user_id = uuid.uuid4()
        session.add(
            User(
                id=user_id,
                email=f"{user_id}@example.com",
                hashed_password="test",
                is_active=True,
            )
        )
        session.commit()

        task = Task(
            name="Contract Task",
            user_id=user_id,
            automation_type="crm",
            automation_config={"action": "record_follow_up"},
            status="pending",
        )
        session.add(task)
        session.commit()
        session.refresh(task)

        fetched = tasks_public.get_task_by_id(session, task.id, str(user_id))
        assert fetched is not None
        assert fetched["id"] == task.id

        class _DispatchResult:
            envelope = {"job_id": "job-1", "status": "queued", "trace_id": "trace-1"}

        monkeypatch.setattr(
            "AINDY.core.execution_dispatcher.dispatch_autonomous_job",
            lambda **kwargs: _DispatchResult(),
        )

        dispatch = tasks_public.queue_task_automation(
            session,
            task,
            str(user_id),
            reason="contract_test",
        )

        assert dispatch is not None
        assert dispatch["job_id"] == "job-1"
        assert dispatch["status"] == "queued"
    finally:
        session.close()
        engine.dispose()
