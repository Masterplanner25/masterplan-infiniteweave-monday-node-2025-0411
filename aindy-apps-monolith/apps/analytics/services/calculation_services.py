"""Compatibility shim for analytics calculation services."""

import sys

from .calculations import calculation_services as _impl

sys.modules[__name__] = _impl
