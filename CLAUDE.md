# A.I.N.D.Y.

## 1. Project Identity

A.I.N.D.Y. is a modular-monolith backend and frontend system built around a runtime platform in `AINDY/`, domain apps in `apps/`, and a React client in `client/`. It combines a flow engine, syscall layer, memory subsystem, queueing, scheduling, and domain features such as tasks, analytics, masterplan, identity, and agent coordination. The codebase is in transition toward clearer platform/domain separation, but it is still a single deployable backend with shared infrastructure and shared persistence. Work in this repository must preserve that separation direction rather than deepening direct cross-domain coupling.

## 2. Non-Negotiable Architecture Rules

The execution contract is the first rule to check before changing any route or service code. The project rule is that application and platform business routes go through `execute_with_pipeline(...)`, with route logic placed inside a `handler(ctx)` function. The execution contract exists to centralize memory capture, event emission, execution-unit lifecycle, trace propagation, and response normalization. Do not treat older direct-return infrastructure endpoints as precedents for new work.

Services are expected to stay pure. They should implement business logic and return data, or data plus execution signals, but they should not emit events, write memory, construct HTTP responses, or act as their own execution entry points. If a service needs side effects, return signals and let the pipeline apply them.

Memory writes and event emission belong to the execution pipeline only. The pipeline is where execution signals are merged, side effects are recorded, execution envelopes are injected, and lifecycle events such as `execution.started` and `execution.completed` are emitted. Direct calls from services to memory capture or system-event emission are architectural violations unless the code is itself part of platform pipeline machinery.

The canonical response chain is `ExecutionResult -> canonical response dict -> response adapter`. In practice, `execute_with_pipeline()` runs the handler, gets an `ExecutionResult`, calls `result.to_response()`, and then passes the canonical payload through `adapt_response(...)`. Do not bypass this by returning raw `Response` objects, `JSONResponse` objects, or ad hoc dicts from new business routes.

Two implementation details matter when reading the repo:

- The route wrapper lives in `AINDY/core/execution_helper.py`.
- The pipeline implementation is the `AINDY/core/execution_pipeline/` package, not a single `execution_pipeline.py` file.

There are explicit exemptions in `AINDY/core/execution_guard.py` for `/`, `/docs`, `/redoc`, `/openapi.json`, `/health*`, and `/ready`. Those are infrastructure exceptions. They are not permission to add more non-pipeline business routes.

## 3. Repository Structure

The repository has three main layers:

- `AINDY/` — runtime platform. Execution engine, syscalls, scheduling, memory, auth, queues, health, startup, and worker logic. This layer is intended to be domain-agnostic. Current repo state has no `from apps...` imports under `AINDY/`.
- `apps/` — domain modules. Tasks, analytics, masterplan, identity, freelance, search, arm, agent, and others. Domains register routes, jobs, syscalls, flows, symbols, health checks, and adapters through the plugin registry.
- `client/` — React 18 + Vite frontend. API modules live in `client/src/api/`.

Within `AINDY/`, the most important subareas are:

- `AINDY/core/` — execution pipeline, response adaptation, distributed queue, execution guards, system-event service, retry policy, and execution envelopes.
- `AINDY/kernel/` — syscall dispatcher, syscall registry, circuit breaker, event bus, resource manager, and related execution primitives.
- `AINDY/platform_layer/` — plugin registry, bootstrap graph/contract helpers, cache backend, health services, metrics, scheduler integration, and route/response adapters.
- `AINDY/routes/` — platform and infrastructure HTTP routes such as `/platform/*`, `/health*`, `/auth/*`, and `/api/version`.
- `AINDY/runtime/` — flow engine, dynamic flow definitions, flow registry/loading, memory runtime, and Nodus-related runtime integration.
- `AINDY/agents/` — agent runtime, tool registry, capability service, ranking, and agent orchestration support.

There are also two structural boundaries to keep in mind:

- `AINDY/routes/` contains HTTP entry points and platform adapters. This layer should not become a second business-logic layer.
- `apps/*/routes/` contains domain HTTP entry points. Each domain route module should remain thin and delegate into services plus the execution pipeline.

## 4. Plugin System

The plugin manifest is `aindy_plugins.json`, and in the current repo it lists only one plugin: `apps.bootstrap`. That means the platform loads domain behavior indirectly through the app bootstrap aggregator rather than importing each app module from `AINDY/`.

`apps/bootstrap.py` defines the domain bootstrap graph. It keeps a hard-coded `APP_BOOTSTRAP_MODULES` map, reads each app's `BOOTSTRAP_DEPENDS_ON`, resolves a topological order with `resolve_boot_order(...)`, and then calls each app module's `register()` function in order. Core domains come from `AINDY/config.py` as `CORE_DOMAINS = ["tasks", "identity", "agent"]`.

Bootstrap failure policy is asymmetric:

- If a core domain fails to bootstrap, startup aborts.
- If a peripheral domain fails, startup continues in degraded mode and the failed domain is published as degraded.

App `register()` functions usually call registry hooks such as:

