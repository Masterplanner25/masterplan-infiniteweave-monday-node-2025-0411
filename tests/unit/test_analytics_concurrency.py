from __future__ import annotations

import threading
import time
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from AINDY.db.database import Base
from AINDY.db.models.user import User
from apps.analytics.models import ScoreHistory, UserScore
from apps.analytics.services.infinity_orchestrator import execute as execute_infinity_orchestrator
from apps.analytics.services.infinity_service import calculate_infinity_score, orchestrator_score_context


def _build_session_factory(tmp_path):
    import AINDY.db.model_registry  # noqa: F401
    import AINDY.memory.memory_persistence  # noqa: F401
    import apps.bootstrap

    apps.bootstrap.bootstrap_models()

    engine = create_engine(
        f"sqlite:///{tmp_path / 'analytics_concurrency.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=engine,
    )


def _seed_user(session_factory) -> str:
    user_id = uuid.uuid4()
    session = session_factory()
    try:
        session.add(
            User(
                id=user_id,
                email=f"{user_id}@example.com",
                hashed_password="test",
                is_active=True,
            )
        )
        session.commit()
    finally:
        session.close()
    return str(user_id)


def test_duplicate_trigger_is_suppressed_for_same_user(tmp_path, monkeypatch):
    engine, session_factory = _build_session_factory(tmp_path)
    user_id = _seed_user(session_factory)

    import apps.analytics.services.infinity_orchestrator as orchestrator_module

    monkeypatch.setattr(orchestrator_module, "get_recent_memory", lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator_module, "get_user_metrics", lambda *args, **kwargs: {})
    monkeypatch.setattr(orchestrator_module, "get_relevant_memories", lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator_module, "compute_current_state", lambda *args, **kwargs: {})
    monkeypatch.setattr(orchestrator_module, "rank_goals", lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator_module, "get_task_graph_context", lambda *args, **kwargs: {})
    monkeypatch.setattr(orchestrator_module, "get_social_performance_signals", lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator_module, "emit_system_event", lambda **kwargs: None)
    monkeypatch.setattr(orchestrator_module, "evaluate_pending_adjustment", lambda **kwargs: None)
    monkeypatch.setattr(
        orchestrator_module,
        "run_loop",
        lambda **kwargs: type("Adjustment", (), {"id": "adj-1", "adjustment_payload": {"next_action": {"type": "noop"}}, "trace_id": "trace-1"})(),
    )
    monkeypatch.setattr(
        orchestrator_module,
        "serialize_adjustment",
        lambda adjustment: {"id": "adj-1", "trace_id": "trace-1", "adjustment_payload": {"next_action": {"type": "noop"}}},
    )

    start_barrier = threading.Barrier(2)
    results: list[dict] = []

    def _worker():
        session = session_factory()
        try:
            start_barrier.wait()
            results.append(
                execute_infinity_orchestrator(
                    user_id=user_id,
                    trigger_event="manual",
                    db=session,
                )
            )
        finally:
            session.close()

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    verification = session_factory()
    try:
        history_rows = verification.query(ScoreHistory).filter(ScoreHistory.user_id == uuid.UUID(user_id)).count()
        user_score_rows = verification.query(UserScore).filter(UserScore.user_id == uuid.UUID(user_id)).count()
    finally:
        verification.close()
        engine.dispose()

    assert len(results) == 2
    assert sum(1 for result in results if result["score"]["metadata"].get("skipped") == "duplicate_inflight") == 1
    assert history_rows == 1
    assert user_score_rows == 1


def test_parallel_score_updates_increment_lock_version_without_duplicate_rows(tmp_path, monkeypatch):
    engine, session_factory = _build_session_factory(tmp_path)
    user_id = _seed_user(session_factory)

    import apps.analytics.services.infinity_service as infinity_service_module

    def _score(value):
        def _inner(*args, **kwargs):
            time.sleep(0.05)
            return value, 1
        return _inner

    monkeypatch.setattr(infinity_service_module, "calculate_execution_speed", _score(60.0))
    monkeypatch.setattr(infinity_service_module, "calculate_decision_efficiency", _score(62.0))
    monkeypatch.setattr(infinity_service_module, "calculate_ai_productivity_boost", _score(64.0))
    monkeypatch.setattr(infinity_service_module, "calculate_focus_quality", _score(66.0))
    monkeypatch.setattr(infinity_service_module, "calculate_masterplan_progress", _score(68.0))

    seed_session = session_factory()
    try:
        seed_session.add(
            UserScore(
                user_id=uuid.UUID(user_id),
                master_score=0.0,
                execution_speed_score=0.0,
                decision_efficiency_score=0.0,
                ai_productivity_boost_score=0.0,
                focus_quality_score=0.0,
                masterplan_progress_score=0.0,
                confidence="baseline",
                data_points_used=0,
                trigger_event="seed",
                lock_version=1,
            )
        )
        seed_session.commit()
    finally:
        seed_session.close()

    start_barrier = threading.Barrier(5)

    def _worker(index: int):
        session = session_factory()
        try:
            start_barrier.wait()
            with orchestrator_score_context():
                result = calculate_infinity_score(
                    user_id=user_id,
                    db=session,
                    trigger_event=f"parallel-{index}",
                )
            assert result is not None
        finally:
            session.close()

    threads = [threading.Thread(target=_worker, args=(idx,)) for idx in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    verification = session_factory()
    try:
        score_row = verification.query(UserScore).filter(UserScore.user_id == uuid.UUID(user_id)).one()
        history_rows = verification.query(ScoreHistory).filter(ScoreHistory.user_id == uuid.UUID(user_id)).all()
    finally:
        verification.close()
        engine.dispose()

    assert score_row.lock_version == 6
    assert len(history_rows) == 5
    assert len({row.id for row in history_rows}) == 5
