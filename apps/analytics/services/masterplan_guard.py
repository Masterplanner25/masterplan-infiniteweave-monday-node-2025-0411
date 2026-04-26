"""Compatibility shim for analytics masterplan guard services."""

import sys

from .integration import masterplan_guard as _impl

sys.modules[__name__] = _impl
