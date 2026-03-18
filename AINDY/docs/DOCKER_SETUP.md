# A.I.N.D.Y. Docker Database Setup

## Why Docker?

A.I.N.D.Y. requires PostgreSQL with the pgvector extension for Memory Bridge Phase 2
(semantic similarity search). pgvector is not available as a prebuilt binary for
PostgreSQL 18 on Windows, so we use Docker with `pgvector/pgvector:pg16`.

## Prerequisites

- Docker Desktop for Windows — download from https://www.docker.com/products/docker-desktop/
- After installing Docker Desktop, ensure it is running before proceeding.

## Quick Start

```bash
# From the repo root (masterplan-infiniteweave-monday-node-2025-0411/)

# 1. Start the database container
docker-compose up -d

# 2. Wait for PostgreSQL to be ready (~5 seconds)
docker exec aindy-pgvector pg_isready -U postgres

# 3. Install the vector extension
docker exec aindy-pgvector psql -U postgres -d base -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 4. Update AINDY/.env — change port 5432 → 5433
# DATABASE_URL=postgresql+psycopg2://postgres:<password>@localhost:5433/base

# 5. Also update AINDY/alembic.ini line 66 — change port 5432 → 5433
# sqlalchemy.url = postgresql+psycopg2://postgres:<password>@localhost:5433/base

# 6. Run all Alembic migrations (from AINDY/ directory)
cd AINDY
alembic upgrade head

# 7. Verify
python -c "
from db.database import engine
from sqlalchemy import text
with engine.connect() as conn:
    r = conn.execute(text(\"SELECT installed_version FROM pg_available_extensions WHERE name='vector'\"))
    print('pgvector:', r.fetchone()[0])
"
```

## Connection Details

| Field        | Value                                                              |
|--------------|--------------------------------------------------------------------|
| Host         | localhost                                                          |
| Port         | **5433** (not 5432 — avoids conflict with local PostgreSQL 18)    |
| Database     | base                                                               |
| User         | postgres                                                           |
| DATABASE_URL | `postgresql+psycopg2://postgres:<password>@localhost:5433/base`   |

## Data Persistence

Data is stored in the `aindy_pgdata` Docker volume. It persists across container
restarts and `docker-compose down`. To wipe all data:

```bash
docker volume rm masterplan-infiniteweave-monday-node-2025-0411_aindy_pgdata
```

## Verify pgvector After Setup

```python
python -c "
from db.database import engine
from sqlalchemy import text
from pgvector.sqlalchemy import Vector

with engine.connect() as conn:
    r = conn.execute(text(
        \"SELECT installed_version FROM pg_available_extensions WHERE name='vector'\"
    ))
    row = r.fetchone()
    print(f'pgvector extension: {row[0] if row else \"NOT FOUND\"}')

v = Vector(1536)
print('Vector(1536) SQLAlchemy type: OK')
print('Phase 2 ready: YES')
"
```

## Common Commands

```bash
# Start container
docker-compose up -d

# Stop container (data preserved in volume)
docker-compose down

# Check container status
docker ps --filter "name=aindy-pgvector"

# View container logs
docker logs aindy-pgvector

# Connect to psql directly
docker exec -it aindy-pgvector psql -U postgres -d base

# Check pgvector version in psql
SELECT * FROM pg_available_extensions WHERE name = 'vector';
```

## Switching Back to PostgreSQL 18

If you need to revert to the local PostgreSQL 18 instance:

```bash
# 1. Restore the original .env
cp AINDY/.env.pg18 AINDY/.env

# 2. Restore alembic.ini — change port 5433 back to 5432

# 3. Stop the Docker container
docker-compose down
```

Note: The pgvector extension and `embedding` column will not be available on PostgreSQL 18.
Memory Bridge Phase 2 requires the Docker container.

## Port Choice

Port `5433` is used deliberately to avoid conflicting with any local PostgreSQL 18
installation on the default port `5432`. Both can run simultaneously.