- `register_router(...)`
- `register_syscall(...)`
- `register_flow(...)`
- `register_job(...)`
- `register_health_check(...)`
- `register_response_adapter(...)`
- `register_execution_adapter(...)`

Startup plugin loading happens through `load_plugins()` in `AINDY/startup.py`, followed by bootstrap manifest validation. The platform rule is that `AINDY/` should not grow direct `apps/` imports at module level; domain code enters through the manifest/plugin mechanism.

Operationally, startup is doing more than router registration. `AINDY/startup.py` also performs deployment guards, schema checks, syscall verification, router-boundary validation, cache/backend checks, and scheduler/background initialization. If a change affects boot order or app registration, read `AINDY/startup.py` before patching `apps/bootstrap.py`.

## 5. Syscall Layer

The syscall layer is the preferred cross-domain boundary inside the backend. The naming convention is `sys.v{N}.{domain}.{action}`. The main implementation is `AINDY/kernel/syscall_dispatcher.py`.

The dispatcher contract is important:

- it parses versioned syscall names
- validates registration and schemas
- enforces required capabilities
- checks tenant context and quota
- propagates trace and execution-unit identity
- executes the handler
- validates output non-fatally
- returns a standard envelope

The dispatcher does not raise to the caller. It always returns an envelope with:

- `status`
- `data`
- `trace_id`
- `execution_unit_id`
- `syscall`
- `version`
- `duration_ms`
- `error`
- `warning`

Prefer a syscall over a direct Python import whenever one domain needs data or behavior from another domain. That keeps the caller independent of the callee's import tree, capability model, and internal service layout. The registered syscall inventory is exposed through `GET /platform/syscalls`.

When writing syscall-related code, preserve these properties:

- versioned names stay stable once published
- payload validation happens at the dispatcher boundary
- capability checks happen before handler execution
- handlers return data, while the dispatcher is responsible for the outer envelope

## 6. Cross-Domain Rules

The current coupling policy is documented in `docs/architecture/CROSS_DOMAIN_COUPLING.md`. The short version is:

1. Never import another domain's services or models at module level.
2. Deferred imports inside function bodies are acceptable in the monolith when no better boundary exists.
3. Do not expose ORM models as cross-domain contracts when a service function or syscall can provide the needed data shape.
4. When in doubt, use a syscall.

Also keep in mind that route-level and startup-time import failures have different blast radii. Module-level imports in startup paths are the most dangerous.

## 7. Development Commands

These are the verified project commands and entry points:

```sh
# Start local stack (Postgres + API quickstart, no worker, no Redis profile)
docker compose up

# Full stack (+ Redis, worker, frontend, nginx)
docker compose --profile full up

# Fast default test suite (SQLite in-memory, TEST_MODE=true)
pytest tests/ -x -q

# Integration suite config (tests/integration, Mongo enabled)
pytest -c pytest.integration.ini

# PostgreSQL-oriented suite/config
pytest -c pytest.postgres.ini

# Apply database migrations
alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "description"

# Lint
ruff check .

# Frontend tests (run from client/)
npm test

# Frontend dev server (run from client/)
npm run dev
```

Command notes:

- `pytest.ini` uses SQLite in-memory, disables heavy async execution, and skips Mongo ping by default.
- `pytest.integration.ini` targets `tests/integration` and expects real Mongo availability.
- `pytest.postgres.ini` expects PostgreSQL on `localhost:5433`.
- `docker-compose.yml` quickstart uses only `postgres` + `api`; Redis and worker are in the `full` profile.
- `alembic.ini` is configured for the `alembic/` migration directory.

Test tiers in this repo are materially different:

- default `pytest` is the fastest feedback loop and is designed to run with SQLite in-memory plus `TEST_MODE=true`
- `pytest.integration.ini` is for slower integration behavior and expects external services that the default suite stubs or disables
- `pytest.postgres.ini` is specifically for behavior that differs on PostgreSQL, including database semantics that SQLite does not model well

If a change touches schema, startup, plugin loading, or queueing, the default suite is not always enough. Choose the test tier that matches the risk.

## 8. Adding a New Route

When adding a new HTTP route:

1. Put the route in the owning app's `routes/` directory, or in `AINDY/routes/` only if it is truly platform or infrastructure behavior.
2. Use `execute_with_pipeline()` from `AINDY/core/execution_helper.py`.
3. Put business logic in a service module, not in the route.
4. Register the router in the owning app's `bootstrap.py` with `register_router(...)`.
5. Only create an Alembic migration if the route change also introduces or changes persisted schema.

Minimal pattern:

```python
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from AINDY.core.execution_helper import execute_with_pipeline
from AINDY.db.database import get_db
from AINDY.services.auth_service import get_current_user

router = APIRouter(prefix="/example", tags=["Example"])


@router.post("/my_endpoint")
async def my_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        from apps.example.services import my_service

        result = my_service.do_work(db, str(current_user["sub"]))
        return {"data": result}

    return await execute_with_pipeline(
        request=request,
        route_name="example.my_endpoint",
        handler=handler,
        user_id=str(current_user["sub"]),
        metadata={"db": db},
    )
```

