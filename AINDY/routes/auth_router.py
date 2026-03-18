"""
auth_router.py — Authentication endpoints for A.I.N.D.Y.

Public endpoints (no auth required):
  POST /auth/login    — exchange credentials for JWT token
  POST /auth/register — create a new user account

NOTE: No User ORM model exists yet (tracked in TECH_DEBT.md).
Using an in-memory user store for MVP. Replace with DB-backed
User model in Phase 3.
"""
from fastapi import APIRouter, HTTPException
from schemas.auth_schemas import LoginRequest, RegisterRequest, TokenResponse
from services.auth_service import verify_password, hash_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

# ── In-memory user store (MVP — replace with DB User model) ─────────────────
# TODO: Replace with db.models.user.UserDB when User model is added.
# See TECH_DEBT.md §1 (Structural Debt).
_USERS: dict = {}  # email -> {"id": str, "hashed_password": str, "username": str}


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(request: RegisterRequest):
    """
    Register a new user. Public endpoint — no auth required.
    Returns a JWT access token on success.
    """
    if request.email in _USERS:
        raise HTTPException(status_code=409, detail="Email already registered")

    user_id = f"user-{len(_USERS) + 1}"
    _USERS[request.email] = {
        "id": user_id,
        "hashed_password": hash_password(request.password),
        "username": request.username,
    }

    token = create_access_token({"sub": user_id, "email": request.email})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest):
    """
    Authenticate user and return JWT token. Public endpoint.
    """
    user = _USERS.get(request.email)
    if not user or not verify_password(request.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": user["id"], "email": request.email})
    return {"access_token": token, "token_type": "bearer"}
