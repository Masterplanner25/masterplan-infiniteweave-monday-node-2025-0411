from pydantic import BaseModel
from fastapi import APIRouter

from AINDY.config import settings

router = APIRouter(prefix="/api", tags=["version"])


class VersionResponse(BaseModel):
    api_version: str
    min_client_version: str
    breaking_change_policy: str
    changelog_url: str | None


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
    )
