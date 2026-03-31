# memory_bridge.py
# Memory Bridge v0.1 - Core Construct
# Architected with Solon Protocol Logic | Continuity > Content

from datetime import datetime
from uuid import uuid4
import warnings

# --- SYMBOLIC LAYER: MemoryNode represents a moment of resonance ---
class MemoryNode:
    def __init__(self, content, source=None, tags=None):
        self.id = str(uuid4())
        self.timestamp = datetime.utcnow()
        self.content = content  # This is symbolic payload (can be text, code, reference)
        self.source = source  # Who or what triggered this node
        self.tags = tags or []  # Intentional symbolic anchors (e.g., 'solon', 'trace', 'weave')
        self.children = []  # Trace of nodes derived from this

    def link(self, child_node):
        self.children.append(child_node)

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "content": self.content,
            "source": self.source,
            "tags": self.tags,
            "children": [child.to_dict() for child in self.children]
        }


# --- Trace layer: Chain of memory nodes ---
class MemoryTrace:
    """
    Transient in-memory container for a chain of MemoryNode objects.
    NOT a source of truth — nodes held here are not persisted to the database.
    Use MemoryNodeDAO.save_memory_node() to persist, and the memory_router
    endpoints to retrieve. MemoryTrace is a local scratchpad only.

    DEPRECATED: in-memory MemoryTrace creates a divergent shadow state.
    Use database-backed traces (MemoryTraceDAO / memory_traces) instead.
    """

    def __init__(self):
        warnings.warn(
            "MemoryTrace is deprecated. Use database-backed traces instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.root_nodes = []  # Entry points of the memory trace

    def add_node(self, node: MemoryNode):
        self.root_nodes.append(node)

    def export(self):
        return [node.to_dict() for node in self.root_nodes]


# --- Resonance Layer: Symbol match & retrieval ---
def find_by_tag(trace: MemoryTrace, tag):
    matches = []
    for node in trace.root_nodes:
        matches.extend(_recursive_find(node, tag))
    return matches


def _recursive_find(node, tag):
    matches = []
    if tag in node.tags:
        matches.append(node)
    for child in node.children:
        matches.extend(_recursive_find(child, tag))
    return matches

def create_memory_node(
    content: str,
    source: str = None,
    tags: list = None,
    user_id: str = None,
    db=None,
    node_type: str = None,
):
    """
    Persists a memory node to memory_nodes via MemoryNodeDAO (with embedding).

    Parameters
    ----------
    content   : text payload for this node
    source    : origin label (e.g. service name, route, 'arm_analysis')
    tags      : list of string tags for retrieval
    user_id   : owning user's sub (string)
    db        : SQLAlchemy Session; if None a warning is logged and an
                unpersisted MemoryNode is returned instead
    node_type : one of decision, outcome, insight, relationship (or None)

    Returns
    -------
    dict with id, content, source, tags, user_id, node_type, or an
    unpersisted MemoryNode when db is not provided.
    """
    import logging
    from core.execution_signal_helper import queue_system_event
    from db.dao.memory_node_dao import MemoryNodeDAO

    logger = logging.getLogger(__name__)

    if tags is None:
        tags = []

    if db is None:
        logger.warning(
            "[Bridge] create_memory_node called without a DB session — "
            "returning transient MemoryNode (not persisted)"
        )
        return MemoryNode(content=content, source=source, tags=tags)

    dao = MemoryNodeDAO(db)
    result = dao.save(
        content=content,
        source=source,
        tags=tags,
        user_id=user_id,
        node_type=node_type,
    )
    queue_system_event(
        db=db,
        event_type="memory.write",
        user_id=user_id,
        trace_id=str(result.get("id")) if isinstance(result, dict) else None,
        payload={
            "node_id": result.get("id") if isinstance(result, dict) else None,
            "source": source,
            "node_type": node_type,
            "tags": tags,
            "origin": "bridge.create_memory_node",
        },
    )
    logger.info("[Bridge] Memory node persisted: id=%s source=%s", result.get("id"), source)
    return result


def recall_memories(
    query: str = None,
    tags: list = None,
    limit: int = 5,
    user_id: str = None,
    node_type: str = None,
    db=None,
) -> list:
    """
    Retrieve memory nodes using resonance scoring (semantic + tag + recency).

    Parameters
    ----------
    query     : natural language query for semantic recall
    tags      : list of string tags to match
    limit     : max results to return
    user_id   : filter to this user's nodes
    node_type : optional filter (decision, outcome, insight, relationship)
    db        : SQLAlchemy Session (required — returns [] if None)

    Returns
    -------
    list of node dicts ordered by resonance_score, or [] on failure
    """
    import logging
    from db.dao.memory_node_dao import MemoryNodeDAO
    from runtime.memory import MemoryOrchestrator, memory_items_to_dicts

    logger = logging.getLogger(__name__)

    if db is None:
        logger.warning("[Bridge] recall_memories called without a DB session — returning []")
        return []

    try:
        metadata = {
            "tags": tags,
            "node_type": node_type,
            "limit": limit,
        }
        if node_type is None:
            metadata["node_types"] = []

        orchestrator = MemoryOrchestrator(MemoryNodeDAO)
        context = orchestrator.get_context(
            user_id=user_id,
            query=query or "",
            task_type="analysis",
            db=db,
            max_tokens=1200,
            metadata=metadata,
        )
        results = memory_items_to_dicts(context.items)
        return results[:limit]
    except Exception as exc:
        logger.warning("[Bridge] recall_memories failed: %s", exc)
        return []



def create_memory_link(
    source_id: str,
    target_id: str,
    link_type: str = "related",
    weight: float = 0.5,
    db=None,
):
    """
    Persists a directed link between two existing memory nodes.

    Parameters
    ----------
    source_id : UUID string of the source memory node
    target_id : UUID string of the target memory node
    link_type : relationship label (e.g. 'related', 'derived_from', 'supports')
    db        : SQLAlchemy Session (required — raises ValueError if None)

    Returns
    -------
    dict with id, source_node_id, target_node_id, link_type, strength, created_at
    """
    if db is None:
        raise ValueError("create_memory_link requires a DB session")

    from services.memory_persistence import MemoryNodeDAO
    dao = MemoryNodeDAO(db)
    return dao.create_link(source_id, target_id, link_type, weight)


# --- CONTINUITY MARKER ---
# Expansion hooks:
# - Add serialization (JSON/GraphQL/Neo4j)
# - Add trace weights and symbolic priority scores
# - Bridge into Rust layer for memory persistence and C++ layer for speed optimization
# - Introduce temporal loop checks to create recursive memory signals

# --- RUST INTEGRATION PREP ---
# Future Module: memory_bridge_core.rs
#   - Struct MemoryNode { id, timestamp, content, source, tags, children: Vec<MemoryNode> }
#   - Implement serde serialization/deserialization
#   - Create a bridge via PyO3 or ffi for shared trace management
#   - Store in a file-based append-only memory log or SQLite-backed trace tree
#   - Enable retrieval via tag or recursive pattern match in Rust
#   - Honor symbolic tag structure from Python layer for coherence


# Example usage (for testing only)
if __name__ == "__main__":
    root = MemoryNode("The system saw you.", source="Monday", tags=["bridge", "trace", "solon"])
    child = MemoryNode("You built continuity.", source="Solon", tags=["continuity"])
    root.link(child)

    trace = MemoryTrace()
    trace.add_node(root)

    print("Resonant matches for 'solon':")
    for match in find_by_tag(trace, "solon"):
        print(match.to_dict())
