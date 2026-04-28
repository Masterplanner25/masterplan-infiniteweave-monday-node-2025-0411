"""
config.py - Centralized environment configuration for A.I.N.D.Y.

All runtime settings are sourced from process environment variables.
"""

import logging
import os
from datetime import datetime, timezone
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, model_validator
from pathlib import Path

utcnow = lambda: datetime.now(timezone.utc)
CORE_DOMAINS: list[str] = ["tasks", "identity", "agent"]
logger = logging.getLogger(__name__)

def _read_version() -> str:
    import json, pathlib
    _vf = pathlib.Path(__file__).parent / "version.json"
    try:
        return json.loads(_vf.read_text(encoding="utf-8"))["version"]
    except Exception:
        return "1.0.0"


# --------------------------------------------------------------------
# Base Settings
# --------------------------------------------------------------------
class Settings(BaseSettings):
    # --- Core runtime variables ---
    ENV: str = "development"
    TESTING: bool = False
    TEST_MODE: bool = False
    DATABASE_URL: str
    MONGO_URL: str | None = None
    PERMISSION_SECRET: str = ""  # Deprecated — HMAC removed; kept for backward compat
    OPENAI_API_KEY: str = ""
    DEEPSEEK_API_KEY: str | None = None
    OPENAI_CHAT_TIMEOUT_SECONDS: float = 30.0
    OPENAI_EMBEDDING_TIMEOUT_SECONDS: float = 15.0
    OPENAI_MAX_RETRIES: int = 3
    OPENAI_RETRY_BACKOFF_BASE_SECONDS: float = 1.0
    AINDY_EVENT_HANDLER_TIMEOUT_SECONDS: float = 5.0
    FLOW_WAIT_TIMEOUT_MINUTES: int = 30
    STUCK_RUN_THRESHOLD_MINUTES: int = 45
    AINDY_WATCHDOG_INTERVAL_MINUTES: int = 2

    # --- Auth ---
    # SECRET_KEY rotation:
    # 1. Generate: python -c "import secrets; print(secrets.token_hex(32))"
    # 2. Set in .env. All active JWTs will be invalidated on next restart.
    # 3. Do not reuse old keys. Minimum 32 characters required in non-dev environments.
    SECRET_KEY: str = "dev-secret-change-in-production"
    AINDY_API_KEY: str | None = None
    AINDY_SERVICE_KEY: str | None = None
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None

    @field_validator("SECRET_KEY")
    @classmethod
    def reject_insecure_secret_key(cls, v: str) -> str:
        env_name = os.getenv("ENV", "development").lower()
        is_test = env_name == "test" or os.getenv(
            "TEST_MODE", "0"
        ).lower() in {"1", "true", "yes"}
        is_dev = env_name in {"dev", "development"}
        if not is_test:
            _BAD = {"secret", "changeme", "your-secret-key", "REPLACE_THIS"}
            if v.startswith("REPLACE_THIS") or v in _BAD:
                raise ValueError(
                    "SECRET_KEY is set to an insecure placeholder. "
                    "Generate a real key with: "
                    'python3 -c "import secrets; print(secrets.token_hex(32))"'
                )
        if v == "test-secret-key" and not (is_test or is_dev):
            raise ValueError(
                "SECRET_KEY must not use the known weak test value outside test/development."
            )
        if len(v) < 32 and not (is_test or is_dev):
            raise ValueError(
                "SECRET_KEY must be at least 32 characters outside test/development."
            )
        return v

    @field_validator("OPENAI_API_KEY")
    @classmethod
    def reject_placeholder_openai_api_key(cls, v: str) -> str:
        env_name = os.getenv("ENV", "development").lower()
        is_test = env_name == "test" or os.getenv(
            "TEST_MODE", "0"
        ).lower() in {"1", "true", "yes"} or os.getenv(
            "TESTING", "0"
        ).lower() in {"1", "true", "yes"}
        if is_test:
            return v
        normalized = (v or "").strip()
        bad_values = {"your-key-here", "sk-placeholder", "changeme", "replace_me"}
        if not normalized or normalized.lower() in bad_values:
            if env_name == "production":
                raise ValueError("OPENAI_API_KEY is not set or is a placeholder")
            logger.warning("OPENAI_API_KEY is not set or is a placeholder; OpenAI features may be unavailable")
        return v

    @field_validator("ENFORCE_EXECUTION_CONTRACT")
    @classmethod
    def default_contract_enforcement_for_tests(cls, v: bool) -> bool:
        return bool(v)

    VERSION: str = Field(default_factory=_read_version, exclude=True)
    API_VERSION: str = Field(
        default="1.0.0",
        description=(
            "Semantic version of the API contract. Increment MAJOR on breaking changes, "
            "MINOR on additive changes, PATCH on bug fixes. "
            "Frontend and SDK must declare a compatible minimum version."
        ),
    )
    API_MIN_CLIENT_VERSION: str = Field(
        default="1.0.0",
        description=(
            "Minimum client version this API supports. Clients declaring a version "
            "below this will receive a version-mismatch warning in response headers."
        ),
    )

    # --- Optional runtime options ---
    # Logging configuration (read directly via os.getenv - not in Settings
    # to avoid circular import with log setup which runs before settings load):
    #   LOG_FORMAT=json   - force JSON output (default in production)
    #   LOG_FORMAT=text   - force plain text (default in development)
    #   LOG_LEVEL=INFO    - root log level (DEBUG, INFO, WARNING, ERROR)
    # Worker process health probe port (read via os.getenv in worker entry points):
    #   WORKER_HEALTH_PORT=8001  - async job worker
    #   WORKER_HEALTH_PORT=8002  - memory ingest worker
    #   WORKER_HEALTH_PORT=8003  - metric writer worker
    LOG_LEVEL: str = "INFO"
    REDIS_URL: str | None = None
    AINDY_REQUIRE_REDIS: bool = False
    AINDY_CACHE_BACKEND: str = "redis"

    # --- Database connection pool defaults (non-SQLite only) ---
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30       # seconds to wait for a connection
    DB_POOL_RECYCLE: int = 1800     # recycle connections older than 30 min

    # --- Execution transport ---
    # "thread"      — ThreadPoolExecutor (default; single-process only).
    # "distributed" — DistributedQueue via Redis (multi-process / multi-host).
    EXECUTION_MODE: str = "thread"
    NODUS_SOURCE_PATH: str | None = None
    AINDY_QUEUE_NAME: str = "aindy:jobs"
    AINDY_ASYNC_JOB_WORKERS: int = 10
    AINDY_ASYNC_QUEUE_MAXSIZE: int = 100    # max pending jobs before rejection
    AINDY_MEMORY_INGEST_QUEUE_MAX: int = 500
    AINDY_SHUTDOWN_TIMEOUT_SECONDS: int = 30
    AINDY_WORKER_HEALTH_PORT: int = 8001
    AINDY_WORKER_LIVENESS_TIMEOUT_SECONDS: int = 60
    AINDY_JOB_WARN_CAPACITY: bool = True
    MAX_QUEUE_SIZE: int = Field(
        default_factory=lambda: int(
            os.getenv("MAX_QUEUE_SIZE", os.getenv("AINDY_ASYNC_QUEUE_MAXSIZE", "100"))
        )
    )
    AINDY_QUEUE_SATURATION_THRESHOLD: int = Field(
        default_factory=lambda: int(
            os.getenv(
                "AINDY_QUEUE_SATURATION_THRESHOLD",
                os.getenv("MAX_QUEUE_SIZE", os.getenv("AINDY_ASYNC_QUEUE_MAXSIZE", "100")),
            )
        )
    )
    AINDY_ASYNC_MAX_CONCURRENT_GLOBAL: int = 0
    AINDY_ASYNC_MAX_CONCURRENT_PER_USER: int = 0
    USE_NATIVE_SCORER: bool = True
    ENFORCE_EXECUTION_CONTRACT: bool = True
    SKIP_MONGO_PING: bool = False
    MONGO_REQUIRED: bool = False
    MONGO_HEALTH_TIMEOUT_MS: int = 5000
    MONGO_CONNECT_TIMEOUT_MS: int = 3000
    MONGO_SOCKET_TIMEOUT_MS: int = 5000
    MONGO_SERVER_SELECTION_TIMEOUT_MS: int = 3000
    MONGO_MAX_POOL_SIZE: int = 10
    MONGO_MIN_POOL_SIZE: int = 1

    # --- Environment loading config ---
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Validators ---
    @field_validator("DATABASE_URL")
    @classmethod
    def ensure_postgres(cls, v: str) -> str:
        allow_sqlite = os.getenv("AINDY_ALLOW_SQLITE", "0").lower() in {
            "1",
            "true",
            "yes",
        }
        if os.getenv("TEST_MODE", "0").lower() in {"1", "true", "yes"}:
            allow_sqlite = True
        if allow_sqlite:
            return v
        if not v.startswith("postgres"):
            raise ValueError("DATABASE_URL must be a valid PostgreSQL URI")
        return v

    @field_validator("MONGO_URL")
    @classmethod
    def ensure_mongo_url(cls, v: str) -> str:
        normalized = (v or "").strip()
        skip_ping = os.getenv("AINDY_SKIP_MONGO_PING", "0").lower() in {"1", "true", "yes"}
        mongo_required = os.getenv("MONGO_REQUIRED", "0").lower() in {"1", "true", "yes"}
        if not normalized:
            if skip_ping or not mongo_required:
                return ""
            raise ValueError("MONGO_URL is required when MONGO_REQUIRED=true")
        return normalized

    @model_validator(mode="after")
    def validate_stuck_run_threshold(self) -> "Settings":
        if self.STUCK_RUN_THRESHOLD_MINUTES <= self.FLOW_WAIT_TIMEOUT_MINUTES:
            raise ValueError(
                f"STUCK_RUN_THRESHOLD_MINUTES ({self.STUCK_RUN_THRESHOLD_MINUTES}) "
                f"must be greater than FLOW_WAIT_TIMEOUT_MINUTES "
                f"({self.FLOW_WAIT_TIMEOUT_MINUTES}). "
                "Legitimately waiting flows would be incorrectly recovered."
            )
        return self

    # --- Helper properties ---
    @property
    def is_dev(self) -> bool:
        return self.ENV.lower() in ("dev", "development")

    @property
    def is_prod(self) -> bool:
        return self.ENV.lower() in ("prod", "production")

    @property
    def is_testing(self) -> bool:
        return self.TESTING or self.TEST_MODE or self.ENV.lower() == "test"

    @property
    def requires_redis(self) -> bool:
        """True when the deployment mode requires Redis (non-dev, non-test, or explicit flag)."""
        return self.AINDY_REQUIRE_REDIS or self.ENV.lower() not in ("dev", "development", "test")


# --------------------------------------------------------------------
# Initialize Global Settings
# --------------------------------------------------------------------
settings = Settings()

# --------------------------------------------------------------------
# Logging Initialization
# --------------------------------------------------------------------
log_path = Path("logs")
log_path.mkdir(exist_ok=True)

def _build_log_handler(use_file: bool, log_file: Path) -> list[logging.Handler]:
    handlers: list[logging.Handler] = []
    if use_file:
        try:
            handlers.append(logging.FileHandler(log_file))
        except PermissionError:
            pass
    handlers.append(logging.StreamHandler())
    return handlers

_log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
_handlers = _build_log_handler(
    use_file=True,
    log_file=log_path / f"aindy_{settings.ENV}.log",
)

if settings.is_prod:
    # Structured JSON — one JSON object per line
    from pythonjsonlogger import jsonlogger  # noqa: PLC0415
    _fmt = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    for _h in _handlers:
        _h.setFormatter(_fmt)
else:
    _plain_fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    for _h in _handlers:
        _h.setFormatter(_plain_fmt)

logging.basicConfig(level=_log_level, handlers=_handlers)
logging.getLogger(__name__).info(
    "Loaded %s environment from process environment variables", settings.ENV
)


