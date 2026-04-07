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

---

## Execution System (OS-LIKE — 2026-04-06)

### Classification

A.I.N.D.Y. is classified as OS-LIKE: every request enters one pipeline, every execution is identity-bound, and every DB operation is domain-owned.

### Canonical execution path

```text
HTTP request
   |
   v
route handler (zero DB, input validation only)
   |
   v
execute_with_pipeline / execute_with_pipeline_sync   ← core/execution_helper.py
   |
   v
ExecutionPipeline.run()                              ← core/execution_pipeline.py
   |-- _safe_require_eu()       → creates ExecutionUnit in DB
   |-- ExecutionDispatcher      → sole INLINE/ASYNC decision authority
   |-- handler(ctx)             → closure calling domain service
   |-- _inject_execution_envelope()  → auto-injects {eu_id, trace_id, status, duration_ms, ...}
   |
   v
response with canonical execution_envelope
```

### Key components

| Component | File | Responsibility |
|---|---|---|
| `ExecutionPipeline` | `core/execution_pipeline.py` | Timing, EU creation, envelope injection, signal processing |
| `ExecutionDispatcher` | `core/execution_dispatcher.py` | Sole authority for INLINE vs ASYNC decisions |
| `ExecutionUnit` | `db/models/execution_unit.py` | Durable per-request identity record |
| `require_execution_unit()` | `core/execution_gate.py` | Creates EU before handler executes |
| `to_envelope()` | `core/execution_gate.py` | Canonical `{eu_id, trace_id, status, output, error, duration_ms, attempt_count}` |
| `RetryPolicy` | `core/retry_policy.py` | Resolved via `_resolve_policy_for_eu()`, stored on `eu.extra["retry_policy"]` |
| Domain services | `domain/` | Exclusively own all `db.query` / `db.add` / `db.commit` |

### Route purity rules

- Routes contain zero `db.query`, `db.add`, or `db.commit` calls
- Routes validate input, build a handler closure, call `execute_with_pipeline_sync`, return result
- All domain logic (including DB access) lives in `domain/` services
- Handler closures capture route-level variables; domain imports are lazy inside the closure

### Execution envelope

Auto-injected by `ExecutionPipeline._inject_execution_envelope()` for every dict-typed handler response:

```json
{
  "execution_envelope": {
    "eu_id": "uuid",
    "trace_id": "uuid",
    "status": "SUCCESS",
    "output": null,
    "error": null,
    "duration_ms": 12.4,
    "attempt_count": 1
  }
}
```

No per-route envelope construction is required.

### Async decisions

`ExecutionDispatcher._decide_mode()` is the only place that calls `async_heavy_execution_enabled()`. No route or domain service submits async jobs directly.

### See also

- `docs/architecture/EXECUTION_CONTRACT.md` — formal execution contract
- `docs/architecture/EXECUTION_AUDIT.md` — per-domain audit (all PASS as of 2026-04-06)
- `docs/architecture/SYSCALL_SYSTEM.md` — syscall layer, ABI versioning
- `docs/architecture/OS_ISOLATION_LAYER.md` — tenant isolation, quota enforcement
