"""Compatibility shim for analytics dependency adapters."""

import sys

from .integration import dependency_adapter as _impl

sys.modules[__name__] = _impl
