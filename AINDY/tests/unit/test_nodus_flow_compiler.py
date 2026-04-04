"""
tests/unit/test_nodus_flow_compiler.py

Unit tests for services/nodus_flow_compiler.py — Sprint 3 (Nodus Flow DSL).

Coverage groups
===============
A. _condition_truthy / _condition_falsy helpers
B. NodusFlowGraph.step() validation
C. NodusFlowGraph.compile() — sequential (no conditions)
D. NodusFlowGraph.compile() — conditional edges
E. NodusFlowGraph.compile() — edge cases
F. compile_nodus_flow() — happy path (mocked VM)
G. compile_nodus_flow() — error paths
H. nodus.flow.compile node
I. nodus.flow.run node
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from runtime.nodus_flow_compiler import (
    NodusFlowGraph,
    _condition_falsy,
    _condition_truthy,
    compile_nodus_flow,
)


# ===========================================================================
# A. Condition helper closures
# ===========================================================================

class TestConditionTruthy:
    def test_truthy_when_key_present_and_set(self):
        fn = _condition_truthy("ready")
        assert fn({"ready": True}) is True

    def test_truthy_when_key_is_string(self):
        fn = _condition_truthy("ready")
        assert fn({"ready": "yes"}) is True

    def test_falsy_when_key_is_false(self):
        fn = _condition_truthy("ready")
        assert fn({"ready": False}) is False

    def test_falsy_when_key_missing(self):
        fn = _condition_truthy("ready")
        assert fn({}) is False

    def test_falsy_when_key_is_empty_string(self):
        fn = _condition_truthy("ready")
        assert fn({"ready": ""}) is False

    def test_falsy_when_key_is_zero(self):
        fn = _condition_truthy("ready")
        assert fn({"ready": 0}) is False

    def test_function_has_descriptive_name(self):
        fn = _condition_truthy("my_key")
        assert "my_key" in fn.__name__


class TestConditionFalsy:
    def test_true_when_key_missing(self):
        fn = _condition_falsy("ready")
        assert fn({}) is True

    def test_true_when_key_is_false(self):
        fn = _condition_falsy("ready")
        assert fn({"ready": False}) is True

    def test_false_when_key_is_truthy(self):
        fn = _condition_falsy("ready")
        assert fn({"ready": True}) is False

    def test_true_when_key_is_empty_string(self):
        fn = _condition_falsy("ready")
        assert fn({"ready": ""}) is True

    def test_function_has_descriptive_name(self):
        fn = _condition_falsy("my_key")
        assert "my_key" in fn.__name__

    def test_truthy_and_falsy_are_complementary(self):
        state_true = {"flag": True}
        state_false = {"flag": False}
        t = _condition_truthy("flag")
        f = _condition_falsy("flag")
        assert t(state_true) != f(state_true)
        assert t(state_false) != f(state_false)


# ===========================================================================
# B. NodusFlowGraph.step() validation
# ===========================================================================

class TestNodusFlowGraphStep:
    def test_step_requires_string(self):
        graph = NodusFlowGraph("test")
        with pytest.raises(ValueError, match="non-empty string"):
            graph.step(123)  # type: ignore

    def test_step_rejects_empty_string(self):
        graph = NodusFlowGraph("test")
        with pytest.raises(ValueError, match="non-empty string"):
            graph.step("")

    def test_step_rejects_whitespace_only(self):
        graph = NodusFlowGraph("test")
        with pytest.raises(ValueError, match="non-empty string"):
            graph.step("   ")

    def test_step_strips_whitespace_from_node_name(self):
        graph = NodusFlowGraph("test")
        graph.step("  fetch_data  ")
        assert graph._steps[0]["node"] == "fetch_data"

    def test_step_records_when_condition(self):
        graph = NodusFlowGraph("test")
        graph.step("analyze", when="data_ready")
        assert graph._steps[0]["when"] == "data_ready"

    def test_step_defaults_when_to_none(self):
        graph = NodusFlowGraph("test")
        graph.step("fetch_data")
        assert graph._steps[0]["when"] is None

    def test_multiple_steps_recorded_in_order(self):
        graph = NodusFlowGraph("test")
        graph.step("a")
        graph.step("b")
        graph.step("c")
        nodes = [s["node"] for s in graph._steps]
        assert nodes == ["a", "b", "c"]


# ===========================================================================
# C. NodusFlowGraph.compile() — sequential steps (no conditions)
# ===========================================================================

class TestNodusFlowGraphCompileSequential:
    def test_single_step_produces_terminal_node(self):
        graph = NodusFlowGraph("test")
        graph.step("only")
        flow = graph.compile()
        assert flow["start"] == "only"
        assert flow["edges"]["only"] == []
        assert "only" in flow["end"]

    def test_two_steps_simple_edge(self):
        graph = NodusFlowGraph("test")
        graph.step("a")
        graph.step("b")
        flow = graph.compile()
        assert flow["start"] == "a"
        assert flow["edges"]["a"] == ["b"]
        assert flow["edges"]["b"] == []
        assert flow["end"] == ["b"]

    def test_three_steps_chain(self):
        graph = NodusFlowGraph("test")
        graph.step("fetch")
        graph.step("process")
        graph.step("store")
        flow = graph.compile()
        assert flow["start"] == "fetch"
        assert flow["edges"]["fetch"] == ["process"]
        assert flow["edges"]["process"] == ["store"]
        assert flow["edges"]["store"] == []
        assert flow["end"] == ["store"]

    def test_all_steps_present_in_edges(self):
        graph = NodusFlowGraph("test")
        names = ["a", "b", "c", "d"]
        for n in names:
            graph.step(n)
        flow = graph.compile()
        assert set(flow["edges"].keys()) == set(names)

    def test_no_steps_raises_value_error(self):
        graph = NodusFlowGraph("empty")
        with pytest.raises(ValueError, match="no steps"):
            graph.compile()


# ===========================================================================
# D. NodusFlowGraph.compile() — conditional edges
# ===========================================================================

class TestNodusFlowGraphCompileConditional:
    def _three_step_conditional(self):
        """a → b(when="flag") → c"""
        graph = NodusFlowGraph("test")
        graph.step("a")
        graph.step("b", when="flag")
        graph.step("c")
        return graph.compile()

    def test_conditional_produces_two_edges_from_previous(self):
        flow = self._three_step_conditional()
        edges_a = flow["edges"]["a"]
        assert len(edges_a) == 2

    def test_conditional_truthy_edge_targets_conditional_node(self):
        flow = self._three_step_conditional()
        truthy_edge = flow["edges"]["a"][0]
        assert truthy_edge["target"] == "b"

    def test_conditional_falsy_edge_targets_step_after_conditional(self):
        flow = self._three_step_conditional()
        falsy_edge = flow["edges"]["a"][1]
        assert falsy_edge["target"] == "c"

    def test_conditional_truthy_closure_evaluates_correctly(self):
        flow = self._three_step_conditional()
        truthy_fn = flow["edges"]["a"][0]["condition"]
        assert truthy_fn({"flag": True}) is True
        assert truthy_fn({"flag": False}) is False

    def test_conditional_falsy_closure_evaluates_correctly(self):
        flow = self._three_step_conditional()
        falsy_fn = flow["edges"]["a"][1]["condition"]
        assert falsy_fn({"flag": True}) is False
        assert falsy_fn({"flag": False}) is True

    def test_node_after_conditional_has_simple_edge(self):
        flow = self._three_step_conditional()
        # "b" → "c" is unconditional
        assert flow["edges"]["b"] == ["c"]

    def test_last_node_is_terminal(self):
        flow = self._three_step_conditional()
        assert flow["edges"]["c"] == []
        assert "c" in flow["end"]

    def test_start_is_always_first_declared_step(self):
        flow = self._three_step_conditional()
        assert flow["start"] == "a"


# ===========================================================================
# E. NodusFlowGraph.compile() — edge cases
# ===========================================================================

class TestNodusFlowGraphCompileEdgeCases:
    def test_conditional_on_last_step_emits_only_truthy_edge(self):
        """a → b(when="flag") where b is the last step."""
        graph = NodusFlowGraph("test")
        graph.step("a")
        graph.step("b", when="flag")
        flow = graph.compile()
        # "a" gets only one conditional edge (truthy → b)
        edges_a = flow["edges"]["a"]
        assert len(edges_a) == 1
        assert edges_a[0]["target"] == "b"
        assert edges_a[0]["condition"]({"flag": True}) is True

    def test_conditional_on_last_step_makes_previous_node_terminal(self):
        """When the only reachable path is conditional, "a" is also an end node."""
        graph = NodusFlowGraph("test")
        graph.step("a")
        graph.step("b", when="flag")
        flow = graph.compile()
        assert "a" in flow["end"]
        assert "b" in flow["end"]

    def test_multiple_conditionals_in_sequence(self):
        """a → b(when=x) → c(when=y) → d"""
        graph = NodusFlowGraph("test")
        graph.step("a")
        graph.step("b", when="x")
        graph.step("c", when="y")
        graph.step("d")
        flow = graph.compile()
        # a: if x→b, else→c
        assert flow["edges"]["a"][0]["target"] == "b"
        assert flow["edges"]["a"][1]["target"] == "c"
        # b: if y→c, else→d
        assert flow["edges"]["b"][0]["target"] == "c"
        assert flow["edges"]["b"][1]["target"] == "d"
        # c→d unconditional
        assert flow["edges"]["c"] == ["d"]
        # d terminal
        assert flow["end"] == ["d"]

    def test_first_step_unconditional_when_no_when(self):
        graph = NodusFlowGraph("test")
        graph.step("start")
        graph.step("end")
        flow = graph.compile()
        # Simple string edge, not a list of dicts
        assert flow["edges"]["start"] == ["end"]


# ===========================================================================
# F. compile_nodus_flow() — happy path (mocked Nodus VM)
# ===========================================================================

def _make_fake_run(*node_names, conditions=None):
    """
    Return a side_effect for NodusRuntime.run_source that simulates the Nodus
    VM executing a flow script — it calls flow.step() on the injected graph.

    conditions: dict mapping step index (int) → when key string
    """
    _conditions = conditions or {}

    def _run(script, filename=None, initial_globals=None, host_globals=None):
        graph = (host_globals or {}).get("flow")
        if graph is not None:
            for i, name in enumerate(node_names):
                when = _conditions.get(i)
                graph.step(name, when=when)
        return {"ok": True}
    return _run


class TestCompileNodusFlow:
    def test_returns_valid_flow_dict_for_sequential_steps(self):
        mock_rt = MagicMock()
        mock_rt.run_source.side_effect = _make_fake_run("a", "b", "c")
        with patch("nodus.runtime.embedding.NodusRuntime", return_value=mock_rt):
            flow = compile_nodus_flow("flow.step('a')...", "my_flow")
        assert flow["start"] == "a"
        assert flow["end"] == ["c"]
        assert "a" in flow["edges"]
        assert "b" in flow["edges"]
        assert "c" in flow["edges"]

    def test_returns_valid_flow_dict_with_conditional(self):
        mock_rt = MagicMock()
        # step("a"), step("b", when="flag"), step("c")
        mock_rt.run_source.side_effect = _make_fake_run("a", "b", "c", conditions={1: "flag"})
        with patch("nodus.runtime.embedding.NodusRuntime", return_value=mock_rt):
            flow = compile_nodus_flow("...", "cond_flow")
        edges_a = flow["edges"]["a"]
        assert len(edges_a) == 2
        assert edges_a[0]["target"] == "b"
        assert edges_a[1]["target"] == "c"

    def test_runtime_called_with_flow_global(self):
        mock_rt = MagicMock()
        mock_rt.run_source.side_effect = _make_fake_run("node")
        with patch("nodus.runtime.embedding.NodusRuntime", return_value=mock_rt):
            compile_nodus_flow("flow.step('node')", "f")
        call_kwargs = mock_rt.run_source.call_args
        assert "flow" in (call_kwargs.kwargs.get("host_globals") or {})

    def test_vm_not_installed_raises_runtime_error(self):
        with patch.dict("sys.modules", {"nodus": None, "nodus.runtime": None, "nodus.runtime.embedding": None}):
            with pytest.raises(RuntimeError, match="not installed"):
                compile_nodus_flow("flow.step('x')", "f")

    def test_vm_error_raises_value_error(self):
        mock_rt = MagicMock()
        mock_rt.run_source.return_value = {"ok": False, "error": "syntax error"}
        with patch("nodus.runtime.embedding.NodusRuntime", return_value=mock_rt):
            with pytest.raises(ValueError, match="syntax error"):
                compile_nodus_flow("bad script", "f")

    def test_vm_ok_false_no_error_message_still_raises(self):
        mock_rt = MagicMock()
        mock_rt.run_source.return_value = {"ok": False}
        with patch("nodus.runtime.embedding.NodusRuntime", return_value=mock_rt):
            with pytest.raises(ValueError):
                compile_nodus_flow("bad", "f")

    def test_no_steps_declared_raises_value_error(self):
        mock_rt = MagicMock()
        # VM succeeds but script never calls flow.step()
        mock_rt.run_source.return_value = {"ok": True}
        with patch("nodus.runtime.embedding.NodusRuntime", return_value=mock_rt):
            with pytest.raises(ValueError, match="no steps"):
                compile_nodus_flow("# empty", "f")


# ===========================================================================
# H. nodus.flow.compile node
# ===========================================================================

def _make_compile_state(**overrides):
    state = {
        "nodus_flow_script": "flow.step('a')\nflow.step('b')",
        "nodus_flow_name": "my_flow",
    }
    state.update(overrides)
    return state


def _make_node_context():
    return {"db": MagicMock(), "user_id": "user-123", "run_id": "run-456", "trace_id": "trace-789"}


class TestNodusFlowCompileNode:
    def test_returns_failure_when_no_script(self):
        from runtime.nodus_adapter import nodus_flow_compile_node
        result = nodus_flow_compile_node({"nodus_flow_name": "f"}, _make_node_context())
        assert result["status"] == "FAILURE"
        assert "nodus_flow_script" in result["error"]

    def test_returns_success_and_compiled_flow(self):
        from runtime.nodus_adapter import nodus_flow_compile_node
        mock_flow = {"start": "a", "edges": {"a": [], "b": []}, "end": ["b"]}
        with patch("runtime.nodus_flow_compiler.compile_nodus_flow", return_value=mock_flow):
            result = nodus_flow_compile_node(_make_compile_state(), _make_node_context())
        assert result["status"] == "SUCCESS"
        assert result["output_patch"]["nodus_compiled_flow"] == mock_flow

    def test_echoes_flow_name_in_output_patch(self):
        from runtime.nodus_adapter import nodus_flow_compile_node
        mock_flow = {"start": "a", "edges": {"a": []}, "end": ["a"]}
        with patch("runtime.nodus_flow_compiler.compile_nodus_flow", return_value=mock_flow):
            result = nodus_flow_compile_node(_make_compile_state(), _make_node_context())
        assert result["output_patch"]["nodus_flow_name"] == "my_flow"

    def test_defaults_flow_name_to_nodus_flow(self):
        from runtime.nodus_adapter import nodus_flow_compile_node
        mock_flow = {"start": "a", "edges": {"a": []}, "end": ["a"]}
        with patch("runtime.nodus_flow_compiler.compile_nodus_flow", return_value=mock_flow) as mock_compile:
            nodus_flow_compile_node({"nodus_flow_script": "flow.step('a')"}, _make_node_context())
        mock_compile.assert_called_once_with("flow.step('a')", "nodus_flow")

    def test_returns_failure_on_value_error_from_compiler(self):
        from runtime.nodus_adapter import nodus_flow_compile_node
        with patch("runtime.nodus_flow_compiler.compile_nodus_flow", side_effect=ValueError("bad script")):
            result = nodus_flow_compile_node(_make_compile_state(), _make_node_context())
        assert result["status"] == "FAILURE"
        assert "bad script" in result["error"]
        assert "bad script" in result["output_patch"]["nodus_flow_compile_error"]

    def test_returns_failure_on_runtime_error_from_compiler(self):
        from runtime.nodus_adapter import nodus_flow_compile_node
        with patch("runtime.nodus_flow_compiler.compile_nodus_flow", side_effect=RuntimeError("not installed")):
            result = nodus_flow_compile_node(_make_compile_state(), _make_node_context())
        assert result["status"] == "FAILURE"
        assert "not installed" in result["error"]


# ===========================================================================
# I. nodus.flow.run node
# ===========================================================================

def _make_run_state(**overrides):
    mock_flow = {"start": "a", "edges": {"a": []}, "end": ["a"]}
    state = {
        "nodus_compiled_flow": mock_flow,
        "nodus_flow_name": "my_flow",
        "nodus_flow_input": {"key": "val"},
    }
    state.update(overrides)
    return state


class TestNodusFlowRunNode:
    def test_returns_failure_when_no_compiled_flow(self):
        from runtime.nodus_adapter import nodus_flow_run_node
        result = nodus_flow_run_node({}, _make_node_context())
        assert result["status"] == "FAILURE"
        assert "nodus_compiled_flow" in result["error"]

    def test_returns_success_on_successful_inner_run(self):
        from runtime.nodus_adapter import nodus_flow_run_node
        mock_runner = MagicMock()
        mock_runner.start.return_value = {
            "status": "SUCCESS",
            "run_id": "inner-run-1",
            "trace_id": "trace-1",
        }
        with patch("runtime.nodus_adapter.PersistentFlowRunner", return_value=mock_runner):
            result = nodus_flow_run_node(_make_run_state(), _make_node_context())
        assert result["status"] == "SUCCESS"
        assert result["output_patch"]["nodus_flow_status"] == "SUCCESS"
        assert result["output_patch"]["nodus_flow_run_id"] == "inner-run-1"

    def test_returns_failure_on_failed_inner_run(self):
        from runtime.nodus_adapter import nodus_flow_run_node
        mock_runner = MagicMock()
        mock_runner.start.return_value = {
            "status": "FAILED",
            "error": "inner node failed",
            "run_id": "inner-run-2",
        }
        with patch("runtime.nodus_adapter.PersistentFlowRunner", return_value=mock_runner):
            result = nodus_flow_run_node(_make_run_state(), _make_node_context())
        assert result["status"] == "FAILURE"
        assert "inner node failed" in result["error"]

    def test_passes_nodus_flow_input_as_initial_state(self):
        from runtime.nodus_adapter import nodus_flow_run_node
        mock_runner = MagicMock()
        mock_runner.start.return_value = {"status": "SUCCESS", "run_id": "r"}
        state = _make_run_state(nodus_flow_input={"my_key": "my_val"})
        with patch("runtime.nodus_adapter.PersistentFlowRunner", return_value=mock_runner):
            nodus_flow_run_node(state, _make_node_context())
        call_args = mock_runner.start.call_args
        assert call_args.kwargs.get("initial_state") == {"my_key": "my_val"} or \
               call_args.args[0] == {"my_key": "my_val"}

    def test_runner_exception_returns_failure(self):
        from runtime.nodus_adapter import nodus_flow_run_node
        with patch("runtime.nodus_adapter.PersistentFlowRunner", side_effect=RuntimeError("db down")):
            result = nodus_flow_run_node(_make_run_state(), _make_node_context())
        assert result["status"] == "FAILURE"
        assert "db down" in result["error"]
        assert "db down" in result["output_patch"]["nodus_flow_run_error"]

    def test_result_includes_full_run_result(self):
        from runtime.nodus_adapter import nodus_flow_run_node
        full_result = {"status": "SUCCESS", "run_id": "r", "trace_id": "t", "state": {"x": 1}}
        mock_runner = MagicMock()
        mock_runner.start.return_value = full_result
        with patch("runtime.nodus_adapter.PersistentFlowRunner", return_value=mock_runner):
            result = nodus_flow_run_node(_make_run_state(), _make_node_context())
        assert result["output_patch"]["nodus_flow_result"] == full_result

    def test_defaults_flow_name_to_nodus_flow_in_runner_start(self):
        from runtime.nodus_adapter import nodus_flow_run_node
        mock_runner = MagicMock()
        mock_runner.start.return_value = {"status": "SUCCESS", "run_id": "r"}
        state = _make_run_state()
        state.pop("nodus_flow_name")  # omit name — should default
        with patch("runtime.nodus_adapter.PersistentFlowRunner", return_value=mock_runner):
            nodus_flow_run_node(state, _make_node_context())
        call_kwargs = mock_runner.start.call_args.kwargs
        assert call_kwargs.get("flow_name") == "nodus_flow"

