"""
Identity Router - v5 Phase 2

API for viewing and managing user identity profiles.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from db.database import get_db
from services.auth_service import get_current_user
from services.identity_boot_service import boot_identity_context
from services.identity_service import IdentityService
from services.system_event_service import (
    SystemEventEmissionError,
    emit_system_event,
)
from utils.user_ids import require_user_id

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
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = require_user_id(current_user.get("sub"))
    result = boot_identity_context(user_id, db)

    try:
        emit_system_event(
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


@router.get("/")
async def get_identity(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get the current user's identity profile.
    """
    service = IdentityService(db=db, user_id=str(current_user.get("sub")))
    return service.get_profile()


@router.put("/")
async def update_identity(
    body: UpdateIdentityRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Explicitly update identity preferences.
    """
    service = IdentityService(db=db, user_id=str(current_user.get("sub")))
    return service.update_explicit(**body.model_dump(exclude_none=True))


@router.get("/evolution")
async def get_identity_evolution(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get the evolution history of the user's identity.
    """
    service = IdentityService(db=db, user_id=str(current_user.get("sub")))
    return service.get_evolution_summary()


@router.get("/context")
async def get_identity_context(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get the identity context string used in LLM prompts.
    """
    service = IdentityService(db=db, user_id=str(current_user.get("sub")))
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
