from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import AINDY.platform_layer.platform_loader as loader


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self.filter_arg = None

    def filter(self, arg):
        self.filter_arg = arg
        return self

    def all(self):
        return [row for row in self._rows if getattr(row, "is_active", True)]


class _FakeSession:
    def __init__(self, rows_by_model):
        self._rows_by_model = rows_by_model
        self.queries = {}

    def query(self, model):
        query = _FakeQuery(self._rows_by_model[model])
        self.queries[model] = query
        return query


def test_load_active_dynamic_nodes_only(monkeypatch):
    import AINDY.db.models.dynamic_node as dynamic_node_module
    import AINDY.runtime.flow_engine as flow_engine
    import AINDY.platform_layer.node_registry as node_registry

    class FakeDynamicNode:
        is_active = object()

    rows = [
        SimpleNamespace(
            name="existing-node",
            node_type="plugin",
            handler_config={"handler": "pkg:existing"},
            secret="s1",
            created_by="user-1",
            is_active=True,
        ),
        SimpleNamespace(
            name="webhook-node",
            node_type="webhook",
            handler_config={"url": "https://example.test/hook", "timeout_seconds": 17},
            secret="s2",
            created_by="user-2",
            is_active=True,
        ),
        SimpleNamespace(
            name="inactive-node",
            node_type="plugin",
            handler_config={"handler": "pkg:inactive"},
            secret="s3",
            created_by="user-3",
            is_active=False,
        ),
    ]
    db = _FakeSession({FakeDynamicNode: rows})
    calls: list[dict] = []

    monkeypatch.setattr(dynamic_node_module, "DynamicNode", FakeDynamicNode)
    monkeypatch.setattr(flow_engine, "NODE_REGISTRY", {"existing-node": object()})

    def fake_register(name, node_type, handler, **kwargs):
        calls.append(
            {
                "name": name,
                "node_type": node_type,
                "handler": handler,
                **kwargs,
            }
        )

    monkeypatch.setattr(node_registry, "register_external_node", fake_register)

    stats = {"nodes_loaded": 0, "nodes_skipped": 0}
    loader._load_nodes(db, stats)

    assert db.queries[FakeDynamicNode].filter_arg is FakeDynamicNode.is_active
    assert stats["nodes_loaded"] == 1
    assert stats["nodes_skipped"] == 1
    assert calls == [
        {
            "name": "webhook-node",
            "node_type": "webhook",
            "handler": "https://example.test/hook",
            "timeout_seconds": 17,
            "secret": "s2",
            "user_id": "user-2",
            "overwrite": False,
            "db": None,
        }
    ]


def test_load_dynamic_flows_only_active(monkeypatch):
    import AINDY.db.models.dynamic_flow as dynamic_flow_module
    import AINDY.runtime.flow_engine as flow_engine
    import AINDY.runtime.flow_registry as flow_registry

    class FakeDynamicFlow:
        is_active = object()

    rows = [
        SimpleNamespace(
            name="existing-flow",
            definition_json={"nodes": ["a"], "edges": {"a": ["b"]}, "start": "a", "end": ["b"]},
            created_by="user-1",
            is_active=True,
        ),
        SimpleNamespace(
            name="new-flow",
            definition_json={"nodes": ["start", "end"], "edges": {"start": ["end"]}, "start": "start", "end": ["end"]},
            created_by="user-2",
            is_active=True,
        ),
        SimpleNamespace(
            name="inactive-flow",
            definition_json={"nodes": ["x"], "edges": {}, "start": "x", "end": ["x"]},
            created_by="user-3",
            is_active=False,
        ),
    ]
    db = _FakeSession({FakeDynamicFlow: rows})
    calls: list[dict] = []

    monkeypatch.setattr(dynamic_flow_module, "DynamicFlow", FakeDynamicFlow)
    monkeypatch.setattr(flow_engine, "FLOW_REGISTRY", {"existing-flow": object()})

    def fake_register(name, **kwargs):
        calls.append({"name": name, **kwargs})

    monkeypatch.setattr(flow_registry, "register_dynamic_flow", fake_register)

    stats = {"flows_loaded": 0, "flows_skipped": 0}
    loader._load_flows(db, stats)

    assert db.queries[FakeDynamicFlow].filter_arg is FakeDynamicFlow.is_active
    assert stats["flows_loaded"] == 1
    assert stats["flows_skipped"] == 1
    assert calls == [
        {
            "name": "new-flow",
            "nodes": ["start", "end"],
            "edges": {"start": ["end"]},
            "start": "start",
            "end": ["end"],
            "user_id": "user-2",
            "overwrite": False,
            "db": None,
        }
    ]


