from __future__ import annotations

from typing import Optional


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def score_lead_result(
    *,
    overall_score: Optional[float] = None,
    fit_score: Optional[float] = None,
    intent_score: Optional[float] = None,
    data_quality_score: Optional[float] = None,
) -> float:
    if overall_score is not None:
        return _clamp01(overall_score / 100.0)
    parts = [s for s in (fit_score, intent_score, data_quality_score) if s is not None]
    if not parts:
        return 0.0
    return _clamp01(sum(parts) / (len(parts) * 100.0))


def score_research_result(
    *,
    summary: str,
    memory_context_count: int = 0,
) -> float:
    length_factor = _clamp01(len(summary or "") / 500.0)
    memory_factor = _clamp01(memory_context_count / 5.0)
    return _clamp01(0.7 * length_factor + 0.3 * memory_factor)


def score_seo_result(
    *,
    readability: float,
    avg_keyword_density: float,
    word_count: int,
) -> float:
    readability_score = _clamp01(readability / 100.0)
    density_score = _clamp01(1.0 - (abs(avg_keyword_density - 2.0) / 2.0))
    length_score = _clamp01(word_count / 1000.0)
    return _clamp01(0.7 * readability_score + 0.2 * density_score + 0.1 * length_score)

