"""Compatibility shim for analytics task bridge services."""

import sys

from .integration import tasks_bridge as _impl

sys.modules[__name__] = _impl
