"""FastAPI dependencies for authentication, multi-tenancy, and database access."""

from __future__ import annotations

import os
from typing import Dict, Any, Optional
from fastapi import Request, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import auth.service as auth_service

security_bearer = HTTPBearer(auto_error=False)

COOKIE_NAMES = ["__Host-session_token", "session_token"]


def get_token_from_request(request: Request, bearer: Optional[HTTPAuthorizationCredentials]) -> Optional[str]:
    """Extract session token from Authorization Bearer header, custom header, or HttpOnly cookie."""
    # 1. Check Authorization Bearer header (explicit credentials take precedence)
    if bearer and bearer.credentials:
        return bearer.credentials

    # 2. Check custom header (common in API proxies)
    custom_hdr = request.headers.get("x-session-token")
    if custom_hdr:
        return custom_hdr

    # 3. Check cookies (ambient session cookie)
    for name in COOKIE_NAMES:
        token = request.cookies.get(name)
        if token:
            return token

    return None


async def get_current_user_optional(
    request: Request,
    bearer: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
) -> Optional[Dict[str, Any]]:
    """Retrieve current authenticated user if token present, or None without throwing."""
    token = get_token_from_request(request, bearer)
    if not token:
        return None

    user_data = auth_service.validate_session(token)
    if user_data:
        return user_data
    return None


async def get_current_user(
    request: Request,
    bearer: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
) -> Dict[str, Any]:
    """Require valid authenticated user; raises 401 if missing or invalid."""
    user = await get_current_user_optional(request, bearer)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in with your email verification code.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
