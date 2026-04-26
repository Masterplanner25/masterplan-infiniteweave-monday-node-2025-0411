# Analytics Module Architecture

## Overview
`apps/analytics/` owns metric calculation, Infinity score computation, loop decisioning, and the route/syscall surfaces that expose those capabilities. It does not own task data, social data, memory retrieval, or masterplan authorization; those come in through syscall or adapter boundaries.

## Sub-packages
### `services/calculations`
Purpose: Stateless metric calculators, batch calculation helpers, and simple compute-oriented persistence helpers.

Files in this package:
- `calculation_services.py`
- `calculations.py`
- `compute_service.py`

Entry points:
- `save_calculation()`
- `calculate_twr()` and the other pure metric calculators
- `process_batch()`
- `list_calculation_results()`
- `list_masterplans_compute()`
- `create_masterplan_compute()`

Key dependencies:
- `apps.analytics.models`
- `apps.analytics.schemas`
- `services/orchestration/concurrency.py`
- `AINDY.platform_layer.registry`

Safe to modify in isolation:
- Pure formulas in `calculation_services.py`
- Batch aggregation behavior in `calculations.py`
- Read/write query shape in `compute_service.py`

### `services/scoring`
Purpose: Infinity score computation plus per-user weight and threshold adaptation.

Files in this package:
- `infinity_service.py`
- `kpi_weight_service.py`
- `policy_adaptation_service.py`

Entry points:
- `calculate_infinity_score()`
- `get_user_kpi_snapshot()`
- `get_effective_weights()`
- `adapt_kpi_weights()`
- `get_effective_thresholds()`
- `adapt_policy_thresholds()`

Key dependencies:
- `apps.analytics.models`
- `apps.analytics.user_score`
- `services/orchestration/concurrency.py`
- `services/orchestration/infinity_loop.py`
- `apps.automation.infinity_loop`
- `apps.arm.models`
- `AINDY.db.models.watcher_signal`

Safe to modify in isolation:
- Score formulas in `infinity_service.py` if the returned keys and persistence contract stay unchanged
- Learning-rate and threshold-tuning logic in the adaptation services

### `services/orchestration`
Purpose: The runtime control plane for analytics execution, including lease management, loop evaluation, and the top-level orchestrator.

Files in this package:
- `concurrency.py`
- `infinity_loop.py`
- `infinity_orchestrator.py`

Entry points:
- `execute()`
- `handle_goal_state_changed()`
- `run_loop()`
- `evaluate_pending_adjustment()`
- `get_latest_adjustment()`
- `serialize_adjustment()`
- lease helpers from `concurrency.py`

Key dependencies:
- `services/scoring`
- `services/integration`
- `AINDY.core.execution_signal_helper`
- `AINDY.core.system_event_service`
- `AINDY.platform_layer.registry`
- `AINDY.platform_layer.trace_context`

Safe to modify in isolation:
- Lease and transaction behavior in `concurrency.py`
- Loop heuristics in `infinity_loop.py` if the adjustment payload contract remains stable
- Orchestrator sequencing in `infinity_orchestrator.py` if it still emits the same system events and returns the same result shape

### `services/integration`
Purpose: Boundary adapters to other domains and syscall-based guards.

Files in this package:
- `dependency_adapter.py`
- `tasks_bridge.py`
- `masterplan_guard.py`

Entry points:
- `fetch_recent_memory()`
- `fetch_user_metrics()`
- `fetch_task_graph_context()`
- `fetch_social_performance_signals()`
- `fetch_memory_signals()`
- `assert_masterplan_owned_via_syscall()`
- `get_task_graph_context_via_syscall()`

Key dependencies:
- `apps.identity.services.identity_boot_service`
- `apps.social.services.social_performance_service`
- `apps.automation.models`
- `AINDY.memory.memory_scoring_service`
- `AINDY.platform_layer.system_state_service`
- `AINDY.kernel.syscall_dispatcher`

Safe to modify in isolation:
- Translation logic between analytics and external domains
- Syscall payload/response shaping

