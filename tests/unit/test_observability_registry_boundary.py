from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock


class _LeaseQuery:
    def __init__(self, row):
        self.row = row

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.row


def test_observability_scheduler_status_node_fails_cleanly_without_task_symbols(monkeypatch):
    from AINDY.runtime.flow_definitions_observability import (
        observability_scheduler_status_node,
    )

    lease = SimpleNamespace(
        owner_id="worker-1",
        acquired_at=None,
        heartbeat_at=None,
        expires_at=None,
    )
    db = MagicMock()
    db.query.return_value = _LeaseQuery(lease)

    monkeypatch.setattr(
        "AINDY.platform_layer.scheduler_service.get_scheduler",
        lambda: SimpleNamespace(running=True),
    )
    monkeypatch.setattr("AINDY.platform_layer.registry.get_symbol", lambda _name: None)

    result = observability_scheduler_status_node({}, {"db": db, "user_id": str(uuid4())})

    assert result["status"] == "FAILURE"
    assert "tasks domain not available" in result["error"]


def test_observability_rippletrace_node_fails_cleanly_without_domain_symbols(monkeypatch):
    from AINDY.runtime.flow_definitions_observability import (
        observability_rippletrace_node,
    )

    query = MagicMock()
    query.filter.return_value = query
    query.count.return_value = 1

    db = MagicMock()
    db.query.return_value = query

    monkeypatch.setattr("AINDY.platform_layer.registry.get_symbol", lambda _name: None)

    result = observability_rippletrace_node(
        {"trace_id": "trace-1"},
        {"db": db, "user_id": str(uuid4())},
    )

    assert result["status"] == "FAILURE"
    assert "rippletrace domain not available" in result["error"]
