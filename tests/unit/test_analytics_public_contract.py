from __future__ import annotations

import inspect
import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-required-length-1234567890")

from AINDY.db.database import Base
from AINDY.db.models.user import User
from apps.analytics import public as analytics_public
from apps.analytics.models import ScoreSnapshotDB, UserScore


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


def test_analytics_public_contract_holds():
    assert analytics_public.PUBLIC_API_VERSION == "1.0"
    assert analytics_public.__all__

    for name in analytics_public.__all__:
        exported = getattr(analytics_public, name)
        assert callable(exported)
        assert inspect.get_annotations(exported)


def test_analytics_public_happy_paths(monkeypatch):
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

        calc = analytics_public.save_calculation(session, "Execution Speed", 12.5, str(user_id))
        assert calc is not None
        assert calc.metric_name == "Execution Speed"

        session.add(
            UserScore(
                id="score-1",
                user_id=user_id,
                master_score=91.0,
                execution_speed_score=81.0,
                decision_efficiency_score=82.0,
                ai_productivity_boost_score=83.0,
                focus_quality_score=84.0,
                masterplan_progress_score=85.0,
                score_version="v1",
                data_points_used=7,
                confidence="high",
                trigger_event="contract_test",
                lock_version=1,
            )
        )
        session.commit()

        snapshot = analytics_public.get_user_kpi_snapshot(str(user_id), session)
        assert snapshot is not None
        assert snapshot["master_score"] == 91.0

        monkeypatch.setattr(
            analytics_public,
            "_run_infinity_orchestrator",
            lambda user_id, trigger_event, db: {
                "score": {"master_score": 91.0},
                "prior_evaluation": None,
                "adjustment": {"id": "adj-1"},
                "next_action": "noop",
                "memory_context_count": 0,
                "memory_signal_count": 0,
                "memory_influence": {
                    "memory_adjustment": {},
                    "memory_summary": {},
                },
            },
        )
        orchestrated = analytics_public.run_infinity_orchestrator(
            str(user_id),
            "contract_test",
            session,
        )
        assert orchestrated["next_action"] == "noop"

        user_score = analytics_public.get_user_score(str(user_id), session)
        assert user_score is not None
        assert user_score["id"] == "score-1"

        user_scores = analytics_public.get_user_scores([str(user_id)], session)
        assert str(user_id) in user_scores

        now = datetime.now(timezone.utc)
        created_snapshot = analytics_public.create_score_snapshot(
            drop_point_id="drop-1",
            db=session,
            narrative_score=0.8,
            velocity_score=0.7,
            spread_score=0.6,
            timestamp=now,
            snapshot_id="snap-1",
        )
        assert created_snapshot["id"] == "snap-1"
        session.commit()

        session.add(
            ScoreSnapshotDB(
                id="snap-0",
                drop_point_id="drop-1",
                timestamp=now - timedelta(minutes=5),
                narrative_score=0.4,
                velocity_score=0.5,
                spread_score=0.6,
            )
        )
        session.commit()

        latest_snapshot = analytics_public.get_score_snapshot("drop-1", session)
        assert latest_snapshot is not None
        assert latest_snapshot["id"] == "snap-1"

        snapshots = analytics_public.list_score_snapshots("drop-1", session, limit=2)
        assert [item["id"] for item in snapshots] == ["snap-1", "snap-0"]

        drop_point_ids = analytics_public.list_score_snapshot_drop_point_ids(session)
        assert "drop-1" in drop_point_ids
    finally:
        session.close()
        engine.dispose()
