"""Compatibility shim for analytics orchestration concurrency."""

import sys

from .orchestration import concurrency as _impl

sys.modules[__name__] = _impl
