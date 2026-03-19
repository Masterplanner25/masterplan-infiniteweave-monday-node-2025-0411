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

        score = (semantic * 0.6) + (tag_match * 0.2) + (recency * 0.2)
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
            semantic = c.get("semantic_score", 0.0)

            tag_score = 0.0
            if tags:
                node_tags = set(c.get("tags") or [])
                query_tags = set(tags)
                if query_tags:
                    tag_score = len(node_tags & query_tags) / len(query_tags)

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

            resonance = (
                (semantic * 0.6)
                + (tag_score * 0.2)
                + (recency_score * 0.2)
            )
            c["tag_score"] = round(tag_score, 4)
            c["recency_score"] = round(recency_score, 4)
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