def test_load_webhooks_only_active(monkeypatch):
    import AINDY.db.models.webhook_subscription as webhook_model_module
    import AINDY.platform_layer.event_service as event_service

    class FakeWebhookSubscription:
        is_active = object()

    now = datetime(2026, 4, 4, 12, 0, tzinfo=timezone.utc)
    rows = [
        SimpleNamespace(
            id="existing-id",
            event_type="execution.completed",
            callback_url="https://example.test/existing",
            secret="one",
            created_by="user-1",
            created_at=now,
            is_active=True,
        ),
        SimpleNamespace(
            id="new-id",
            event_type="task.completed",
            callback_url="https://example.test/new",
            secret="two",
            created_by="user-2",
            created_at=now,
            is_active=True,
        ),
        SimpleNamespace(
            id="inactive-id",
            event_type="task.failed",
            callback_url="https://example.test/inactive",
            secret="three",
            created_by="user-3",
            created_at=now,
            is_active=False,
        ),
    ]
    db = _FakeSession({FakeWebhookSubscription: rows})
    calls: list[dict] = []

    monkeypatch.setattr(webhook_model_module, "WebhookSubscription", FakeWebhookSubscription)
    monkeypatch.setattr(event_service, "has_loaded_webhook_subscription", lambda sub_id: sub_id == "existing-id")
    monkeypatch.setattr(event_service, "restore_webhook_subscription", lambda **kwargs: calls.append(kwargs) or True)

    stats = {"webhooks_loaded": 0, "webhooks_skipped": 0}
    loader._load_webhooks(db, stats)

    assert db.queries[FakeWebhookSubscription].filter_arg is FakeWebhookSubscription.is_active
    assert stats["webhooks_loaded"] == 1
    assert stats["webhooks_skipped"] == 1
    assert calls == [
        {
            "subscription_id": "new-id",
            "event_type": "task.completed",
            "callback_url": "https://example.test/new",
            "secret": "two",
            "user_id": "user-2",
            "created_at": now.isoformat(),
        }
    ]


def test_loader_handles_db_failure_gracefully(caplog):
    db = MagicMock()
    db.query.side_effect = RuntimeError("db offline")

    with caplog.at_level("ERROR"):
        stats = loader.load_dynamic_registry(db)

    assert stats == {
        "nodes_loaded": 0,
        "nodes_skipped": 0,
        "flows_loaded": 0,
        "flows_skipped": 0,
        "webhooks_loaded": 0,
        "webhooks_skipped": 0,
    }
    assert "cannot query dynamic_nodes" in caplog.text
    assert "cannot query dynamic_flows" in caplog.text
    assert "cannot query webhook_subscriptions" in caplog.text


def test_loader_skips_bad_row_and_continues(monkeypatch, caplog):
    import AINDY.db.models.dynamic_node as dynamic_node_module
    import AINDY.runtime.flow_engine as flow_engine
    import AINDY.platform_layer.node_registry as node_registry

    class FakeDynamicNode:
        is_active = object()

    rows = [
        SimpleNamespace(
            name="bad-node",
            node_type="plugin",
            handler_config={"handler": "pkg:bad"},
            secret="bad",
            created_by="user-1",
            is_active=True,
        ),
        SimpleNamespace(
            name="good-node",
            node_type="plugin",
            handler_config={"handler": "pkg:good"},
            secret="good",
            created_by="user-2",
            is_active=True,
        ),
    ]
    db = _FakeSession({FakeDynamicNode: rows})

    monkeypatch.setattr(dynamic_node_module, "DynamicNode", FakeDynamicNode)
    monkeypatch.setattr(flow_engine, "NODE_REGISTRY", {})

    def fake_register(name, *_args, **_kwargs):
        if name == "bad-node":
            raise ValueError("broken handler")

    monkeypatch.setattr(node_registry, "register_external_node", fake_register)

    stats = {"nodes_loaded": 0, "nodes_skipped": 0}
    with caplog.at_level("WARNING"):
        loader._load_nodes(db, stats)

    assert stats["nodes_loaded"] == 1
    assert stats["nodes_skipped"] == 1
    assert "skipping node 'bad-node'" in caplog.text or 'skipping node "bad-node"' in caplog.text


