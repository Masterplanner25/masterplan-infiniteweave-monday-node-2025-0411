# Deployment Model

This document distinguishes current deployment reality from required policy rules.

**CI/CD status (2026-03-18):** GitHub Actions pipeline is live. See `.github/workflows/ci.yml`. Two jobs run on every push/PR to `main`: `lint` (ruff) and `test` (pytest + coverage). Required secrets documented in `.github/SECRETS.md`.

## 1. Current Deployment Structure

### Current State
- Backend entry point: `AINDY/main.py` (FastAPI app).
- Gateway entry point: `AINDY/server.js` (Express server).
- Frontend location: `client/` (React + Vite).
- Local startup methods observed:
- `AINDY/main.py` is typically started via `uvicorn main:app --reload` (referenced in `AINDY/AINDY_README.md` and `start_all.ps1`).
- Gateway started via `node server.js` (referenced in `start_all.ps1` and `package.json`).
- Frontend started via `npm run dev` from `client/` (referenced in `start_all.ps1`).
- Environment variable requirements are enforced in `AINDY/config.py`.
- PostgreSQL is required; SQLite is not accepted by `DATABASE_URL` validation (`AINDY/config.py`).
- MongoDB is used via `AINDY/db/mongo_setup.py` and social routes in `AINDY/routes/social_router.py`.
- No orchestration framework is present in the repository.
- CI/CD pipeline: GitHub Actions (`.github/workflows/ci.yml`). Runs lint + tests on every push/PR to `main`. pgvector service container used for `alembic upgrade head` step. Coverage enforced at 64% floor.

## 2. Environment Configuration

### A. Required Environment Variables
> See `AINDY/.env.example` for a template with all variable names. Never commit the real `.env` file.
- `DATABASE_URL` (required; must be PostgreSQL URI).
- `OPENAI_API_KEY` (required by `AINDY/config.py` and used in `AINDY/services/genesis_ai.py`).
- `DEEPSEEK_API_KEY` (optional in config; referenced in `AINDY/config.py`).
- `MONGO_URL` (optional; defaults to `mongodb://localhost:27017` in `AINDY/db/mongo_setup.py`).
- `MONGO_DB_NAME` (optional; defaults to `aindy_social_layer` in `AINDY/db/mongo_setup.py`).
- `DEEPSEEK_CONFIG_PATH` (optional; defaults to `deepseek_config.json` in `AINDY/services/deepseek_arm_service.py`).
- `AINDY_CACHE_BACKEND` (optional; `memory` or `redis`, defaults to `memory`).
- `REDIS_URL` (required if `AINDY_CACHE_BACKEND=redis`).

### B. Environment Separation Rules (Policy)
- Local, development, and production environments must use separate `.env` configurations.
- No production secrets may be stored in code or committed files.
- No fallback to SQLite is permitted; PostgreSQL is required.

## 3. Deployment Order of Operations

### Required Sequence (Policy)
1. Validate environment variables are present and correctly set.
2. Validate database connectivity.
3. Run migrations: `alembic upgrade head` (from `AINDY/`).
4. Start backend: `uvicorn main:app` (from `AINDY/`).
5. Start gateway: `node server.js` (from `AINDY/` or repo root depending on working directory).
6. Start frontend: `npm run dev` in `client/` (if running as a separate process).

## 4. Migration Enforcement During Deployment

### Policy
- Application must not start against an outdated schema.
- Deployment must ensure DB revision matches Alembic head.
- Schema mismatch must block deployment.
- Startup enforcement can be disabled explicitly via `AINDY_ENFORCE_SCHEMA=false` (not recommended for production).

### Development Reminder
> **After any change to `AINDY/db/models/`, run `alembic upgrade head` before starting the server or running the test suite.**
> SQLAlchemy model changes do not modify the database automatically. Schema drift is a silent failure mode: the app may start without error but write or query columns that don't exist yet. Always apply pending migrations immediately after editing a model file — this rule applies in every environment (local dev, CI, staging, production).

## 5. Runtime Safeguards

