from __future__ import annotations

import ast
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[2]


def test_apps_do_not_import_private_aindy_symbols():
    app_root = ROOT / "apps"
    violations: list[str] = []

    for path in app_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if not node.module or not node.module.startswith("AINDY."):
                continue
            private_names = [alias.name for alias in node.names if alias.name.startswith("_")]
            if private_names:
                violations.append(
                    f"{path.relative_to(ROOT)}:{node.lineno}:{node.module}:{','.join(private_names)}"
                )

    assert violations == []


def test_automation_memory_wrappers_use_public_runtime_facade():
    from apps.automation.syscalls.syscall_handlers import (
        _mas_memory_list,
        _mas_memory_trace,
        _mas_memory_tree,
    )

    context = MagicMock(user_id="user-1")
    memory_runtime = MagicMock(
        list_memory_nodes=MagicMock(return_value={"nodes": [], "count": 0, "path": "/tmp"}),
        get_memory_tree=MagicMock(return_value={"tree": {}, "node_count": 0, "path": "/tmp"}),
        trace_memory_chain=MagicMock(return_value={"chain": [], "depth": 0, "path": "/tmp"}),
    )

    with patch.dict(sys.modules, {"AINDY.platform_layer.memory_runtime": memory_runtime}):
        assert _mas_memory_list({"path": "/tmp"}, context)["path"] == "/tmp"
        assert _mas_memory_tree({"path": "/tmp"}, context)["path"] == "/tmp"
        assert _mas_memory_trace({"path": "/tmp"}, context)["path"] == "/tmp"

    memory_runtime.list_memory_nodes.assert_called_once_with({"path": "/tmp"}, context)
    memory_runtime.get_memory_tree.assert_called_once_with({"path": "/tmp"}, context)
    memory_runtime.trace_memory_chain.assert_called_once_with({"path": "/tmp"}, context)


def test_automation_watcher_ingest_uses_public_watcher_contract():
    from apps.automation.syscalls.syscall_handlers import _handle_watcher_ingest

    mock_db = MagicMock()
    watcher_signal_module = MagicMock(WatcherSignal=MagicMock(return_value=MagicMock()))
    watcher_contract = MagicMock(
        get_valid_signal_types=MagicMock(return_value={"app_focused", "session_ended"}),
        get_valid_activity_types=MagicMock(return_value={"coding"}),
        parse_signal_timestamp=MagicMock(return_value=None),
    )
    context = MagicMock(user_id="a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    payload = {
        "signals": [
            {
                "signal_type": "app_focused",
                "activity_type": "coding",
                "timestamp": "2026-01-01T10:00:00Z",
                "session_id": "sess-1",
                "user_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
            }
        ]
    }

    with patch.dict(
        sys.modules,
        {
            "AINDY.db.database": MagicMock(SessionLocal=MagicMock(return_value=mock_db)),
            "apps.automation.models": watcher_signal_module,
            "AINDY.platform_layer.watcher_contract": watcher_contract,
        },
    ):
        result = _handle_watcher_ingest(payload, context)

    assert result["watcher_ingest_result"]["accepted"] == 1
    watcher_contract.get_valid_signal_types.assert_called()
    watcher_contract.get_valid_activity_types.assert_called()
    watcher_contract.parse_signal_timestamp.assert_called_once_with("2026-01-01T10:00:00Z")
