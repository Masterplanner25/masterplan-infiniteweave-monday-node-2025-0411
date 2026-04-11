"""Top-level config shim so legacy imports keep working."""

from AINDY.config import Settings, settings

__all__ = ["settings", "Settings"]
