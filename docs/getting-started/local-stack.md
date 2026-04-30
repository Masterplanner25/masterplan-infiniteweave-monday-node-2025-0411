# Getting Started

This guide gets a local A.I.N.D.Y. instance running and executes one real platform syscall in under 15 minutes.

## 1. Start the stack

From the repo root:

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
# write that value to SECRET_KEY in .env
docker compose up -d
```

To run redis-backed tests: `pip install redis==5.0.4 fakeredis`

This starts PostgreSQL and the API on `http://localhost:8000`.

MongoDB is part of the normal runtime startup path. On application boot, `main.py` eagerly calls `db.mongo_setup.init_mongo()`, so a real `MONGO_URL` must be configured unless you are intentionally using the explicit bypass for tests or constrained local verification.

For a normal local run, set `MONGO_URL` in `.env` to a reachable MongoDB instance before starting the stack.

If you need a short-lived API boot without Mongo for local debugging, set:

```bash
export AINDY_SKIP_MONGO_PING=1
```

That bypass is intended for tests and constrained environments. Any route that requires Mongo-backed social data will still fail at execution time without a working Mongo connection.

Verify health:

```bash
curl http://localhost:8000/health
```

## 2. Create a user and get a token

Register:

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"Passw0rd!123","username":"demo"}'
```

Response:

```json
{"access_token":"<jwt>","token_type":"bearer"}
```

Export it:

```bash
export AINDY_TOKEN="<jwt>"
```

If the user already exists, log in instead:

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"Passw0rd!123"}'
```

## 3. Discover available syscalls

```bash
curl http://localhost:8000/platform/syscalls \
  -H "Authorization: Bearer $AINDY_TOKEN"
```

## 4. Execute your first syscall

```bash
curl -X POST http://localhost:8000/platform/syscall \
  -H "Authorization: Bearer $AINDY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "sys.v1.memory.read",
    "payload": {
      "path": "/memory/*",
      "limit": 5
    }
  }'
```

Expected response shape:

```json
{
  "status": "success",
  "data": {"nodes": [], "count": 0},
  "trace_id": "<id>",
  "execution_unit_id": "<id>",
  "syscall": "sys.v1.memory.read"
}
```

## 5. Optional: run the Nodus CLI

```bash
python cli.py run script.nd --api-url http://localhost:8000 --api-token "$AINDY_TOKEN" --trace
```

## Troubleshooting

- `401 Authentication required`: token missing or expired.
- Connection failure on `localhost:8000`: restart the stack with `docker compose up -d`.
- Startup failure mentioning `SECRET_KEY`: generate a real key and update repo-root `.env`.
- Startup failure mentioning `MONGO_URL` or Mongo connectivity: configure `MONGO_URL` to a reachable MongoDB instance, or set `AINDY_SKIP_MONGO_PING=1` only for local/test-only verification.
- Schema errors: run `alembic upgrade head` before starting the app outside Docker.
