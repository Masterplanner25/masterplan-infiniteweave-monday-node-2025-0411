"""Identity domain bootstrap."""
from __future__ import annotations

BOOTSTRAP_DEPENDS_ON: list[str] = []
APP_DEPENDS_ON: list[str] = ["analytics"]


def register() -> None:
    _register_router()
    _register_response_adapters()
    _register_events()


def _register_router() -> None:
    from AINDY.platform_layer.registry import register_router
    from apps.identity.routes.identity_router import router as identity_router
    register_router(identity_router)


def _register_response_adapters() -> None:
    from AINDY.platform_layer.registry import register_response_adapter
    from apps._adapters import raw_json_adapter
    register_response_adapter("auth", raw_json_adapter)


def _register_events() -> None:
    from AINDY.platform_layer.event_service import register_event_handler
    register_event_handler("auth.register.completed", _handle_auth_register_completed)


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
