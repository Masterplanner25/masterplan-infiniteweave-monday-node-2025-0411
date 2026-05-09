from __future__ import annotations

from importlib import import_module
from unittest.mock import patch

from AINDY.kernel.syscall_registry import SYSCALL_REGISTRY


TEST_USER_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"


def test_runtime_agent_helper_syscalls_are_kernel_owned_before_domain_registration():
    expected = {
        "sys.v1.agent.count_runs": "agent.read",
        "sys.v1.agent.list_recent_durations": "agent.read",
        "sys.v1.agent.list_recent_runs": "agent.read",
        "sys.v1.agent.ensure_initial_run": "agent.write",
    }

    for syscall_name, capability in expected.items():
        assert syscall_name in SYSCALL_REGISTRY
        assert SYSCALL_REGISTRY[syscall_name].capability == capability


def test_agent_dispatch_tool_is_not_registered_after_domain_handler_registration():
    from AINDY.kernel.syscall_handlers import register_all_domain_handlers

    register_all_domain_handlers()

    assert "sys.v1.agent.dispatch_tool" not in SYSCALL_REGISTRY


def test_agent_tool_modules_dispatch_directly_to_owned_syscalls():
    cases = [
        ("apps.tasks.agents.tools", "task_create", {"task_name": "Write tests"}, "sys.v1.task.create", "task.create"),
        ("apps.tasks.agents.tools", "task_complete", {"task_id": "t-1"}, "sys.v1.task.complete_full", "task.complete_full"),
        ("apps.search.agents.tools", "leadgen_search", {"query": "acme"}, "sys.v1.leadgen.search_ai", "leadgen.search_ai"),
        ("apps.search.agents.tools", "research_query", {"query": "market"}, "sys.v1.research.query", "research.query"),
        ("apps.masterplan.agents.tools", "genesis_message", {"message": "Next step?"}, "sys.v1.genesis.message", "genesis.message"),
        ("apps.arm.agents.tools", "arm_analyze", {"target": "repo"}, "sys.v1.arm.analyze", "arm.analyze"),
        ("apps.arm.agents.tools", "arm_generate", {"prompt": "refactor"}, "sys.v1.arm.generate", "arm.generate"),
        ("apps.agent.agents.tools", "memory_recall", {"query": "auth"}, "sys.v1.memory.read", "memory.read"),
    ]

    for module_name, fn_name, args, syscall_name, capability in cases:
        module = import_module(module_name)
        fn = getattr(module, fn_name)
        with patch(f"{module_name}.invoke_tool_syscall", return_value={"ok": True}) as invoke:
            fn(args, TEST_USER_ID, None)
        invoke.assert_called_once_with(
            syscall_name,
            args,
            user_id=TEST_USER_ID,
            capability=capability,
        )


def test_memory_write_adds_agent_source_before_direct_syscall_dispatch():
    import apps.agent.agents.tools as agent_tools

    with patch("apps.agent.agents.tools.invoke_tool_syscall", return_value={"node": {"id": "n-1"}}) as invoke:
        result = agent_tools.memory_write({"content": "note"}, TEST_USER_ID, None)

    assert result == {"node_id": "n-1"}
    invoke.assert_called_once()
    dispatched_name, dispatched_payload = invoke.call_args.args
    assert dispatched_name == "sys.v1.memory.write"
    assert dispatched_payload["content"] == "note"
    assert dispatched_payload["source"] == "agent"
    assert invoke.call_args.kwargs["user_id"] == TEST_USER_ID
    assert invoke.call_args.kwargs["capability"] == "memory.write"
