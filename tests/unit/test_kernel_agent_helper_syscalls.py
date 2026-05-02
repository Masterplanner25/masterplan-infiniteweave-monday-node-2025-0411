from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from AINDY.kernel import syscall_registry
from AINDY.kernel.syscall_registry import SyscallContext


TEST_USER_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"


def _ctx(db) -> SyscallContext:
    return SyscallContext(
        execution_unit_id="eu-agent-helper",
        user_id=TEST_USER_ID,
        capabilities=["agent.read", "agent.write"],
        trace_id="trace-agent-helper",
        metadata={"_db": db},
    )


def test_count_runs_handler_counts_filtered_rows():
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value = query
    query.count.return_value = 3

    result = syscall_registry._handle_agent_count_runs(
        {"user_id": TEST_USER_ID, "status": ["approved", "executing"]},
        _ctx(db),
    )

    assert result == {"count": 3}
    db.query.assert_called_once()
    assert query.filter.call_count >= 2


def test_list_recent_runs_handler_serializes_rows():
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query

    row_one = MagicMock()
    row_two = MagicMock()
    query.all.return_value = [row_one, row_two]

    with patch("AINDY.agents.agent_runtime.run_to_dict", side_effect=[{"run_id": "r1"}, {"run_id": "r2"}]):
        result = syscall_registry._handle_agent_list_recent_runs(
            {"user_id": TEST_USER_ID, "limit": 2},
            _ctx(db),
        )

    assert result == {"runs": [{"run_id": "r1"}, {"run_id": "r2"}]}


def test_ensure_initial_run_handler_creates_missing_sentinel():
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value = query
    query.first.return_value = None

    created_run_id = uuid.uuid4()

    def _refresh(run):
        run.id = created_run_id

    db.refresh.side_effect = _refresh

    result = syscall_registry._handle_agent_ensure_initial_run(
        {"user_id": TEST_USER_ID},
        _ctx(db),
    )

    assert result == {"run_id": str(created_run_id), "created": True}
    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()


def test_list_recent_durations_handler_returns_serialized_times():
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value = query

    started_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    completed_at = datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc)
    row = MagicMock(started_at=started_at, completed_at=completed_at, created_at=started_at)
    query.all.return_value = [row]

    result = syscall_registry._handle_agent_list_recent_durations(
        {"user_id": TEST_USER_ID, "window_hours": 4},
        _ctx(db),
    )

    assert result == {
        "durations": [
            {
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
            }
        ],
        "count": 1,
    }
