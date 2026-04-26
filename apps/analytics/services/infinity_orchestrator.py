"""Compatibility shim for analytics infinity orchestrator services."""

import sys

from .orchestration import infinity_orchestrator as _impl

sys.modules[__name__] = _impl
