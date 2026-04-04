"""
auth_router.py — Authentication endpoints for A.I.N.D.Y.

Public endpoints (no auth required):
  POST /auth/login    — exchange credentials for JWT token
  POST /auth/register — create a new user account

Phase 3: Uses PostgreSQL User model via DB session (replaced in-memory store).
"""
from fastapi import APIRouter, Depends, Request
from core.execution_signal_helper import queue_system_event
from sqlalchemy.orm import Session
from core.execution_helper import execute_with_pipeline
from db.database import get_db
from schemas.auth_schemas import LoginRequest, RegisterRequest, TokenResponse
from services.auth_service import create_access_token, register_user, authenticate_user
from domain.signup_initialization_service import initialize_signup_state

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    request: Request,
    body: RegisterRequest,
    db: Session = Depends(get_db),
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
        queue_system_event(
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

    return await execute_with_pipeline(
        request=request,
        route_name="auth.register",
        handler=handler,
        metadata={"db": db},
        input_payload=body.model_dump(),
        success_status_code=201,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    body: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    Authenticate user and return JWT token. Public endpoint.
    """
    def handler(ctx):
        user = authenticate_user(email=body.email, password=body.password, db=db)
        queue_system_event(
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

    return await execute_with_pipeline(
        request=request,
        route_name="auth.login",
        handler=handler,
        metadata={"db": db},
        input_payload=body.model_dump(),
    )

