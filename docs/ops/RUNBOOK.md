---
title: "A.I.N.D.Y. Operations Runbook"
last_verified: "2026-04-25"
api_version: "1.0"
status: current
owner: "platform-team"
---

# A.I.N.D.Y. Operations Runbook

## Failure Mode Runbooks

For the three most likely production failure modes, see `docs/ops/RUNBOOK_FAILURE_MODES.md`.

Covers:
- OpenAI degradation
- Redis loss
- Stuck job storm

## 1. Prerequisites
- PostgreSQL: use PostgreSQL 16 with `pgvector` support; the repo quickstart uses `pgvector/pgvector:pg16`.
- Redis: required when `AINDY_REQUIRE_REDIS=true` or `ENV` is not `dev`/`development`/`test`. Also required for `EXECUTION_MODE=distributed`.
- MongoDB: required only when `MONGO_REQUIRED=true`. If `SKIP_MONGO_PING=true`, startup skips the ping; if `MONGO_REQUIRED=true`, that skip becomes a startup error.
- OpenAI API key: required. `config.py` rejects missing or placeholder `OPENAI_API_KEY` outside test mode.
- Nodus VM: required only when any registered flow node is `nodus.execute` or starts with `nodus.`. `NODUS_SOURCE_PATH` must point to the root directory that makes `nodus.runtime.embedding` importable.

## 2. Required Environment Variables
### 2a. Always Required
| Variable | What it does | Example | How to obtain |
|---|---|---|---|
| `DATABASE_URL` | Primary SQLAlchemy database URL | `postgresql://aindy:strongpass@db:5432/aindy` | Create the PostgreSQL DB/user first |
| `OPENAI_API_KEY` | Required AI provider key | `sk-proj-...` | Obtain from OpenAI |
| `SECRET_KEY` | JWT signing key; default is intentionally unsafe | `9a4c...` | `python -c "import secrets; print(secrets.token_hex(32))"` |

### 2b. Conditional / Optional
#### Redis
| Variable | Default | Effect | When to set |
|---|---|---|---|
| `REDIS_URL` | `None` | Enables Redis health, cache, queue, worker heartbeat, event bus | Any non-dev deployment; always for `EXECUTION_MODE=distributed` |
| `AINDY_REQUIRE_REDIS` | `False` | Forces Redis-required startup behavior | Single-instance prod that must still fail fast on missing Redis |
| `AINDY_QUEUE_NAME` | `aindy:jobs` | Queue key name | Separate environments/tenants |

#### Mongo
| Variable | Default | Effect | When to set |
|---|---|---|---|
| `MONGO_URL` | `None` | Enables Mongo-backed features | When Mongo features are used |
| `MONGO_REQUIRED` | `False` | Missing/unreachable Mongo becomes fatal | Production deployments that depend on Mongo |
| `SKIP_MONGO_PING` | `False` | Skips startup ping | Dev only |
| `MONGO_HEALTH_TIMEOUT_MS` | `5000` | Mongo ping timeout | Slow networks |
| `MONGO_CONNECT_TIMEOUT_MS` | `3000` | Mongo connect timeout | Any deployment |
| `MONGO_SOCKET_TIMEOUT_MS` | `5000` | Per-operation Mongo timeout | Any deployment |
| `MONGO_SERVER_SELECTION_TIMEOUT_MS` | `3000` | Mongo server discovery timeout | Any deployment |
| `MONGO_MAX_POOL_SIZE` | `10` | Max Mongo connections | Tune for social traffic |
| `MONGO_MIN_POOL_SIZE` | `1` | Min Mongo connections | Keep warm connection available |

#### Nodus
| Variable | Default | Effect | When to set |
|---|---|---|---|
| `NODUS_SOURCE_PATH` | `None` | Adds Nodus source to `sys.path` and enables import check | Any deployment with registered `nodus.*` nodes |

