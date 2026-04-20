"""
ARM Configuration Manager

Manages DeepSeek/ARM configuration parameters.
Uses a DB-backed singleton row by default so config updates are visible
across instances immediately. When ``config_path`` is passed explicitly,
the legacy file-backed behavior is preserved for tests.
"""
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


DEFAULT_CONFIG = {
    "model": "gpt-4o",
    "analysis_model": "gpt-4o",
    "generation_model": "gpt-4o",
    "temperature": 0.2,               # Low: deterministic analysis
    "generation_temperature": 0.4,    # Slightly higher: creative generation
    "max_chunk_tokens": 4000,
    "max_output_tokens": 2000,
    "retry_limit": 3,
    "retry_delay_seconds": 2,
    "max_file_size_bytes": 100_000,
    "allowed_extensions": [
        ".py", ".js", ".ts", ".jsx",
        ".tsx", ".json", ".md", ".txt", ".yaml", ".yml",
    ],
    # Infinity Algorithm defaults for Task Priority calculation
    "task_complexity_default": 3,
    "task_urgency_default": 5,
    "resource_cost_default": 2,
}

# Allowed keys for runtime updates — prevents injection of arbitrary config
_UPDATABLE_KEYS = set(DEFAULT_CONFIG.keys())


class ConfigManager:
    """
    Loads, reads, and persists ARM configuration.

    Default runtime storage is a DB-backed singleton row.
    Passing ``config_path`` preserves the legacy JSON file mode used by tests.
    Runtime values override defaults.
    Only keys present in DEFAULT_CONFIG are accepted for updates.
    """

    def __init__(self, config_path: str = None, db=None):
        self.db = db
        self._use_file = config_path is not None
        if self._use_file:
            self.config_path = Path(config_path)
        else:
            self.config_path = None
        if self._use_file and self.config_path is None:
            repo_root = Path(__file__).resolve().parents[4]
            self.config_path = repo_root / "AINDY" / "deepseek_config.json"
        self._config = self._load()

    # ── I/O ─────────────────────────────────────────────────────────────────

    def _load(self) -> dict:
        """Load config from the active storage backend, merging with defaults."""
        if self._use_file and self.config_path and self.config_path.exists():
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    loaded = json.load(f)
                # Loaded values override defaults
                return {**DEFAULT_CONFIG, **loaded}
            except Exception as exc:
                logger.warning("[ARMConfig] Config load failed for %s: %s", self.config_path, exc)
        elif not self._use_file:
            try:
                loaded = self._load_from_db()
                if loaded:
                    return {**DEFAULT_CONFIG, **loaded}
            except Exception as exc:
                logger.warning("[ARMConfig] DB config load failed: %s", exc)
        return DEFAULT_CONFIG.copy()

    def _persist(self) -> None:
        """Write current config state to the active storage backend."""
        if self._use_file and self.config_path is not None:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2)
            return
        self._persist_to_db(self._config)

    def _load_from_db(self) -> dict:
        from apps.arm.dao.arm_config_dao import get_config

        if self.db is not None:
            config = get_config(self.db)
            return self._model_to_dict(config) if config else {}

        from AINDY.db.database import SessionLocal

        db = SessionLocal()
        try:
            config = get_config(db)
            return self._model_to_dict(config) if config else {}
        finally:
            db.close()

    def _persist_to_db(self, config: dict) -> None:
        from apps.arm.dao.arm_config_dao import upsert_config

        if self.db is not None:
            upsert_config(self.db, **config)
            return

        from AINDY.db.database import SessionLocal

        db = SessionLocal()
        try:
            upsert_config(db, **config)
        finally:
            db.close()

    @staticmethod
    def _model_to_dict(config) -> dict:
        if config is None:
            return {}
        return {
            key: getattr(config, key)
            for key in DEFAULT_CONFIG.keys()
        }

    # ── Accessors ────────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Read a single config value."""
        self._config = self._load()
        return self._config.get(key, default)

    def get_all(self) -> dict:
        """Return a copy of the full config (used by GET /arm/config)."""
        self._config = self._load()
        return self._config.copy()

    # ── Mutations ────────────────────────────────────────────────────────────

    def update(self, updates: dict) -> dict:
        """
        Apply a partial config update and persist to disk.

        Only keys present in DEFAULT_CONFIG are accepted.
        Unknown keys are silently ignored (prevents injection).

        Used by PUT /arm/config.
        Phase 2: will also be called by the Infinity Algorithm
        self-tuning feedback loop.
        """
        filtered = {k: v for k, v in updates.items() if k in _UPDATABLE_KEYS}
        current = self._load()
        current.update(filtered)
        self._config = current
        self._persist()
        return self._config.copy()

    # ── Infinity Algorithm ───────────────────────────────────────────────────

    def calculate_task_priority(
        self,
        complexity: float = None,
        urgency: float = None,
        resource_cost: float = None,
    ) -> float:
        """
        Infinity Algorithm Task Priority formula:

            TP = (Complexity × Urgency) / Resource Cost

        Falls back to configured defaults when parameters are not provided.
        Guards against division by zero.
        """
        c = complexity if complexity is not None else self.get("task_complexity_default", 3)
        u = urgency if urgency is not None else self.get("task_urgency_default", 5)
        r = resource_cost if resource_cost is not None else self.get("resource_cost_default", 2)
        if not r:
            r = 0.001  # prevent ZeroDivisionError
        return (c * u) / r
