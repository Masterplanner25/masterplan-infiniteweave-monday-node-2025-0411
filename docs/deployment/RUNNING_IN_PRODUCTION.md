# Running AINDY in Production

## Required Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `SECRET_KEY` | Yes | JWT signing key (min 32 chars; generate with `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `REDIS_URL` | For distributed mode | Redis connection string |
| `MONGO_URL` | For memory features | MongoDB connection string |
| `AINDY_API_KEY` | Recommended | Platform API key for dev key bootstrap |

Notes from current runtime config:
- `EXECUTION_MODE` defaults to `thread` in `AINDY/config.py`, but distributed deployments must set it explicitly.
- `AINDY_ENFORCE_SCHEMA=true` is the normal startup default and the server checks Alembic head on boot.
- `AINDY_REQUIRE_REDIS=true` should be set for production multi-instance deployments.
- `AINDY_CACHE_BACKEND=redis` is the intended distributed-cache setting.

## Execution Modes

- `EXECUTION_MODE=thread` — single-instance, in-process. No worker needed. Default for quickstart.
- `EXECUTION_MODE=distributed` — multi-instance. Requires `REDIS_URL` and at least one running worker process.

In Docker Compose:
- `docker compose up` starts the API in thread mode by default.
- `docker compose --profile full up` is the distributed stack shape, but you should also set `EXECUTION_MODE=distributed` explicitly for the API when using that profile.

## Starting a Worker (distributed mode only)

```bash
WORKER_CONCURRENCY=4 python -m AINDY.worker
```

The worker emits a heartbeat to Redis (`aindy:worker:heartbeat`). The API server checks for this heartbeat at startup and warns if no worker is detected.

## Multi-Instance Checklist

- [ ] `REDIS_URL` set and reachable
- [ ] `AINDY_REQUIRE_REDIS=true`
- [ ] `AINDY_CACHE_BACKEND=redis`
- [ ] `EXECUTION_MODE=distributed`
- [ ] At least one worker process running per deployment
- [ ] `SECRET_KEY` is at least 32 characters and not the default placeholder
- [ ] `MONGO_URL` set if memory bridge features are required (`MONGO_REQUIRED=true`)

## Secret Rotation

JWT tokens are invalidated on `SECRET_KEY` change. To rotate:

1. Generate a new key.
2. Set it in the environment.
3. Restart all API instances. All active sessions will be invalidated.

## Schema Migrations

The server enforces Alembic schema head at startup (`AINDY_ENFORCE_SCHEMA=true` default). Run migrations before deploying a new version:

```bash
alembic upgrade head
```