#### Cache
| Variable | Default | Effect | When to set |
|---|---|---|---|
| `AINDY_CACHE_BACKEND` | `redis` | `redis`, `memory`, or `off` | `redis` for shared deployments; `memory` only for local single-instance |

#### Execution Mode
| Variable | Default | Effect | When to set |
|---|---|---|---|
| `ENV` | `development` | Controls `is_dev`/`is_prod`, Redis requirement, dev bootstrap | Always set explicitly in deployment |
| `EXECUTION_MODE` | `thread` | `thread` or `distributed` | `distributed` when running separate workers |
| `AINDY_ENABLE_BACKGROUND_TASKS` | `true` | Enables scheduler leadership/startup hooks | Disable only for API followers or local debugging |
| `AINDY_ENFORCE_SCHEMA` | `true` | Enforces Alembic-head startup gate | Keep `true`; production rejects `false` |
| `DB_POOL_SIZE` | `10` | SQL pool size | Tune for concurrency |
| `DB_MAX_OVERFLOW` | `20` | Extra transient DB connections | Tune for burst load |
| `DB_POOL_TIMEOUT` | `30` | Wait time for pool checkout | Tune for DB pressure |
| `DB_POOL_RECYCLE` | `1800` | Recycle age in seconds | Tune for stale-connection environments |

## 3. First-Time Setup Sequence
1. Provision PostgreSQL and database.
```sql
CREATE USER aindy WITH PASSWORD 'change-this';
CREATE DATABASE aindy OWNER aindy;
```
2. Run migrations.
```bash
alembic -c alembic.ini upgrade head
```
If skipped, startup raises:
```text
Schema drift detected. Run alembic upgrade head.
```
3. Start the API server. Container quickstart command from `docker-compose.yml`:
```bash
sh -c "alembic -c alembic.ini upgrade head && uvicorn AINDY.main:app --host 0.0.0.0 --port 8000"
```
Direct process command from `Dockerfile`:
```bash
uvicorn AINDY.main:app --host 0.0.0.0 --port 8000
```
4. Verify startup with `/health`.
```bash
curl http://localhost:8000/health
```
Healthy shape:
```json
{
  "status": "healthy",
  "timestamp": "2026-04-24T00:00:00+00:00",
  "version": "1.0.0",
  "degraded_domains": [],
  "deployment_contract": {
    "environment": "production",
    "execution_mode": "thread",
    "requires": {
      "redis": true,
      "worker": false,
      "event_bus": true,
      "queue_backend": false,
      "schema_enforcement": true
    },
    "optional_in_dev": {
      "redis": false,
      "worker": false,
      "scheduler_leadership": true,
      "peripheral_domains": true
    }
  },
  "dependencies": {
    "postgres": {"status": "ok", "latency_ms": 3.2, "detail": null},
    "redis": {"status": "ok", "latency_ms": 1.1, "detail": null},
    "queue": {"status": "ok", "detail": null, "backend": "redis", "degraded": false, "redis_available": true},
    "mongo": {"status": "degraded", "latency_ms": null, "detail": "MONGO_URL not configured (embeddings disabled)"},
    "schema": {"status": "ok", "latency_ms": null, "detail": null},
    "ai_providers": {"status": "ok", "latency_ms": null, "detail": null, "openai": {"circuit": "closed", "failure_count": 0}, "deepseek": {"circuit": "closed", "failure_count": 0}}
  },
  "db_pool": {"pool_size": 10, "checkedout": 0, "overflow": 0, "checked_in": 10}
}
```
5. Create the first admin and first API key.
   In `ENV=dev`, `_ensure_dev_api_key()` auto-bootstraps only if `AINDY_API_KEY` is set; it creates/elevates a user and creates a `platform.admin` key. In production there is no automatic admin bootstrap.
