"""
config.py – Centralized environment and configuration management for A.I.N.D.Y.
Implements clean separation between development and production via .env files.

Usage:
    from config import settings
    engine = create_engine(settings.DATABASE_URL)
"""

from pathlib import Path
import logging
from datetime import datetime, timezone
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

utcnow = lambda: datetime.now(timezone.utc)

# --------------------------------------------------------------------
# Base Settings
# --------------------------------------------------------------------
class Settings(BaseSettings):
    # --- Core runtime variables ---
    ENV: str = "development"
    DATABASE_URL: str
    PERMISSION_SECRET: str
    OPENAI_API_KEY: str
    DEEPSEEK_API_KEY: str | None = None

    # --- Optional runtime options ---
    LOG_LEVEL: str = "INFO"

    # --- Environment loading config ---
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # --- Validators ---
    @field_validator("DATABASE_URL")
    @classmethod
    def ensure_postgres(cls, v: str) -> str:
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

logging.getLogger(__name__).info(f"Loaded {settings.ENV} environment from .env")


