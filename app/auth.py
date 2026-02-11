"""
Authentication utilities for user login and session management.
Uses DB-backed session cookies with CSRF protection.
"""

import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, status, Request
from passlib.context import CryptContext
from app import db

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SESSION_EXPIRE_MINUTES = int(os.getenv("SESSION_EXPIRE_MINUTES", "1440"))  # 24 hours


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_session(user_id: str) -> tuple[str, str]:
    """
    Create a durable DB-backed session.

    Returns:
        (session_token, csrf_token)
    """
    session_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=SESSION_EXPIRE_MINUTES)
    db.create_session(session_token, user_id, expires_at, csrf_token)
    return session_token, csrf_token


def get_session(session_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch active session data from DB.
    """
    if not session_token:
        return None
    return db.get_session(session_token)


def delete_session(session_token: str) -> None:
    """Delete a session token from DB."""
    if session_token:
        db.delete_session(session_token)


def get_current_user(request: Request) -> str:
    """
    Dependency to get current authenticated user from session cookie.
    Raises HTTPException if not authenticated.
    """
    session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    session = get_session(session_token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session"
        )

    return str(session["user_id"])


def get_current_user_optional(request: Request) -> Optional[str]:
    """
    Optional dependency to get current user. Returns None if not authenticated.
    """
    session_token = request.cookies.get("session_token")
    if not session_token:
        return None
    session = get_session(session_token)
    return str(session["user_id"]) if session else None


def validate_csrf(request: Request) -> None:
    """
    Validate CSRF token for cookie-authenticated mutating requests.
    Uses double-submit cookie pattern with server-side session validation.
    """
    session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    session = get_session(session_token)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

    csrf_header = request.headers.get("X-CSRF-Token")
    csrf_cookie = request.cookies.get("csrf_token")
    expected = session.get("csrf_token")

    if not csrf_header or not csrf_cookie or not expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing")

    if csrf_header != csrf_cookie or csrf_header != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
