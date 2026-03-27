from __future__ import annotations

import json
import logging
from typing import Any


def emit_observability_event(
    logger: logging.Logger,
    *,
    event: str,
    level: str = "warning",
    **payload: Any,
) -> None:
    record = {"event": event, **payload}
    message = json.dumps(record, ensure_ascii=False, default=str)
    log_fn = getattr(logger, str(level).lower(), logger.warning)
    log_fn(message)
