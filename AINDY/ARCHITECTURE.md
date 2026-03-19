**Memory Bridge v3 - Structured Continuity**

This document captures the v3 architecture layer for Memory Bridge: temporal history + multi-hop traversal.

**Traversal Diagram**
```text
start_node
   |
   | strongest outbound link
   v
node_1 ----> node_2 ----> node_3
   |            |
   |            +--> (branch) node_2b
   |
   +--> (branch) node_1b

Rules:
1. Depth-first traversal (DFS)
2. Follow strongest links first
3. Stop at max_depth or no outbound links
4. Visited set prevents cycles (A -> B -> A)
```

**History Model (Append-Only)**
- Every explicit update to a MemoryNode writes a `memory_node_history` row.
- History stores **previous** values only; current state remains in `memory_nodes`.

**Why It Matters**
- Retrieval can explain *why* a memory matters by following connected chains over time.
- Historical snapshots allow temporal reconstruction of what the system knew at a given point.
