"""Compatibility shim for analytics compute services."""

import sys

from .calculations import compute_service as _impl

sys.modules[__name__] = _impl
