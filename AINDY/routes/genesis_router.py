import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from services.auth_service import get_current_user
from services.flow_engine import run_flow
from services.rate_limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/genesis", tags=["Genesis"])


def _genesis_run_flow(flow_name: str, payload: dict, db, user_id: str):
    """Run a genesis flow, decoding HTTP errors from node results."""
    result = run_flow(flow_name, payload, db=db, user_id=user_id)
    data = result.get("data")

    if isinstance(data, dict) and data.get("_http_status") == 202:
        return JSONResponse(status_code=202, content=data.get("_http_response", {}))

    if result.get("status") == "FAILED":
        error = result.get("error", "")
        if error.startswith("HTTP_"):
            parts = error.split(":", 1)
            code = int(parts[0].replace("HTTP_", ""))
            msg = parts[1] if len(parts) > 1 else error
            raise HTTPException(status_code=code, detail={"error": f"genesis_{flow_name}_failed", "message": msg})
        raise HTTPException(status_code=500, detail=f"{flow_name} failed")

    return data


@router.post("/session")
def create_genesis_session(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return _genesis_run_flow("genesis_session_create", {}, db, user_id)


@router.post("/message")
@limiter.limit("20/minute")
def genesis_message(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    session_id = payload.get("session_id")
    user_message = payload.get("message")

    if not session_id:
        raise HTTPException(status_code=400, detail={"error": "session_id_required", "message": "session_id is required"})
    if not user_message:
        raise HTTPException(status_code=400, detail={"error": "message_required", "message": "message is required"})

    result = run_flow("genesis_message", {"session_id": session_id, "message": user_message}, db=db, user_id=user_id)
    if result.get("status") != "SUCCESS":
        raise HTTPException(status_code=500, detail="Genesis message execution failed")
    return result


@router.get("/session/{session_id}")
def get_genesis_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return _genesis_run_flow("genesis_session_get", {"session_id": session_id}, db, str(current_user["sub"]))


@router.get("/draft/{session_id}")
def get_genesis_draft(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return _genesis_run_flow("genesis_draft_get", {"session_id": session_id}, db, str(current_user["sub"]))


@router.post("/synthesize")
@limiter.limit("5/minute")
def synthesize_genesis(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail={"error": "session_id_required", "message": "session_id required"})
    return _genesis_run_flow("genesis_synthesize", {"session_id": session_id}, db, str(current_user["sub"]))


class AuditRequest(BaseModel):
    session_id: int


@router.post("/audit")
@limiter.limit("5/minute")
def audit_genesis_draft(
    request: Request,
    body: AuditRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Run a strategic integrity audit on the persisted draft for a genesis session."""
    return _genesis_run_flow("genesis_audit", {"session_id": body.session_id}, db, str(current_user["sub"]))


@router.post("/lock")
def lock_masterplan(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    session_id = payload.get("session_id")
    draft = payload.get("draft")
    if not session_id or not draft:
        raise HTTPException(status_code=400, detail={"error": "missing_session_or_draft", "message": "Missing session or draft"})
    return _genesis_run_flow("genesis_lock", {"session_id": session_id, "draft": draft}, db, str(current_user["sub"]))


@router.post("/{plan_id}/activate")
def activate_masterplan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return _genesis_run_flow("genesis_activate", {"plan_id": plan_id}, db, str(current_user["sub"]))
