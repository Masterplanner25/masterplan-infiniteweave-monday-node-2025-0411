"""
Identity Router - v5 Phase 2

API for viewing and managing user identity profiles.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from AINDY.core.execution_signal_helper import queue_system_event
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from AINDY.core.execution_helper import execute_with_pipeline
from AINDY.db.database import get_db
from AINDY.services.auth_service import get_current_user
from apps.identity.services.identity_boot_service import boot_identity_context
from apps.identity.services.identity_service import IdentityService
from AINDY.core.system_event_service import (
    SystemEventEmissionError,
)
from AINDY.platform_layer.user_ids import require_user_id

router = APIRouter(prefix="/identity", tags=["Identity Layer"])


class UpdateIdentityRequest(BaseModel):
    tone: Optional[str] = None
    preferred_languages: Optional[list[str]] = None
    preferred_tools: Optional[list[str]] = None
    avoided_tools: Optional[list[str]] = None
    risk_tolerance: Optional[str] = None
    speed_vs_quality: Optional[str] = None
    learning_style: Optional[str] = None
    detail_preference: Optional[str] = None
    communication_notes: Optional[str] = None
    decision_notes: Optional[str] = None
    learning_notes: Optional[str] = None


@router.get("/boot")
async def boot_identity(
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = require_user_id(current_user.get("sub"))

    def handler(ctx):
        result = boot_identity_context(user_id, db)

        try:
            queue_system_event(
                db=db,
                event_type="identity.boot",
                user_id=user_id,
                payload={
                    "memory_loaded": len(result["memory"]),
                    "runs_loaded": len(result["runs"]),
                    "score": result["system_state"]["score"],
                    "active_flows": len(result["flows"]),
                },
                required=True,
            )
        except SystemEventEmissionError as exc:
            raise HTTPException(
                status_code=500,
                detail="Identity boot event emission failed",
            ) from exc

        return result

    return await execute_with_pipeline(
        request=request,
        route_name="identity.boot",
        handler=handler,
        user_id=str(user_id),
        metadata={"db": db, "disable_memory_capture": True},
    )


@router.get("/")
async def get_identity(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get the current user's identity profile.
    """
    user_id = str(current_user.get("sub"))

    def handler(ctx):
        service = IdentityService(db=db, user_id=user_id)
        return service.get_profile()

    return await execute_with_pipeline(
        request=request,
        route_name="identity.get",
        handler=handler,
        user_id=user_id,
        metadata={"db": db},
    )


@router.put("/")
async def update_identity(
    request: Request,
    body: UpdateIdentityRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Explicitly update identity preferences.
    """
    user_id = str(current_user.get("sub"))

    def handler(ctx):
        service = IdentityService(db=db, user_id=user_id)
        return service.update_explicit(**body.model_dump(exclude_none=True))

    return await execute_with_pipeline(
        request=request,
        route_name="identity.update",
        handler=handler,
        user_id=user_id,
        metadata={"db": db},
        input_payload=body.model_dump(exclude_none=True),
    )


@router.get("/evolution")
async def get_identity_evolution(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get the evolution history of the user's identity.
    """
    user_id = str(current_user.get("sub"))

    def handler(ctx):
        service = IdentityService(db=db, user_id=user_id)
        return service.get_evolution_summary()

    return await execute_with_pipeline(
        request=request,
        route_name="identity.evolution",
        handler=handler,
        user_id=user_id,
        metadata={"db": db},
    )


@router.get("/context")
async def get_identity_context(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get the identity context string used in LLM prompts.
    """
    user_id = str(current_user.get("sub"))

    def handler(ctx):
        service = IdentityService(db=db, user_id=user_id)
        context = service.get_context_for_prompt()
        return {
            "context": context,
            "is_empty": len(context.strip()) == 0,
            "message": (
                "This context is injected into AI prompts to personalize responses."
                if context.strip()
                else "No identity context yet. Use A.I.N.D.Y. features to build your profile."
            ),
        }

    return await execute_with_pipeline(
        request=request,
        route_name="identity.context",
        handler=handler,
        user_id=user_id,
        metadata={"db": db},
    )

