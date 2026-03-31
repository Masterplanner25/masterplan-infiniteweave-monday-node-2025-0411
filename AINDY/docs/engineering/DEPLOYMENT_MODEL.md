# Deployment Model

This document describes the current deployment shape of A.I.N.D.Y. and the operational constraints implied by the codebase.

## 1. Current Deployment Structure
- Backend entry point: `AINDY/main.py` (FastAPI app).
- Gateway entry point: `AINDY/server.js` (Express bridge/gateway).
- Frontend: `client/` (React + Vite).
- Domain routes are registered from `AINDY/routes/__init__.py`.
- Legacy compatibility endpoints are now router-backed in `AINDY/routes/legacy_surface_router.py`; they are no longer defined in `main.py`.

## 2. Startup Sequence
Recommended order:
1. Provide required environment variables.
2. Start PostgreSQL.
3. Start MongoDB if using social-layer features.
4. Run `alembic upgrade head`.
5. Start FastAPI with `uvicorn main:app`.
6. Start `server.js` if the Node gateway is required.
7. Start the frontend from `client/`.

## 3. Runtime Enforcement at Startup
The backend performs real startup checks:
- cache backend initialization (`memory` or `redis`)
- `SECRET_KEY` safety validation
- Alembic schema drift guard when `AINDY_ENFORCE_SCHEMA=true`
- background-task lease acquisition
- APScheduler startup only on the lease leader (if the `apscheduler` dependency is present; otherwise the service logs that the scheduler is disabled)
- flow registration
- stuck-run recovery scan

If schema drift is detected, startup fails with `Run alembic upgrade head`.

## 4. Environment Variables
Required or operationally important variables:
- `DATABASE_URL`
- `SECRET_KEY`
- `OPENAI_API_KEY`
- `ALLOWED_ORIGINS`
- `AINDY_ENFORCE_SCHEMA`
- `AINDY_ENABLE_BACKGROUND_TASKS`
- `AINDY_CACHE_BACKEND`
- `REDIS_URL` when Redis cache is enabled
- `MONGO_URL`
- `MONGO_DB_NAME`

## 5. Background Work Model
- Background work is not started by daemon threads.
- APScheduler is the active scheduler when installed; otherwise the system continues running without scheduled jobs.
- Leadership is coordinated through the DB lease in `background_task_leases`.
- Lease timestamps are normalized as timezone-aware UTC in the Python lease path before comparison or persistence.
- Only one instance should actively run scheduled jobs at a time.
- Follower instances still serve API traffic but do not start the scheduler.

## 6. Scaling Reality
What scales reasonably:
- stateless API reads and writes behind the Postgres-backed auth and ownership model
- multiple API instances, provided lease leadership remains single-writer for scheduler duties

What does not yet scale cleanly:
- synchronous LLM-heavy request paths
- mixed Postgres + Mongo side effects without outbox coordination
- in-process execution/orchestration under high concurrent load

## 7. Observability Surface
Available:
- request metrics persisted to `request_metrics`
- durable `SystemEvent` rows for successful health/auth/async-execution paths
- health logs
- scheduler/leadership status
- flow runs and automation logs
- agent run traces

Missing:
- distributed tracing
- durable cross-service event bus
- consistent provider-level latency/cost telemetry

## 8. Current Deployment Risks
- External provider latency still impacts request-serving threads.
- Mongo-backed features remain optional and are not enforced as a readiness gate.
- Redis cache is optional; default in-memory cache remains per-process.
- Legacy compatibility routes keep old client surfaces alive, but they do not reduce monolith coupling.

## 9. CI/CD
- GitHub Actions runs lint and tests on push/PR.
- CI applies Alembic migrations before tests.
- Coverage enforcement exists, but CI success does not prove multi-process or production-runtime correctness.
