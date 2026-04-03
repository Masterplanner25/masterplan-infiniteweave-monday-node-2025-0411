"""
nodus_flow_compiler.py — Compile a Nodus script into a PersistentFlowRunner flow dict.

The Nodus script defines flow routing using the ``flow.*`` API:

    flow.step("fetch_data")
    flow.step("analyze", when="data_ready")   # skipped when state["data_ready"] is falsy
    flow.step("summarize")

``compile_nodus_flow(script, flow_name)`` executes the script in the Nodus VM with a
:class:`NodusFlowGraph` injected as the ``flow`` global, then calls ``flow.compile()``
to produce a flow dict compatible with :class:`~runtime.flow_engine.PersistentFlowRunner`
and ``FLOW_REGISTRY``.

Compilation algorithm
=====================
Steps are declared in order.  For each step at index ``i``, the compiler inspects
the *next* step (``i+1``) to decide what edge(s) leave node ``i``:

* **Unconditional next step** — simple string edge: ``[next_node]``
* **Conditional next step** (``when="key"``) — two conditional edges:
    - truthy: ``{"condition": _condition_truthy("key"), "target": next_node}``
    - falsy:  ``{"condition": _condition_falsy("key"),  "target": step_after_next}``
  When the conditional step is the *last* step only the truthy edge is emitted;
  the current node also becomes a terminal (added to ``end``).
* **Last step** — empty edge list; node added to ``end``.

Condition closures
==================
Conditional edges use closures produced by :func:`_condition_truthy` /
:func:`_condition_falsy`.  These are Python callables and live in-memory only —
they are **not** serialised to the database.  Flow dicts produced here must be
held in ``FLOW_REGISTRY`` (or a local variable) and not reconstructed from DB.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Condition helpers
# ---------------------------------------------------------------------------

def _condition_truthy(key: str) -> Callable[[dict], bool]:
    """Return a condition function that is True when ``state[key]`` is truthy."""
    def _check(state: dict) -> bool:
        return bool(state.get(key))
    _check.__name__ = f"when_{key}_truthy"
    return _check


def _condition_falsy(key: str) -> Callable[[dict], bool]:
    """Return a condition function that is True when ``state[key]`` is falsy."""
    def _check(state: dict) -> bool:
        return not bool(state.get(key))
    _check.__name__ = f"when_{key}_falsy"
    return _check


# ---------------------------------------------------------------------------
# NodusFlowGraph
# ---------------------------------------------------------------------------

class NodusFlowGraph:
    """
    Flow graph builder injected as the ``flow`` global into Nodus flow scripts.

    The Nodus script calls :meth:`step` to declare nodes in execution order.
    The compiler then calls :meth:`compile` to produce a flow dict understood
    by :class:`~runtime.flow_engine.PersistentFlowRunner`.

    Example Nodus script::

        flow.step("fetch_data")
        flow.step("analyze", when="data_ready")
        flow.step("summarize")

    Compiled flow dict::

        {
            "start": "fetch_data",
            "edges": {
                "fetch_data": [
                    {"condition": <truthy "data_ready">, "target": "analyze"},
                    {"condition": <falsy  "data_ready">, "target": "summarize"},
                ],
                "analyze":  ["summarize"],
                "summarize": [],
            },
            "end": ["summarize"],
        }
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._steps: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API (called from inside the Nodus script)
    # ------------------------------------------------------------------

    def step(self, node_name: str, when: Optional[str] = None) -> None:
        """
        Declare the next step in the flow.

        Parameters
        ----------
        node_name:
            Name of an existing registered node (must be in ``NODE_REGISTRY``
            when the flow is executed).
        when:
            State key whose truthiness gates this step at runtime.  When the
            key's value is falsy in the flow state, this step is skipped and
            the flow advances to the next declared step.
        """
        if not isinstance(node_name, str) or not node_name.strip():
            raise ValueError(
                "flow.step() requires a non-empty string node_name; "
                f"got {node_name!r}"
            )
        self._steps.append({"node": node_name.strip(), "when": when})

    # ------------------------------------------------------------------
    # Compiler (called by compile_nodus_flow after script execution)
    # ------------------------------------------------------------------

    def compile(self) -> dict:
        """
        Build a :class:`~runtime.flow_engine.PersistentFlowRunner`-compatible
        flow dict from the recorded steps.

        Returns
        -------
        dict
            Keys: ``start`` (str), ``edges`` (dict), ``end`` (list[str]).

        Raises
        ------
        ValueError
            When no steps have been declared.
        """
        steps = self._steps
        if not steps:
            raise ValueError(
                f"Nodus flow {self._name!r} declares no steps — "
                "call flow.step() at least once inside the script"
            )

        edges: dict[str, Any] = {}
        end_nodes: list[str] = []

        for i, step in enumerate(steps):
            node = step["node"]
            j = i + 1  # index of the next declared step

            if j >= len(steps):
                # Terminal node — no outgoing edges
                edges[node] = []
                end_nodes.append(node)
            else:
                next_step = steps[j]
                cond_key: Optional[str] = next_step["when"]

                if cond_key is not None:
                    # Next step is conditional — emit truthy + falsy edges
                    if j + 1 < len(steps):
                        # There is a step after the conditional one to fall through to
                        fallthrough_node = steps[j + 1]["node"]
                        edges[node] = [
                            {
                                "condition": _condition_truthy(cond_key),
                                "target": next_step["node"],
                            },
                            {
                                "condition": _condition_falsy(cond_key),
                                "target": fallthrough_node,
                            },
                        ]
                    else:
                        # Conditional step is also the last — only truthy edge
                        # If condition is false at runtime the flow halts here
                        edges[node] = [
                            {
                                "condition": _condition_truthy(cond_key),
                                "target": next_step["node"],
                            },
                        ]
                        end_nodes.append(node)
                else:
                    # Unconditional advance to next step
                    edges[node] = [next_step["node"]]

        return {
            "start": steps[0]["node"],
            "edges": edges,
            "end": end_nodes if end_nodes else [steps[-1]["node"]],
        }


