from __future__ import annotations

import inspect
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response

logger = logging.getLogger(__name__)

try:
    from AINDY.platform_layer.metrics import (
        active_executions_total as aindy_active_executions_total,
        execution_duration_seconds,
        execution_total,
    )

    _METRICS_AVAILABLE = True
except Exception:  # pragma: no cover
    _METRICS_AVAILABLE = False