```bash
curl -X POST http://localhost:8000/auth/register -H "Content-Type: application/json" -d '{"email":"admin@example.com","password":"change-this"}'
psql "$DATABASE_URL" -c "UPDATE users SET is_admin = true WHERE email = 'admin@example.com';"
JWT=$(curl -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d '{"email":"admin@example.com","password":"change-this"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -X POST http://localhost:8000/platform/keys -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" -d '{"name":"bootstrap","scopes":["platform.admin"]}'
```
6. Start the worker when `EXECUTION_MODE=distributed`.
```bash
WORKER_CONCURRENCY=1 python -m AINDY.worker.worker_loop
```
7. Verify the worker heartbeat in Redis.
```bash
redis-cli -u "$REDIS_URL" GET aindy:worker:heartbeat
```

## 4. Startup Failure Reference
| Error message (exact or exact prefix) | Cause | Fix |
|---|---|---|
| `SECRET_KEY is using the insecure default placeholder. Set a strong SECRET_KEY in your .env before running in non-development deployments.` | Default placeholder in non-dev deployment | Set a real `SECRET_KEY` |
| `SECRET_KEY is too short (` | `SECRET_KEY` under 32 chars outside test/dev | Replace with 32+ char key |
| `REDIS_URL is required in non-development deployments. Set REDIS_URL in your environment or set AINDY_REQUIRE_REDIS=false to allow single-instance mode.` | Redis-required deployment with no `REDIS_URL` | Set `REDIS_URL` or explicitly allow single-instance mode |
| `Redis is configured but not reachable at startup. Verify REDIS_URL and Redis availability before starting.` | Redis unreachable | Fix Redis/network |
| `AINDY_EVENT_BUS_ENABLED=false is not permitted when Redis-backed deployment contracts are required. Enable the event bus for production-safe WAIT/RESUME behavior.` | Event bus disabled while required | Enable event bus |
| `Unsupported AINDY_CACHE_BACKEND=` | Invalid cache backend | Use `redis`, `memory`, or `off` |
| `AINDY_ENFORCE_SCHEMA=false is not permitted in production (ENV=production). Schema enforcement is a required safety gate. To deploy with a schema change, run: alembic upgrade head` | Production with schema gate disabled | Re-enable schema enforcement and migrate |
| `Schema guard unavailable: alembic not installed.` | Alembic package unavailable | Install Alembic in runtime image |
| `Schema drift detected. Run alembic upgrade head.` | DB not at Alembic head | Run migrations |
| `APScheduler failed to start. Check apscheduler installation.` | Scheduler startup failure | Fix APScheduler/runtime image |
| `[startup] Registered Nodus nodes require the Nodus VM, but it is unavailable.` | `nodus.*` nodes registered but VM missing/unimportable | Set `NODUS_SOURCE_PATH` correctly |
| `Required flow nodes missing after bootstrap:` | Registry/bootstrap mismatch | Fix flow registration/bootstrap imports |
| `Event bus subscriber failed to start:` | Subscriber could not connect/start | Fix Redis/event-bus startup path |
| `RuntimeError(str(_rbv))` | Router boundary validation failed during startup | Fix the boundary violation reported in logs |

## 5. Health Check Reference
`GET /health` returns:
- `status`: `healthy`, `degraded`, or `critical`
- `timestamp`: response timestamp
- `version`: app version from `version.json`
- `degraded_domains`: registry-reported degraded domains
- `deployment_contract`: runtime contract summary
- `dependencies`: map of dependency checks
- `db_pool`: `pool_size`, `checkedout`, `overflow`, `checked_in`
- `warnings`: optional; includes `db_pool_near_exhaustion` when checked-out connections exceed the configured threshold

Healthy means `status: "healthy"` and dependency statuses are `ok` or explicitly non-required states such as `degraded` for unconfigured optional Mongo. `critical` returns HTTP 503.

## 6. Nodus VM Setup
Nodus is an external scripting VM used by `nodus.*` flow nodes.

`NODUS_SOURCE_PATH` must point to the source directory that contains the importable `nodus` package root.

Verify importability:
```bash
python -c "import sys; sys.path.insert(0, '/your/nodus/path'); import nodus.runtime.embedding; print('OK')"
```

