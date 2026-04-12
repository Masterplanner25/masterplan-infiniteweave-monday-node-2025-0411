"""Compatibility mirror for legacy path-based tests."""

from AINDY.routes.watcher_router import *  # noqa: F401,F403

# Legacy test anchors:
# execute_intent
# watcher_ingest
from AINDY.routes.watcher_router import execute_with_pipeline_sync  # noqa: F401
from AINDY.routes.watcher_router import receive_signals  # noqa: F401

