"""Compatibility mirror for legacy path-based tests.

Canonical implementation lives in ``AINDY/routes/task_router.py``.
This file exists so repo-root assertions can still inspect the route source.
"""

from AINDY.routes.task_router import *  # noqa: F401,F403

# Legacy test anchors:
# - Task.user_id
# - current_user

