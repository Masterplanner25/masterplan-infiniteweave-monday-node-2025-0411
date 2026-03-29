from __future__ import annotations

import pytest

from runtime.memory import scorer as scorer_module
from runtime.memory import native_scorer as native_module
from runtime.memory.scorer import MemoryScorer


def test_native_scoring_parity_with_python_fallback(monkeypatch):
    prepared_nodes = [
        {
            "similarity": 0.8,
            "recency": 0.7,
            "success_rate": 0.9,
            "usage_frequency": 3.0,
            "graph_bonus": 0.4,
            "impact_score": 2.0,
            "trace_bonus": 0.1,
            "low_value_flag": False,
        },
        {
            "similarity": 0.4,
            "recency": 0.2,
            "success_rate": 0.1,
            "usage_frequency": 9.0,
            "graph_bonus": 0.8,
            "impact_score": 5.0,
            "trace_bonus": 0.0,
            "low_value_flag": True,
        },
    ]

    python_scores = [scorer_module._score_node_python(node) for node in prepared_nodes]
    native_scores = scorer_module._score_nodes(prepared_nodes)

    assert len(native_scores) == len(python_scores)
    for native, python_score in zip(native_scores, python_scores):
        assert native == pytest.approx(python_score, abs=1e-9)


def test_memory_scorer_falls_back_when_native_unavailable(monkeypatch):
    monkeypatch.setattr(
        scorer_module,
        "score_memory_nodes_native",
        lambda **_: {
            "scores": None,
            "engine": "python",
            "duration_ms": 0.1,
            "fallback_used": True,
            "error": "unavailable",
        },
    )
    scorer = MemoryScorer()
    node = {
        "id": "n1",
        "content": "fallback path",
        "node_type": "outcome",
        "semantic_score": 0.9,
        "recency_score": 1.0,
        "success_rate": 0.8,
        "usage_frequency": 4,
        "graph_score": 0.5,
        "impact_score": 2.0,
    }

    scored = scorer.score([node], request=None)

    assert scored[0].id == "n1"
    assert scored[0].score > 0.0


def test_native_wrapper_returns_standardized_fallback_shape_when_disabled(monkeypatch):
    monkeypatch.setenv("USE_NATIVE_SCORER", "false")

    result = native_module.score_memory_nodes(
        similarities=[0.1],
        recencies=[0.2],
        success_rates=[0.3],
        usage_frequencies=[1.0],
        graph_bonuses=[0.0],
        impact_scores=[0.0],
        trace_bonuses=[0.0],
        low_value_flags=[False],
    )

    assert set(result.keys()) == {"scores", "engine", "duration_ms", "fallback_used", "error"}
    assert result["scores"] is None
    assert result["engine"] == "python"
    assert result["fallback_used"] is True
    assert result["error"] == "disabled"