## Execution Flow
Main KPI and loop path:

`apps/analytics/routes/main_router.py::_execute_main`
-> `apps.analytics.services.orchestration.infinity_orchestrator.execute`
-> `apps.analytics.services.integration.dependency_adapter.fetch_*`
-> `apps.analytics.services.scoring.infinity_service.calculate_infinity_score`
-> `apps.analytics.services.scoring.kpi_weight_service.get_effective_weights`
-> `apps.analytics.services.orchestration.infinity_loop.evaluate_pending_adjustment`
-> `apps.analytics.services.orchestration.infinity_loop.run_loop`
-> `apps.analytics.services.scoring.policy_adaptation_service.get_effective_thresholds`
-> `apps.analytics.services.integration.dependency_adapter.create_loop_adjustment`
-> persisted `UserScore`, `ScoreHistory`, and `LoopAdjustment` rows

Lightweight calculation path:

`apps/analytics/routes/main_router.py`
-> `apps.analytics.services.calculations.calculation_services.*`
-> optional `save_calculation()`
-> persisted `CalculationResult`

## Dependency Graph
Internal service edges:

- `calculations.py -> calculation_services.py`
- `calculation_services.py -> orchestration/concurrency.py`
- `infinity_service.py -> orchestration/concurrency.py`
- `infinity_service.py -> scoring/kpi_weight_service.py`
- `policy_adaptation_service.py -> orchestration/infinity_loop.py`
- `infinity_loop.py -> orchestration/concurrency.py`
- `infinity_loop.py -> integration/dependency_adapter.py`
- `infinity_loop.py -> scoring/infinity_service.py`
- `infinity_loop.py -> scoring/kpi_weight_service.py`
- `infinity_loop.py -> scoring/policy_adaptation_service.py`
- `infinity_orchestrator.py -> orchestration/concurrency.py`
- `infinity_orchestrator.py -> orchestration/infinity_loop.py`
- `infinity_orchestrator.py -> scoring/infinity_service.py`
- `infinity_orchestrator.py -> scoring/policy_adaptation_service.py`
- `infinity_orchestrator.py -> integration/dependency_adapter.py`
- `dependency_adapter.py -> tasks_bridge.py`

Root entry points:
- `services/calculations/calculation_services.py`
- `services/calculations/compute_service.py`
- `services/orchestration/infinity_orchestrator.py`
- `services/scoring/kpi_weight_service.py`
- `services/scoring/policy_adaptation_service.py`
- `services/integration/masterplan_guard.py`

Leaf nodes:
- `services/orchestration/concurrency.py`
- `services/integration/tasks_bridge.py`
- `services/integration/masterplan_guard.py`
- `services/calculations/compute_service.py`

Longest call chain:

`routes/main_router.py`
-> `orchestration/infinity_orchestrator.py::execute`
-> `scoring/infinity_service.py::calculate_infinity_score`
-> `scoring/kpi_weight_service.py::get_effective_weights`
-> `orchestration/infinity_loop.py::run_loop`
-> `scoring/policy_adaptation_service.py::get_effective_thresholds`
-> `integration/dependency_adapter.py::create_loop_adjustment`

## What Is Safe To Modify In Isolation
- `services/calculations`: formula and batch behavior changes are isolated as long as function names and result shapes remain unchanged.
- `services/scoring`: scoring and adaptation heuristics are isolated if the persisted model fields and orchestrator-facing dict keys stay stable.
- `services/orchestration`: sequencing and lease behavior are isolated if `execute()` still owns score updates and loop creation.
- `services/integration`: external-domain fetches and syscall guards are isolated if they keep returning the same analytics-facing shapes.

## Circular Import Status
[NONE FOUND] No import-time circular import currently breaks module loading. There is a runtime execution cycle between orchestration and scoring services, but it is mediated through function-local imports rather than module-level circular imports.

## Known Issues
- `services/` still contains thin compatibility shim modules for the old flat import paths. The implementation lives only in the new sub-packages, but tests and patch targets still depend on the historic paths.
