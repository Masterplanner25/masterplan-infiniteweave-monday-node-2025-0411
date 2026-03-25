import json
import logging
import threading
import os
import time
import uuid
from contextvars import ContextVar
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from services.rate_limiter import limiter
from services import scheduler_service
from services import task_services
from services.threadweaver import (
    analyze_drop_point,
    get_dashboard_snapshot,
    get_top_drop_points,
)
from services.delta_engine import (
    compute_deltas,
    find_momentum_leaders,
    emerging_drops as compute_emerging_drops,
)
from services.prediction_engine import (
    predict_drop_point,
    prediction_summary,
    scan_drop_point_predictions,
)
from services.recommendation_engine import (
    recommend_for_drop_point,
    recommendations_summary,
)
from services.influence_graph import build_influence_graph, influence_chain
from services.causal_engine import build_causal_graph, get_causal_chain
from services.narrative_engine import generate_narrative, narrative_summary
from services.learning_engine import (
    evaluate_outcome,
    adjust_thresholds,
    learning_stats,
)
from services.strategy_engine import (
    build_strategies,
    list_strategies,
    get_strategy,
    match_strategies,
)
from services.playbook_engine import (
    build_playbook,
    list_playbooks,
    get_playbook,
    match_playbooks,
)
from services.content_generator import (
    generate_content,
    generate_content_for_drop,
    generate_variations,
)
from db.database import SessionLocal, get_db
from sqlalchemy.orm import Session
try:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext
except Exception:
    Config = None
    ScriptDirectory = None
    MigrationContext = None
from routes import ROUTERS
from config import settings
from db.models.metrics_models import *
from db.models.request_metric import RequestMetric

# --- Ensure root path is importable ---
import sys, os
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


# For in-memory caching
# If you want to use Redis (uncomment and configure):
# from fastapi_cache.backends.redis import RedisBackend
# from redis import asyncio as aioredis