# ---------------------------------------------------------------------------
# Public compile function
# ---------------------------------------------------------------------------

def compile_nodus_flow(script: str, flow_name: str) -> dict:
    """
    Execute a Nodus flow script and return the compiled flow dict.

    The script must call ``flow.step()`` one or more times.  A
    :class:`NodusFlowGraph` instance is injected as the ``flow`` global;
    calling ``flow.step()`` records nodes and their conditional edges.

    Parameters
    ----------
    script:
        Nodus source code that declares flow routing via ``flow.step()``.
    flow_name:
        Logical name for the flow (used in log messages and error text).

    Returns
    -------
    dict
        A flow dict compatible with
        :class:`~runtime.flow_engine.PersistentFlowRunner`.

    Raises
    ------
    RuntimeError
        When the Nodus VM package is not installed.
    ValueError
        When the script declares no steps, or the Nodus VM reports a
        script-level error.
    """
    try:
        from nodus.runtime.embedding import NodusRuntime
    except ImportError as exc:
        raise RuntimeError(
            "Nodus VM not installed — run: pip install nodus"
        ) from exc

    graph = NodusFlowGraph(flow_name)
    runtime = NodusRuntime()

    flow_globals: dict[str, Any] = {"flow": graph}

    result = runtime.run_source(
        script,
        filename=f"<nodus_flow:{flow_name}>",
        initial_globals=flow_globals,
        host_globals=flow_globals,
    )

    if not (result or {}).get("ok"):
        error = (result or {}).get("error") or "Nodus VM returned an error"
        raise ValueError(
            f"Nodus flow script error in {flow_name!r}: {error}"
        )

    flow_dict = graph.compile()
    logger.info(
        "[NodusFlowCompiler] Compiled %r — nodes=%s start=%r end=%r",
        flow_name,
        list(flow_dict["edges"].keys()),
        flow_dict["start"],
        flow_dict["end"],
    )
    return flow_dict
