# Runtime Behavior

## 1. Application Startup Flow
- Entry point is `AINDY/main.py`.
- Module import side effects include:
- `AINDY/config.py` loading environment via `Settings` and initializing logging handlers.
- `AINDY/db/database.py` creating the SQLAlchemy engine and `SessionLocal` at import time.
- `AINDY/main.py` inserts the repository root into `sys.path` if missing.
- App initialization order in `AINDY/main.py`:
- `app = FastAPI(title="A.I.N.D.Y. Memory Bridge")`.
- Router registration via iterating `ROUTERS` from `AINDY/routes/__init__.py` and `app.include_router(route)`.
- CORS middleware configured with permissive `allow_origins=["*"]` and all methods/headers.
- HTTP middleware `log_requests` logs request method/URL and response status via `logging`.
- Startup event `startup` (async) initializes `fastapi-cache` with `InMemoryBackend`, creates a DB session via `SessionLocal()`, defines local `handle_recurrence` and `check_reminders` functions, and starts two daemon threads targeting those local functions.
- Startup event `ensure_system_identity` (sync) opens a DB session and ensures an `AuthorDB` row with id `author-system` exists in the authors table.
- DB initialization behavior:
- Engine creation and UTC timezone enforcement are in `AINDY/db/database.py` and occur at import time.
- No explicit migration or schema verification is executed on startup.
- The `startup` event creates a session but does not explicitly close it.

## 2. Background Task Lifecycle
- Daemon threads are created in `AINDY/main.py` within the `startup` event using `threading.Thread(..., daemon=True).start()`.
- The thread targets are local functions `handle_recurrence` and `check_reminders` defined inside `startup`.
- Those local functions log start and completion messages and do not contain loops or DB access.
- Separate loop-based implementations exist in `AINDY/services/task_services.py` as `check_reminders()` and `handle_recurrence()`:
- Each contains `while True` loops with `time.sleep(60)`.
- Each creates a `SessionLocal()` per loop iteration and closes it in `finally`.
- These loop-based functions are not invoked from `AINDY/main.py` in the current implementation.
- There is no scheduler, queue, or supervision framework in the current implementation.

## 3. Database Session Lifecycle
- Per-request SQLAlchemy sessions are provided by `get_db()` in `AINDY/db/database.py` which yields a `SessionLocal()` and closes it in `finally`.
- Many routes use `Depends(get_db)` which enforces per-request session creation and closure.
- Some routes define local `get_db()` functions using `SessionLocal()` (e.g., `AINDY/routes/main_router.py`, `AINDY/routes/analytics_router.py`) and close sessions in `finally`.
- Commit/rollback behavior:
- Many services explicitly `commit()` after writes.
- `AINDY/services/memory_persistence.py` wraps operations in try/except and calls `rollback()` on SQLAlchemy errors, then re-raises.
- `AINDY/routes/arm_router.py` wraps service calls and converts exceptions to `HTTPException`.
- Background loop session creation in `AINDY/services/task_services.py` uses `SessionLocal()` inside loop and closes in `finally`.
- Potential session leakage:
- `AINDY/main.py` creates a DB session in `startup` and does not explicitly close it.
- Cross-thread session sharing is not present in the current implementation.
- MongoDB client lifecycle:
- `AINDY/db/mongo_setup.py` uses a process-level singleton `_client` created lazily on first use.
- There is no explicit client close or shutdown hook.

## 4. External Model Call Behavior
- OpenAI call flow is implemented in `AINDY/services/genesis_ai.py`:
- Uses `OpenAI(api_key=os.getenv("OPENAI_API_KEY"))`.
- Calls `client.chat.completions.create(...)` with model `gpt-4o-mini` and temperature `0.4`.
- Expects JSON in `response.choices[0].message.content` and attempts `json.loads`.
- On JSON parse failure, returns a fixed fallback dict with a minimal reply and empty `state_update`.
- There is no retry or timeout configuration in `AINDY/services/genesis_ai.py`.
- DeepSeek invocation path is implemented in `AINDY/services/deepseek_arm_service.py`:
- `run_analysis` and `generate_code` call `DeepSeekCodeAnalyzer` methods after validation and config load.
- Exceptions are not caught around analyzer execution; they propagate to the caller.
- `AINDY/routes/arm_router.py` catches exceptions and returns `HTTP 500` with a message.
- There is no retry or timeout configuration in the DeepSeek integration.

## 5. Logging and Error Propagation
- Logging mechanisms:
- `AINDY/config.py` configures `logging.basicConfig` with file and stream handlers.
- `AINDY/main.py` configures logging and logs each request/response in middleware.
- Multiple modules use `print(...)` for runtime messages and errors (e.g., `AINDY/services/task_services.py`, `AINDY/routes/network_bridge_router.py`).
- Error propagation patterns:
- Routes often raise `HTTPException` on input validation or service errors (e.g., `AINDY/routes/genesis_router.py`, `AINDY/routes/arm_router.py`).
- Many services do not catch exceptions and allow them to propagate to FastAPI.
- `AINDY/services/genesis_ai.py` catches JSON parse failures and returns a fallback response.
- Stack trace exposure in HTTP responses is not explicitly defined in the current implementation.
- Structured logging beyond basic logging and prints is not implemented.

## 6. Shutdown Expectations
- No FastAPI shutdown events are defined in `AINDY/main.py`.
- Daemon threads will terminate when the process exits; no graceful stop logic is implemented.
- No explicit resource cleanup for SQLAlchemy engine or MongoDB client exists.
- Behavior not explicitly defined in current implementation for graceful shutdown or cleanup.

## 7. Known Runtime Risks
- Concurrency risks:
- Async routes in `AINDY/routes/arm_router.py` call synchronous, potentially long-running functions, which can block the event loop.
- Infinite loop risks:
- `AINDY/services/task_services.py` contains infinite loops if those functions are started; no supervision or cancellation is implemented.
- DB exhaustion risks:
- Background loop functions open sessions repeatedly; if invoked without proper lifecycle control, connection pool pressure may increase.
- A session is created in `AINDY/main.py` startup and not explicitly closed.
- Blocking call risks:
- DeepSeek analysis and generation are synchronous and may block request handling.
- OpenAI requests are synchronous and may block request handling.
- Missing supervision risks:
- No scheduler, worker framework, or health supervision for background tasks is implemented.
