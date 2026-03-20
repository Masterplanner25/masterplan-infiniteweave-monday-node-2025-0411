"""
MemoryNodeDAO - canonical data-access object for memory_nodes and memory_links.

All memory persistence goes through this class. Import and use from routes and
services; do not instantiate MemoryNodeDAO from bridge.py (bridge calls are
routed through services.memory_persistence.MemoryNodeDAO for backward compat).
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from services.memory_persistence import MemoryNodeModel, MemoryLinkModel


class MemoryNodeDAO:
    """Canonical DAO for memory_nodes and memory_links tables."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _node_to_dict(self, n: MemoryNodeModel) -> dict:
        return {
            "id": str(n.id),
            "content": n.content,
            "tags": n.tags,
            "node_type": n.node_type,
            "source": n.source,
            "source_agent": getattr(n, "source_agent", None),
            "is_shared": getattr(n, "is_shared", None),
            "user_id": n.user_id,
            "extra": n.extra,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "updated_at": n.updated_at.isoformat() if n.updated_at else None,
        }

    def _get_model_by_id(self, node_id: str, user_id: str = None) -> Optional[MemoryNodeModel]:
        try:
            node_uuid = uuid.UUID(str(node_id))
        except ValueError:
            return None
        query = self.db.query(MemoryNodeModel).filter(MemoryNodeModel.id == node_uuid)
        if user_id:
            query = query.filter(MemoryNodeModel.user_id == user_id)
        return query.first()

    def _strength_value(self, strength) -> float:
        if strength is None:
            return 0.0
        if isinstance(strength, (int, float)):
            return float(strength)
        try:
            return float(strength)
        except (TypeError, ValueError):
            normalized = str(strength).strip().lower()
            return {
                "low": 0.3,
                "medium": 0.6,
                "high": 0.9,
            }.get(normalized, 0.0)

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def save(
        self,
        content: str,
        source: str = None,
        tags: List[str] = None,
        user_id: str = None,
        node_type: str = None,
        extra: dict = None,
        generate_embedding: bool = True,
    ) -> dict:
        """Insert a new memory node and return its dict representation."""
        from services.embedding_service import generate_embedding as gen_emb

        db_node = MemoryNodeModel(
            content=content,
            tags=tags or [],
            node_type=node_type,
            source=source,
            user_id=user_id,
            extra=extra or {},
        )

        if generate_embedding:
            db_node.embedding = gen_emb(content)

        try:
            self.db.add(db_node)
            self.db.commit()
            self.db.refresh(db_node)
            return self._node_to_dict(db_node)
        except SQLAlchemyError:
            self.db.rollback()
            raise

    def save_as_agent(
        self,
        content: str,
        source: str,
        agent_namespace: str,
        tags: list[str] = None,
        node_type: str = None,
        is_shared: bool = False,
        user_id: str = None,
        generate_embedding: bool = True,
    ) -> MemoryNodeModel:
        """
        Save a memory node with agent namespace tagging.

        is_shared=True: visible to all agents for this user.
        is_shared=False: private to this agent's namespace.
        """
        from services.embedding_service import generate_embedding as gen_emb

        db_node = MemoryNodeModel(
            content=content,
            tags=tags or [],
            node_type=node_type,
            source=source,
            source_agent=agent_namespace,
            is_shared=is_shared,
            user_id=user_id,
            extra={},
        )

        if generate_embedding:
            db_node.embedding = gen_emb(content)

        try:
            self.db.add(db_node)
            self.db.commit()
            self.db.refresh(db_node)
            return db_node
        except SQLAlchemyError:
            self.db.rollback()
            raise

    def get_by_id(self, node_id: str, user_id: str = None) -> Optional[dict]:
        """Return a node dict by UUID string, or None if not found."""
        db_node = self._get_model_by_id(node_id, user_id=user_id)
        if not db_node:
            return None
        return self._node_to_dict(db_node)

    def get_by_tags(self, tags: List[str], limit: int = 50, mode: str = "AND") -> List[dict]:
        """
        Return nodes whose tags array contains the given tags.
        mode='AND'  - all tags must be present.
        mode='OR'   - any tag must be present.
        """
        query = self.db.query(MemoryNodeModel)
        clean_tags = [t for t in (tags or []) if t]
        if clean_tags:
            if mode.upper() == "OR":
                query = query.filter(
                    or_(*[MemoryNodeModel.tags.contains([t]) for t in clean_tags])
                )
            else:
                for t in clean_tags:
                    query = query.filter(MemoryNodeModel.tags.contains([t]))
        return [self._node_to_dict(n) for n in query.limit(limit).all()]

    # ------------------------------------------------------------------
    # Semantic similarity retrieval
    # ------------------------------------------------------------------

    def find_similar(
        self,
        query_embedding: list,
        limit: int = 5,
        user_id: str = None,
        node_type: str = None,
        min_similarity: float = 0.0,
    ) -> list:
        """
        Find nodes similar to query_embedding using pgvector.
        Uses <=> cosine distance operator.
        Distance 0 = identical, 2 = opposite.
        Similarity = 1 - (distance / 2).
        """
        from pgvector.sqlalchemy import Vector
        from sqlalchemy import Float, cast

        distance_expr = cast(
            MemoryNodeModel.embedding.op("<=>")(
                cast(query_embedding, Vector(1536))
            ),
            Float,
        )

        query = self.db.query(
            MemoryNodeModel.id,
            MemoryNodeModel.content,
            MemoryNodeModel.tags,
            MemoryNodeModel.node_type,
            MemoryNodeModel.source,
            MemoryNodeModel.source_agent,
            MemoryNodeModel.is_shared,
            MemoryNodeModel.user_id,
            MemoryNodeModel.extra,
            MemoryNodeModel.created_at,
            MemoryNodeModel.updated_at,
            distance_expr.label("distance")
        ).filter(
            MemoryNodeModel.embedding.isnot(None)
        )

        if user_id:
            query = query.filter(MemoryNodeModel.user_id == user_id)
        if node_type:
            query = query.filter(MemoryNodeModel.node_type == node_type)

        results = query.order_by(distance_expr.asc()).limit(limit).all()

        output = []
        for row in results:
            distance = row.distance
            similarity = max(0.0, 1.0 - (distance / 2.0))
            if similarity >= min_similarity:
                node_dict = {
                    "id": str(row.id),
                    "content": row.content,
                    "tags": row.tags,
                    "node_type": row.node_type,
                    "source": row.source,
                    "source_agent": row.source_agent,
                    "is_shared": row.is_shared,
                    "user_id": row.user_id,
                    "extra": row.extra,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                }
                node_dict["similarity"] = round(similarity, 4)
                node_dict["distance"] = round(float(distance), 4)
                output.append(node_dict)

        return output

    # ------------------------------------------------------------------
    # Graph query: get nodes linked to a given node
    # ------------------------------------------------------------------

    def get_linked_nodes(
        self,
        node_id: str,
        direction: str = "both",
        limit: int = None,
        user_id: str = None,
    ) -> List[dict]:
        """
        Return all nodes directly linked to node_id.

        direction='out'  - nodes this node points to (source -> target)
        direction='in'   - nodes that point to this node (target <- source)
        direction='both' - union of both directions (default)
        """
        try:
            node_uuid = uuid.UUID(str(node_id))
        except ValueError:
            return []

        linked: List[dict] = []

        if direction in ("out", "both"):
            links = (
                self.db.query(MemoryLinkModel)
                .filter(MemoryLinkModel.source_node_id == node_uuid)
                .all()
            )
            target_ids = [lnk.target_node_id for lnk in links]
            if target_ids:
                query = self.db.query(MemoryNodeModel).filter(MemoryNodeModel.id.in_(target_ids))
                if user_id:
                    query = query.filter(MemoryNodeModel.user_id == user_id)
                if limit:
                    query = query.limit(limit)
                nodes = query.all()
                linked.extend(self._node_to_dict(n) for n in nodes)

        if direction in ("in", "both"):
            links = (
                self.db.query(MemoryLinkModel)
                .filter(MemoryLinkModel.target_node_id == node_uuid)
                .all()
            )
            source_ids = [lnk.source_node_id for lnk in links]
            if source_ids:
                # deduplicate against already-added nodes
                seen_ids = {d["id"] for d in linked}
                query = self.db.query(MemoryNodeModel).filter(MemoryNodeModel.id.in_(source_ids))
                if user_id:
                    query = query.filter(MemoryNodeModel.user_id == user_id)
                if limit:
                    query = query.limit(limit)
                nodes = query.all()
                linked.extend(
                    self._node_to_dict(n) for n in nodes if str(n.id) not in seen_ids
                )

        return linked

    # ------------------------------------------------------------------
    # Resonance recall
    # ------------------------------------------------------------------

    def recall(
        self,
        query: str = None,
        tags: list = None,
        limit: int = 5,
        user_id: str = None,
        node_type: str = None,
        expand_results: bool = False,
    ) -> list:
        """
        Retrieve most relevant memories using resonance scoring.

        score = (semantic * 0.40) + (graph * 0.15) + (recency * 0.15)
                + (success_rate * 0.20) + (usage_freq * 0.10)
        recency = exp(-age_days / 30.0)  # half-life 30 days

        At least one of query or tags required.
        """
        from services.embedding_service import generate_query_embedding
        from datetime import datetime
        import math

        candidates = []

        # Semantic path
        if query:
            query_embedding = generate_query_embedding(query)
            similar = self.find_similar(
                query_embedding=query_embedding,
                limit=limit * 3,
                user_id=user_id,
                node_type=node_type,
            )
            for item in similar:
                item["semantic_score"] = item.get("similarity", 0.0)
                candidates.append(item)

        # Tag path
        if tags:
            tag_nodes = self.get_by_tags(tags=tags, limit=limit * 3)
            existing_ids = {c["id"] for c in candidates}
            for node_dict in tag_nodes:
                if node_dict["id"] not in existing_ids:
                    if user_id and node_dict.get("user_id") != user_id:
                        continue
                    if node_type and node_dict.get("node_type") != node_type:
                        continue
                    node_dict["semantic_score"] = 0.0
                    candidates.append(node_dict)

        now = datetime.utcnow()
        scored = []

        for c in candidates:
            # Signal 1: Semantic similarity (from find_similar)
            semantic = c.get("semantic_score", 0.0)

            # Signal 2: Graph connectivity
            graph_score = 0.0
            try:
                graph_score = self.get_graph_connectivity_score(c["id"])
            except Exception:
                graph_score = 0.0

            # Signal 3: Recency decay (half-life 30 days)
            recency_score = 0.5
            created_str = c.get("created_at")
            if created_str:
                try:
                    if isinstance(created_str, str):
                        created = datetime.fromisoformat(
                            created_str.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                    else:
                        created = created_str
                    age_days = (now - created).days
                    recency_score = math.exp(-age_days / 30.0)
                except Exception:
                    recency_score = 0.5

            # Signal 4: Success rate (0.5 = no data, neutral prior)
            success_rate = 0.5
            adaptive_weight = 1.0
            usage_freq = 0.0
            node_obj = self._get_model_by_id(c["id"])
            if node_obj:
                success_rate = self.get_success_rate(node_obj)
                adaptive_weight = node_obj.weight or 1.0
                usage_freq = self.get_usage_frequency_score(node_obj)
                c["success_count"] = node_obj.success_count or 0
                c["failure_count"] = node_obj.failure_count or 0
                c["usage_count"] = node_obj.usage_count or 0

            # Signal 5: Usage frequency
            usage_freq = usage_freq or 0.0

            # Tag match (auxiliary — not in main formula)
            tag_score = 0.0
            if tags:
                node_tags = set(c.get("tags") or [])
                query_tags = set(tags)
                if query_tags:
                    tag_score = len(node_tags & query_tags) / len(query_tags)

            resonance = (
                (semantic * 0.40)
                + (graph_score * 0.15)
                + (recency_score * 0.15)
                + (success_rate * 0.20)
                + (usage_freq * 0.10)
            ) * adaptive_weight

            resonance = min(1.0, resonance)
            resonance = min(1.0, resonance + (tag_score * 0.1))

            c["semantic_score"] = round(semantic, 4)
            c["graph_score"] = round(graph_score, 4)
            c["tag_score"] = round(tag_score, 4)
            c["recency_score"] = round(recency_score, 4)
            c["success_rate"] = round(success_rate, 4)
            c["usage_frequency"] = round(usage_freq, 4)
            c["adaptive_weight"] = round(adaptive_weight, 4)
            c["resonance_score"] = round(resonance, 4)
            scored.append(c)

        scored.sort(key=lambda x: x["resonance_score"], reverse=True)

        seen = set()
        results = []
        for item in scored:
            if item["id"] not in seen:
                seen.add(item["id"])
                results.append(item)
            if len(results) >= limit:
                break

        if expand_results and results:
            top_ids = [r["id"] for r in results[:3]]
            expansion = self.expand(
                node_ids=top_ids,
                user_id=user_id,
                include_linked=True,
                include_similar=True,
                limit_per_node=2,
            )
            return {
                "results": results,
                "expanded": expansion["expanded_nodes"],
                "expansion_map": expansion["expansion_map"],
                "total_context_nodes": len(results) + len(expansion["expanded_nodes"]),
            }

        return results

    def recall_from_agent(
        self,
        agent_namespace: str,
        query: str = None,
        tags: list[str] = None,
        limit: int = 5,
        user_id: str = None,
        include_private: bool = False,
    ) -> list[dict]:
        """
        Query memory from a specific agent's namespace.

        include_private: if True, also return private nodes.
        Cross-agent queries must use include_private=False.
        """
        try:
            results = self.recall(
                query=query,
                tags=tags,
                limit=limit * 5,
                user_id=user_id,
            )

            if isinstance(results, dict):
                results = results.get("results", [])

            filtered = [
                r for r in results
                if r.get("source_agent") == agent_namespace
                and (include_private or r.get("is_shared") is True)
            ]

            return filtered[:limit]

        except Exception as exc:
            import logging
            logging.warning(
                "recall_from_agent failed for %s: %s",
                agent_namespace,
                exc,
            )
            return []

    def recall_federated(
        self,
        query: str = None,
        tags: list[str] = None,
        agent_namespaces: list[str] = None,
        limit: int = 5,
        user_id: str = None,
    ) -> dict:
        """
        Federated recall - query across multiple agents.

        Queries each specified agent's shared memory and
        merges results by resonance score.
        """
        from db.models.agent import SYSTEM_AGENTS

        namespaces = agent_namespaces or list(SYSTEM_AGENTS)

        results_by_agent = {}
        all_results = []

        for namespace in namespaces:
            agent_results = self.recall_from_agent(
                agent_namespace=namespace,
                query=query,
                tags=tags,
                limit=limit,
                user_id=user_id,
                include_private=False,
            )

            if agent_results:
                results_by_agent[namespace] = agent_results
                all_results.extend(agent_results)

        seen_ids = set()
        merged = []
        for result in sorted(
            all_results,
            key=lambda x: x.get("resonance_score", 0),
            reverse=True,
        ):
            if result["id"] not in seen_ids:
                seen_ids.add(result["id"])
                merged.append(result)

        return {
            "query": query,
            "tags": tags,
            "agents_queried": namespaces,
            "results_by_agent": results_by_agent,
            "merged_results": merged[:limit],
            "total_found": len(merged),
            "federation_summary": {
                namespace: len(results)
                for namespace, results in results_by_agent.items()
            },
        }

    def share_memory(
        self,
        node_id: str,
        user_id: str,
    ) -> Optional[MemoryNodeModel]:
        """
        Make a private memory node visible to all agents.

        Once shared, any agent querying this user's shared
        memory pool can see this node.
        Cannot be unshared (append-only sharing policy).
        """
        node = self._get_model_by_id(node_id, user_id=user_id)
        if not node:
            return None

        if not node.is_shared:
            node.is_shared = True
            self.db.add(node)
            self.db.commit()
            self.db.refresh(node)

        return node

    def recall_by_type(
        self,
        node_type: str,
        query: str = None,
        limit: int = 5,
        user_id: str = None,
    ) -> list:
        """Retrieve memories of a specific type."""
        from services.memory_persistence import VALID_NODE_TYPES
        if node_type not in VALID_NODE_TYPES:
            raise ValueError(
                f"Invalid node_type. Must be one of: {VALID_NODE_TYPES}"
            )
        return self.recall(
            query=query,
            node_type=node_type,
            limit=limit,
            user_id=user_id,
        )

    def update(
        self,
        node_id: str,
        user_id: str,
        content: str = None,
        tags: list[str] = None,
        node_type: str = None,
        source: str = None,
        regenerate_embedding: bool = True,
    ) -> Optional[MemoryNodeModel]:
        """
        Update a MemoryNode and record the previous state in memory_node_history.

        Only records history when values actually change.
        Never called for embedding updates or score updates.

        Returns updated node or None if not found.
        """
        from db.models.memory_node_history import MemoryNodeHistory
        from datetime import datetime

        node = self._get_model_by_id(node_id, user_id=user_id)
        if not node:
            return None

        changes = []
        previous = {}

        if content is not None and content != node.content:
            previous["previous_content"] = node.content
            changes.append("content")
            node.content = content

        if tags is not None and tags != (node.tags or []):
            previous["previous_tags"] = node.tags
            changes.append("tags")
            node.tags = tags

        if node_type is not None and node_type != node.node_type:
            previous["previous_node_type"] = node.node_type
            changes.append("node_type")
            node.node_type = node_type

        if source is not None and source != node.source:
            previous["previous_source"] = node.source
            changes.append("source")
            node.source = source

        if not changes:
            return node

        change_type = changes[0] if len(changes) == 1 else "multiple"
        change_summary = ", ".join(f"{c} updated" for c in changes)

        history = MemoryNodeHistory(
            node_id=node.id,
            changed_by=user_id,
            change_type=change_type,
            change_summary=change_summary,
            **previous,
        )

        node.updated_at = datetime.utcnow()

        if "content" in changes and regenerate_embedding:
            try:
                from services.embedding_service import generate_embedding
                node.embedding = generate_embedding(node.content)
            except Exception as exc:
                import logging
                logging.warning("Embedding regeneration failed on update: %s", exc)

        self.db.add(history)
        self.db.add(node)
        self.db.commit()
        self.db.refresh(node)
        return node

    def get_history(self, node_id: str, user_id: str, limit: int = 20) -> list[dict]:
        """
        Get the change history for a memory node.
        Returns entries in reverse chronological order.
        """
        from db.models.memory_node_history import MemoryNodeHistory

        node = self._get_model_by_id(node_id, user_id=user_id)
        if not node:
            return []

        history = (
            self.db.query(MemoryNodeHistory)
            .filter(MemoryNodeHistory.node_id == node.id)
            .order_by(MemoryNodeHistory.changed_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": h.id,
                "node_id": str(h.node_id),
                "changed_at": h.changed_at.isoformat() if h.changed_at else None,
                "changed_by": h.changed_by,
                "change_type": h.change_type,
                "change_summary": h.change_summary,
                "previous_content": h.previous_content,
                "previous_tags": h.previous_tags,
                "previous_node_type": h.previous_node_type,
                "previous_source": h.previous_source,
            }
            for h in history
        ]

    def record_feedback(
        self,
        node_id: str,
        outcome: str,  # "success" | "failure" | "neutral"
        user_id: str = None,
    ) -> Optional[MemoryNodeModel]:
        """
        Record explicit or automatic feedback on a memory node.

        Updates success/failure counts and adjusts the adaptive
        weight. The weight is used in resonance v2 scoring to
        boost memories that consistently lead to good outcomes
        and suppress those that lead to failures.

        Weight adjustment rules:
          success: weight += 0.1 (max 2.0)
          failure: weight -= 0.15 (min 0.1)
          neutral: no weight change, usage_count incremented

        Called by:
          - Explicit: POST /memory/nodes/{id}/feedback
          - Automatic: ARM analysis score, task completion,
                       Genesis lock
        """
        from datetime import datetime

        node = self._get_model_by_id(node_id, user_id=user_id)
        if not node:
            return None

        now = datetime.utcnow()
        node.usage_count = (node.usage_count or 0) + 1
        node.last_used_at = now
        node.last_outcome = outcome

        if outcome == "success":
            node.success_count = (node.success_count or 0) + 1
            node.weight = min(2.0, (node.weight or 1.0) + 0.1)
        elif outcome == "failure":
            node.failure_count = (node.failure_count or 0) + 1
            node.weight = max(0.1, (node.weight or 1.0) - 0.15)

        self.db.add(node)
        self.db.commit()
        self.db.refresh(node)
        return node

    def get_success_rate(self, node: MemoryNodeModel) -> float:
        """
        Calculate success rate for a node (0.0 - 1.0).
        Returns 0.5 (neutral) if no feedback recorded yet.
        """
        total = (node.success_count or 0) + (node.failure_count or 0)
        if total == 0:
            return 0.5
        return (node.success_count or 0) / total

    def get_usage_frequency_score(
        self,
        node: MemoryNodeModel,
        max_usage: int = 100,
    ) -> float:
        """
        Normalize usage count to 0.0-1.0 score.
        Frequently used memories score higher.
        Capped at max_usage to prevent domination.
        """
        usage = node.usage_count or 0
        return min(1.0, usage / max(max_usage, 1))

    def get_graph_connectivity_score(
        self,
        node_id: str,
        max_connections: int = 20,
    ) -> float:
        """
        Score how well-connected this node is in the graph.
        More connections = more central to the memory network
        = higher score.

        Normalized to 0.0-1.0.
        Capped at max_connections to prevent hub domination.
        """
        try:
            node_uuid = uuid.UUID(str(node_id))
        except ValueError:
            return 0.0

        outbound = (
            self.db.query(MemoryLinkModel)
            .filter(MemoryLinkModel.source_node_id == node_uuid)
            .count()
        )
        inbound = (
            self.db.query(MemoryLinkModel)
            .filter(MemoryLinkModel.target_node_id == node_uuid)
            .count()
        )

        total_connections = outbound + inbound
        return min(1.0, total_connections / max(max_connections, 1))

    def traverse(
        self,
        start_node_id: str,
        max_depth: int = 3,
        link_type: str = None,
        user_id: str = None,
        min_strength: float = 0.0,
    ) -> dict:
        """
        DFS traversal from a starting node.

        Follows chains of thought by depth-first exploring
        the strongest links at each hop.

        Returns a traversal tree with the path taken,
        nodes visited, and the chain of thought narrative.

        max_depth: maximum hops from start node (default 3)
        link_type: filter to specific relationship types
        min_strength: minimum link strength to follow

        Cycle prevention: visited set tracks all seen nodes.
        DFS strategy: at each node, follow highest-strength
                      outbound link first.
        """
        start_node = self.get_by_id(start_node_id, user_id=user_id)
        if not start_node:
            return {
                "start_node_id": start_node_id,
                "found": False,
                "chain": [],
                "nodes_visited": 0,
            }

        visited = set()
        chain = []

        def dfs(node_id: str, depth: int, path: list) -> None:
            if depth > max_depth:
                return
            if node_id in visited:
                return

            visited.add(node_id)

            node = self.get_by_id(node_id, user_id=user_id)
            if not node:
                return

            entry = {
                "depth": depth,
                "node": node,
                "path": list(path),
                "children": [],
            }

            if depth > 0:
                chain.append(entry)

            link_query = self.db.query(MemoryLinkModel).filter(
                MemoryLinkModel.source_node_id == uuid.UUID(str(node_id))
            )

            if link_type:
                link_query = link_query.filter(MemoryLinkModel.link_type == link_type)

            links = link_query.all()

            filtered_links = []
            for link in links:
                strength_val = self._strength_value(link.strength)
                if strength_val >= min_strength:
                    filtered_links.append((link, strength_val))

            filtered_links.sort(key=lambda x: x[1], reverse=True)

            for link, _strength_val in filtered_links:
                target_id = str(link.target_node_id)
                if target_id not in visited:
                    next_path = path + [
                        {
                            "node_id": node_id,
                            "link_type": link.link_type,
                            "strength": link.strength,
                        }
                    ]
                    dfs(target_id, depth + 1, next_path)

        dfs(start_node_id, 0, [])

        narrative = self._build_chain_narrative(start_node, chain)

        return {
            "start_node_id": start_node_id,
            "start_node": start_node,
            "found": True,
            "max_depth": max_depth,
            "nodes_visited": len(visited),
            "chain": chain,
            "chain_length": len(chain),
            "narrative": narrative,
        }

    def _build_chain_narrative(self, start_node: dict, chain: list) -> str:
        """
        Build a human-readable chain of thought narrative
        from a DFS traversal result.

        This is the "WHY something matters" layer -
        not just what was found, but how the chain connects.
        """
        start_content = (start_node or {}).get("content", "")
        if not chain:
            return (
                f"Starting from: '{start_content[:80]}'. "
                f"No connected memories found."
            )

        parts = [
            f"Chain of thought starting from '{start_content[:60]}...':"
        ]

        for entry in chain:
            node = entry["node"]
            depth = entry["depth"]
            path = entry["path"]

            indent = "  " * depth
            node_type = node.get("node_type", "memory")
            content_preview = node.get("content", "")[:80]

            if path:
                last_link = path[-1]
                link_desc = {
                    "related": "relates to",
                    "caused": "caused",
                    "follows": "led to",
                    "supports": "supports",
                    "contradicts": "contradicts",
                }.get(last_link.get("link_type", "related"), "connects to")
                parts.append(
                    f"{indent}-> [{node_type}] {link_desc}: '{content_preview}'"
                )
            else:
                parts.append(
                    f"{indent}-> [{node_type}] '{content_preview}'"
                )

        parts.append(
            f"\nChain depth: {len(chain)} nodes. "
            f"This reveals the connected context "
            f"behind the original memory."
        )

        return "\n".join(parts)

    def expand(
        self,
        node_ids: list[str],
        user_id: str = None,
        include_similar: bool = True,
        include_linked: bool = True,
        limit_per_node: int = 3,
    ) -> dict:
        """
        Expand a set of nodes to include their neighbors.

        Used after recall() to enrich results with related
        context. Two expansion strategies:
          - include_linked: direct graph connections
          - include_similar: semantic neighbors via embedding

        Returns the original nodes plus their expanded context,
        deduplicated by node_id.
        """
        all_nodes = {}
        expansion_map = {}

        for node_id in node_ids:
            expansion_map[node_id] = {"linked": [], "similar": []}

            if include_linked:
                linked = self.get_linked_nodes(
                    node_id=node_id,
                    direction="both",
                    limit=limit_per_node,
                    user_id=user_id,
                )
                for neighbor in linked:
                    nid = neighbor["id"]
                    if nid not in all_nodes and nid not in node_ids:
                        all_nodes[nid] = neighbor
                        expansion_map[node_id]["linked"].append(nid)

            if include_similar:
                node = self._get_model_by_id(node_id, user_id=user_id)
                if node and node.embedding is not None:
                    similar = self.find_similar(
                        query_embedding=node.embedding,
                        limit=limit_per_node + 1,
                        user_id=user_id,
                    )
                    for s in similar:
                        sid = s["id"]
                        if sid != node_id and sid not in all_nodes and sid not in node_ids:
                            all_nodes[sid] = s
                            expansion_map[node_id]["similar"].append(sid)

        return {
            "original_node_ids": node_ids,
            "expanded_nodes": list(all_nodes.values()),
            "expansion_count": len(all_nodes),
            "expansion_map": expansion_map,
        }

    # ------------------------------------------------------------------
    # Link operations
    # ------------------------------------------------------------------

    def create_link(
        self, source_id: str, target_id: str, link_type: str = "related"
    ) -> dict:
        """Create a directed link between two existing nodes."""
        sid = uuid.UUID(str(source_id))
        tid = uuid.UUID(str(target_id))
        if sid == tid:
            raise ValueError("source_id and target_id cannot be the same")
        count = (
            self.db.query(MemoryNodeModel.id)
            .filter(MemoryNodeModel.id.in_([sid, tid]))
            .count()
        )
        if count != 2:
            raise ValueError("source and/or target node does not exist")
        link = MemoryLinkModel(source_node_id=sid, target_node_id=tid, link_type=link_type)
        try:
            self.db.add(link)
            self.db.commit()
            self.db.refresh(link)
            return {
                "id": str(link.id),
                "source_node_id": str(link.source_node_id),
                "target_node_id": str(link.target_node_id),
                "link_type": link.link_type,
                "strength": link.strength,
                "created_at": link.created_at.isoformat() if link.created_at else None,
            }
        except SQLAlchemyError:
            self.db.rollback()
            raise

    def suggest(
        self,
        query: str = None,
        tags: list[str] = None,
        context: str = None,
        user_id: str = None,
        limit: int = 3,
    ) -> dict:
        """
        Generate suggestions based on past high-performing
        memories.

        Finds memories with:
        - High resonance v2 score (semantically relevant)
        - High success rate (led to good outcomes)
        - High adaptive weight (reinforced over time)

        Returns actionable suggestions with reasoning.

        This is the "based on past, do this" layer —
        memory actively guides future decisions.
        """
        if not query and not tags:
            return {
                "suggestions": [],
                "message": "Provide query or tags for suggestions",
            }

        candidates = self.recall(
            query=query,
            tags=tags,
            limit=limit * 3,
            user_id=user_id,
        )

        if isinstance(candidates, dict):
            candidates = candidates.get("results", [])

        high_performers = [
            c for c in candidates
            if c.get("success_rate", 0.5) > 0.6
            and c.get("adaptive_weight", 1.0) > 0.8
        ]

        if not high_performers:
            high_performers = candidates[:limit]

        suggestions = []
        for memory in high_performers[:limit]:
            node_type = memory.get("node_type", "memory")
            content = memory.get("content", "")
            success_rate = memory.get("success_rate", 0.5)
            weight = memory.get("adaptive_weight", 1.0)
            resonance = memory.get("resonance_score", 0.0)

            if node_type == "decision":
                action = (
                    f"Consider repeating this decision: "
                    f"{content[:120]}"
                )
                reasoning = (
                    f"This decision type succeeded "
                    f"{success_rate*100:.0f}% of the time "
                    f"in similar contexts."
                )
            elif node_type == "outcome":
                action = (
                    f"This approach worked before: "
                    f"{content[:120]}"
                )
                reasoning = (
                    f"Similar actions led to positive outcomes "
                    f"with {success_rate*100:.0f}% success rate."
                )
            elif node_type == "insight":
                action = f"Apply this insight: {content[:120]}"
                reasoning = (
                    f"This pattern has been validated "
                    f"{memory.get('usage_count', 0)} times."
                )
            else:
                action = f"Relevant context: {content[:120]}"
                reasoning = f"High relevance score: {resonance:.2f}"

            warning = None
            if memory.get("failure_count", 0) > 0:
                failure_rate = 1 - success_rate
                if failure_rate > 0.3:
                    warning = (
                        f"Caution: this approach failed "
                        f"{failure_rate*100:.0f}% of the time. "
                        f"Review context carefully."
                    )

            suggestions.append({
                "node_id": memory.get("id"),
                "node_type": node_type,
                "action": action,
                "reasoning": reasoning,
                "warning": warning,
                "confidence": round(resonance * weight, 3),
                "success_rate": round(success_rate, 3),
                "usage_count": memory.get("usage_count", 0),
                "resonance_score": round(resonance, 3),
            })

        suggestions.sort(
            key=lambda x: x["confidence"],
            reverse=True,
        )

        return {
            "query": query,
            "tags": tags,
            "suggestions": suggestions,
            "suggestion_count": len(suggestions),
            "message": (
                f"Based on {len(suggestions)} high-performing "
                f"past memories, here's what worked before:"
                if suggestions else
                "Not enough feedback data yet. Use memory nodes "
                "and record outcomes to build suggestions."
            ),
        }
