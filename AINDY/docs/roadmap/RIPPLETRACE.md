# RippleTrace

## 1. System Role
RippleTrace is the system’s influence and signal-analysis layer. It tracks content origins, ripple signals, derived patterns, and higher-level relationship views.

It is not the memory system and it is not the canonical execution runtime.

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

Still true:
- RippleTrace is tightly coupled to the monolith
- the compatibility surface is operationally useful but architecturally legacy
- no separate worker/eventing model exists for heavy RippleTrace computation
