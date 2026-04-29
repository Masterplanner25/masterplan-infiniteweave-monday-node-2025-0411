from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, Uuid, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from AINDY.kernel.syscall_registry import SyscallContext


Base = declarative_base()


class TestWatcherSignal(Base):
    __tablename__ = "watcher_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    signal_type = Column(String(64), nullable=False, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    app_name = Column(String(255), nullable=False)
    window_title = Column(Text, nullable=True)
    activity_type = Column(String(32), nullable=False)
    signal_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    received_at = Column(DateTime(timezone=True), nullable=False)
    duration_seconds = Column(Integer, nullable=True)
    focus_score = Column(Integer, nullable=True)
    signal_metadata = Column(JSON, nullable=True)


def _ctx(db_session) -> SyscallContext:
    return SyscallContext(
        execution_unit_id="eu-watcher-query",
        user_id="",
        capabilities=["watcher.query"],
        trace_id="trace-watcher-query",
        metadata={"_db": db_session},
    )


def _seed_signal(session, **overrides):
    now = datetime.now(timezone.utc)
    row = TestWatcherSignal(
        user_id=overrides.get("user_id"),
        signal_type=overrides.get("signal_type", "session_started"),
        session_id=overrides.get("session_id", "session-a"),
        app_name=overrides.get("app_name", "cursor"),
        window_title=overrides.get("window_title", "main.py"),
        activity_type=overrides.get("activity_type", "work"),
        signal_timestamp=overrides.get("signal_timestamp", now),
        received_at=overrides.get("received_at", now + timedelta(seconds=1)),
        duration_seconds=overrides.get("duration_seconds", 10),
        focus_score=overrides.get("focus_score", 1),
        signal_metadata=overrides.get("signal_metadata", {"source": "test"}),
    )
    session.add(row)
    session.commit()
    return row


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return Session()


def test_handle_watcher_query_returns_serialized_payload(monkeypatch):
    from apps.automation import models as automation_models
    from apps.automation.syscalls.syscall_handlers import handle_watcher_query

    session = _session()
    monkeypatch.setattr(automation_models, "WatcherSignal", TestWatcherSignal)
    row = _seed_signal(session)

    result = handle_watcher_query({}, _ctx(session))

    assert result["total"] == 1
    assert isinstance(result["signals"][0], dict)
    assert result["signals"][0]["id"] == row.id
    assert result["signals"][0]["signal_type"] == "session_started"
    assert result["signals"][0]["metadata"] == {"source": "test"}


def test_handle_watcher_query_filters_by_user_id(monkeypatch):
    from apps.automation import models as automation_models
    from apps.automation.syscalls.syscall_handlers import handle_watcher_query

    session = _session()
    monkeypatch.setattr(automation_models, "WatcherSignal", TestWatcherSignal)
    wanted_user = uuid4()
    _seed_signal(session, user_id=wanted_user, session_id="session-user-1")
    _seed_signal(session, user_id=uuid4(), session_id="session-user-2")

    result = handle_watcher_query({"user_id": str(wanted_user)}, _ctx(session))

    assert result["total"] == 1
    assert [signal["session_id"] for signal in result["signals"]] == ["session-user-1"]


def test_handle_watcher_query_filters_by_session_id(monkeypatch):
    from apps.automation import models as automation_models
    from apps.automation.syscalls.syscall_handlers import handle_watcher_query

    session = _session()
    monkeypatch.setattr(automation_models, "WatcherSignal", TestWatcherSignal)
    _seed_signal(session, session_id="session-match")
    _seed_signal(session, session_id="session-other")

    result = handle_watcher_query({"session_id": "session-match"}, _ctx(session))

    assert result["total"] == 1
    assert result["signals"][0]["session_id"] == "session-match"


def test_handle_watcher_query_respects_limit_and_offset(monkeypatch):
    from apps.automation import models as automation_models
    from apps.automation.syscalls.syscall_handlers import handle_watcher_query

    session = _session()
    monkeypatch.setattr(automation_models, "WatcherSignal", TestWatcherSignal)
    base_time = datetime.now(timezone.utc)
    _seed_signal(session, session_id="oldest", signal_timestamp=base_time - timedelta(minutes=2))
    _seed_signal(session, session_id="middle", signal_timestamp=base_time - timedelta(minutes=1))
    _seed_signal(session, session_id="newest", signal_timestamp=base_time)

    result = handle_watcher_query({"limit": 1, "offset": 1}, _ctx(session))

    assert result["total"] == 3
    assert len(result["signals"]) == 1
    assert result["signals"][0]["session_id"] == "middle"

