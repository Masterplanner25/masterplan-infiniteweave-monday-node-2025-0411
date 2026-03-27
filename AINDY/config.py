"""
config.py - Centralized environment configuration for A.I.N.D.Y.

All runtime settings are sourced from process environment variables.
"""

import logging
import os
from datetime import datetime, timezone
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from pathlib import Path

utcnow = lambda: datetime.now(timezone.utc)

# --------------------------------------------------------------------
# Base Settings
# --------------------------------------------------------------------
class Settings(BaseSettings):
    # --- Core runtime variables ---
    ENV: str = "development"
    TESTING: bool = False
    TEST_MODE: bool = False
    DATABASE_URL: str
    PERMISSION_SECRET: str = ""  # Deprecated — HMAC removed; kept for backward compat
    OPENAI_API_KEY: str
    DEEPSEEK_API_KEY: str | None = None

    # --- Auth ---
    SECRET_KEY: str = "dev-secret-change-in-production"
    AINDY_API_KEY: str | None = None
    AINDY_SERVICE_KEY: str | None = None

    @field_validator("SECRET_KEY")
    @classmethod
    def warn_insecure_secret_key(cls, v: str) -> str:
        if v == "dev-secret-change-in-production":
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "SECRET_KEY is using the insecure default placeholder. "
                "Set SECRET_KEY in the environment before deploying to production."
            )
        return v

    # --- Optional runtime options ---
    LOG_LEVEL: str = "INFO"
    REDIS_URL: str | None = None
    AINDY_CACHE_BACKEND: str = "memory"

    # --- Environment loading config ---
    model_config = SettingsConfigDict(
        extra="ignore"
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

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_path / f"aindy_{settings.ENV}.log"),
        logging.StreamHandler(),
    ],
)

logging.getLogger(__name__).info(
    "Loaded %s environment from process environment variables",
    settings.ENV,
)


