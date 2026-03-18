# memory_bridge.py
# Memory Bridge v0.1 - Core Construct
# Architected with Solon Protocol Logic | Continuity > Content

from datetime import datetime
from uuid import uuid4

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
    """

    def __init__(self):
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
    node_type: str = "generic",
):
    """
    Persists a memory node to memory_nodes via MemoryNodeDAO.

    Parameters
    ----------
    content   : text payload for this node
    source    : origin label (e.g. service name, route, 'leadgen')
    tags      : list of string tags for retrieval
    user_id   : owning user's sub (string)
    db        : SQLAlchemy Session; if None a warning is logged and an
                unpersisted MemoryNode is returned instead
    node_type : node classification (default 'generic')

    Returns
    -------
    dict with id, content, source, tags, user_id, node_type, or an
    unpersisted MemoryNode when db is not provided.
    """
    import logging
    from services.memory_persistence import MemoryNodeDAO

    logger = logging.getLogger(__name__)

    if tags is None:
        tags = []

    if db is None:
        logger.warning(
            "[Bridge] create_memory_node called without a DB session — "
            "returning transient MemoryNode (not persisted)"
        )
        return MemoryNode(content=content, source=source, tags=tags)

    node = MemoryNode(content=content, source=source, tags=tags)
    node.node_type = node_type
    node.user_id = user_id

    dao = MemoryNodeDAO(db)
    db_node = dao.save_memory_node(node)
    logger.info("[Bridge] Memory node persisted: id=%s source=%s", db_node.id, source)
    return {
        "id": str(db_node.id),
        "content": db_node.content,
        "source": db_node.source,
        "tags": db_node.tags,
        "user_id": db_node.user_id,
        "node_type": db_node.node_type,
        "created_at": db_node.created_at.isoformat() if db_node.created_at else None,
    }



def create_memory_link(
    source_id: str,
    target_id: str,
    link_type: str = "related",
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
    return dao.create_link(source_id, target_id, link_type)


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
