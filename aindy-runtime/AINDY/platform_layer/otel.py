"""OpenTelemetry bootstrap for A.I.N.D.Y."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)
_initialized = False

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _OTEL_AVAILABLE = True
except ImportError:
    trace = None
    Resource = None
    SERVICE_NAME = None
    TracerProvider = None
    BatchSpanProcessor = None
    _OTEL_AVAILABLE = False


class _NoopSpan:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def set_status(self, *args, **kwargs):
        return None

    def record_exception(self, *args, **kwargs):
        return None


class _NoopTracer:
    def start_as_current_span(self, *args, **kwargs):
        return _NoopSpan()


def init_otel(service_name: str = "aindy") -> None:
    """Initialize OTEL TracerProvider. Safe to call multiple times (idempotent)."""
    global _initialized
    if _initialized:
        return
    if not _OTEL_AVAILABLE:
        logger.info("[otel] OpenTelemetry packages not installed - tracing is no-op")
        _initialized = True
        return

    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("[otel] OTLP exporter configured: %s", otlp_endpoint)
        except Exception as exc:
            logger.warning("[otel] OTLP exporter setup failed (tracing disabled): %s", exc)
    else:
        logger.info("[otel] OTEL_EXPORTER_OTLP_ENDPOINT not set - tracing is no-op")

    trace.set_tracer_provider(provider)
    _initialized = True


def get_tracer(name: str = "aindy"):
    if not _OTEL_AVAILABLE:
        return _NoopTracer()
    return trace.get_tracer(name)


def span_context_from_trace_id(trace_id_hex: str | None):
    """Convert an existing hex trace_id string to an OTEL SpanContext for linking."""
    if not _OTEL_AVAILABLE or not trace_id_hex:
        return None
    try:
        tid = int(trace_id_hex.replace("-", "")[:32], 16)
        sid = tid & ((1 << 64) - 1)
        if sid == 0:
            sid = 1
        return trace.SpanContext(
            trace_id=tid,
            span_id=sid,
            is_remote=True,
            trace_flags=trace.TraceFlags(trace.TraceFlags.SAMPLED),
            trace_state=trace.TraceState(),
        )
    except Exception:
        return None
