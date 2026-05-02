from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, call, patch

import pytest

import AINDY.nodus.runtime.aindy_runtime as _mod


def make_event(event_type: str):
    event = MagicMock()
    event.type = event_type
    event.to_dict.return_value = {"type": event_type, "data": {}}
    return event


@contextmanager
def fake_capture_output(max_stdout_chars=None):
    stdout = MagicMock()
    stderr = MagicMock()
    stdout.getvalue.return_value = "stdout"
    stderr.getvalue.return_value = "stderr"
    yield stdout, stderr


@pytest.fixture
def mock_vm():
    vm = MagicMock()
    vm.event_bus.events.return_value = []
    vm.input_fn = None
    vm.max_frames = None
    return vm


@pytest.fixture
def runtime_env(mock_vm):
    loader_instance = MagicMock()
    result_obj = MagicMock()
    result_obj.to_dict.return_value = {"ok": True, "stage": "execute"}

    with (
        patch.object(_mod.NodusRuntime, "__init__", return_value=None),
        patch.object(_mod, "VM", return_value=mock_vm) as mock_vm_ctor,
        patch.object(_mod, "ModuleLoader", return_value=loader_instance) as mock_loader_ctor,
        patch.object(_mod, "capture_output", side_effect=fake_capture_output) as mock_capture,
        patch.object(_mod, "configure_vm_limits") as mock_limits,
        patch.object(_mod, "Result") as mock_result,
        patch.object(_mod, "normalize_filename", return_value="<memory>"),
    ):
        mock_result.success.return_value = result_obj
        rt = _mod.AINDYNodusRuntime(project_root="stdlib-root")
        rt.project_root = "stdlib-root"
        rt.allowed_paths = ["sandbox"]
        rt.allow_input = False
        rt.max_steps = 111
        rt.timeout_ms = 222
        rt.max_stdout_chars = 333
        rt.max_frames = 444
        rt._host_functions = {}
        rt._blocked_input = MagicMock(name="blocked_input")
        rt._invoke_host_function = MagicMock(side_effect=lambda vm, fn, *args: fn(*args))
        yield {
            "rt": rt,
            "vm": mock_vm,
            "vm_ctor": mock_vm_ctor,
            "loader": loader_instance,
            "loader_ctor": mock_loader_ctor,
            "capture": mock_capture,
            "limits": mock_limits,
            "result": mock_result,
            "result_obj": result_obj,
        }


def test_init_defaults_project_root_to_stdlib_dir():
    assert _mod._os.path.isdir(_mod._STDLIB_DIR) is True
    with patch.object(_mod.NodusRuntime, "__init__", return_value=None) as mock_init:
        _mod.AINDYNodusRuntime()
    assert mock_init.call_args.kwargs["project_root"] == _mod._STDLIB_DIR


def test_init_preserves_explicit_project_root():
    with patch.object(_mod.NodusRuntime, "__init__", return_value=None) as mock_init:
        _mod.AINDYNodusRuntime(project_root="custom/path")
    assert mock_init.call_args.kwargs["project_root"] == "custom/path"


def test_stdlib_dir_exists_in_real_tree():
    assert _mod._os.path.isdir(_mod._STDLIB_DIR) is True


def test_register_function_recall_from_adds_stdlib_alias():
    fn = MagicMock()
    with (
        patch.object(_mod.NodusRuntime, "__init__", return_value=None),
        patch.object(_mod.NodusRuntime, "register_function") as mock_register,
    ):
        rt = _mod.AINDYNodusRuntime(project_root="x")
        rt.register_function("recall_from", fn, arity=4)
    assert mock_register.call_args_list == [
        call("recall_from", fn, arity=4),
        call("__memory_stdlib_recall_from", fn, arity=4),
    ]


def test_register_function_recall_all_adds_stdlib_alias():
    fn = MagicMock()
    with (
        patch.object(_mod.NodusRuntime, "__init__", return_value=None),
        patch.object(_mod.NodusRuntime, "register_function") as mock_register,
    ):
        rt = _mod.AINDYNodusRuntime(project_root="x")
        rt.register_function("recall_all", fn, arity=3)
    assert mock_register.call_args_list == [
        call("recall_all", fn, arity=3),
        call("__memory_stdlib_recall_all", fn, arity=3),
    ]


def test_register_function_share_adds_stdlib_alias():
    fn = MagicMock()
    with (
        patch.object(_mod.NodusRuntime, "__init__", return_value=None),
        patch.object(_mod.NodusRuntime, "register_function") as mock_register,
    ):
        rt = _mod.AINDYNodusRuntime(project_root="x")
        rt.register_function("share", fn, arity=1)
    assert mock_register.call_args_list == [
        call("share", fn, arity=1),
        call("__memory_stdlib_share", fn, arity=1),
    ]


def test_register_function_recall_has_no_alias_side_effect():
    fn = MagicMock()
    with (
        patch.object(_mod.NodusRuntime, "__init__", return_value=None),
        patch.object(_mod.NodusRuntime, "register_function") as mock_register,
    ):
        rt = _mod.AINDYNodusRuntime(project_root="x")
        rt.register_function("recall", fn, arity=3)
    assert mock_register.call_args_list == [call("recall", fn, arity=3)]


def test_register_function_set_state_has_no_alias_side_effect():
    fn = MagicMock()
    with (
        patch.object(_mod.NodusRuntime, "__init__", return_value=None),
        patch.object(_mod.NodusRuntime, "register_function") as mock_register,
    ):
        rt = _mod.AINDYNodusRuntime(project_root="x")
        rt.register_function("set_state", fn, arity=2)
    assert mock_register.call_args_list == [call("set_state", fn, arity=2)]


