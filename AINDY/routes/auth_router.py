"""
auth_router.py — Authentication endpoints for A.I.N.D.Y.

Public endpoints (no auth required):
  POST /auth/login    — exchange credentials for JWT token
  POST /auth/register — create a new user account

Phase 3: Uses PostgreSQL User model via DB session (replaced in-memory store).
"""
from fastapi import APIRouter, Depends, Request
from AINDY.core.execution_signal_helper import queue_system_event
from sqlalchemy.orm import Session
from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from AINDY.schemas.auth_schemas import LoginRequest, RegisterRequest, TokenResponse
from AINDY.services.auth_service import create_access_token, register_user, authenticate_user
from AINDY.domain.signup_initialization_service import initialize_signup_state

router = APIRouter(prefix="/auth", tags=["auth"])
emit_system_event = queue_system_event


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(
    body: RegisterRequest,
    db: Session = Depends(get_db),
    request: Request = None,
):
    """
    Register a new user. Public endpoint — no auth required.
    Returns a JWT access token on success.
    """
    def handler(ctx):
        user = register_user(
            email=body.email,
            password=body.password,
            username=body.username,
            db=db,
        )
        initialize_signup_state(db=db, user=user)
        emit_system_event(
            db=db,
            event_type="auth.register.completed",
            user_id=user.id,
            payload={
                "email": user.email,
                "username": user.username,
            },
            required=True,
        )
        token = create_access_token({"sub": str(user.id), "email": user.email})
        return {"access_token": token, "token_type": "bearer"}

    if request is None:
        return handler(None)

    return execute_with_pipeline_sync(
        request=request,
        route_name="auth.register",
        handler=handler,
        metadata={"db": db},
        input_payload=body.model_dump(),
        success_status_code=201,
    )


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    db: Session = Depends(get_db),
    request: Request = None,
):
    """
    Authenticate user and return JWT token. Public endpoint.
    """
    def handler(ctx):
        user = authenticate_user(email=body.email, password=body.password, db=db)
        emit_system_event(
            db=db,
            event_type="auth.login.completed",
            user_id=user.id,
            payload={
                "email": user.email,
            },
            required=True,
        )
        token = create_access_token({"sub": str(user.id), "email": user.email})
        return {"access_token": token, "token_type": "bearer"}

    if request is None:
        return handler(None)

    return execute_with_pipeline_sync(
        request=request,
        route_name="auth.login",
        handler=handler,
        metadata={"db": db},
        input_payload=body.model_dump(),
    )