# ── Request-scoped logging context ──────────────────────────────────────────
# ContextVar carries the current request_id through async call stacks.
# Default "-" appears in log lines that originate outside a request context.
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestContextFilter(logging.Filter):
    """Inject request_id from ContextVar into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_ctx.get()
        return True


# config.py already called logging.basicConfig (FileHandler + StreamHandler).
# Upgrade all root-logger handlers in-place: attach the filter and apply the
# new format that includes [request_id].  No duplicate basicConfig call needed.
_REQUEST_LOG_FORMAT = "%(asctime)s - %(levelname)s - [%(request_id)s] - %(message)s"
_ctx_filter = RequestContextFilter()
for _handler in logging.root.handlers:
    _handler.addFilter(_ctx_filter)
    _handler.setFormatter(logging.Formatter(_REQUEST_LOG_FORMAT))

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    cache_backend = os.getenv("AINDY_CACHE_BACKEND", "memory").lower()
    if os.getenv("PYTEST_CURRENT_TEST"):
        cache_backend = "memory"
    if cache_backend == "redis":
        try:
            from redis import asyncio as aioredis
            from fastapi_cache.backends.redis import RedisBackend
        except Exception as exc:
            logger.error("Redis cache backend unavailable: %s", exc)
            raise RuntimeError("Redis cache backend unavailable.") from exc
        if not settings.REDIS_URL:
            raise RuntimeError("REDIS_URL is required for redis cache backend.")
        redis = aioredis.from_url(settings.REDIS_URL, encoding="utf8", decode_responses=True)
        FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")
        logger.info("Cache backend initialized: redis")
    else:
        FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
        logger.info("Cache backend initialized: memory")

    # SECRET_KEY guard — reject insecure placeholder in production
    _placeholder = "dev-secret-change-in-production"
    if settings.SECRET_KEY == _placeholder:
        if settings.is_prod:
            raise RuntimeError(
                "SECRET_KEY is using the insecure default placeholder. "
                "Set a strong SECRET_KEY in your .env before running in production."
            )
        else:
            logger.warning(
                "SECRET_KEY is using the insecure default placeholder. "
                "This is acceptable for local development but MUST be changed before production."
            )

    enforce_schema = os.getenv("AINDY_ENFORCE_SCHEMA", "true").lower() in {"1", "true", "yes"}
    if enforce_schema and not os.getenv("PYTEST_CURRENT_TEST"):
        if not (Config and ScriptDirectory and MigrationContext):
            logger.error("Schema guard unavailable: alembic not installed.")
            raise RuntimeError("Schema guard unavailable: alembic not installed.")
        db = SessionLocal()
        try:
            conn = db.connection()
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()

            alembic_cfg = Config("alembic.ini")
            script = ScriptDirectory.from_config(alembic_cfg)
            heads = script.get_heads()

            if not current_rev or (current_rev not in heads):
                logger.error(
                    "Schema drift detected. current=%s heads=%s",
                    current_rev,
                    heads,
                )
                raise RuntimeError("Schema drift detected. Run alembic upgrade head.")
        finally:
            db.close()

    enable_background = os.getenv("AINDY_ENABLE_BACKGROUND_TASKS", "true").lower() in {"1", "true", "yes"}
    if os.getenv("PYTEST_CURRENT_TEST"):
        enable_background = False

    # Acquire the inter-instance DB lease first; only the leader starts APScheduler.
    # start_background_tasks() returns True iff this instance holds the lease.
    is_leader = task_services.start_background_tasks(enable=enable_background, log=logger)
    if is_leader:
        scheduler_service.start()

    # Register Flow Engine flows and nodes
    from services.flow_definitions import register_all_flows
    register_all_flows()

    # Sprint N+7: Recover any FlowRun/AgentRun rows stranded by prior crash
    if enable_background and not os.getenv("PYTEST_CURRENT_TEST"):
        from services.stuck_run_service import scan_and_recover_stuck_runs
        _scan_db = SessionLocal()
        try:
            scan_and_recover_stuck_runs(_scan_db)
        except Exception as _scan_exc:
            logger.warning("Stuck-run startup scan failed (non-fatal): %s", _scan_exc)
        finally:
            _scan_db.close()

    # Seed system identity
    from db.models.author_model import AuthorDB
    from datetime import datetime
    db = SessionLocal()
    try:
        system_id = "author-system"
        existing = db.query(AuthorDB).filter_by(id=system_id).first()
        if not existing:
            system_author = AuthorDB(
                id=system_id,
                name="A.I.N.D.Y. System",
                platform="Internal Core",
                notes="Autogenerated identity for runtime self-reference.",
                joined_at=datetime.utcnow(),
                last_seen=datetime.utcnow(),
            )
            db.add(system_author)
            db.commit()
            logger.info("Seeded system author: A.I.N.D.Y. System")
        else:
            existing.last_seen = datetime.utcnow()
            db.commit()
            logger.info("System author already present, timestamp refreshed.")
    except Exception as e:
        logger.warning(f"System identity seed failed (non-fatal): {e}")
    finally:
        db.close()

    yield
    # --- Shutdown ---
    task_services.stop_background_tasks(log=logger)
    scheduler_service.stop()


app = FastAPI(title="A.I.N.D.Y. Memory Bridge", lifespan=lifespan)

# Rate limiting — protects AI/expensive endpoints from abuse
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

for route in ROUTERS:
    app.include_router(route)

# CORS — explicit origins only (wildcard + credentials is a security violation)
import os as _os
_ALLOWED_ORIGINS = [
    o.strip()
    for o in _os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://localhost:3000,http://localhost:5000",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    message = detail if isinstance(detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "http_error",
            "message": message,
            "details": detail if not isinstance(detail, str) else None,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Invalid request",
            "details": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "Internal server error",
            "details": None,
        },
    )

def _extract_user_id_from_request(request: Request):
    auth = request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        from services.auth_service import decode_access_token
        payload = decode_access_token(token)
        if not payload or "sub" not in payload:
            return None
        return uuid.UUID(str(payload["sub"]))
    except Exception:
        return None


@app.middleware("http")
async def log_requests(request, call_next):
    request_id = str(uuid.uuid4())
    _request_id_ctx.set(request_id)  # propagate through async call stack
    start_time = time.time()

    response = await call_next(request)

    duration_ms = round((time.time() - start_time) * 1000, 2)
    response.headers["X-Request-ID"] = request_id

    user_id = _extract_user_id_from_request(request)
    log_payload = {
        "event": "request_complete",
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
        "user_id": str(user_id) if user_id else None,
    }
    logger.info(json.dumps(log_payload, ensure_ascii=False))

    db = None
    try:
        db = SessionLocal()
        db.add(
            RequestMetric(
                request_id=request_id,
                user_id=user_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
        )
        db.commit()
    except Exception as exc:
        logger.warning("Failed to record request metric: %s", exc)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    return response

@app.get("/")
def home():
    return {"message": "A.I.N.D.Y. API is running!"}


@app.get("/analyze_ripple/{drop_point_id}")
def analyze_ripple(
    drop_point_id: str,
    db: Session = Depends(get_db),
):
    metrics = analyze_drop_point(drop_point_id, db)
    if not metrics:
        raise HTTPException(status_code=404, detail="Drop point not found")
    return metrics


@app.get("/dashboard")
def proofboard_dashboard(db: Session = Depends(get_db)):
    snapshot = get_dashboard_snapshot(db)
    leaders = find_momentum_leaders(db)
    predictions = scan_drop_point_predictions(db, limit=20)
    snapshot.update(
        {
            "fastest_accelerating_drop": leaders.get("fastest_accelerating"),
            "biggest_spike_drop": leaders.get("biggest_spike"),
            "predicted_spike_candidates": [
                p for p in predictions if p["prediction"] == "likely_to_spike"
            ],
            "declining_drops": [
                p for p in predictions if p["prediction"] == "declining"
            ],
            "recommendations_summary": recommendations_summary(db, limit=10),
        }
    )
    return snapshot


@app.get("/top_drop_points")
def top_drop_points(db: Session = Depends(get_db)):
    return {"top_drop_points": get_top_drop_points(db)}


@app.get("/ripple_deltas/{drop_point_id}")
def ripple_deltas(drop_point_id: str, db: Session = Depends(get_db)):
    return compute_deltas(drop_point_id, db)


@app.get("/emerging_drops")
def emerging_drops(db: Session = Depends(get_db)):
    return {"emerging_drops": compute_emerging_drops(db)}


@app.get("/predict/{drop_point_id}")
def predict_drop_point_view(drop_point_id: str, db: Session = Depends(get_db)):
    return predict_drop_point(drop_point_id, db)


@app.get("/prediction_summary")
def prediction_summary_view(db: Session = Depends(get_db)):
    return prediction_summary(db)


@app.get("/recommend/{drop_point_id}")
def recommend_drop_point(drop_point_id: str, db: Session = Depends(get_db)):
    return recommend_for_drop_point(drop_point_id, db)


@app.get("/recommendations_summary")
def recommendations_summary_view(db: Session = Depends(get_db)):
    return recommendations_summary(db)


@app.get("/influence_graph")
def influence_graph_view(db: Session = Depends(get_db)):
    return build_influence_graph(db)


@app.get("/influence_chain/{drop_point_id}")
def influence_chain_view(drop_point_id: str, db: Session = Depends(get_db)):
    return influence_chain(drop_point_id, db)


@app.get("/causal_graph")
def causal_graph_view(db: Session = Depends(get_db)):
    return build_causal_graph(db)


@app.get("/causal_chain/{drop_point_id}")
def causal_chain_view(drop_point_id: str, db: Session = Depends(get_db)):
    return get_causal_chain(drop_point_id, db)


@app.get("/narrative/{drop_point_id}")
def narrative_view(drop_point_id: str, db: Session = Depends(get_db)):
    return generate_narrative(drop_point_id, db)


@app.get("/narrative_summary")
def narrative_summary_view(db: Session = Depends(get_db)):
    return {"stories": narrative_summary(db)}


@app.get("/strategies")
def strategies_view(db: Session = Depends(get_db)):
    build_strategies(db)
    return {"strategies": list_strategies(db)}


@app.get("/strategy/{strategy_id}")
def strategy_view(strategy_id: str, db: Session = Depends(get_db)):
    strategy = get_strategy(strategy_id, db)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


@app.get("/strategy_match/{drop_point_id}")
def strategy_match_view(drop_point_id: str, db: Session = Depends(get_db)):
    return {"matches": match_strategies(drop_point_id, db)}


@app.post("/build_playbook/{strategy_id}")
def build_playbook_view(strategy_id: str, db: Session = Depends(get_db)):
    return build_playbook(strategy_id, db)


@app.get("/playbooks")
def playbooks_view(db: Session = Depends(get_db)):
    return {"playbooks": list_playbooks(db)}


@app.get("/playbook/{playbook_id}")
def playbook_view(playbook_id: str, db: Session = Depends(get_db)):
    playbook = get_playbook(playbook_id, db)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return playbook


@app.get("/playbook_match/{drop_point_id}")
def playbook_match_view(drop_point_id: str, db: Session = Depends(get_db)):
    return {"matches": match_playbooks(drop_point_id, db)}


@app.get("/generate_content/{playbook_id}")
def generate_content_view(playbook_id: str, db: Session = Depends(get_db)):
    return generate_content(playbook_id, db)


@app.post("/generate_content_for_drop/{drop_point_id}")
def generate_content_for_drop_view(drop_point_id: str, db: Session = Depends(get_db)):
    return generate_content_for_drop(drop_point_id, db)


@app.get("/generate_variations/{playbook_id}")
def generate_variations_view(playbook_id: str, db: Session = Depends(get_db)):
    return generate_variations(playbook_id, db)


@app.get("/learning_stats")
def learning_stats_view(db: Session = Depends(get_db)):
    return learning_stats(db)


@app.post("/evaluate/{drop_point_id}")
def evaluate_drop_point(drop_point_id: str, db: Session = Depends(get_db)):
    result = evaluate_outcome(drop_point_id, db)
    adjust_thresholds(db)
    return result
