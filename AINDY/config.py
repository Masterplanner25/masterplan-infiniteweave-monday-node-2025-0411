"""
config.py - Centralized environment configuration for A.I.N.D.Y.

All runtime settings are sourced from process environment variables.
"""

import logging
import os
from datetime import datetime, timezone
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from pathlib import Path

utcnow = lambda: datetime.now(timezone.utc)

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
    OPENAI_API_KEY: str
    DEEPSEEK_API_KEY: str | None = None

    # --- Auth ---
    SECRET_KEY: str = "dev-secret-change-in-production"
    AINDY_API_KEY: str | None = None
    AINDY_SERVICE_KEY: str | None = None

    @field_validator("SECRET_KEY")
    @classmethod
    def reject_insecure_secret_key(cls, v: str) -> str:
        env_name = os.getenv("ENV", "").lower()
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

    VERSION: str = Field(default_factory=_read_version, exclude=True)

    # --- Optional runtime options ---
    LOG_LEVEL: str = "INFO"
    REDIS_URL: str | None = None
    AINDY_CACHE_BACKEND: str = "memory"

    # --- Database connection pool ---
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30       # seconds to wait for a connection
    DB_POOL_RECYCLE: int = 1800     # recycle connections older than 30 min

    # --- Execution transport ---
    # "thread"      — ThreadPoolExecutor (default; single-process only).
    # "distributed" — DistributedQueue via Redis (multi-process / multi-host).
    EXECUTION_MODE: str = "thread"
    AINDY_QUEUE_NAME: str = "aindy:jobs"
    AINDY_ASYNC_JOB_WORKERS: int = 4
    AINDY_ASYNC_QUEUE_MAXSIZE: int = 100    # max pending jobs before rejection
    USE_NATIVE_SCORER: bool = True
    ENFORCE_EXECUTION_CONTRACT: bool = False
    SKIP_MONGO_PING: bool = False

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
        if not v or not v.strip():
            if os.getenv("AINDY_SKIP_MONGO_PING", "0").lower() in {"1","true","yes"}:
                return ""
            raise ValueError("MONGO_URL is required for runtime")
        return v.strip()

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


