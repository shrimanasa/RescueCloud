"""RescueCloud Authentication & Authorization Module.

Implements JWT Bearer token generation, verification, bcrypt password hashing,
and FastAPI role-based access control (RBAC).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from pathlib import Path
from dotenv import load_dotenv

# Automatically load environment variables from .env if present
load_dotenv()
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Cryptographic & token configurations (REQUIRED in production)
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "FATAL: JWT_SECRET_KEY environment variable is required and cannot be empty. "
        "Define JWT_SECRET_KEY in your environment or .env file (minimum 32 characters)."
    )
if len(SECRET_KEY) < 32:
    raise RuntimeError(
        "FATAL: JWT_SECRET_KEY must be at least 32 characters long for cryptographic security."
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))

# Administrative user credentials (REQUIRED in production)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

if not ADMIN_USERNAME or not ADMIN_PASSWORD:
    raise RuntimeError(
        "FATAL: ADMIN_USERNAME and ADMIN_PASSWORD environment variables are required. "
        "Define ADMIN_USERNAME and ADMIN_PASSWORD in your environment or .env file. "
        "No hardcoded administrative fallback credentials are permitted in production."
    )

# Pre-hashed administrative password
_DEFAULT_ADMIN_HASH = bcrypt.hashpw(ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

# In-memory user store
USERS_DB: Dict[str, Dict[str, Any]] = {
    ADMIN_USERNAME: {
        "username": ADMIN_USERNAME,
        "password_hash": _DEFAULT_ADMIN_HASH,
        "role": "admin",
        "full_name": os.getenv("ADMIN_FULL_NAME", "SOC Administrator"),
    },
}

# Optional clinical doctor credentials loaded strictly from environment if configured
DOCTOR_USERNAME = os.getenv("DOCTOR_USERNAME")
DOCTOR_PASSWORD = os.getenv("DOCTOR_PASSWORD")
if DOCTOR_USERNAME and DOCTOR_PASSWORD:
    USERS_DB[DOCTOR_USERNAME] = {
        "username": DOCTOR_USERNAME,
        "password_hash": bcrypt.hashpw(DOCTOR_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
        "role": "doctor",
        "full_name": os.getenv("DOCTOR_FULL_NAME", "Chief Medical Officer"),
    }

security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Generate a bcrypt salt and hash for a password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create and sign a JWT access token with an expiration timestamp."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)]
) -> dict:
    """FastAPI dependency to extract and verify the current authenticated user from Bearer header."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Missing Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_access_token(token)
    username: Optional[str] = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role: str = payload.get("role", "viewer")
    return {
        "username": username,
        "role": role,
        "full_name": payload.get("full_name", username),
    }


def require_role(allowed_roles: List[str]):
    """FastAPI dependency factory enforcing role-based access control."""
    async def role_checker(current_user: Annotated[dict, Depends(get_current_user)]) -> dict:
        user_role = current_user.get("role", "viewer")
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required one of: {allowed_roles}, got: '{user_role}'.",
            )
        return current_user

    return role_checker


# Token and password policy
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
MIN_PASSWORD_LENGTH: int = 12
BCRYPT_ROUNDS: int = 12  # OWASP rec: 10+. Each extra round adds ~100ms per login.

# Note: increasing BCRYPT_ROUNDS above 12 adds ~100ms per login per extra round.
# Profile against your expected concurrent login volume before increasing.
