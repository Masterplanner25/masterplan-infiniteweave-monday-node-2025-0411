from datetime import datetime
from typing import Dict, List, Set

from sqlalchemy.orm import Session

from db.models import DropPointDB, PingDB


def _split_terms(value: str) -> Set[str]:
    if not value:
        return set()
    return {term.strip().lower() for term in value.split(",") if term.strip()}


def _collect_platforms(pings: List[PingDB]) -> Dict[str, Set[str]]:
    platform_map: Dict[str, Set[str]] = {}
    for ping in pings:
        if ping.drop_point_id not in platform_map:
            platform_map[ping.drop_point_id] = set()
        if ping.source_platform:
            platform_map[ping.drop_point_id].add(ping.source_platform.lower())
    return platform_map


def build_influence_graph(db: Session) -> Dict[str, List[Dict]]:
    drops = db.query(DropPointDB).all()
    if not drops:
        return {"nodes": [], "edges": []}

    pings = db.query(PingDB).all()
    platform_map = _collect_platforms(pings)

    nodes = [
        {
            "id": dp.id,
            "title": dp.title,
            "platform": dp.platform,
            "narrative_score": dp.narrative_score or 0.0,
            "date_dropped": dp.date_dropped.isoformat() if dp.date_dropped else None,
        }
        for dp in drops
    ]

    id_map = {dp.id: dp for dp in drops}

    edges: List[Dict] = []
    for i, a in enumerate(drops):
        themes_a = _split_terms(a.core_themes)
        entities_a = _split_terms(a.tagged_entities)
        platforms_a = platform_map.get(a.id, set())
        for b in drops[i + 1 :]:
            if a.id == b.id:
                continue
            themes_b = _split_terms(b.core_themes)
            entities_b = _split_terms(b.tagged_entities)
            platforms_b = platform_map.get(b.id, set())

            overlap_count = len(themes_a & themes_b)
            entity_overlap = len(entities_a & entities_b)

            temporal_score = 0
            if a.date_dropped and b.date_dropped:
                diff = abs((a.date_dropped - b.date_dropped).total_seconds())
                days = diff / 86400
                if days < 1:
                    temporal_score = 2
                elif days < 7:
                    temporal_score = 1

            ping_similarity = 1 if platforms_a & platforms_b else 0

            score = overlap_count * 2 + entity_overlap * 3 + temporal_score + ping_similarity
            strength = min(1.0, score / 10)
            if strength <= 0.2:
                continue

            if entity_overlap > 0:
                edge_type = "entity_link"
            elif overlap_count > 0:
                edge_type = "semantic_link"
            else:
                edge_type = "temporal_link"

            edge = {
                "source": a.id,
                "target": b.id,
                "strength": round(strength, 3),
                "type": edge_type,
            }
            edges.append(edge)

            # Add reverse edge for completeness
            edges.append(
                {
                    "source": b.id,
                    "target": a.id,
                    "strength": round(strength, 3),
                    "type": edge_type,
                }
            )

    return {"nodes": nodes, "edges": edges}


def _connected_edges(drop_point_id: str, edges: List[Dict]) -> List[Dict]:
    return [
        edge
        for edge in edges
        if edge["source"] == drop_point_id or edge["target"] == drop_point_id
    ]


def influence_chain(drop_point_id: str, db: Session) -> Dict:
    graph = build_influence_graph(db)
    if not graph["nodes"]:
        return {"drop_point_id": drop_point_id, "connected_nodes": [], "strongest_edges": []}

    node_map = {node["id"]: node for node in graph["nodes"]}
    if drop_point_id not in node_map:
        return {"drop_point_id": drop_point_id, "connected_nodes": [], "strongest_edges": []}

    connected = _connected_edges(drop_point_id, graph["edges"])
    strongest_edges = sorted(connected, key=lambda e: e["strength"], reverse=True)[:5]
    connected_node_ids = {
        edge["target"] if edge["source"] == drop_point_id else edge["source"]
        for edge in connected
    }

    connected_nodes = [node_map[dp_id] for dp_id in connected_node_ids if dp_id in node_map]
    return {
        "drop_point_id": drop_point_id,
        "connected_nodes": connected_nodes,
        "strongest_edges": strongest_edges,
    }

