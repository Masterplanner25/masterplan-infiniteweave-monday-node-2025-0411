from __future__ import annotations

import logging
from typing import Iterable, List, Optional

from .context_builder import ContextBuilder
from .filters import MemoryFilter
from .query_expander import QueryExpander
from .scorer import MemoryScorer
from .strategies import StrategySelector
from .types import MemoryContext, MemoryItem, RecallRequest
from AINDY.db.dao.memory_trace_dao import MemoryTraceDAO

logger = logging.getLogger(__name__)


class MemoryOrchestrator:
    def __init__(self, dao):
        self.dao = dao
        self.query_expander = QueryExpander()
        self.strategy_selector = StrategySelector()
        self.scorer = MemoryScorer()
        self.filter = MemoryFilter()
        self.context_builder = ContextBuilder()

    def get_context(
        self,
        *,
        user_id: str,
        query: str,
        task_type: str,
        db,
        max_tokens: int = 1200,
        metadata: Optional[dict] = None,
    ) -> MemoryContext:
        try:
            request = RecallRequest(query=query, user_id=user_id, task_type=task_type, metadata=metadata)
            expanded_query = self.query_expander.expand(request)
            strategy = self.strategy_selector.select(request)
            request.metadata["diversity_factor"] = strategy.diversity_factor
            self._inject_trace_context(request, db)

            tags = request.metadata.get("tags") if request.metadata else None
            override_node_type = request.metadata.get("node_type") if request.metadata else None
            override_node_types = request.metadata.get("node_types") if request.metadata else None
            if override_node_type:
                strategy.node_types = [override_node_type]
            if override_node_types is not None:
                strategy.node_types = list(override_node_types)

            requested_limit = request.metadata.get("limit") if request.metadata else None
            retrieval_limit = strategy.initial_pool_size
            if isinstance(requested_limit, int) and requested_limit > retrieval_limit:
                retrieval_limit = requested_limit

            candidates = self._recall_candidates(
                db=db,
                user_id=user_id,
                query=expanded_query,
                tags=tags,
                node_types=strategy.node_types,
                limit=retrieval_limit,
            )

            scored = self.scorer.score(candidates, request)
            filtered = self.filter.apply(scored, request)
            trimmed = self._enforce_token_budget(filtered, max_tokens)
            if isinstance(requested_limit, int) and requested_limit > 0:
                trimmed = trimmed[:requested_limit]
            context = self.context_builder.build(trimmed)

            logger.info(
                "[MemoryOrchestrator] query=%s task_type=%s candidates=%s returned=%s tokens=%s",
                query,
                task_type,
                len(candidates),
                len(trimmed),
                context.total_tokens,
            )
            return context

        except Exception as exc:
            logger.warning("[MemoryOrchestrator] recall failed: %s", exc)
            return _empty_context()

    def _recall_candidates(
        self,
        *,
        db,
        user_id: str,
        query: str,
        tags: Optional[list],
        node_types: List[str],
        limit: int,
    ) -> List[dict]:
        dao = self.dao(db) if callable(self.dao) else self.dao
        if not dao:
            return []

        if not node_types:
            return _safe_recall(dao, query, tags, limit, user_id, None)

        if len(node_types) == 1:
            return _safe_recall(dao, query, tags, limit, user_id, node_types[0])

        per_type = max(1, int(limit / len(node_types)))
        results: List[dict] = []
        seen = set()

        for node_type in node_types:
            chunk = _safe_recall(dao, query, tags, per_type, user_id, node_type)
            for item in chunk:
                item_id = item.get("id")
                if item_id and item_id in seen:
                    continue
                seen.add(item_id)
                results.append(item)
            if len(results) >= limit:
                break

        return results

    def _enforce_token_budget(self, nodes: List[MemoryItem], max_tokens: int) -> List[MemoryItem]:
        total = 0
        trimmed: List[MemoryItem] = []
        for node in nodes:
            tokens = _estimate_tokens(node.content)
            if total + tokens > max_tokens:
                break
            trimmed.append(node)
            total += tokens
        return trimmed

    def _inject_trace_context(self, request: RecallRequest, db) -> None:
        if not request.metadata:
            return
        trace_id = request.metadata.get("trace_id")
        if not trace_id:
            return
        try:
            trace_dao = MemoryTraceDAO(db)
            nodes = trace_dao.get_trace_nodes(trace_id, user_id=request.user_id, limit=500)
            request.metadata["trace_node_ids"] = {entry.get("node_id") for entry in nodes if entry.get("node_id")}
        except Exception as exc:
            logger.warning("[MemoryOrchestrator] trace context failed: %s", exc)


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def _empty_context() -> MemoryContext:
    return MemoryContext(items=[], total_tokens=0, metadata={"fallback": True}, formatted="")


def _safe_recall(dao, query, tags, limit, user_id, node_type) -> List[dict]:
    try:
        results = dao.recall(
            query=query,
            tags=tags,
            limit=limit,
            user_id=user_id,
            node_type=node_type,
        )
        if isinstance(results, dict):
            return results.get("results", [])
        return results or []
    except Exception:
        return []


def memory_items_to_dicts(items: Iterable[MemoryItem]) -> List[dict]:
    output = []
    for item in items:
        base = dict(item.raw) if isinstance(item.raw, dict) else {}
        base.update(
            {
                "id": item.id,
                "content": item.content,
                "node_type": item.node_type,
                "tags": item.tags,
                "score": item.score,
                "similarity": item.similarity,
                "recency": item.recency,
                "success_rate": item.success_rate,
                "usage_frequency": item.usage_frequency,
            }
        )
        output.append(base)
    return output
