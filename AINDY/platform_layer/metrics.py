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

db_pool_checkedout = Gauge(
    "aindy_db_pool_checkedout",
    "Number of connections currently checked out from the pool",
    registry=REGISTRY,
)

db_pool_overflow = Gauge(
    "aindy_db_pool_overflow",
    "Number of overflow connections currently in use",
    registry=REGISTRY,
)

db_pool_size = Gauge(
    "aindy_db_pool_size",
    "Configured pool size",
    registry=REGISTRY,
)

db_pool_pressure = Gauge(
    "aindy_db_pool_pressure_ratio",
    "Connection pool pressure: checkedout / (pool_size + max_overflow). "
    "1.0 = fully saturated. Alert threshold recommended at 0.8.",
    registry=REGISTRY,
)

db_pool_exhaustion_events_total = Counter(
    "aindy_db_pool_exhaustion_events_total",
    "Number of times the pool pressure threshold was crossed (rising edge only)",
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

deepseek_retries_total = Counter(
    "aindy_deepseek_retries_total",
    "Total DeepSeek call retries",
    ["call_type"],
    registry=REGISTRY,
)

deepseek_errors_total = Counter(
    "aindy_deepseek_errors_total",
    "Total DeepSeek call failures after all retries exhausted",
    ["call_type"],
    registry=REGISTRY,
)

embedding_generation_total = Counter(
    "aindy_embedding_generation_total",
    "Total embedding generation requests by outcome",
    ["outcome"],  # success | failure
    registry=REGISTRY,
)

embedding_generation_retries_total = Counter(
    "aindy_embedding_generation_retries_total",
    "Total embedding generation retries before a terminal outcome",
    registry=REGISTRY,
)

embedding_generation_latency_seconds = Histogram(
    "aindy_embedding_generation_latency_seconds",
    "Embedding generation latency in seconds",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
    registry=REGISTRY,
)

mongo_health_status = Gauge(
    "aindy_mongo_health_status",
    "MongoDB connectivity status reported by startup health checks",
    registry=REGISTRY,
)

# Queue

async_queue_depth = Gauge(
    "aindy_async_queue_depth",
    "Pending async jobs currently queued",
    ["backend"],
    registry=REGISTRY,
)

async_queue_in_flight = Gauge(
    "aindy_async_queue_in_flight",
    "Async jobs currently being processed",
    ["backend"],
    registry=REGISTRY,
)

async_queue_delayed = Gauge(
    "aindy_async_queue_delayed",
    "Async jobs currently delayed before enqueue",
    ["backend"],
    registry=REGISTRY,
)

async_queue_dlq_depth = Gauge(
    "aindy_async_queue_dlq_depth",
    "Async jobs currently in the dead-letter queue",
    ["backend"],
    registry=REGISTRY,
)

async_queue_capacity = Gauge(
    "aindy_async_queue_capacity",
    "Configured async queue capacity",
    ["backend"],
    registry=REGISTRY,
)

async_queue_enqueue_total = Counter(
    "aindy_async_queue_enqueue_total",
    "Total async job enqueue attempts by outcome",
    ["backend", "outcome"],
    registry=REGISTRY,
)

async_queue_dequeue_total = Counter(
    "aindy_async_queue_dequeue_total",
    "Total async job dequeues",
    ["backend"],
    registry=REGISTRY,
)

async_queue_failure_total = Counter(
    "aindy_async_queue_failure_total",
    "Total async job queue failures by stage",
    ["backend", "stage"],
    registry=REGISTRY,
)

queue_backend_mode = Gauge(
    "aindy_queue_backend_mode",
    "Active queue backend: 1=redis, 0=in_memory (degraded)",
    registry=REGISTRY,
)

queue_backend_fallback_total = Counter(
    "aindy_queue_backend_fallback_total",
    "Number of times the queue fell back from Redis to in-memory",
    registry=REGISTRY,
)

quota_redis_mode = Gauge(
    "aindy_quota_redis_mode",
    "Active quota backend: 1=redis (cross-instance), 0=in_memory (per-instance only)",
    registry=REGISTRY,
)

quota_redis_fallback_total = Counter(
    "aindy_quota_redis_fallback_total",
    "Number of times the quota backend fell back from Redis to in-memory",
    registry=REGISTRY,
)

request_metric_drops_total = Counter(
    "aindy_request_metric_drops_total",
    "Number of RequestMetric rows dropped due to queue saturation",
    registry=REGISTRY,
)

memory_ingest_dropped_total = Counter(
    "aindy_memory_ingest_dropped_total",
    "Number of memory ingest writes dropped due to bounded queue backpressure",
    registry=REGISTRY,
)

memory_ingest_queue_depth = Gauge(
    "aindy_memory_ingest_queue_depth",
    "Current depth of the bounded memory ingest queue",
    registry=REGISTRY,
)

memory_ingest_queue_capacity = Gauge(
    "aindy_memory_ingest_queue_capacity",
    "Configured capacity of the bounded memory ingest queue",
    registry=REGISTRY,
)

startup_recovery_failure_total = Counter(
    "aindy_startup_recovery_failure_total",
    "Number of startup recovery scan failures",
    ["recovery_type"],
    registry=REGISTRY,
)

startup_recovery_runs_recovered_total = Counter(
    "aindy_startup_recovery_runs_recovered_total",
    "Number of stuck runs recovered at startup",
    ["recovery_type"],
    registry=REGISTRY,
)

wait_recovery_poll_failure_total = Counter(
    "aindy_wait_recovery_poll_failure_total",
    "Number of wait recovery poll failures (background job)",
    registry=REGISTRY,
)

system_health_tier = Gauge(
    "aindy_system_health_tier",
    "Current system health tier: 0=healthy, 1=degraded, 2=critical",
    registry=REGISTRY,
)

ai_circuit_breaker_state = Gauge(
    "aindy_ai_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half_open, 2=open)",
    ["provider"],
    registry=REGISTRY,
)

deferred_boundary_violations_total = Gauge(
    "aindy_deferred_boundary_violations_total",
    "Number of deferred cross-domain imports detected in router files "
    "(function-body imports crossing app domain boundaries)",
    registry=REGISTRY,
)

resume_watchdog_resumes_total = Counter(
    "aindy_resume_watchdog_resumes_total",
    "Number of flows resumed by the watchdog due to missed Redis events",
    registry=REGISTRY,
)

event_handler_timeouts_total = Counter(
    "aindy_event_handler_timeouts_total",
    "Number of event handler invocations that exceeded the timeout",
    ["event_type"],
    registry=REGISTRY,
)

event_handler_duration_seconds = Histogram(
    "aindy_event_handler_duration_seconds",
    "Wall-clock time per event handler invocation",
    ["event_type", "handler_name", "result"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=REGISTRY,
)

infinity_score_write_failures_total = Counter(
    "aindy_infinity_score_write_failures_total",
    "Total number of Infinity score write failures",
    ["reason"],
    registry=REGISTRY,
)
