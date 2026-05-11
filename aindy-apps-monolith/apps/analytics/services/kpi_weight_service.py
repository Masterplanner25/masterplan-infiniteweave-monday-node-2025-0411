"""Compatibility shim for analytics KPI weight services."""

import sys

from .scoring import kpi_weight_service as _impl

sys.modules[__name__] = _impl