def test_load_dynamic_registry_reports_combined_restore_summary(monkeypatch):
    import AINDY.db.models.dynamic_node as dynamic_node_module
    import AINDY.db.models.dynamic_flow as dynamic_flow_module
    import AINDY.db.models.webhook_subscription as webhook_model_module
    import AINDY.runtime.flow_engine as flow_engine
    import AINDY.platform_layer.node_registry as node_registry
    import AINDY.runtime.flow_registry as flow_registry
    import AINDY.platform_layer.event_service as event_service

    class FakeDynamicNode:
        is_active = object()

    class FakeDynamicFlow:
        is_active = object()

    class FakeWebhookSubscription:
        is_active = object()

    now = datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc)
    db = _FakeSession(
        {
            FakeDynamicNode: [
                SimpleNamespace(
                    name="existing-node",
                    node_type="plugin",
                    handler_config={"handler": "pkg:existing"},
                    secret="s1",
                    created_by="user-1",
                    is_active=True,
                ),
                SimpleNamespace(
                    name="restored-node",
                    node_type="plugin",
                    handler_config={"handler": "pkg:restored"},
                    secret="s2",
                    created_by="user-2",
                    is_active=True,
                ),
            ],
            FakeDynamicFlow: [
                SimpleNamespace(
                    name="existing-flow",
                    definition_json={"nodes": ["a"], "edges": {}, "start": "a", "end": ["a"]},
                    created_by="user-1",
                    is_active=True,
                ),
                SimpleNamespace(
                    name="restored-flow",
                    definition_json={"nodes": ["start", "end"], "edges": {"start": ["end"]}, "start": "start", "end": ["end"]},
                    created_by="user-2",
                    is_active=True,
                ),
            ],
            FakeWebhookSubscription: [
                SimpleNamespace(
                    id="existing-sub",
                    event_type="execution.completed",
                    callback_url="https://example.test/existing",
                    secret="one",
                    created_by="user-1",
                    created_at=now,
                    is_active=True,
                ),
                SimpleNamespace(
                    id="restored-sub",
                    event_type="task.completed",
                    callback_url="https://example.test/restored",
                    secret="two",
                    created_by="user-2",
                    created_at=now,
                    is_active=True,
                ),
            ],
        }
    )

    node_calls: list[str] = []
    flow_calls: list[str] = []
    webhook_calls: list[str] = []

    monkeypatch.setattr(dynamic_node_module, "DynamicNode", FakeDynamicNode)
    monkeypatch.setattr(dynamic_flow_module, "DynamicFlow", FakeDynamicFlow)
    monkeypatch.setattr(webhook_model_module, "WebhookSubscription", FakeWebhookSubscription)
    monkeypatch.setattr(flow_engine, "NODE_REGISTRY", {"existing-node": object()})
    monkeypatch.setattr(flow_engine, "FLOW_REGISTRY", {"existing-flow": object()})
    monkeypatch.setattr(node_registry, "register_external_node", lambda name, *_args, **_kwargs: node_calls.append(name))
    monkeypatch.setattr(flow_registry, "register_dynamic_flow", lambda name, **_kwargs: flow_calls.append(name))
    monkeypatch.setattr(event_service, "has_loaded_webhook_subscription", lambda sub_id: sub_id == "existing-sub")
    monkeypatch.setattr(event_service, "restore_webhook_subscription", lambda **kwargs: webhook_calls.append(kwargs["subscription_id"]) or True)

    stats = loader.load_dynamic_registry(db)

    assert stats == {
        "nodes_loaded": 1,
        "nodes_skipped": 1,
        "flows_loaded": 1,
        "flows_skipped": 1,
        "webhooks_loaded": 1,
        "webhooks_skipped": 1,
    }
    assert node_calls == ["restored-node"]
    assert flow_calls == ["restored-flow"]
    assert webhook_calls == ["restored-sub"]
