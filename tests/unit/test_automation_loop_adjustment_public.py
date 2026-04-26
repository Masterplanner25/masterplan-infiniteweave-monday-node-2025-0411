from __future__ import annotations

from datetime import datetime, timezone

from apps.automation.public import create_loop_adjustment, get_loop_adjustments, get_user_feedback


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filter_calls = []
        self.order_by_calls = []
        self.limit_value = None
        self.for_update_called = False

    def filter(self, *args):
        self.filter_calls.append(args)
        return self

    def order_by(self, *args):
        self.order_by_calls.append(args)
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def with_for_update(self):
        self.for_update_called = True
        return self

    def all(self):
        return self.rows


class _FakeDB:
    def __init__(self, rows):
        self.query_obj = _FakeQuery(rows)
        self.added = []
        self.flushed = False

    def query(self, _model):
        return self.query_obj

    def add(self, row):
        self.added.append(row)

    def flush(self):
        self.flushed = True


class _FakeRow:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_get_loop_adjustments_returns_dicts():
    rows = [
        _FakeRow(
            id="adj-1",
            user_id="00000000-0000-0000-0000-000000000001",
            decision_type="review_plan",
            prediction_accuracy=88,
            applied_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    ]
    db = _FakeDB(rows)

    result = get_loop_adjustments("00000000-0000-0000-0000-000000000001", db, limit=5)

    assert isinstance(result, list)
    assert result[0]["id"] == "adj-1"
    assert result[0]["decision_type"] == "review_plan"
    assert result[0]["applied_at"].startswith("2026-01-01")
    assert db.query_obj.limit_value == 5


def test_get_loop_adjustments_with_prediction_accuracy_applies_filter():
    db = _FakeDB([])

    get_loop_adjustments(
        "00000000-0000-0000-0000-000000000001",
        db,
        with_prediction_accuracy=True,
    )

    assert len(db.query_obj.filter_calls) == 2


def test_get_loop_adjustments_with_unevaluated_only_applies_filter():
    db = _FakeDB([])

    get_loop_adjustments(
        "00000000-0000-0000-0000-000000000001",
        db,
        unevaluated_only=True,
    )

    assert len(db.query_obj.filter_calls) == 2


def test_get_user_feedback_returns_list_of_dicts():
    rows = [
        _FakeRow(
            id="fb-1",
            feedback_value=1,
            feedback_text="good",
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
    ]
    db = _FakeDB(rows)

    result = get_user_feedback("00000000-0000-0000-0000-000000000001", db, limit=3)

    assert result == [
        {
            "id": "fb-1",
            "feedback_value": 1,
            "feedback_text": "good",
            "created_at": "2026-01-02T00:00:00+00:00",
        }
    ]


def test_create_loop_adjustment_creates_record_and_returns_dict():
    db = _FakeDB([])

    result = create_loop_adjustment(
        db=db,
        user_id="00000000-0000-0000-0000-000000000001",
        trigger_event="manual",
        decision_type="review_plan",
    )

    assert db.added
    assert db.flushed is True
    assert result["trigger_event"] == "manual"
    assert result["decision_type"] == "review_plan"
