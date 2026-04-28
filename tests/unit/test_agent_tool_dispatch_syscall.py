from __future__ import annotations

from unittest.mock import patch

from AINDY.kernel.syscall_registry import SYSCALL_REGISTRY, SyscallContext


TEST_USER_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"


def _ctx(*, capabilities: list[str]) -> SyscallContext:
    return SyscallContext(
        execution_unit_id="eu-agent-dispatch",
        user_id=TEST_USER_ID,
        capabilities=capabilities,
        trace_id="trace-agent-dispatch",
    )


def test_agent_dispatch_tool_registered_after_domain_handler_registration():
    from AINDY.kernel.syscall_handlers import register_all_domain_handlers

    register_all_domain_handlers()

    assert "sys.v1.agent.dispatch_tool" in SYSCALL_REGISTRY
    entry = SYSCALL_REGISTRY["sys.v1.agent.dispatch_tool"]
    assert entry.capability == "agent.tool_dispatch"
    assert entry.input_schema["required"] == ["tool_name", "payload", "user_id", "syscall_name"]


def test_agent_dispatch_tool_dispatch_returns_standard_envelope():
    from AINDY.kernel.syscall_dispatcher import get_dispatcher
    from AINDY.kernel.syscall_handlers import register_all_domain_handlers

    register_all_domain_handlers()

    with patch("AINDY.kernel.syscall_dispatcher.get_dispatcher") as mock_get_dispatcher:
        mock_get_dispatcher.return_value.dispatch.return_value = {
            "status": "success",
            "data": {"ok": True, "value": 7},
            "error": None,
        }
        result = get_dispatcher().dispatch(
            "sys.v1.agent.dispatch_tool",
            {
                "tool_name": "test.tool",
                "payload": {"x": 1},
                "user_id": TEST_USER_ID,
                "syscall_name": "sys.v1.test.tool",
                "capability": "test.tool",
            },
            _ctx(capabilities=["agent.tool_dispatch"]),
        )

    assert result["status"] == "success"
    assert result["data"] == {"ok": True, "value": 7}
    assert result["trace_id"] == "trace-agent-dispatch"
    assert result["execution_unit_id"] == "eu-agent-dispatch"
    assert result["syscall"] == "sys.v1.agent.dispatch_tool"
    assert result["version"] == "v1"
    assert isinstance(result["duration_ms"], int)
    assert result["error"] is None
