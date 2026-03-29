"""
auth_router.py — Authentication endpoints for A.I.N.D.Y.

Public endpoints (no auth required):
  POST /auth/login    — exchange credentials for JWT token
  POST /auth/register — create a new user account

Phase 3: Uses PostgreSQL User model via DB session (replaced in-memory store).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.database import get_db
from schemas.auth_schemas import LoginRequest, RegisterRequest, TokenResponse
from services.auth_service import create_access_token, register_user, authenticate_user
from services.signup_initialization_service import initialize_signup_state
from services.system_event_service import emit_system_event

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """
    Register a new user. Public endpoint — no auth required.
    Returns a JWT access token on success.
    """
    user = register_user(
        email=request.email,
        password=request.password,
        username=request.username,
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


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate user and return JWT token. Public endpoint.
    """
    user = authenticate_user(email=request.email, password=request.password, db=db)
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
