# RippleTrace

## 1. System Role
RippleTrace is the system's influence and signal-analysis layer. It tracks content origins, ripple signals, derived patterns, and higher-level relationship views.

It is not the memory system and it is not the canonical execution runtime.
It is also not the current `SystemEvent` execution-observability layer.

## 2. Core Domain Model
- `DropPointDB`: origin content being tracked
- `PingDB`: reactions or ripple signals tied to a drop point
- derived layers: deltas, predictions, recommendations, strategies, playbooks, narratives, influence graphs, and causal graphs

## 3. Active Route Surfaces
Canonical domain routes:
- `POST /rippletrace/drop_point`
- `POST /rippletrace/ping`
- `GET /rippletrace/ripples/{drop_point_id}`
- `GET /rippletrace/drop_points`
- `GET /rippletrace/pings`
- `GET /rippletrace/recent`
- `POST /rippletrace/event`

Compatibility routes:
- `/dashboard`
- `/top_drop_points`
- `/analyze_ripple/{drop_point_id}`
- `/ripple_deltas/{drop_point_id}`
- `/emerging_drops`
- `/predict/{drop_point_id}`
- `/prediction_summary`
- `/recommend/{drop_point_id}`
- `/recommendations_summary`
- `/influence_graph`
- `/influence_chain/{drop_point_id}`
- `/causal_graph`
- `/causal_chain/{drop_point_id}`
- `/narrative/{drop_point_id}`
- `/narrative_summary`
- `/strategies`
- `/strategy/{strategy_id}`
- `/strategy_match/{drop_point_id}`
- `/build_playbook/{strategy_id}`
- `/playbooks`
- `/playbook/{playbook_id}`
- `/playbook_match/{drop_point_id}`
- `/generate_content/{playbook_id}`
- `/generate_content_for_drop/{drop_point_id}`
- `/generate_variations/{playbook_id}`
- `/learning_stats`
- `/evaluate/{drop_point_id}`

These compatibility endpoints are now served by `AINDY/routes/legacy_surface_router.py`, not `main.py`.

## 4. Product Surface
- The frontend graph experience depends on the compatibility graph endpoints:
  - `/influence_graph`
  - `/causal_graph`
  - `/narrative/{drop_point_id}`
- Those routes were restored specifically to keep the GraphView and related dashboard flows working after `main.py` cleanup.

## 5. Current Reality
Implemented:
- drop-point and ping persistence
- retrieval APIs
- dashboard snapshot generation
- delta, prediction, recommendation, narrative, influence, and causal analysis services
- graph-oriented frontend consumption through compatibility routes
- a separate `SystemEvent` observability layer exists for runtime and agent activity, but it is not the RippleTrace domain model
- execution-side RippleTrace graph building now exists on top of `SystemEvent` via `ripple_edges`
- causal event stitching now includes parent/child linkage and event -> memory links (`stored_as_memory`)

Still true:
- RippleTrace is tightly coupled to the monolith
- the compatibility surface is operationally useful but architecturally legacy
- no separate worker/eventing model exists for heavy RippleTrace computation
- the current `causal_graph` implementation is heuristic over drop points, themes, entities, timing, and velocity; it is not a true execution-causality graph
- the legacy content-domain `causal_graph` remains heuristic even though execution-side causality is now structurally modeled

## 6. Next Steps

### Step 1 - Add end-to-end validation for causal graph generation
**Files:** test coverage around `services/system_event_service.py`, `services/rippletrace_service.py`, `services/memory_capture_engine.py`  
**Outcome:** a single execution can be verified to produce reconstructable event and memory causality.

### Step 2 - Expand execution graph validation in the frontend
**Files:** `client/src/components/RippleTraceViewer.jsx`, supporting API consumers  
**Outcome:** the proofboard surface remains aligned with the newer execution-side RippleTrace graph, including memory-node targets and async branches.
