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

This starts PostgreSQL and the API on `http://localhost:8000`. The default profile skips Mongo startup so the platform API can boot with just Postgres.

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
- Schema errors: run `alembic upgrade head` before starting the app outside Docker.
