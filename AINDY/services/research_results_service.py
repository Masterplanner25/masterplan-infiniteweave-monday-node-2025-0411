from sqlalchemy.orm import Session
from bridge import create_memory_node  # ✅ import symbolic memory constructs
from db.models.research_results import ResearchResult
from db.models.research_results_schema import ResearchResultCreate

# symbolic structure to trace memory relationships
class MemoryTrace:
    def __init__(self):
        self.traces = []

    def add_trace(self, source: str, target: str, relation: str = "linked"):
        trace = {"source": source, "target": target, "relation": relation}
        self.traces.append(trace)
        print(f"[Trace] Linked {source} → {target}")

    def all_traces(self):
        return self.traces
    
# Initialize a global memory trace for this runtime session
global_trace = MemoryTrace()

def log_to_memory_bridge(query: str, summary: str):
    """
    Logs research results into A.I.N.D.Y.'s Memory Bridge layer.
    Creates a symbolic MemoryNode tagged for continuity and recall.
    """
    try:
        node = MemoryNode(
            content=f"Research Summary for '{query}': {summary}",
            source="Research Engine",
            tags=["research", "insight", "bridge"]
        )
        global_trace.add_node(node)
        print(f"[MemoryBridge] Logged research node for query: {query}")
    except Exception as e:
        print(f"[MemoryBridge] Logging failed: {e}")

def create_research_result(db: Session, result: ResearchResultCreate):
    db_item = ResearchResult(**result.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)

    # 🧩 Step 4: Log this research to the Memory Bridge
    log_to_memory_bridge(db_item.query, db_item.summary)

    return db_item


def get_all_research_results(db: Session):
    return db.query(ResearchResult).order_by(ResearchResult.created_at.desc()).all()
