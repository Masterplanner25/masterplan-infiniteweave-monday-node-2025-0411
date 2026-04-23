from __future__ import annotations

from pathlib import Path

import AINDY.platform_layer.event_service as event_service
import AINDY.platform_layer.nodus_script_store as nodus_store
import AINDY.platform_layer.platform_loader as platform_loader


def test_nodus_script_store_reconstructs_registry_from_disk(tmp_path, monkeypatch):
    original_registry = dict(nodus_store._NODUS_SCRIPT_REGISTRY)
    monkeypatch.setattr(nodus_store, "_SCRIPTS_DIR", tmp_path)
    nodus_store._NODUS_SCRIPT_REGISTRY.clear()
    try:
        script_path = tmp_path / "restored-script.nodus"
        script_path.write_text("let restored = true", encoding="utf-8")

        loaded = nodus_store.load_script_source("restored-script")

        assert loaded == "let restored = true"
        assert nodus_store._NODUS_SCRIPT_REGISTRY["restored-script"]["restored_from_disk"] is True
        assert nodus_store.list_script_metadata(include_disk=False) == [
            {
                "name": "restored-script",
                "description": None,
                "size_bytes": len("let restored = true".encode("utf-8")),
                "uploaded_at": None,
                "uploaded_by": None,
            }
        ]
    finally:
        nodus_store._NODUS_SCRIPT_REGISTRY.clear()
        nodus_store._NODUS_SCRIPT_REGISTRY.update(original_registry)


def test_webhook_restore_api_is_idempotent():
    original_subscriptions = dict(event_service._SUBSCRIPTIONS)
    event_service._SUBSCRIPTIONS.clear()
    try:
        assert event_service.restore_webhook_subscription(
            subscription_id="sub-1",
            event_type="execution.completed",
            callback_url="https://example.test/hook",
            secret="secret",
            user_id="user-1",
            created_at="2026-04-22T00:00:00+00:00",
        ) is True
        assert event_service.restore_webhook_subscription(
            subscription_id="sub-1",
            event_type="execution.completed",
            callback_url="https://example.test/hook",
            secret="secret",
            user_id="user-1",
            created_at="2026-04-22T00:00:00+00:00",
        ) is False
        assert event_service.has_loaded_webhook_subscription("sub-1") is True
        assert event_service.get_webhook("sub-1") == {
            "id": "sub-1",
            "event_type": "execution.completed",
            "callback_url": "https://example.test/hook",
            "signed": True,
            "created_at": "2026-04-22T00:00:00+00:00",
            "created_by": "user-1",
            "delivery_attempts": 0,
            "delivery_successes": 0,
            "delivery_failures": 0,
            "last_delivered_at": None,
            "last_status": None,
        }
    finally:
        event_service._SUBSCRIPTIONS.clear()
        event_service._SUBSCRIPTIONS.update(original_subscriptions)


def test_platform_loader_uses_public_webhook_restore_api():
    source = Path(platform_loader.__file__).read_text(encoding="utf-8")
    assert "has_loaded_webhook_subscription" in source
    assert "restore_webhook_subscription" in source
    assert "_SUBSCRIPTIONS" not in source
    assert "_load_subscription" not in source