The route name matters. Response adapters and execution metadata often key off the route prefix.

Also check `docs/platform/interfaces/API_CONTRACTS.md` before adding or moving a route. The current repo has three mount groups:

- root/infrastructure routes mounted at `/`
- platform routes mounted under `/platform`
- app routes mounted under `/apps`

Do not add a new top-level root path for domain behavior unless it is an explicit compatibility surface and there is already precedent for it.

## 9. Adding a New Domain App

To add a new domain app:

1. Create `apps/{name}/`.
2. Add at minimum `bootstrap.py`, `routes/`, `services/`, and `__init__.py`. Add `models.py` only if the app owns persisted schema.
3. In `bootstrap.py`, define `register()` and declare `BOOTSTRAP_DEPENDS_ON`.
4. Inside `register()`, call the appropriate registry hooks such as `register_router(...)`, `register_syscall(...)`, `register_flow(...)`, and any adapters/health checks the app needs.
5. If the app adds DB models, load them through `AINDY/db/model_registry.py` via the app bootstrap's `register_models(...)` callback and create an Alembic migration.
6. Add the app to `APP_BOOTSTRAP_MODULES` in `apps/bootstrap.py`.
7. Do not change `aindy_plugins.json` for a new app. The plugin manifest stays pointed at `apps.bootstrap`.

The important distinction is:

- `aindy_plugins.json` controls top-level plugin entry points.
- `apps/bootstrap.py` controls domain app discovery/order inside the apps layer.

For app-owned models, do not import them into `AINDY/db/model_registry.py` directly. The current model registry only imports platform models itself and expects app model registration to happen through the app bootstrap's `register_models(...)` callback. That pattern is part of the platform/domain boundary.

## 10. Key Files Reference

| File | Purpose |
|------|---------|
| `AINDY/main.py` | FastAPI app factory and lifespan wiring (`create_app`) |
| `AINDY/startup.py` | Startup/shutdown orchestration, plugin loading, guards, scheduler setup |
| `AINDY/config.py` | Environment variables and runtime settings (`Settings`) |
| `AINDY/routing.py` | Mounts root, platform, and app routers |
| `AINDY/core/execution_helper.py` | `execute_with_pipeline()` route wrapper |
| `AINDY/core/execution_pipeline/__init__.py` | Execution pipeline package entry point exporting `ExecutionPipeline` and `ExecutionContext` |
| `AINDY/core/execution_pipeline/pipeline.py` | Pipeline run loop, signal handling, event emission, execution envelope injection |
| `AINDY/core/response_adapter.py` | Canonical response adaptation from execution result to HTTP response |
| `AINDY/kernel/syscall_dispatcher.py` | Versioned syscall dispatch and standard envelope boundary |
| `AINDY/platform_layer/registry.py` | Platform registry for routers, syscalls, flows, jobs, adapters, symbols, and plugin loading |
| `AINDY/db/database.py` | SQLAlchemy engine, `SessionLocal`, and `get_db` |
| `AINDY/db/model_registry.py` | Platform model imports plus app-model registration bridge |
| `apps/bootstrap.py` | Top-level domain boot sequencer and dependency ordering |
| `.codex/rules.md` | Original execution-contract rule file |
| `docs/architecture/CROSS_DOMAIN_COUPLING.md` | Coupling map, remediation status, and governance |
| `docs/platform/interfaces/API_CONTRACTS.md` | Verified HTTP route inventory and contract notes |

One repo quirk to know up front: some older instructions refer to `AINDY/core/execution_pipeline.py`, but in the current tree the implementation is the `AINDY/core/execution_pipeline/` package plus `AINDY/core/execution_helper.py`.

Another important quirk: `docs/platform/interfaces/API_CONTRACTS.md` reflects the current implemented route surface, including legacy compatibility paths. If a route shape in code and the contracts doc disagree, fix the code or the doc before adding more callers.

## 11. What NOT to Do

- Do not call business services inline from route handlers without going through `execute_with_pipeline()`.
- Do not import from `apps/*` in `AINDY/*` at module level.
- Do not write memory or emit execution events from services.
- Do not add module-level cross-domain imports inside `apps/*`.
- Do not bypass Alembic for schema changes.
- Do not rename flow node functions or flow-node names casually; they are persisted in runtime state and related records.
- Do not use private AINDY APIs with leading underscores when a public boundary can be exposed instead.
- Do not treat legacy direct-return routes as acceptable precedents for new business endpoints.
- Do not skip the execution contract; `AINDY/core/execution_guard.py` and startup validation are designed to catch bypasses.

If you are unsure whether a change belongs in `AINDY/` or `apps/`, bias toward:

- platform/runtime concerns in `AINDY/`
- business/domain behavior in `apps/`
- a syscall boundary instead of a direct cross-domain import

Read first, patch second, and treat startup-time import paths as the highest-risk part of the system.
