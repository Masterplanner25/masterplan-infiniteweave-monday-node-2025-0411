"""
Prometheus metrics registry for A.I.N.D.Y.

All metrics are defined here and imported where needed.
Never use the default `prometheus_client` registry directly —
always import from this module.
"""
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

REGISTRY = CollectorRegistry(auto_describe=True)

# ── Execution pipeline ────────────────────────────────────────────────────────

execution_total = Counter(
    "aindy_execution_total",
    "Total executions by route and outcome",
    ["route", "status"],  # status: success | failed | waiting
    registry=REGISTRY,
)

execution_duration_seconds = Histogram(
    "aindy_execution_duration_seconds",
    "Execution handler duration in seconds",
    ["route"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
    registry=REGISTRY,
)

# ── Scheduler ────────────────────────────────────────────────────────────────

scheduler_queue_depth = Gauge(
    "aindy_scheduler_queue_depth",
    "Items in the scheduler priority queues",
    ["priority"],  # high | normal | low
    registry=REGISTRY,
)

scheduler_waiting_count = Gauge(
    "aindy_scheduler_waiting_count",
    "Flows currently registered in WAIT state (in-memory)",
    registry=REGISTRY,
)

# ── Resource manager ─────────────────────────────────────────────────────────

active_executions_total = Gauge(
    "aindy_active_executions_total",
    "Total active executions across all tenants (in-memory counter)",
    registry=REGISTRY,
)

# ── OpenAI client ─────────────────────────────────────────────────────────────

openai_retries_total = Counter(
    "aindy_openai_retries_total",
    "Total OpenAI call retries",
    ["call_type"],  # chat | embedding
    registry=REGISTRY,
)

openai_errors_total = Counter(
    "aindy_openai_errors_total",
    "Total OpenAI call failures after all retries exhausted",
    ["call_type"],
    registry=REGISTRY,
)
