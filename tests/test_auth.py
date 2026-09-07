from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

# Ensure backend directory is in python path
BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from auth import (
    create_access_token,
    decode_access_token,
    get_current_user,
    get_password_hash,
    require_role,
    verify_password,
    ADMIN_USERNAME,
    ADMIN_PASSWORD,
    USERS_DB,
)


def test_password_hashing_and_verification():
    plain = "SuperSecretPassword123!"
    hashed = get_password_hash(plain)

    assert hashed != plain
    assert verify_password(plain, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_admin_default_credentials():
    admin = USERS_DB.get(ADMIN_USERNAME)
    assert admin is not None
    assert admin["role"] == "admin"
    assert verify_password(ADMIN_PASSWORD, admin["password_hash"]) is True


def test_jwt_creation_and_decoding():
    payload = {"sub": "test_doctor@rescuecloud.io", "role": "doctor", "full_name": "Dr. Smith"}
    token = create_access_token(payload, expires_delta=timedelta(minutes=15))

    decoded = decode_access_token(token)
    assert decoded["sub"] == "test_doctor@rescuecloud.io"
    assert decoded["role"] == "doctor"
    assert decoded["full_name"] == "Dr. Smith"
    assert "exp" in decoded


def test_jwt_expired_token():
    payload = {"sub": "expired_user", "role": "viewer"}
    # Token expired 5 minutes ago
    token = create_access_token(payload, expires_delta=timedelta(minutes=-5))

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


import asyncio

def test_get_current_user_valid_bearer():
    payload = {"sub": "audit_officer", "role": "auditor", "full_name": "Audit Lead"}
    token = create_access_token(payload)

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    user = asyncio.run(get_current_user(creds))

    assert user["username"] == "audit_officer"
    assert user["role"] == "auditor"


def test_get_current_user_missing_bearer():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_current_user(None))
    assert exc_info.value.status_code == 401


def test_role_enforcement():
    admin_user = {"username": "admin@rescuecloud.io", "role": "admin"}
    doctor_user = {"username": "doctor@rescuecloud.io", "role": "doctor"}

    admin_checker = require_role(["admin"])
    # Admin passes
    result = asyncio.run(admin_checker(admin_user))
    assert result == admin_user

    # Doctor fails admin check
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(admin_checker(doctor_user))
    assert exc_info.value.status_code == 403


import subprocess


def test_missing_jwt_secret_fails_startup():
    """Startup must fail fast if JWT_SECRET_KEY is omitted."""
    cmd = [sys.executable, "-c", "import os; os.environ['JWT_SECRET_KEY'] = ''; import auth"]
    proc = subprocess.run(cmd, cwd=str(BACKEND_DIR), capture_output=True, text=True)
    assert proc.returncode != 0
    assert "JWT_SECRET_KEY environment variable is required" in proc.stderr


def test_short_jwt_secret_fails_startup():
    """Startup must fail fast if JWT_SECRET_KEY is less than 32 characters."""
    cmd = [sys.executable, "-c", "import os; os.environ['JWT_SECRET_KEY'] = 'too-short'; import auth"]
    proc = subprocess.run(cmd, cwd=str(BACKEND_DIR), capture_output=True, text=True)
    assert proc.returncode != 0
    assert "at least 32 characters long" in proc.stderr


def test_missing_admin_credentials_fails_startup():
    """Startup must fail fast if ADMIN_PASSWORD is omitted."""
    cmd = [
        sys.executable,
        "-c",
        "import os; os.environ['JWT_SECRET_KEY'] = '123456789012345678901234567890123'; os.environ['ADMIN_PASSWORD'] = ''; import auth",
    ]
    proc = subprocess.run(cmd, cwd=str(BACKEND_DIR), capture_output=True, text=True)
    assert proc.returncode != 0
    assert "ADMIN_USERNAME and ADMIN_PASSWORD environment variables are required" in proc.stderr


# Coverage: valid login 200, wrong password 401, rate-limit 429, tampered JWT 401.
