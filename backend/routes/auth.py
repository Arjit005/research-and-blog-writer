"""Authentication API endpoints (Email OTP & HttpOnly Session Management)."""

from __future__ import annotations

import os
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Response, Depends, HTTPException, status

import auth.service as auth_service
from backend.schemas import OTPRequest, OTPVerifyRequest, PasswordAuthRequest, AuthResponse, UserResponse
from backend.deps import get_current_user, get_token_from_request, security_bearer

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

IS_PROD = os.getenv("RENDER") or os.getenv("NODE_ENV") == "production"
COOKIE_NAME = "__Host-session_token" if IS_PROD else "session_token"
COOKIE_MAX_AGE = 7 * 24 * 3600  # 7 days


def _get_client_ip(request: Request) -> str:
    """Extract client IP respecting X-Forwarded-For proxies."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


@router.post("/login", response_model=AuthResponse)
def login_with_password_endpoint(body: PasswordAuthRequest, request: Request, response: Response) -> AuthResponse:
    """Authenticate or register user with Password (and optional OTP 2FA)."""
    client_ip = _get_client_ip(request)
    success, msg, session_token, user_data = auth_service.login_or_register_with_password(
        email=body.email,
        password=body.password,
        otp_code=body.otp_code,
        request_ip=client_ip,
    )

    if not success or not session_token or not user_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=msg)

    # Set hardened HttpOnly cookie
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=bool(IS_PROD),
        samesite="lax",
        path="/",
    )

    return AuthResponse(
        success=True,
        message=msg,
        user=UserResponse(id=user_data["id"], email=user_data["email"]),
        token=session_token,
    )


@router.post("/otp/request", response_model=AuthResponse)
def request_otp_endpoint(body: OTPRequest, request: Request) -> AuthResponse:
    """Request a single-use 6-digit verification code sent via email."""
    client_ip = _get_client_ip(request)
    success, msg, dev_code = auth_service.request_otp(email=body.email, request_ip=client_ip)

    if not success:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=msg)

    return AuthResponse(
        success=True,
        message=msg,
        dev_code=dev_code if os.getenv("AUTH_DEV_MODE", "").lower() in ("true", "1") else None,
    )


@router.post("/otp/verify", response_model=AuthResponse)
def verify_otp_endpoint(body: OTPVerifyRequest, request: Request, response: Response) -> AuthResponse:
    """Verify 6-digit OTP, authenticate user, and issue secure HttpOnly cookie."""
    client_ip = _get_client_ip(request)
    success, msg, session_token, user_data = auth_service.verify_otp_and_login(
        email=body.email,
        code=body.code,
        request_ip=client_ip,
    )

    if not success or not session_token or not user_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    # Set hardened HttpOnly cookie
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=bool(IS_PROD),
        samesite="lax",
        path="/",
    )

    return AuthResponse(
        success=True,
        message=msg,
        user=UserResponse(id=user_data["id"], email=user_data["email"]),
        token=session_token,
    )


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(user: Dict[str, Any] = Depends(get_current_user)) -> UserResponse:
    """Return currently authenticated user profile."""
    return UserResponse(id=user["id"], email=user["email"])


@router.post("/logout", response_model=AuthResponse)
def logout_endpoint(request: Request, response: Response) -> AuthResponse:
    """Revoke active session token and clear HttpOnly cookie."""
    token = get_token_from_request(request, None)
    if token:
        auth_service.logout_user(token)

    for name in [COOKIE_NAME, "session_token", "__Host-session_token"]:
        response.delete_cookie(name, path="/")

    return AuthResponse(success=True, message="Successfully logged out.")
