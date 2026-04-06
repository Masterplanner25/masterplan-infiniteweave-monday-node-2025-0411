You are working in the AINDY/ Python/FastAPI codebase.

TASK: V1-PLAT-003 — Simplify docker-compose.yml so the default `docker compose up`
starts a minimal quickstart stack (PostgreSQL + API only). MongoDB, the worker,
and the frontend move behind named profiles so they don't block a first-time user.

FILE TO READ FIRST:
  docker-compose.yml   — root of the repo (not inside AINDY/)

CURRENT STATE (verified):
The file has 6 services: api, worker, frontend, postgres, redis, mongo.
- `api` depends on postgres (healthy), redis (started), mongo (started)
- `worker` depends on all three
- `mongo` is always started
- `api` sets `AINDY_CACHE_BACKEND: ${AINDY_CACHE_BACKEND:-redis}` (defaults to redis)
- No profiles are set on any service

GOAL:
  docker compose up              → starts: postgres + api (cache=memory)
  docker compose --profile full up  → starts everything (cache=redis)
  docker compose --profile social up → adds mongo only

WHY: The quickstart flow documented in V1-REL-001 must work on a clean machine
with a single command. Requiring Redis and MongoDB just to see the API start
creates unnecessary setup friction. MongoDB is only used by domain features
(watcher, social scoring) which are behind ENABLE_DOMAIN_APPS=false anyway.
Redis is an optimisation, not a requirement — the InMemoryBackend handles dev.

CHANGES REQUIRED — docker-compose.yml ONLY:

1. `postgres` service — no change (always runs, no profile)

2. `api` service:
   - Add `profiles: ["", "full"]` so it runs in both default and full profiles.
     (Empty string "" makes it a default-profile service in Compose v2.)
     Actually the correct way in Compose v2 is: do NOT set profiles on services
     that should run by default. Services with no `profiles:` key always start.
     Services WITH a profiles key only start when that profile is active.
     So: api stays with no profiles key (default). Update its config:
   - Change `AINDY_CACHE_BACKEND: ${AINDY_CACHE_BACKEND:-redis}` →
             `AINDY_CACHE_BACKEND: ${AINDY_CACHE_BACKEND:-memory}`
   - Remove `mongo` from `depends_on` (mongo is now profile-gated)
   - Remove `redis` from `depends_on`
   - Keep `depends_on.postgres` (condition: service_healthy)
   - Remove `REDIS_URL` from the environment block (or keep with a note — it's
     ignored when cache backend is memory)

3. `worker` service:
   - Add `profiles: ["full"]`
   - Keep its existing environment unchanged

4. `frontend` service:
   - Add `profiles: ["full"]`
   - Keep its existing environment unchanged

5. `redis` service:
   - Add `profiles: ["full"]`

6. `mongo` service:
   - Add `profiles: ["full", "social"]`
   - Keep its existing environment, ports, volumes unchanged

7. Add a top-level comment block at the very top of the file (after any
   existing comments) explaining the profiles:

       # Usage:
       #   docker compose up                  # quickstart: postgres + api
       #   docker compose --profile full up   # full stack: all services
       #   docker compose --profile social up # adds MongoDB for social features

8. `volumes` block — no change.

DO NOT change any environment variable values other than AINDY_CACHE_BACKEND
on the api service.
DO NOT change port mappings.
DO NOT remove any services — they move to profiles, not deleted.

VERIFY THE RESULT:
Run (do not execute docker, just validate the YAML syntax):
  python -c "import yaml; yaml.safe_load(open('docker-compose.yml'))" 
from the repo root. If this raises a YAML parse error, fix it before finishing.

ACCEPTANCE CRITERIA:
- `python -c "import yaml; yaml.safe_load(open('docker-compose.yml'))"` exits 0.
- The `api` and `postgres` services have no `profiles:` key (they always start).
- The `worker`, `frontend`, `redis` services have `profiles: [full]`.
- The `mongo` service has `profiles: [full, social]`.
- `api` depends_on only `postgres` (condition: service_healthy).
- `api` has `AINDY_CACHE_BACKEND: ${AINDY_CACHE_BACKEND:-memory}`.
- The comment block describing the three usage modes is present at the top.