### Policy
- Ensure PostgreSQL is used (no silent fallback).
- Ensure background threads do not block startup (`AINDY/main.py`).
- Ensure model provider keys are configured before use (`OPENAI_API_KEY`).
- Ensure `AINDY_ENFORCE_SCHEMA` is set appropriately for the environment (defaults to `true`).

## 6. Scaling Considerations (Current Reality)

### Current State
- Background tasks use daemon threads started in `AINDY/main.py`.
- There is no distributed scheduler or worker queue.
- No horizontal scaling guarantees are implemented.
- Multiple instances will each run background threads independently.
- SQLAlchemy pooling is configured in `AINDY/db/database.py` (`pool_size=10`, `max_overflow=20`).
- MongoDB client uses a singleton instance in `AINDY/db/mongo_setup.py`.

## 7. Logging and Observability

### Current State
- Logging is configured in `AINDY/config.py` with file and stream handlers.
- Request logging middleware exists in `AINDY/main.py` (structured JSON logs).
- Centralized logging and tracing are not present.
- FastAPI cache uses `InMemoryBackend` by default (per-process). Redis is supported via `AINDY_CACHE_BACKEND=redis` and `REDIS_URL`.
- Basic liveness endpoints exist:
- `GET /health/` in `AINDY/routes/health_router.py` performs component checks, endpoint pings, and logs to DB.
- `GET /dashboard/health` in `AINDY/routes/health_dashboard_router.py` returns recent health logs.
- `/health/` performs HTTP pings to local endpoints (e.g., `/calculate_twr`, `/seo/analyze`, `/seo/meta`, `/memory/metrics`) and can report degraded status if those routes are unavailable.

## 8. Known Deployment Risks
- Schema drift risk if Alembic migrations are not applied before start.
- Background task duplication if multiple instances are started.
- Missing retry logic for external model providers (`AINDY/services/genesis_ai.py`, `AINDY/services/deepseek_arm_service.py`).
- Lack of graceful shutdown hooks in `AINDY/main.py`.
- Readiness/health checks are limited; only health routes exist (no readiness gate is enforced).

## 9. Policy Rules for Safe Deployment
- No deployment without successful migration to Alembic head.
- No schema change without updated `docs/architecture/DATA_MODEL_MAP.md`.
- No change to invariants without updating `docs/governance/INVARIANTS.md`.
- No external provider integration without explicit fallback handling.
- No merge without passing CI (`lint` + `test` jobs in `.github/workflows/ci.yml`). See `.github/SECRETS.md` for required Actions secrets.

## 10. CI/CD Environment (GitHub Actions)

### Job: `lint`
- Runner: `ubuntu-latest`
- Tool: `ruff==0.15.6` (config: `AINDY/ruff.toml`)
- Excludes: `legacy/`, `bridge/memory_bridge_rs/`, `alembic/`

### Job: `test`
- Runner: `ubuntu-latest`
- Service: `pgvector/pgvector:pg16` (DB `base`, port 5433)
- Steps: install deps → `alembic upgrade head` → `pytest --cov-fail-under=64`
- Coverage artifact: `coverage.xml` (uploaded to Codecov)
- `tests/validate_memory_loop.py` excluded (requires live OpenAI + real DB)
- All API/DB calls are mocked via `tests/conftest.py` — no real secrets needed for test execution

### Required Actions Secrets
See `.github/SECRETS.md`. The CI `test` job supplies `DATABASE_URL` via the service container config and uses placeholder values for API keys during mocked test runs.

## Appendix: `/health/` Ping Targets
Defined in `AINDY/routes/health_router.py`:

- `POST http://127.0.0.1:8000/calculate_twr`
  - Payload: `{ "returns": [0.1, 0.05, 0.2] }`
- `POST http://127.0.0.1:8000/seo/analyze`
  - Payload: `{ "text": "AI Search Optimization", "top_n": 3 }`
- `POST http://127.0.0.1:8000/seo/meta`
  - Payload: `{ "text": "AI Search Optimization", "limit": 160 }`
- `GET http://127.0.0.1:8000/memory/metrics`
