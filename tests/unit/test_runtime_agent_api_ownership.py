from __future__ import annotations

from AINDY.routes import APP_ROUTERS
from AINDY.routes.agent_router import router as runtime_agent_router


def test_runtime_agent_router_is_app_surface_router():
    assert runtime_agent_router in APP_ROUTERS


def test_plugin_registry_does_not_own_agent_router_after_bootstrap():
    import apps.bootstrap as bs
    from AINDY.platform_layer import registry

    bs._BOOTSTRAPPED = False
    registry._loaded_plugins.clear()
    registry._registered_apps.clear()
    registry._bootstrap_dependencies.clear()
    registry._routers.clear()
    registry._root_routers.clear()
    registry._legacy_root_routers.clear()
    registry.publish_degraded_domains(())

    bs.bootstrap()

    registered_prefixes = [getattr(router, "prefix", None) for router in registry.get_routers()]
    assert "/agent" not in registered_prefixes
