"""
A.I.N.D.Y. Authentication Service

Provides:
- JWT token creation and verification (user auth)
- API key validation (service-to-service auth)
- Password hashing utilities
"""
import os
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, Security, Depends
from fastapi.security import (
    HTTPBearer,
    HTTPAuthorizationCredentials,
    APIKeyHeader,
)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT config — read at import time (env is set by conftest before import)
SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
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


def verify_api_key(
    api_key: str = Security(api_key_header),
) -> str:
    """
    FastAPI dependency for API-key-protected routes.
    Usage: key: str = Depends(verify_api_key)
    Used for service-to-service calls (bridge, internal).
    """
    valid_keys = set(filter(None, [
        os.getenv("AINDY_API_KEY"),
        os.getenv("AINDY_SERVICE_KEY"),
    ]))
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
