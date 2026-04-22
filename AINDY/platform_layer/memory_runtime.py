from __future__ import annotations

from typing import Any


def list_memory_nodes(payload: dict[str, Any], context: Any) -> dict[str, Any]:
    from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
    from AINDY.db.database import SessionLocal

    path: str = payload.get("path", "")
    if not path:
        raise ValueError("sys.v1.memory.list requires 'path'")
    limit: int = int(payload.get("limit", 50))

    db = SessionLocal()
    try:
        dao = MemoryNodeDAO(db)
        nodes = dao.query_path(path_expr=path, user_id=getattr(context, "user_id", None), limit=limit)
        return {"nodes": nodes, "count": len(nodes), "path": path}
    finally:
        db.close()


def get_memory_tree(payload: dict[str, Any], context: Any) -> dict[str, Any]:
    from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
    from AINDY.db.database import SessionLocal
    from AINDY.memory.memory_address_space import build_tree, is_exact, normalize_path, wildcard_prefix

    path: str = payload.get("path", "")
    if not path:
        raise ValueError("sys.v1.memory.tree requires 'path'")
    limit: int = int(payload.get("limit", 200))

    db = SessionLocal()
    try:
        dao = MemoryNodeDAO(db)
        if is_exact(path):
            nodes = dao.walk_path(normalize_path(path), user_id=getattr(context, "user_id", None), limit=limit)
        else:
            nodes = dao.walk_path(wildcard_prefix(path), user_id=getattr(context, "user_id", None), limit=limit)
        tree = build_tree(nodes)
        return {"tree": tree, "node_count": len(nodes), "path": path}
    finally:
        db.close()


def trace_memory_chain(payload: dict[str, Any], context: Any) -> dict[str, Any]:
    from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
    from AINDY.db.database import SessionLocal

    path: str = payload.get("path", "")
    if not path:
        raise ValueError("sys.v1.memory.trace requires 'path'")
    depth: int = int(payload.get("depth", 5))

    db = SessionLocal()
    try:
        dao = MemoryNodeDAO(db)
        chain = dao.causal_trace(path=path, depth=depth, user_id=getattr(context, "user_id", None))
        return {"chain": chain, "depth": len(chain), "path": path}
    finally:
        db.close()


__all__ = [
    "get_memory_tree",
    "list_memory_nodes",
    "trace_memory_chain",
]
