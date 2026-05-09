from pydantic import BaseModel
from fastapi import APIRouter

from AINDY.config import settings
from AINDY.platform_layer.deployment_contract import runtime_ui_surface_state

router = APIRouter(prefix="/api", tags=["version"])


class RuntimeSurfaceResponse(BaseModel):
    boot_mode: str
    boot_profile: str
    boot_profile_source: str
    app_plugins_loaded: bool
    app_plugin_count: int
    ui_mode: str
    default_route: str
    platform_home: str


class VersionResponse(BaseModel):
    api_version: str
    min_client_version: str
    breaking_change_policy: str
    changelog_url: str | None
    runtime: RuntimeSurfaceResponse


@router.get("/version", response_model=VersionResponse)
async def get_api_version():
    return VersionResponse(
        api_version=settings.API_VERSION,
        min_client_version=settings.API_MIN_CLIENT_VERSION,
        breaking_change_policy=(
            "MAJOR version increments indicate breaking changes. "
            "Clients must re-deploy when the MAJOR version changes. "
            "MINOR and PATCH increments are safe for existing clients."
        ),
        changelog_url=None,
        runtime=RuntimeSurfaceResponse(**runtime_ui_surface_state()),
    )
