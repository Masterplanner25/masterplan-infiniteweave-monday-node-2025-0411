"""Compatibility shim for analytics infinity loop services."""

import sys

from .orchestration import infinity_loop as _impl

sys.modules[__name__] = _impl
