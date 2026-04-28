"""
auth_router.py — Authentication endpoints for A.I.N.D.Y.

Public endpoints (no auth required):
  POST /auth/login    — exchange credentials for JWT token
  POST /auth/register — create a new user account

Phase 3: Uses PostgreSQL User model via DB session (replaced in-memory store).
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from AINDY.core.execution_signal_helper import queue_system_event
from sqlalchemy.orm import Session
from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.platform_layer.user_ids import parse_user_id
from AINDY.schemas.auth_schemas import LoginRequest, RegisterRequest, TokenResponse
from AINDY.services.auth_service import (
    authenticate_user,
    create_access_token,
    get_current_user,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])
emit_system_event = queue_system_event
initialize_signup_state = None


@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("10/minute")
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
        token = create_access_token(
            {"sub": str(user.id), "email": user.email, "is_admin": bool(getattr(user, "is_admin", False))},
            token_version=int(getattr(user, "token_version", 0)),
        )
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
@limiter.limit("10/minute")
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
        token = create_access_token(
            {"sub": str(user.id), "email": user.email, "is_admin": bool(getattr(user, "is_admin", False))},
            token_version=int(getattr(user, "token_version", 0)),
        )
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


@router.post("/logout", status_code=200)
@limiter.limit("10/minute")
def logout(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        from AINDY.db.models.user import User

        if current_user.get("auth_type") == "api_key":
            raise HTTPException(status_code=401, detail="Bearer token required")

        user_id = parse_user_id(current_user["sub"])
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.token_version = (int(getattr(user, "token_version", 0)) + 1) % 32767
                db.commit()
        return {"status": "logged_out"}

    return execute_with_pipeline_sync(
        request=request,
        route_name="auth.logout",
        handler=handler,
        user_id=str(current_user["sub"]),
        metadata={"db": db},
    )


@router.post("/admin/invalidate-sessions/{user_id}")
@limiter.limit("20/minute")
def admin_invalidate_sessions(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        from AINDY.db.models.user import User

        if current_user.get("auth_type") == "api_key":
            scopes = set(current_user.get("api_key_scopes") or [])
            if "platform.admin" not in scopes:
                raise HTTPException(status_code=403, detail="Admin required")
        elif not current_user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin required")

        target_id = parse_user_id(user_id)
        if not target_id:
            raise HTTPException(status_code=400, detail="Invalid user_id")

        user = db.query(User).filter(User.id == target_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.token_version = (int(getattr(user, "token_version", 0)) + 1) % 32767
        db.commit()
        return {"status": "sessions_invalidated", "user_id": str(target_id)}

    return execute_with_pipeline_sync(
        request=request,
        route_name="auth.admin.invalidate_sessions",
        handler=handler,
        user_id=str(current_user["sub"]),
        metadata={"db": db},
        input_payload={"user_id": user_id},
    )

