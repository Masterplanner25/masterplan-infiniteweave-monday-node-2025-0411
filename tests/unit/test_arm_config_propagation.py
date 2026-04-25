from __future__ import annotations

from unittest.mock import patch

from apps.arm.dao import arm_config_dao


def test_config_write_on_instance_a_visible_on_instance_b(db_session):
    """
    Prove cross-instance config propagation via the DB.

    Two ConfigManager objects share the same DB session, simulating
    two separate API processes connected to the same database.
    """
    from apps.arm.services.deepseek.config_manager_deepseek import ConfigManager

    instance_a = ConfigManager(db=db_session)
    instance_a.update({"temperature": 0.99, "retry_limit": 7})

    instance_b = ConfigManager(db=db_session)
    config_b = instance_b.get_all()

    assert config_b["temperature"] == 0.99, (
        "Instance B did not see Instance A's temperature update - "
        "config is process-local, not DB-propagated"
    )
    assert config_b["retry_limit"] == 7


def test_analyzer_refresh_picks_up_db_change(db_session, monkeypatch):
    """
    Prove that calling _refresh_runtime_config(db) on an existing
    DeepSeekCodeAnalyzer singleton picks up a DB change made after
    the singleton was initialized.
    """
    from apps.arm.services.deepseek.config_manager_deepseek import ConfigManager
    from apps.arm.services.deepseek.deepseek_code_analyzer import DeepSeekCodeAnalyzer

    monkeypatch.setattr(
        "apps.arm.services.deepseek.deepseek_code_analyzer.get_deepseek_client",
        lambda: object(),
    )

    ConfigManager(db=db_session).update({"temperature": 0.1})

    analyzer = DeepSeekCodeAnalyzer.__new__(DeepSeekCodeAnalyzer)
    analyzer.config_manager = ConfigManager(db=db_session)
    analyzer.config = {}
    analyzer.validator = None
    analyzer.file_processor = None
    analyzer._refresh_runtime_config(db_session)
    assert analyzer.config.get("temperature") == 0.1

    ConfigManager(db=db_session).update({"temperature": 0.77})

    analyzer._refresh_runtime_config(db_session)
    assert analyzer.config.get("temperature") == 0.77, (
        "_refresh_runtime_config did not pick up the DB change - "
        "the analyzer is caching stale config"
    )


def test_arm_config_update_emits_system_event(client, auth_headers, db_session):
    """
    Prove PUT /arm/config emits arm.config.updated SystemEvent.
    """
    with patch("apps.arm.routes.arm_router.queue_system_event") as mock_event:
        response = client.put(
            "/arm/config",
            json={"updates": {"temperature": 0.55}},
            headers=auth_headers,
        )

    assert response.status_code == 200, response.text
    mock_event.assert_called_once()
    kwargs = mock_event.call_args.kwargs
    assert kwargs["db"] is not None
    assert kwargs["event_type"] == "arm.config.updated"
    assert kwargs["source"] == "arm"
    assert kwargs["required"] is False
    assert kwargs["user_id"]
    assert kwargs["payload"]["updated_keys"] == ["temperature"]
    assert kwargs["payload"]["config"]["temperature"] == 0.55

    stored = arm_config_dao.get_config(db_session)
    assert stored is not None
    assert stored.temperature == 0.55
