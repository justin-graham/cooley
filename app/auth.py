"""
Authentication utilities for user login and session management.
Uses session-based authentication with secure HttpOnly cookies.
"""

import os
from datetime import datetime, timedelta
from typing import Optional
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Simple session store (in-memory for MVP, use Redis for production)
sessions = {}  # {session_token: {user_id, expires_at}}
SESSION_EXPIRE_MINUTES = 60 * 24  # 24 hours

def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def create_session(user_id: str) -> str:
    """
    Create a session token for a user.

    Args:
        user_id: UUID string of the user

    Returns:
        Session token (UUID string)
    """
    import uuid
    session_token = str(uuid.uuid4())
    sessions[session_token] = {
        'user_id': user_id,
        'expires_at': datetime.now() + timedelta(minutes=SESSION_EXPIRE_MINUTES)
    }
    return session_token

def get_session(session_token: str) -> Optional[str]:
    """
    Get user_id from session token, or None if invalid/expired.

    Args:
        session_token: Session token string

    Returns:
        User ID if session is valid, None otherwise
    """
    session = sessions.get(session_token)
    if not session:
        return None

    # Check expiration
    if datetime.now() > session['expires_at']:
        del sessions[session_token]
        return None

    return session['user_id']

def delete_session(session_token: str) -> None:
    """Delete a session token."""
    sessions.pop(session_token, None)

def get_current_user(request: Request) -> str:
    """
    Dependency to get current authenticated user from session cookie.
    Raises HTTPException if not authenticated.

    Usage:
        @app.get("/protected")
        async def protected_route(user_id: str = Depends(get_current_user)):
            return {"user_id": user_id}

    Args:
        request: FastAPI request object

    Returns:
        User ID string

    Raises:
        HTTPException: 401 if not authenticated or session expired
    """
    session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    user_id = get_session(session_token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session"
        )

    return user_id

def get_current_user_optional(request: Request) -> Optional[str]:
    """
    Optional dependency to get current user. Returns None if not authenticated.

    Usage:
        @app.get("/")
        async def root(user_id: Optional[str] = Depends(get_current_user_optional)):
            if user_id:
                return {"message": "Authenticated"}
            else:
                return {"message": "Not authenticated"}

    Args:
        request: FastAPI request object

    Returns:
        User ID string if authenticated, None otherwise
    """
    session_token = request.cookies.get("session_token")
    if not session_token:
        return None
    return get_session(session_token)
