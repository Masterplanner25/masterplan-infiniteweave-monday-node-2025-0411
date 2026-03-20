from .bridge import create_memory_node, create_memory_link, recall_memories
from .nodus_memory_bridge import NodusMemoryBridge, create_nodus_bridge


def suggest_from_memory(
    db,
    query: str = None,
    tags: list = None,
    user_id: str = None,
    limit: int = 3,
) -> dict:
    """
    Convenience wrapper for the suggestion engine.
    For use in workflow hooks.
    Returns {"suggestions": [...]} or {} on error.
    """
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
        dao = MemoryNodeDAO(db)
        return dao.suggest(
            query=query,
            tags=tags,
            user_id=user_id,
            limit=limit,
        )
    except Exception as e:
        import logging
        logging.warning("suggest_from_memory failed: %s", e)
        return {"suggestions": []}

