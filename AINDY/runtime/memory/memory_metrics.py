from __future__ import annotations

import json
import logging
from typing import Any, Iterable

from runtime.memory.types import MemoryContext

logger = logging.getLogger(__name__)


class MemoryMetricsEngine:
    """
    Computes memory impact metrics.

    Note: This class does not persist metrics. Persistence is handled by
    ExecutionLoop via MemoryMetricsStore to avoid duplicate writes.
    """
    def compute_impact(
        self,
        result_1: Any,
        result_2: Any,
        memory_context: MemoryContext | None,
    ) -> float:
        quality_1 = self.evaluate_quality(result_1)
        quality_2 = self.evaluate_quality(result_2)
        relevance = self.compute_relevance(memory_context)
        usage = self.compute_usage(memory_context)

        delta = max(quality_2 - quality_1, 0.0)
        impact = delta * relevance * usage
        impact = self._clamp(impact)
        self._emit_summary(
            impact=impact,
            quality_1=quality_1,
            quality_2=quality_2,
            relevance=relevance,
            usage=usage,
            memory_context=memory_context,
        )
        return impact

    def evaluate_quality(self, result: Any) -> float:
        if result is None:
            return 0.0

        if isinstance(result, dict):
            text = self._result_text(result)
            success_score = self._success_score(result)
        else:
            text = str(result)
            success_score = self._success_score(text)

        length_score = min(len(text) / 800, 1.0)
        structure_score = 0.2 if "\n" in text else 0.0
        keyword_score = self._keyword_score(text)

        quality = (
            length_score * 0.4
            + structure_score * 0.2
            + keyword_score * 0.2
            + success_score * 0.2
        )
        return self._clamp(quality)

    def compute_relevance(self, memory_context: MemoryContext | None) -> float:
        if not memory_context or not memory_context.items:
            return 0.0
        similarities = [item.similarity for item in memory_context.items]
        return self._clamp(sum(similarities) / len(similarities))

    def compute_usage(self, memory_context: MemoryContext | None) -> float:
        if not memory_context or not memory_context.items:
            return 0.0
        max_items = 10
        return self._clamp(len(memory_context.items) / max_items)

    def _keyword_score(self, text: str) -> float:
        keywords = [
            "because",
            "therefore",
            "step",
            "plan",
            "strategy",
            "analysis",
            "result",
            "summary",
            "recommendation",
            "next",
        ]
        lower = text.lower()
        hits = sum(1 for k in keywords if k in lower)
        return min(hits / 5, 1.0)

    def _result_text(self, result: dict) -> str:
        if "output" in result:
            return str(result.get("output"))
        if "result" in result:
            return str(result.get("result"))
        return str(result)

    def _success_score(self, result: Any) -> float:
        if isinstance(result, dict):
            if result.get("success") is True or result.get("ok") is True:
                return 1.0
            status = str(result.get("status", "")).lower()
            if status in {"success", "ok", "completed"}:
                return 1.0
            if status in {"failed", "error"}:
                return 0.0
            if "error" in result:
                return 0.0
            return 0.5

        text = str(result).lower()
        if any(token in text for token in ["error", "failed", "exception"]):
            return 0.0
        if any(token in text for token in ["success", "completed", "ok"]):
            return 1.0
        return 0.5

    def _clamp(self, value: float) -> float:
        if value < 0:
            return 0.0
        if value > 1:
            return 1.0
        return float(value)

    def _emit_summary(
        self,
        *,
        impact: float,
        quality_1: float,
        quality_2: float,
        relevance: float,
        usage: float,
        memory_context: MemoryContext | None,
    ) -> None:
        try:
            payload = {
                "event": "memory_metrics_summary",
                "impact_score": impact,
                "quality_baseline": self._clamp(quality_1),
                "quality_result": self._clamp(quality_2),
                "relevance": self._clamp(relevance),
                "usage": self._clamp(usage),
                "memory_count": len(memory_context.items) if memory_context else 0,
            }
            logger.info(json.dumps(payload, ensure_ascii=False))
        except Exception:
            logger.warning("Failed to emit memory metrics summary")
