"""Identity domain bootstrap."""
from __future__ import annotations

BOOTSTRAP_DEPENDS_ON: list[str] = []
APP_DEPENDS_ON: list[str] = ["agent"]


def register() -> None:
    _register_router()
    _register_response_adapters()
    _register_events()
    _register_syscalls()
    _register_health_check()
    # Expose public surface for cross-domain callers.
    from apps.identity import public as identity_public  # noqa: F401


def _register_router() -> None:
    from AINDY.platform_layer.registry import register_router
    from apps.identity.routes.identity_router import router as identity_router
    register_router(identity_router)


def _register_response_adapters() -> None:
    from AINDY.platform_layer.registry import register_response_adapter
    from AINDY.platform_layer.response_adapters import raw_json_adapter
    register_response_adapter("auth", raw_json_adapter)


def _register_events() -> None:
    from AINDY.platform_layer.event_service import register_event_handler
    register_event_handler("auth.register.completed", _handle_auth_register_completed)


def _register_syscalls() -> None:
    from apps.identity.syscalls.syscall_handlers import (
        register_identity_syscall_handlers,
    )

    register_identity_syscall_handlers()


def _handle_auth_register_completed(event: dict) -> None:
    from AINDY.db.models.user import User
    from AINDY.utils.uuid_utils import ensure_uuid
    from apps.identity.services.signup_initialization_service import initialize_signup_state

    db = event.get("db")
    if db is None:
        return
    user_id = event.get("user_id")
    if user_id is None:
        return
    user_id = ensure_uuid(user_id)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return
    initialize_signup_state(db=db, user=user)


def identity_health_check() -> bool:
    from AINDY.db.database import SessionLocal
    from sqlalchemy import text

    try:
        from AINDY.db.models.user_identity import UserIdentity
        from apps.identity.services.identity_service import IdentityService
    except Exception as exc:
        raise RuntimeError(f"identity health import failed: {exc}") from exc

    _ = IdentityService
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        db.query(UserIdentity.id).limit(1).all()
        return True
    finally:
        db.close()


def _register_health_check() -> None:
    from AINDY.platform_layer.domain_health import domain_health_registry
    from AINDY.platform_layer.registry import register_health_check

    domain_health_registry.register("identity", identity_health_check)
    register_health_check("identity", lambda: {"status": "ok"})
