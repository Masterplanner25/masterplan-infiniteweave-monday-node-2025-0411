"""Compatibility shim for analytics policy adaptation services."""

import sys

from .scoring import policy_adaptation_service as _impl

sys.modules[__name__] = _impl
