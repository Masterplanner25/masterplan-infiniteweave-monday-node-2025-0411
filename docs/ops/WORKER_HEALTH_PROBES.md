---
title: "Worker Health Probes"
last_verified: "2026-04-25"
api_version: "1.0"
status: current
owner: "platform-team"
---

# Worker Health Probes

The AINDY worker exposes health probes on port `AINDY_WORKER_HEALTH_PORT` (default `8001`).

## Liveness Probe
`GET /healthz`

Returns `200` when the worker event loop is responsive.
Returns `503` when the worker has been unresponsive for more than `AINDY_WORKER_LIVENESS_TIMEOUT_SECONDS`.

Kubernetes configuration:

```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8001
  initialDelaySeconds: 10
  periodSeconds: 15
  failureThreshold: 3
```

## Readiness Probe
`GET /readyz`

Returns `200` when the worker is ready to accept jobs.
Returns `503` during startup, draining, or when the queue is at capacity.

Kubernetes configuration:

```yaml
readinessProbe:
  httpGet:
    path: /readyz
    port: 8001
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 2
```

## Configuration

| Variable | Default | Purpose |
|---|---:|---|
| `AINDY_WORKER_HEALTH_PORT` | `8001` | Worker health server port |
| `AINDY_WORKER_LIVENESS_TIMEOUT_SECONDS` | `60` | Heartbeat staleness threshold |
