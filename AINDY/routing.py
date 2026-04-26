import os

from fastapi import Depends
from prometheus_client import make_asgi_app as _make_metrics_asgi

from AINDY.core.execution_guard import require_execution_context
from AINDY.platform_layer.metrics import REGISTRY as _METRICS_REGISTRY
from AINDY.platform_layer.registry import get_legacy_root_routers, get_routers
from AINDY.routes.version_router import router as version_router
from AINDY.routes import (
    APP_ROUTERS,
    LEGACY_ROOT_ROUTERS,
    PLATFORM_ROUTERS,
    ROOT_ROUTERS,
    platform_router,
)


def home():
    return {"message": "A.I.N.D.Y. API is running!"}


def register_routes(app) -> None:
    app.mount("/metrics", _make_metrics_asgi(registry=_METRICS_REGISTRY))
    app.get("/")(home)
    app.include_router(version_router)

    for route in ROOT_ROUTERS:
        app.include_router(route, dependencies=[Depends(require_execution_context)])

    for route in PLATFORM_ROUTERS:
        app.include_router(route, prefix="/platform", dependencies=[Depends(require_execution_context)])
    app.include_router(platform_router, dependencies=[Depends(require_execution_context)])

    for route in APP_ROUTERS:
        app.include_router(route, prefix="/apps", dependencies=[Depends(require_execution_context)])

    application_routers = get_routers()
    for route in application_routers:
        app.include_router(route, prefix="/apps", dependencies=[Depends(require_execution_context)])

    if os.getenv("AINDY_ENABLE_LEGACY_SURFACE", "false").lower() in {"1", "true", "yes"}:
        for route in APP_ROUTERS:
            app.include_router(route, dependencies=[Depends(require_execution_context)])
        for route in application_routers:
            app.include_router(route, dependencies=[Depends(require_execution_context)])
        for route in get_legacy_root_routers():
            app.include_router(route, dependencies=[Depends(require_execution_context)])
        for route in LEGACY_ROOT_ROUTERS:
            app.include_router(route, dependencies=[Depends(require_execution_context)])
