"""
routes/__init__.py - platform route registry.

AINDY/routes owns platform and root system routers only. Application routers
are imported from apps/*/routes by AINDY.main and mounted under /apps.
"""
import os

from AINDY.routes.auth_router import router as auth_router
from AINDY.routes.coordination_router import router as coordination_router
from AINDY.routes.flow_router import router as flow_router
from AINDY.routes.health_router import router as health_router
from AINDY.routes.memory_metrics_router import router as memory_metrics_router
from AINDY.routes.memory_router import router as memory_router
from AINDY.routes.memory_trace_router import router as memory_trace_router
from AINDY.routes.observability_router import router as observability_router
from AINDY.routes.platform_router import router as platform_router


ROOT_ROUTERS = [
    health_router,
    auth_router,
]

LEGACY_ROOT_ROUTERS = []

PLATFORM_ROUTERS = [
    flow_router,
    observability_router,
]

# Platform primitives still exposed on the historical /apps surface.
APP_ROUTERS = [
    memory_router,
    memory_metrics_router,
    memory_trace_router,
    coordination_router,
]

if os.getenv("AINDY_ENABLE_LEGACY_SURFACE", "false").lower() in {"1", "true", "yes"}:
    LEGACY_ROOT_ROUTERS.append(flow_router)
    LEGACY_ROOT_ROUTERS.append(observability_router)

ROUTERS = ROOT_ROUTERS + [platform_router] + PLATFORM_ROUTERS + APP_ROUTERS + LEGACY_ROOT_ROUTERS
