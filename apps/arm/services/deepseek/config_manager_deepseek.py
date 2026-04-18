"""
ARM Configuration Manager

Manages DeepSeek/ARM configuration parameters.
Reads from deepseek_config.json at startup.
Supports runtime updates via PUT /arm/config.

Phase 2 will add self-tuning via Infinity Algorithm feedback loop.
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

    Config is stored as a JSON file (deepseek_config.json).
    Runtime values override defaults.
    Only keys present in DEFAULT_CONFIG are accepted for updates.
    """

    def __init__(self, config_path: str = None):
        if config_path is None:
            repo_root = Path(__file__).resolve().parents[4]
            config_path = repo_root / "AINDY" / "deepseek_config.json"
        self.config_path = Path(config_path)
        self._config = self._load()

    # ── I/O ─────────────────────────────────────────────────────────────────

    def _load(self) -> dict:
        """Load config from JSON, merging with defaults for any missing keys."""
        if self.config_path.exists():
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    loaded = json.load(f)
                # Loaded values override defaults
                return {**DEFAULT_CONFIG, **loaded}
            except Exception as exc:
                logger.warning("[ARMConfig] Config load failed for %s: %s", self.config_path, exc)
        return DEFAULT_CONFIG.copy()

    def _persist(self) -> None:
        """Write current config state to JSON file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self._config, f, indent=2)

    # ── Accessors ────────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Read a single config value."""
        return self._config.get(key, default)

    def get_all(self) -> dict:
        """Return a copy of the full config (used by GET /arm/config)."""
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
        self._config.update(filtered)
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
