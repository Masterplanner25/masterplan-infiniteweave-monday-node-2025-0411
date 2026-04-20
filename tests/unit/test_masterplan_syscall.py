"""
Tests for the sys.v1.masterplan.assert_owned syscall and the analytics
cross-domain guard helper.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_ctx(user_id="user-1", db=None):
    from AINDY.kernel.syscall_registry import SyscallContext
    return SyscallContext(
        execution_unit_id="test-run",
        user_id=user_id,
        capabilities=["masterplan.read"],
        trace_id="test-trace",
        metadata={"_db": db} if db is not None else {},
    )


# ── _handle_assert_masterplan_owned ──────────────────────────────────────────

class TestHandleAssertMasterplanOwned:

    def test_returns_ok_when_ownership_holds(self):
        mock_plan = MagicMock()
        mock_db = MagicMock()

        # Patch at the source module because the handler uses lazy imports
        with patch(
            "apps.masterplan.services.masterplan_service.assert_masterplan_owned",
            return_value=mock_plan,
        ) as mock_assert, patch(
            "AINDY.db.database.SessionLocal",
            return_value=mock_db,
        ):
            from apps.masterplan.syscalls.syscall_handlers import _handle_assert_masterplan_owned
            ctx = _make_ctx(user_id="user-1")
            result = _handle_assert_masterplan_owned(
                {"masterplan_id": "42", "user_id": "user-1"}, ctx
            )

        assert result == {"owned": True, "masterplan_id": "42"}

    def test_raises_value_error_not_found_on_404(self):
        from fastapi import HTTPException

        mock_db = MagicMock()
        with patch(
            "apps.masterplan.services.masterplan_service.assert_masterplan_owned",
            side_effect=HTTPException(
                status_code=404,
                detail={"error": "masterplan_not_found", "message": "MasterPlan not found"},
            ),
        ), patch(
            "AINDY.db.database.SessionLocal",
            return_value=mock_db,
        ):
            from apps.masterplan.syscalls.syscall_handlers import _handle_assert_masterplan_owned
            ctx = _make_ctx(user_id="user-2")
            with pytest.raises(ValueError) as exc_info:
                _handle_assert_masterplan_owned(
                    {"masterplan_id": "99", "user_id": "user-2"}, ctx
                )

        assert exc_info.value.args[0].startswith("NOT_FOUND:")
        assert "MasterPlan not found" in exc_info.value.args[0]

    def test_raises_value_error_forbidden_on_403(self):
        from fastapi import HTTPException

        mock_db = MagicMock()
        with patch(
            "apps.masterplan.services.masterplan_service.assert_masterplan_owned",
            side_effect=HTTPException(status_code=403, detail="Forbidden"),
        ), patch(
            "AINDY.db.database.SessionLocal",
            return_value=mock_db,
        ):
            from apps.masterplan.syscalls.syscall_handlers import _handle_assert_masterplan_owned
            ctx = _make_ctx()
            with pytest.raises(ValueError) as exc_info:
                _handle_assert_masterplan_owned(
                    {"masterplan_id": "5", "user_id": "user-1"}, ctx
                )

        assert exc_info.value.args[0].startswith("FORBIDDEN:")

    def test_uses_external_db_from_metadata(self):
        """Handler must use ctx.metadata['_db'] instead of opening a new session."""
        mock_plan = MagicMock()
        mock_external_db = MagicMock()

        with patch(
            "apps.masterplan.services.masterplan_service.assert_masterplan_owned",
            return_value=mock_plan,
        ) as mock_assert, patch(
            "AINDY.db.database.SessionLocal"
        ) as mock_session_local:
            from apps.masterplan.syscalls.syscall_handlers import _handle_assert_masterplan_owned
            ctx = _make_ctx(db=mock_external_db)
            _handle_assert_masterplan_owned(
                {"masterplan_id": "1", "user_id": "user-1"}, ctx
            )

        # SessionLocal must NOT have been called when external db is provided
        mock_session_local.assert_not_called()
        # assert_masterplan_owned must receive the external db
        call_db = mock_assert.call_args[0][0]
        assert call_db is mock_external_db


# ── register_masterplan_syscall_handlers ─────────────────────────────────────

class TestRegisterMasterplanSyscallHandlers:

    def test_syscall_is_registered_after_call(self):
        from AINDY.kernel.syscall_registry import SYSCALL_REGISTRY
        from apps.masterplan.syscalls.syscall_handlers import register_masterplan_syscall_handlers

        register_masterplan_syscall_handlers()
        assert "sys.v1.masterplan.assert_owned" in SYSCALL_REGISTRY

    def test_registered_entry_has_correct_capability(self):
        from AINDY.kernel.syscall_registry import SYSCALL_REGISTRY
        from apps.masterplan.syscalls.syscall_handlers import register_masterplan_syscall_handlers

        register_masterplan_syscall_handlers()
        entry = SYSCALL_REGISTRY["sys.v1.masterplan.assert_owned"]
        assert entry.capability == "masterplan.read"


# ── analytics router has no direct masterplan service import ──────────────────

def test_analytics_router_has_no_direct_masterplan_service_import():
    import ast
    from pathlib import Path

    source = Path("apps/analytics/routes/analytics_router.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", "") or ""
            assert "masterplan.services" not in module, (
                f"Direct masterplan service import found in analytics_router at line {node.lineno}"
            )


# ── assert_masterplan_owned_via_syscall (integration-ish) ────────────────────

class TestAssertMasterplanOwnedViaSyscall:

    def test_raises_404_when_syscall_returns_not_found_error(self):
        from fastapi import HTTPException

        from apps.analytics.services.masterplan_guard import assert_masterplan_owned_via_syscall

        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch.return_value = {
            "status": "error",
            "error": "NOT_FOUND:MasterPlan not found",
        }

        # get_dispatcher is imported lazily inside the function — patch at source
        with patch(
            "AINDY.kernel.syscall_dispatcher.get_dispatcher",
            return_value=mock_dispatcher,
        ):
            with pytest.raises(HTTPException) as exc_info:
                assert_masterplan_owned_via_syscall("42", "user-1", MagicMock())

        assert exc_info.value.status_code == 404

    def test_raises_403_when_syscall_returns_other_error(self):
        from fastapi import HTTPException

        from apps.analytics.services.masterplan_guard import assert_masterplan_owned_via_syscall

        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch.return_value = {
            "status": "error",
            "error": "Permission denied",
        }

        with patch(
            "AINDY.kernel.syscall_dispatcher.get_dispatcher",
            return_value=mock_dispatcher,
        ):
            with pytest.raises(HTTPException) as exc_info:
                assert_masterplan_owned_via_syscall("42", "user-1", MagicMock())

        assert exc_info.value.status_code == 403

    def test_no_exception_when_syscall_succeeds(self):
        from apps.analytics.services.masterplan_guard import assert_masterplan_owned_via_syscall

        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch.return_value = {
            "status": "success",
            "data": {"owned": True, "masterplan_id": "42"},
        }

        with patch(
            "AINDY.kernel.syscall_dispatcher.get_dispatcher",
            return_value=mock_dispatcher,
        ):
            # Must not raise
            assert_masterplan_owned_via_syscall("42", "user-1", MagicMock())
