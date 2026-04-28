# Query Timeout Guide

## Statement Timeout

All PostgreSQL connections in production enforce a statement_timeout
(default 30 seconds, configurable via DB_STATEMENT_TIMEOUT_MS).

If a query exceeds this limit, PostgreSQL cancels it and raises:
  sqlalchemy.exc.OperationalError: canceling statement due to statement timeout

FastAPI's exception handlers surface this as HTTP 500. Application code
that runs long analytics queries must catch this exception and return a
domain-appropriate error (e.g., 503 with a "retry later" message).

## High-risk domains

The following domains run queries that are most likely to approach the
timeout ceiling. If the default 30s is too aggressive, increase
DB_STATEMENT_TIMEOUT_MS or investigate query optimization:

| Domain | Operation | Typical risk |
|---|---|---|
| analytics | KPI recalculation, score snapshots | High |
| arm | Deep analysis aggregations | High |
| masterplan | Genesis block processing | Medium |
| search | Full-text / embedding queries | Medium |
| rippletrace | Ripple graph traversal | Medium |

## Handling timeout errors in services

Wrap long-running service calls:

```python
from sqlalchemy.exc import OperationalError

try:
    result = run_heavy_analysis(db, user_id)
except OperationalError as exc:
    if "statement timeout" in str(exc).lower():
        raise ServiceTimeoutError("Analysis timed out. Retry later.")
    raise
```

## Tuning

For a specific long-running background job that legitimately needs more
time, issue a session-level SET before the query:

```python
db.execute(text("SET LOCAL statement_timeout = '120s';"))
# ... long query ...
```

SET LOCAL applies only for the duration of the current transaction.
Do not use SET (without LOCAL) to globally override the connection timeout.
