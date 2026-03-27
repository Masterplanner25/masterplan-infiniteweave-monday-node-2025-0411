"""
config.py - Environment-variable configuration for A.I.N.D.Y. Watcher.

All settings are read from process environment variables.

Environment variables:
  AINDY_WATCHER_API_URL           Required. Base URL of A.I.N.D.Y. API.
                                  e.g. http://localhost:8000
  AINDY_API_KEY                   Required (unless DRY_RUN=true). API key.
  AINDY_WATCHER_POLL_INTERVAL     Seconds between window samples. Default: 5
  AINDY_WATCHER_FLUSH_INTERVAL    Seconds between signal flushes. Default: 10
  AINDY_WATCHER_BATCH_SIZE        Signals per POST batch. Default: 20
  AINDY_WATCHER_CONFIRMATION_DELAY  Seconds of work before session_started. Default: 30
  AINDY_WATCHER_DISTRACTION_TIMEOUT Seconds of distraction before state change. Default: 60
  AINDY_WATCHER_RECOVERY_DELAY    Seconds of work before recovery confirmed. Default: 30
  AINDY_WATCHER_HEARTBEAT_INTERVAL Seconds between heartbeat signals. Default: 300
  AINDY_WATCHER_DRY_RUN           true/1/yes → log signals, do not POST. Default: false
  AINDY_WATCHER_LOG_LEVEL         DEBUG|INFO|WARNING|ERROR. Default: INFO
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key, "true" if default else "false").lower()
    return val in {"1", "true", "yes"}


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        logger.warning("Invalid value for %s; using default %s", key, default)
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        logger.warning("Invalid value for %s; using default %s", key, default)
        return default


@dataclass
class WatcherConfig:
    api_url: str
    api_key: str
    signals_endpoint: str  # full URL for POST /watcher/signals
    poll_interval: float
    flush_interval: float
    batch_size: int
    confirmation_delay: float
    distraction_timeout: float
    recovery_delay: float
    heartbeat_interval: float
    dry_run: bool
    log_level: str


def load() -> WatcherConfig:
    """
    Load and return WatcherConfig from environment variables.
    Does NOT raise — missing required values are replaced with safe defaults
    that will trigger validation errors via validate().
    """
    api_url = os.getenv("AINDY_WATCHER_API_URL", "http://localhost:8000").rstrip("/")
    api_key = os.getenv("AINDY_API_KEY", "")

    return WatcherConfig(
        api_url=api_url,
        api_key=api_key,
        signals_endpoint=f"{api_url}/watcher/signals",
        poll_interval=_env_float("AINDY_WATCHER_POLL_INTERVAL", 5.0),
        flush_interval=_env_float("AINDY_WATCHER_FLUSH_INTERVAL", 10.0),
        batch_size=_env_int("AINDY_WATCHER_BATCH_SIZE", 20),
        confirmation_delay=_env_float("AINDY_WATCHER_CONFIRMATION_DELAY", 30.0),
        distraction_timeout=_env_float("AINDY_WATCHER_DISTRACTION_TIMEOUT", 60.0),
        recovery_delay=_env_float("AINDY_WATCHER_RECOVERY_DELAY", 30.0),
        heartbeat_interval=_env_float("AINDY_WATCHER_HEARTBEAT_INTERVAL", 300.0),
        dry_run=_env_bool("AINDY_WATCHER_DRY_RUN", default=False),
        log_level=os.getenv("AINDY_WATCHER_LOG_LEVEL", "INFO").upper(),
    )


def validate(cfg: WatcherConfig) -> list[str]:
    """
    Return a list of validation error strings. Empty list = valid.
    """
    errors: list[str] = []

    if not cfg.api_url:
        errors.append("AINDY_WATCHER_API_URL is required")

    if not cfg.dry_run and not cfg.api_key:
        errors.append("AINDY_API_KEY is required when DRY_RUN is false")

    if cfg.poll_interval < 1.0:
        errors.append("AINDY_WATCHER_POLL_INTERVAL must be >= 1 second")

    if cfg.batch_size < 1:
        errors.append("AINDY_WATCHER_BATCH_SIZE must be >= 1")

    if cfg.confirmation_delay < 0:
        errors.append("AINDY_WATCHER_CONFIRMATION_DELAY must be >= 0")

    if cfg.distraction_timeout < 0:
        errors.append("AINDY_WATCHER_DISTRACTION_TIMEOUT must be >= 0")

    return errors
