import ipaddress as _ipaddress
import json
import logging
import os
import time
import uuid

from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.middleware import SlowAPIMiddleware

from AINDY.config import settings
from AINDY.core.execution_guard import validate_execution_contract
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.platform_layer.trace_context import (
    _trace_id_ctx,
    reset_current_request,
    reset_current_trace_id,
    set_current_request,
    set_current_trace_id,
)

logger = logging.getLogger("AINDY.main")

_request_id_ctx = _trace_id_ctx


class RequestContextFilter(logging.Filter):
    """Inject request/trace IDs from ContextVar into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        trace_id = _trace_id_ctx.get()
        record.trace_id = trace_id
        record.request_id = trace_id
        return True


_REQUEST_LOG_FORMAT = "%(asctime)s - %(levelname)s - [trace=%(trace_id)s] - %(message)s"
_ctx_filter = RequestContextFilter()
for _handler in logging.root.handlers:
    _handler.addFilter(_ctx_filter)
    _handler.setFormatter(logging.Formatter(_REQUEST_LOG_FORMAT))

_AINDY_SERVICE_KEY: str = os.getenv("AINDY_SERVICE_KEY", "")


def _semver_tuple(version: str) -> tuple[int, int, int]:
    try:
        parts = str(version).split(".")[:3]
        normalized = [int(part) for part in parts]
        while len(normalized) < 3:
            normalized.append(0)
        return tuple(normalized[:3])  # type: ignore[return-value]
    except (TypeError, ValueError, AttributeError):
        return (0, 0, 0)


def _is_version_below(version: str, minimum: str) -> bool:
    return _semver_tuple(version) < _semver_tuple(minimum)


def _is_metrics_ip_allowed(host: str) -> bool:
    try:
        addr = _ipaddress.ip_address(host)
        return addr.is_loopback or addr.is_private
    except ValueError:
        return False


async def _guard_metrics_endpoint(request: Request, call_next):
    if request.url.path == "/metrics" or request.url.path.startswith("/metrics/"):
        import AINDY.main as main_module

        client_host = (request.client.host if request.client else "") or ""
        if main_module._is_metrics_ip_allowed(client_host):
            return await call_next(request)
        if main_module._AINDY_SERVICE_KEY:
            auth = request.headers.get("Authorization", "")
            if auth == f"Bearer {main_module._AINDY_SERVICE_KEY}":
                return await call_next(request)
            return JSONResponse({"error": "forbidden"}, status_code=403)
        return await call_next(request)
    return await call_next(request)


async def enforce_execution_contract(request: Request, call_next):
    request_token = set_current_request(request)
    try:
        response = await call_next(request)
        validate_execution_contract(request, response)
        return response
    finally:
        reset_current_request(request_token)


async def log_requests(request, call_next):
    from AINDY.exception_handlers import _extract_user_id_from_request

    trace_id = str(uuid.uuid4())
    trace_token = set_current_trace_id(trace_id)
    request.state.trace_id = trace_id
    start_time = time.time()
    try:
        response = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000, 2)
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Request-ID"] = trace_id

        user_id = _extract_user_id_from_request(request)
        log_payload = {
            "event": "request_complete",
            "trace_id": trace_id,
            "request_id": trace_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "user_id": str(user_id) if user_id else None,
        }
        logger.info(json.dumps(log_payload, ensure_ascii=False))

        if not settings.is_testing and not os.getenv("PYTEST_CURRENT_TEST"):
            from AINDY.core.request_metric_writer import PendingMetric, get_writer

            get_writer().enqueue(
                PendingMetric(
                    request_id=trace_id,
                    trace_id=trace_id,
                    user_id=user_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
            )
        return response
    finally:
        reset_current_trace_id(trace_token)


async def add_api_version_headers(request: Request, call_next):
    response = await call_next(request)
    api_version = getattr(settings, "API_VERSION", None) or "0.0.0"
    min_client_version = getattr(settings, "API_MIN_CLIENT_VERSION", None) or "0.0.0"
    response.headers["X-API-Version"] = api_version

    client_version = request.headers.get("X-Client-Version")
    if client_version and _is_version_below(client_version, min_client_version):
        response.headers["X-Version-Warning"] = (
            f"Client version {client_version} is below minimum supported "
            f"{min_client_version}. Please upgrade."
        )

    return response


def register_middleware(app) -> None:
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.middleware("http")(_guard_metrics_endpoint)
    _allowed_origins = [
        o.strip()
        for o in os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:5173,http://localhost:3000,http://localhost:5000",
        ).split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    app.middleware("http")(enforce_execution_contract)
    app.middleware("http")(log_requests)
    app.middleware("http")(add_api_version_headers)
