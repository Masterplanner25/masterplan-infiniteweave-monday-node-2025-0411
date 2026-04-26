"""Social domain bootstrap."""
from __future__ import annotations

import os

BOOTSTRAP_DEPENDS_ON: list[str] = []
APP_DEPENDS_ON: list[str] = ["analytics"]


def register() -> None:
    _register_router()
    _register_response_adapters()
    _register_health_check()


def _register_router() -> None:
    from AINDY.platform_layer.registry import register_router
    from apps.social.routes.social_router import router as social_router
    register_router(social_router)


def _register_response_adapters() -> None:
    from AINDY.platform_layer.registry import register_response_adapter
    from AINDY.platform_layer.response_adapters import legacy_envelope_adapter
    register_response_adapter("social", legacy_envelope_adapter)


def social_health_check() -> bool:
    from AINDY.db.database import SessionLocal
    from sqlalchemy import text

    linkedin_client_id = os.getenv("LINKEDIN_CLIENT_ID")
    linkedin_client_secret = os.getenv("LINKEDIN_CLIENT_SECRET")
    if not linkedin_client_id or not linkedin_client_secret:
        raise RuntimeError("LinkedIn credentials not configured")

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return True
    finally:
        db.close()


def _register_health_check() -> None:
    from AINDY.platform_layer.domain_health import domain_health_registry
    from AINDY.platform_layer.registry import register_health_check

    domain_health_registry.register("social", social_health_check)
    register_health_check("social", _check_health)


def _check_health() -> dict:
    import os

    reasons: list[str] = []
    try:
        from AINDY.config import settings
        from AINDY.db.mongo_setup import ping_mongo

        mongo_status = ping_mongo()
        if mongo_status.get("status") != "ok":
            reasons.append(str(mongo_status.get("reason") or "mongodb unreachable"))

        if not os.getenv("LINKEDIN_CLIENT_ID") or not os.getenv("LINKEDIN_CLIENT_SECRET"):
            reasons.append("linkedin credentials not configured")

        if reasons:
            return {"status": "degraded", "reason": "; ".join(reasons)}
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "degraded", "reason": str(exc)}
