"""
routes/__init__.py — Router registry with platform / apps layer separation.

Mount groups
-------------
ROOT_ROUTERS          — mounted at /          — health probes + auth (no prefix)
platform_router       — mounted at /          — already carries /platform internally
PLATFORM_ROUTERS      — mounted at /platform  — runtime infrastructure
APP_ROUTERS           — mounted at /apps      — mutable domain features

Layer definitions
------------------
Platform (/platform/*):
  Stable, versioned API surface intended for external integrations and tooling.
  Endpoints here represent the runtime itself — flow execution, event routing,
  observability, key management.  Breaking changes require a version bump.

Apps (/apps/*):
  Mutable domain features tied to A.I.N.D.Y.'s business logic.
  Endpoints here evolve freely as product requirements change.

Auth (/auth/*) and Health (/) sit at the root to match RFC / k8s conventions
and for backward compatibility with existing clients.
"""
import os

from .seo_routes import router as seo_router
from .task_router import router as task_router
from .bridge_router import router as bridge_router
from .authorship_router import router as authorship_router
from .rippletrace_router import router as rippletrace_router
from .network_bridge_router import router as network_bridge_router
from .db_verify_router import router as db_verify_router
from .research_results_router import router as research_router, search_history_router
from .main_router import legacy_router as legacy_main_router, router as main_router
from .freelance_router import router as freelance_router
from .arm_router import router as arm_router
from .leadgen_router import router as leadgen_router
from .dashboard_router import router as dashboard_router
from .legacy_surface_router import router as legacy_surface_router
from .health_router import router as health_router
from .health_dashboard_router import router as health_dashboard_router
from .social_router import router as social_router
from .analytics_router import router as analytics_router
from routes.genesis_router import router as genesis_router
from routes.auth_router import router as auth_router
from routes.masterplan_router import router as masterplan_router
from routes.memory_router import router as memory_router
from routes.memory_metrics_router import router as memory_metrics_router
from routes.memory_trace_router import router as memory_trace_router
from routes.identity_router import router as identity_router
from routes.observability_router import router as observability_router
from routes.system_state_router import router as system_state_router
from routes.automation_router import router as automation_router
from routes.flow_router import router as flow_router
from routes.watcher_router import router as watcher_router
from routes.score_router import router as score_router
from routes.agent_router import router as agent_router
from routes.autonomy_router import router as autonomy_router
from routes.goals_router import router as goals_router
from routes.coordination_router import router as coordination_router
from routes.platform_router import router as platform_router


# ---------------------------------------------------------------------------
# Root — health probes + auth (no mount prefix)
# ---------------------------------------------------------------------------
ROOT_ROUTERS = [
    health_router,   # GET /health, /health/, /ready, /health/details
    auth_router,     # POST /auth/register, /auth/login
    db_verify_router,  # GET /db/verify
]

# Legacy root aliases intentionally exposed only when compatibility mode is on.
# These preserve old flat endpoints such as /calculate_twr without re-enabling
# the full /apps/compute domain surface when ENABLE_DOMAIN_APPS=false.
LEGACY_ROOT_ROUTERS = []

# ---------------------------------------------------------------------------
# Platform — runtime infrastructure (mounted at /platform)
# ---------------------------------------------------------------------------
# platform_router is mounted separately in main.py (it already carries /platform
# internally and must not receive a second /platform prefix at mount time).
PLATFORM_ROUTERS = [
    flow_router,           # /platform/flows/runs, /platform/flows/runs/{id}, ...
    observability_router,  # /platform/observability/scheduler/status, /requests, ...
    system_state_router,   # /platform/system/state
    db_verify_router,      # /platform/db/verify
]

# ---------------------------------------------------------------------------
# Apps — mutable domain features (mounted at /apps)
# ---------------------------------------------------------------------------
import os as _os

# Routers always mounted on the platform surface
_PLATFORM_APP_ROUTERS = [
    agent_router,          # /apps/agent/run, /runs, /tools, /trust, ...
    autonomy_router,       # /apps/autonomy/decisions
    task_router,           # /apps/tasks/create, /start, /pause, ...
    goals_router,          # /apps/goals/
    masterplan_router,     # /apps/masterplans/
    genesis_router,        # /apps/genesis/session, /message, ...
    automation_router,     # /apps/automation/logs, /scheduler/status, ...
    memory_router,         # /apps/memory/nodes, /recall, /execute, ...
    memory_metrics_router, # /apps/memory/metrics, /metrics/detail, ...
    memory_trace_router,   # /apps/memory/traces, /traces/{id}, ...
    bridge_router,         # /apps/bridge/nodes, /link, /user_event
    analytics_router,      # /apps/analytics/linkedin/manual, /masterplan/{id}, ...
    score_router,          # /apps/scores/me, /feedback, ...
    identity_router,       # /apps/identity/boot, /evolution, /context
    watcher_router,        # /apps/watcher/signals
    coordination_router,   # /apps/coordination/agents, /graph
    dashboard_router,      # /apps/dashboard/overview
    health_dashboard_router, # /apps/dashboard/health
]

# Domain-specific routers — only mounted when ENABLE_DOMAIN_APPS=true
_DOMAIN_APP_ROUTERS = [
    arm_router,            # /apps/arm/analyze, /generate, /logs, /config, ...
    freelance_router,      # /apps/freelance/order, /deliver, /feedback, ...
    leadgen_router,        # /apps/leadgen/
    seo_router,            # /apps/seo/analyze, /meta, /suggest, ...
    social_router,         # /apps/social/profile, /post, /feed, ...
    authorship_router,     # /apps/authorship/reclaim
    research_router,       # /apps/research/
    search_history_router, # /apps/search/history
    rippletrace_router,    # /apps/rippletrace/drop_point, /ping, ...
    network_bridge_router, # /apps/network_bridge/connect, /authors
    main_router,           # /apps/compute/calculate_*, /results (legacy KPI surface)
]

_enable_domain = _os.getenv("ENABLE_DOMAIN_APPS", "false").lower() in {
    "1", "true", "yes"
}
APP_ROUTERS = _PLATFORM_APP_ROUTERS + (_DOMAIN_APP_ROUTERS if _enable_domain else [])

if os.getenv("AINDY_ENABLE_LEGACY_SURFACE", "false").lower() in {"1", "true", "yes"}:
    APP_ROUTERS.append(legacy_surface_router)
    LEGACY_ROOT_ROUTERS.append(legacy_main_router)
    LEGACY_ROOT_ROUTERS.append(leadgen_router)
    LEGACY_ROOT_ROUTERS.append(arm_router)
    LEGACY_ROOT_ROUTERS.append(freelance_router)
    LEGACY_ROOT_ROUTERS.append(seo_router)
    LEGACY_ROOT_ROUTERS.append(social_router)
    LEGACY_ROOT_ROUTERS.append(authorship_router)
    LEGACY_ROOT_ROUTERS.append(research_router)
    LEGACY_ROOT_ROUTERS.append(search_history_router)
    LEGACY_ROOT_ROUTERS.append(rippletrace_router)
    LEGACY_ROOT_ROUTERS.append(network_bridge_router)
    LEGACY_ROOT_ROUTERS.append(flow_router)
    LEGACY_ROOT_ROUTERS.append(observability_router)

# ---------------------------------------------------------------------------
# ROUTERS — backward-compat flat list consumed by tests and legacy callers.
# main.py uses the layered groups above; this shim keeps existing imports valid.
# ---------------------------------------------------------------------------
ROUTERS = ROOT_ROUTERS + [platform_router] + PLATFORM_ROUTERS + APP_ROUTERS + LEGACY_ROOT_ROUTERS
