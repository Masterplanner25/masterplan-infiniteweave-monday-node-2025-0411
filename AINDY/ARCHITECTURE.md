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

**Memory Bridge v5 - Memory-Native Execution**

**Execution Loop Diagram**
```text
execute → remember → learn → adapt → execute better

1) Recall (pre-execution)
   - retrieve relevant memories by query/tags
2) Execute (workflow runs)
   - caller uses recalled context
3) Remember (post-execution)
   - capture outcome via MemoryCaptureEngine
4) Feedback (learning)
   - record outcomes on recalled memories
```

**Why It Matters**
- Memory is embedded into execution, not a manual afterthought.
- Centralized capture ensures consistent learning across workflows.
