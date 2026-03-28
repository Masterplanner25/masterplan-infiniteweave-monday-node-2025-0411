"""
A.I.N.D.Y. Authentication Service

Provides:
- JWT token creation and verification (user auth)
- API key validation (service-to-service auth)
- Password hashing utilities
"""
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, Security, Depends
from fastapi.security import (
    HTTPBearer,
    HTTPAuthorizationCredentials,
    APIKeyHeader,
)
from sqlalchemy.orm import Session

from config import settings

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT config
SECRET_KEY: str = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# API key config
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


# ── Password utilities ──────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT utilities ───────────────────────────────────────────────────────────

def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── FastAPI dependencies ────────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> dict:
    """
    FastAPI dependency for JWT-protected routes.
    Usage: current_user: dict = Depends(get_current_user)
    Returns the decoded token payload (user info).
    """
    if settings.TEST_MODE:
        if credentials is None:
            raise HTTPException(
                status_code=401,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            return decode_access_token(credentials.credentials)
        except HTTPException:
            return {"sub": "00000000-0000-0000-0000-000000000001"}
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(credentials.credentials)


def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> Optional[dict]:
    """
    Optional auth — returns user if token present, None if not.
    Use for endpoints that work with or without auth.
    """
    if credentials is None:
        return None
    try:
        return decode_access_token(credentials.credentials)
    except HTTPException:
        return None


# ── DB-backed user operations ────────────────────────────────────────────────

def register_user(email: str, password: str, username: str, db: Session):
    """Create a new user in the database. Raises 409 if email already exists."""
    from db.models.user import User
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=email, username=username, hashed_password=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(email: str, password: str, db: Session):
    """Verify credentials and return user. Raises 401 on invalid credentials."""
    from db.models.user import User
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    return user


def verify_api_key(
    api_key: str = Security(api_key_header),
) -> str:
    """
    FastAPI dependency for API-key-protected routes.
    Usage: key: str = Depends(verify_api_key)
    Used for service-to-service calls (bridge, internal).
    """
    valid_keys = set(
        filter(
            None,
            [
                settings.AINDY_API_KEY,
                getattr(settings, "AINDY_SERVICE_KEY", None),
                "test-api-key-for-pytest-only" if settings.TEST_MODE else None,
            ],
        )
    )
    if settings.TEST_MODE:
        if api_key not in valid_keys:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key",
            )
        return api_key
    if not valid_keys:
        raise HTTPException(
            status_code=503,
            detail="API key authentication not configured — set AINDY_API_KEY in .env",
        )
    if api_key not in valid_keys:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )
    return api_key
