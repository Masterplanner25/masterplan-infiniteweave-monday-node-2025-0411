"""
MemoryNodeDAO — canonical data-access object for memory_nodes and memory_links.

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

    def get_by_id(self, node_id: str) -> Optional[dict]:
        """Return a node dict by UUID string, or None if not found."""
        try:
            node_uuid = uuid.UUID(str(node_id))
        except ValueError:
            return None
        db_node = self.db.query(MemoryNodeModel).filter(MemoryNodeModel.id == node_uuid).first()
        if not db_node:
            return None
        return self._node_to_dict(db_node)

    def get_by_tags(self, tags: List[str], limit: int = 50, mode: str = "AND") -> List[dict]:
        """
        Return nodes whose tags array contains the given tags.
        mode='AND'  — all tags must be present.
        mode='OR'   — any tag must be present.
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
        from sqlalchemy import cast

        distance_expr = MemoryNodeModel.embedding.op("<=>")(
            cast(query_embedding, Vector(1536))
        )

        query = self.db.query(
            MemoryNodeModel,
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
        for node, distance in results:
            similarity = max(0.0, 1.0 - (distance / 2.0))
            if similarity >= min_similarity:
                node_dict = self._node_to_dict(node)
                node_dict["similarity"] = round(similarity, 4)
                node_dict["distance"] = round(float(distance), 4)
                output.append(node_dict)

        return output

    # ------------------------------------------------------------------
    # Graph query: get nodes linked to a given node
    # ------------------------------------------------------------------

    def get_linked_nodes(self, node_id: str, direction: str = "both") -> List[dict]:
        """
        Return all nodes directly linked to node_id.

        direction='out'  — nodes this node points to (source → target)
        direction='in'   — nodes that point to this node (target ← source)
        direction='both' — union of both directions (default)
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
                nodes = (
                    self.db.query(MemoryNodeModel)
                    .filter(MemoryNodeModel.id.in_(target_ids))
                    .all()
                )
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
                nodes = (
                    self.db.query(MemoryNodeModel)
                    .filter(MemoryNodeModel.id.in_(source_ids))
                    .all()
                )
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