def test_run_source_passes_host_globals_to_module_loader(runtime_env):
    bridge = object()
    rt = runtime_env["rt"]

    rt.run_source("let x = 1", host_globals={"memory_bridge": bridge})

    assert runtime_env["loader_ctor"].call_args.kwargs["host_globals"] == {"memory_bridge": bridge}


def test_run_source_passes_empty_host_globals_to_module_loader_when_none(runtime_env):
    rt = runtime_env["rt"]

    rt.run_source("let x = 1", host_globals=None)

    assert runtime_env["loader_ctor"].call_args.kwargs["host_globals"] == {}


def test_run_source_passes_host_globals_to_vm_constructor(runtime_env):
    bridge = object()
    rt = runtime_env["rt"]

    rt.run_source("let x = 1", host_globals={"memory_bridge": bridge})

    assert runtime_env["vm_ctor"].call_args.kwargs["host_globals"] == {"memory_bridge": bridge}


def test_run_source_transforms_quoted_bare_memory_import(runtime_env):
    rt = runtime_env["rt"]

    rt.run_source('import "memory"\nlet x = memory.recall_from("arm", "q", [], 1)')

    source = runtime_env["loader"].load_module_from_source.call_args.args[0]
    assert source == 'import "memory" as memory\nlet x = memory.recall_from("arm", "q", [], 1)'


def test_run_source_transforms_unquoted_memory_import(runtime_env):
    rt = runtime_env["rt"]

    rt.run_source("import memory\nlet x = memory.recall_from(\"arm\", \"q\", [], 1)")

    source = runtime_env["loader"].load_module_from_source.call_args.args[0]
    assert source == 'import "memory" as memory\nlet x = memory.recall_from("arm", "q", [], 1)'


def test_run_source_does_not_transform_when_memory_reference_has_no_import(runtime_env):
    rt = runtime_env["rt"]
    source_text = 'let x = memory.recall_from("arm", "q", [], 1)'

    rt.run_source(source_text)

    source = runtime_env["loader"].load_module_from_source.call_args.args[0]
    assert source == source_text


def test_run_source_does_not_double_transform_existing_alias(runtime_env):
    rt = runtime_env["rt"]
    source_text = 'import "memory" as memory\nlet x = memory.recall_from("arm", "q", [], 1)'

    rt.run_source(source_text)

    source = runtime_env["loader"].load_module_from_source.call_args.args[0]
    assert source == source_text


def test_run_source_does_not_transform_when_no_memory_reference(runtime_env):
    rt = runtime_env["rt"]
    source_text = 'import "memory"\nlet x = 1'

    rt.run_source(source_text)

    source = runtime_env["loader"].load_module_from_source.call_args.args[0]
    assert source == source_text


def test_run_source_filters_internal_events(runtime_env):
    rt = runtime_env["rt"]
    runtime_env["vm"].event_bus.events.return_value = [
        make_event("vm_compile"),
        make_event("runtime.step"),
        make_event("nodus.gc"),
        make_event("user_event"),
        make_event("task.completed"),
    ]

    rt.run_source("let x = 1")

    assert rt.last_emitted_events == [
        {"type": "user_event", "data": {}},
        {"type": "task.completed", "data": {}},
    ]


def test_run_source_sets_empty_last_emitted_events_when_bus_empty(runtime_env):
    rt = runtime_env["rt"]
    runtime_env["vm"].event_bus.events.return_value = []

    rt.run_source("let x = 1")

    assert rt.last_emitted_events == []


def test_run_source_exception_reraises_and_leaves_last_emitted_events_empty(runtime_env):
    rt = runtime_env["rt"]
    runtime_env["loader"].load_module_from_source.side_effect = ValueError("boom")

    with patch.object(_mod, "coerce_error", return_value=RuntimeError("coerced")):
        with pytest.raises(RuntimeError, match="coerced"):
            rt.run_source("let x = 1")

    assert rt.last_emitted_events == []


def test_run_source_success_returns_result_success_dict(runtime_env):
    rt = runtime_env["rt"]
    runtime_env["result_obj"].to_dict.return_value = {"ok": True, "stage": "execute"}

    result = rt.run_source("let x = 1")

    assert result == {"ok": True, "stage": "execute"}
    runtime_env["result"].success.assert_called_once_with(
        stage="execute",
        filename="<memory>",
        stdout="stdout",
        stderr="stderr",
    )


def test_run_source_calls_configure_vm_limits_with_resolved_defaults(runtime_env):
    rt = runtime_env["rt"]

    rt.run_source("let x = 1")

    runtime_env["limits"].assert_called_once_with(runtime_env["vm"], max_steps=111, timeout_ms=222)


def test_run_source_sets_vm_max_frames_from_runtime_default(runtime_env):
    rt = runtime_env["rt"]

    rt.run_source("let x = 1")

    assert runtime_env["vm"].max_frames == 444


def test_run_source_uses_explicit_max_frames_override(runtime_env):
    rt = runtime_env["rt"]

    rt.run_source("let x = 1", max_frames=999)

    assert runtime_env["vm"].max_frames == 999


def test_run_source_uses_load_module_from_path_when_filename_exists(runtime_env):
    rt = runtime_env["rt"]

    with patch.object(_mod.os.path, "isfile", return_value=True):
        rt.run_source("let x = 1", filename="real_file.nd")

    runtime_env["loader"].load_module_from_path.assert_called_once_with("real_file.nd", auto_run_main=True)
    runtime_env["loader"].load_module_from_source.assert_not_called()


def test_run_source_sets_blocked_input_when_input_not_allowed(runtime_env):
    rt = runtime_env["rt"]
    runtime_env["vm"].input_fn = None

    rt.run_source("let x = 1")

    assert runtime_env["vm"].input_fn is rt._blocked_input

