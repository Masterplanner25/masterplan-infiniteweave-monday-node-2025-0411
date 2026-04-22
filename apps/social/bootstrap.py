"""Social domain bootstrap."""
from __future__ import annotations

BOOTSTRAP_DEPENDS_ON: list[str] = []


def register() -> None:
    _register_router()
    _register_response_adapters()


def _register_router() -> None:
    from AINDY.platform_layer.registry import register_router
    from apps.social.routes.social_router import router as social_router
    register_router(social_router)


def _register_response_adapters() -> None:
    from AINDY.platform_layer.registry import register_response_adapter
    from apps._adapters import legacy_envelope_adapter
    register_response_adapter("social", legacy_envelope_adapter)
