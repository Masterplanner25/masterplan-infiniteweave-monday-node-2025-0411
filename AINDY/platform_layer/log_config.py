"""Structured JSON logging configuration for A.I.N.D.Y."""
from __future__ import annotations

import logging
import os


_HANDLER_MARKER = "_aindy_structured_logging_handler"


class _CorrelationFilter(logging.Filter):
    """
    Inject request correlation fields into every log record.

    Fields added (all strings, empty string if unavailable):
      trace_id  - current request trace ID from ContextVar
      user_id   - current authenticated user from request context
      env       - deployment environment (ENV setting)
    """

    def __init__(self, env: str = "development") -> None:
        super().__init__()
        self._env = env

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from AINDY.platform_layer.trace_context import (
                get_current_execution_context,
                get_current_request,
                get_current_trace_id,
            )

            record.trace_id = get_current_trace_id() or ""
            request = get_current_request()
            request_state = getattr(request, "state", None)
            record.user_id = ""
            if request_state is not None:
                record.user_id = str(getattr(request_state, "user_id", "") or "")
            if not record.user_id:
                execution_context = get_current_execution_context()
                if isinstance(execution_context, dict):
                    record.user_id = str(execution_context.get("user_id", "") or "")
                elif execution_context is not None:
                    record.user_id = str(getattr(execution_context, "user_id", "") or "")
        except Exception:
            record.trace_id = ""
            record.user_id = ""
        record.env = self._env
        return True


def configure_logging(
    *,
    env: str = "development",
    log_level: str = "INFO",
    json_logs: bool | None = None,
    force: bool = False,
) -> None:
    """
    Configure root logger with structured output.

    json_logs defaults to True in production, False in development/test.
    Set LOG_FORMAT=json to force JSON in any environment.
    Set LOG_FORMAT=text to force plain text in any environment.
    """
    if json_logs is None:
        fmt_env = os.getenv("LOG_FORMAT", "").lower()
        if fmt_env == "json":
            json_logs = True
        elif fmt_env == "text":
            json_logs = False
        else:
            json_logs = env.lower() in {"production", "prod", "staging"}

    correlation_filter = _CorrelationFilter(env=env)

    if json_logs:
        try:
            from pythonjsonlogger import jsonlogger

            formatter = jsonlogger.JsonFormatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(trace_id)s %(user_id)s %(env)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
                rename_fields={
                    "asctime": "timestamp",
                    "levelname": "level",
                    "name": "logger",
                },
            )
        except ImportError:
            formatter = logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s [trace_id=%(trace_id)s user_id=%(user_id)s env=%(env)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s [trace_id=%(trace_id)s user_id=%(user_id)s env=%(env)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(correlation_filter)
    setattr(handler, _HANDLER_MARKER, True)

    root = logging.getLogger()
    current_handler = next(
        (candidate for candidate in root.handlers if getattr(candidate, _HANDLER_MARKER, False)),
        None,
    )
    should_replace = force or current_handler is None or len(root.handlers) != 1

    if should_replace:
        root.handlers.clear()
        root.addHandler(handler)
    else:
        current_handler.setFormatter(formatter)
        for existing_filter in list(current_handler.filters):
            current_handler.removeFilter(existing_filter)
        current_handler.addFilter(correlation_filter)

    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    if env.lower() in {"production", "prod"}:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("apscheduler").setLevel(logging.WARNING)
