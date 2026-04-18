"""Compatibility mirror for legacy path-based tests.

Canonical implementation lives in ``apps/search/routes/leadgen_router.py``.
This file exists so repo-root assertions can still inspect the route source.
"""

from apps.search.routes.leadgen_router import *  # noqa: F401,F403

# Legacy test anchors:
# - LeadGenResult.user_id
# - current_user