If `NODUS_SOURCE_PATH` is unset or unimportable and no `nodus.*` nodes are registered, startup logs:
```text
[startup] Nodus VM not available; no Nodus nodes registered, skipping.
```
If `nodus.*` nodes are registered, startup warns in non-prod and raises in production.

## 7. Docker Compose Quick Start
```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: aindy
      POSTGRES_PASSWORD: change-this
      POSTGRES_DB: aindy
  redis:
    image: redis:7-alpine
  api:
    build: .
    command: sh -c "alembic -c alembic.ini upgrade head && uvicorn AINDY.main:app --host 0.0.0.0 --port 8000"
    environment:
      ENV: production
      DATABASE_URL: postgresql://aindy:change-this@postgres:5432/aindy
      SECRET_KEY: replace-with-32-byte-secret
      OPENAI_API_KEY: sk-proj-...
      REDIS_URL: redis://redis:6379/0
      EXECUTION_MODE: distributed
    depends_on: [postgres, redis]
  worker:
    build: .
    command: python -m AINDY.worker.worker_loop
    environment:
      ENV: production
      DATABASE_URL: postgresql://aindy:change-this@postgres:5432/aindy
      SECRET_KEY: replace-with-32-byte-secret
      OPENAI_API_KEY: sk-proj-...
      REDIS_URL: redis://redis:6379/0
      EXECUTION_MODE: distributed
    depends_on: [postgres, redis]
```
Mongo is optional unless `MONGO_REQUIRED=true`. Redis is optional only for single-instance `EXECUTION_MODE=thread`.

## 8. Common Operational Tasks
```bash
alembic -c alembic.ini upgrade head
alembic -c alembic.ini current
WORKER_CONCURRENCY=1 python -m AINDY.worker.worker_loop
docker compose logs -f api
docker compose logs -f worker
```
For `SECRET_KEY` rotation, use [docs/platform/engineering/RUNBOOK_SECRET_ROTATION.md](/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/docs/platform/engineering/RUNBOOK_SECRET_ROTATION.md:1).

## 9. MongoDB (Social App)

### Configuration
| Variable | Default | Purpose |
|---|---|---|
| `MONGO_URL` | required for social | MongoDB connection string |
| `MONGO_CONNECT_TIMEOUT_MS` | `3000` | Connection timeout |
| `MONGO_SOCKET_TIMEOUT_MS` | `5000` | Per-operation timeout |
| `MONGO_SERVER_SELECTION_TIMEOUT_MS` | `3000` | Server discovery timeout |
| `MONGO_MAX_POOL_SIZE` | `10` | Max concurrent connections |
| `MONGO_MIN_POOL_SIZE` | `1` | Min maintained connections |

### Health Check
`GET /health` -> `platform.mongodb`

`ok`: MongoDB is reachable and responding to ping.

`degraded`: MongoDB is unreachable, not configured, or timing out.

### Impact of MongoDB Failure
- Social app returns degraded responses with empty data and a reason.
- All other apps continue normally on PostgreSQL.
- Platform health returns top-level `degraded`, not `unhealthy`.

### Recovery Steps
1. Check MongoDB connectivity: `mongo $MONGO_URL --eval "db.adminCommand('ping')"`
2. Check logs for Mongo timeout or pool messages.
3. Restart the platform if the client needs to be re-established.
4. If using Atlas, check cluster status in the Atlas dashboard.

### Backup and Restore
MongoDB data for the social app is separate from PostgreSQL.

Backup: `mongodump --uri $MONGO_URL --out /backups/mongo/$(date +%Y%m%d)`

Restore: `mongorestore --uri $MONGO_URL /backups/mongo/<date>/`

Frequency: Daily. Social data is reconstructible from source platforms, but reconstruction is expensive.

### Monitoring
Alert when `platform.mongodb = degraded` for more than 5 minutes.

Page severity: LOW. Social features are degraded, but the platform is still up.
