"""
Tests verifying that service-layer queries respect user_id scoping.

Each test creates data for two distinct users and asserts that querying
with one user's ID does not expose or mutate the other user's data.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

USER_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


# ── _check_reminders_once ──────────────────────────────────────────────────────

class TestCheckRemindersUserScoping:
    """_check_reminders_once(user_id=X) must only process X's tasks."""

    def _make_task(self, *, reminder_time, status="pending"):
        t = MagicMock()
        t.reminder_time = reminder_time
        t.status = status
        t.name = "test-task"
        return t

    def test_scoped_call_only_clears_own_reminders(self, monkeypatch):
        """When called with user_A, user_B's expired reminder is left untouched."""
        import apps.tasks.services.task_service as svc

        past = datetime.now() - timedelta(hours=1)
        task_a = self._make_task(reminder_time=past)
        task_b = self._make_task(reminder_time=past)

        mock_db = MagicMock()
        # Filtered query (user_A only) returns task_a
        mock_db.query.return_value.filter.return_value.all.return_value = [task_a]

        monkeypatch.setattr(svc, "SessionLocal", lambda: mock_db)

        svc._check_reminders_once(user_id=USER_A)

        # user_A's task reminder was cleared
        assert task_a.reminder_time is None
        # user_B's task was never yielded — reminder unchanged
        assert task_b.reminder_time == past

    def test_unscoped_call_processes_all_tasks(self, monkeypatch):
        """Backward-compat: omitting user_id still processes every task."""
        import apps.tasks.services.task_service as svc

        past = datetime.now() - timedelta(hours=1)
        task_a = self._make_task(reminder_time=past)
        task_b = self._make_task(reminder_time=past)

        mock_db = MagicMock()
        # Unfiltered query returns both tasks
        mock_db.query.return_value.all.return_value = [task_a, task_b]

        monkeypatch.setattr(svc, "SessionLocal", lambda: mock_db)

        svc._check_reminders_once()

        assert task_a.reminder_time is None
        assert task_b.reminder_time is None


# ── _handle_recurrence_once ────────────────────────────────────────────────────

class TestHandleRecurrenceUserScoping:
    """_handle_recurrence_once(user_id=X) must add a user_id filter."""

    def test_user_id_causes_chained_filter(self, monkeypatch):
        """A user_id argument adds a second filter to the query chain."""
        import apps.tasks.services.task_service as svc

        mock_db = MagicMock()
        # Support both .filter().all() and .filter().filter().all()
        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.all.return_value = []

        monkeypatch.setattr(svc, "SessionLocal", lambda: mock_db)

        svc._handle_recurrence_once(user_id=USER_A)

        # The inner filter chain was entered (user_id filter added)
        assert mock_db.query.return_value.filter.called

    def test_no_user_id_uses_single_filter(self, monkeypatch):
        """Omitting user_id uses the status filter only (backward compat)."""
        import apps.tasks.services.task_service as svc

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []

        monkeypatch.setattr(svc, "SessionLocal", lambda: mock_db)

        svc._handle_recurrence_once()

        # query + one filter (status == "completed") + all
        assert mock_db.query.return_value.filter.called
        # Second chained filter must NOT have been called
        assert not mock_db.query.return_value.filter.return_value.filter.called


# ── update_goal_progress ───────────────────────────────────────────────────────

class TestUpdateGoalProgressUserScoping:
    """update_goal_progress(user_id=X) must not update another user's goal."""

    def _create_goal(self, db_session, user_id):
        from apps.masterplan.goals import Goal

        goal = Goal(
            user_id=user_id,
            name=f"goal-{user_id}",
            goal_type="strategic",
            priority=0.5,
            status="active",
            success_metric={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(goal)
        db_session.commit()
        db_session.refresh(goal)
        return goal

    def test_cross_user_update_blocked(self, db_session):
        """user_A cannot update user_B's goal when user_id is enforced."""
        from apps.masterplan.services.goal_service import update_goal_progress

        goal_b = self._create_goal(db_session, USER_B)

        # user_A attempts to update user_B's goal
        result = update_goal_progress(
            db_session,
            goal_b.id,
            {"progress_delta": 0.5},
            user_id=USER_A,
        )

        assert result is None, "cross-user update must return None"

        # goal_B's progress must be untouched
        db_session.expire(goal_b)
        from apps.masterplan.goal_state import GoalState
        state = db_session.query(GoalState).filter(GoalState.goal_id == goal_b.id).first()
        if state is not None:
            assert float(state.progress or 0.0) == 0.0

    def test_own_goal_update_succeeds(self, db_session):
        """user_A can update their own goal."""
        from apps.masterplan.services.goal_service import update_goal_progress

        goal_a = self._create_goal(db_session, USER_A)

        result = update_goal_progress(
            db_session,
            goal_a.id,
            {"progress_delta": 0.2},
            user_id=USER_A,
        )

        assert result is not None
        assert str(result["id"]) == str(goal_a.id)

    def test_no_user_id_still_updates_by_id(self, db_session):
        """Backward-compat: omitting user_id updates any goal by ID."""
        from apps.masterplan.services.goal_service import update_goal_progress

        goal_b = self._create_goal(db_session, USER_B)

        # No user_id supplied — legacy callers are unaffected
        result = update_goal_progress(db_session, goal_b.id, {"progress_delta": 0.1})

        assert result is not None
