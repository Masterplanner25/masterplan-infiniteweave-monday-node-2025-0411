from datetime import datetime
from typing import Dict, List, Optional, Set

from sqlalchemy.orm import Session

from AINDY.db.models import DropPointDB
from AINDY.analytics.delta_engine import compute_deltas
from AINDY.analytics.influence_graph import build_influence_graph


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _split_terms(value: Optional[str]) -> Set[str]:
    if not value:
        return set()
    return {term.strip().lower() for term in value.split(",") if term.strip()}


def _velocity_rate(drop_point_id: str, db: Session, cache: Dict[str, float]) -> float:
    if drop_point_id in cache:
        return cache[drop_point_id]
    payload = compute_deltas(drop_point_id, db)
    rate = 0.0
    if isinstance(payload, dict) and payload.get("rates"):
        rate = payload["rates"].get("velocity_rate", 0.0)
    cache[drop_point_id] = rate
    return rate


def build_causal_graph(db: Session) -> Dict[str, List[Dict]]:
    influence = build_influence_graph(db)
    causal_edges: List[Dict] = []
    nodes = influence["nodes"]
    node_lookup = {node["id"]: node for node in nodes}
    drops = db.query(DropPointDB).all()
    if not drops:
        return {"nodes": [], "causal_edges": []}

    themes_map = {dp.id: _split_terms(dp.core_themes) for dp in drops}
    entities_map = {dp.id: _split_terms(dp.tagged_entities) for dp in drops}
    velocity_cache: Dict[str, float] = {}

    for i, a in enumerate(drops):
        for b in drops[i + 1 :]:
            if a.id == b.id:
                continue

            date_a = a.date_dropped
            date_b = b.date_dropped
            temporal_weight = 0
            if date_a and date_b:
                diff_seconds = abs((date_a - date_b).total_seconds())
                if diff_seconds < 86400:
                    temporal_weight = 2
                elif diff_seconds < 604800:
                    temporal_weight = 1
                if date_a <= date_b:
                    cause, effect = a, b
                else:
                    cause, effect = b, a
            else:
                cause, effect = (a, b) if a.id < b.id else (b, a)

            theme_overlap = len(themes_map[cause.id] & themes_map[effect.id])
            entity_overlap = len(entities_map[cause.id] & entities_map[effect.id])
            momentum_alignment = 2 if (
                _velocity_rate(cause.id, db, velocity_cache) > 0
                and _velocity_rate(effect.id, db, velocity_cache) > 0
            ) else 0

            causal_score = temporal_weight + momentum_alignment + theme_overlap + entity_overlap
            confidence = min(1.0, causal_score / 10)
            if confidence <= 0.3:
                continue

            reasons: List[str] = []
            if temporal_weight:
                reasons.append("temporal_order")
            if momentum_alignment:
                reasons.append("momentum_alignment")
            if entity_overlap:
                reasons.append("shared_entities")
            if theme_overlap:
                reasons.append("shared_themes")

            causal_edges.append(
                {
                    "source": cause.id,
                    "target": effect.id,
                    "confidence": round(confidence, 3),
                    "reason": reasons or ["signal_continuity"],
                }
            )

    return {"nodes": nodes, "causal_edges": causal_edges}


def get_causal_chain(drop_point_id: str, db: Session, depth: int = 3) -> Dict:
    graph = build_causal_graph(db)
    node_map = {node["id"]: node for node in graph["nodes"]}
    if drop_point_id not in node_map:
        return {"drop_point_id": drop_point_id, "upstream_causes": [], "downstream_effects": []}

    incoming = {}
    outgoing = {}
    for edge in graph["causal_edges"]:
        outgoing.setdefault(edge["source"], []).append(edge)
        incoming.setdefault(edge["target"], []).append(edge)

    def traverse(start_id: str, edges_map: Dict[str, List[Dict]], forward: bool) -> List[Dict]:
        results = []
        visited = set()

        def dfs(current_id: str, level: int):
            if level >= depth or current_id in visited:
                return
            visited.add(current_id)
            for edge in edges_map.get(current_id, []):
                next_id = edge["target"] if forward else edge["source"]
                entry = {
                    "drop_point_id": next_id,
                    "confidence": edge["confidence"],
                    "reason": edge["reason"],
                    "edge": edge,
                }
                results.append(entry)
                dfs(next_id, level + 1)

        dfs(start_id, 0)
        return results

    upstream = traverse(drop_point_id, incoming, forward=False)
    downstream = traverse(drop_point_id, outgoing, forward=True)
    return {
        "drop_point_id": drop_point_id,
        "upstream_causes": upstream,
        "downstream_effects": downstream,
    }

