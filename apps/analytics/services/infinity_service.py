"""Compatibility shim for analytics infinity scoring services."""

import sys

from .scoring import infinity_service as _impl

sys.modules[__name__] = _impl
