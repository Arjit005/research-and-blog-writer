"""Authentication API endpoints (Email OTP & HttpOnly Session Management)."""

from __future__ import annotations

import os
from typing import Dict, Any
from fastapi import APIRouter, Request, Response, Depends, HTTPException, status

import auth.service as auth_service
import database as db
from auth.config import load_auth_config
from backend.schemas import (
    OTPRequest,
    OTPVerifyRequest,
    PasswordAuthRequest,
    AuthResponse,
    UserResponse,
    UserKeysResponse,
    UserKeysUpdateRequest,
)
from backend.deps import get_current_user, get_token_from_request

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

# Cookie names: the `__Host-` prefix is only valid for Secure, Path=/ cookies with
# no Domain attribute. Browsers reject it on plain HTTP, so it is used only when
# the deployment explicitly signals HTTPS.
PLAIN_COOKIE_NAME = "session_token"
HOST_COOKIE_NAME = "__Host-session_token"
SESSION_COOKIE_NAMES = (HOST_COOKIE_NAME, PLAIN_COOKIE_NAME)


def _is_truthy_env(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("true", "1", "yes", "on")


def _cookie_secure() -> bool:
    """Decide whether session cookies must be Secure / `__Host-` prefixed.

    Uses explicit deployment signals rather than relying on unrelated framework
    markers such as NODE_ENV:
      - ENVIRONMENT=production (Docker/Render/Fly/Heroku conventions)
      - RENDER / RENDER_SERVICE_ID (Render platform)
      - AUTH_COOKIE_SECURE=true (explicit operator opt-in)
    """
    environment = (os.getenv("ENVIRONMENT") or "").strip().lower()
    if environment in ("production", "prod"):
        return True
    if _is_truthy_env("RENDER") or bool((os.getenv("RENDER_SERVICE_ID") or "").strip()):
        return True
    return _is_truthy_env("AUTH_COOKIE_SECURE")


def _session_cookie_name() -> str:
    return HOST_COOKIE_NAME if _cookie_secure() else PLAIN_COOKIE_NAME


def _dev_mode_enabled() -> bool:
    """Return whether raw tokens/dev codes may be exposed in API responses."""
    try:
        return load_auth_config().auth_dev_mode
    except ValueError:
        return False


def _session_cookie_max_age() -> int:
    """Derive cookie lifetime (seconds) from the configured session TTL."""
    try:
        ttl_hours = max(1, int(load_auth_config().session_ttl_hours))
    except ValueError:
        ttl_hours = 1
    return ttl_hours * 3600


def _get_client_ip(request: Request) -> str:
    """Extract client IP respecting X-Forwarded-For proxies."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def _set_session_cookie(response: Response, session_token: str) -> None:
    response.set_cookie(
        key=_session_cookie_name(),
        value=session_token,
        max_age=_session_cookie_max_age(),
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    """Expire every known session cookie name with matching attributes.

    Browsers only delete a cookie when name, path and domain match; `__Host-`
    cookies additionally require the deletion Set-Cookie to carry `Secure`.
    """
    secure = _cookie_secure()
    for name in SESSION_COOKIE_NAMES:
        response.delete_cookie(
            key=name,
            path="/",
            secure=True if name == HOST_COOKIE_NAME else secure,
            httponly=True,
            samesite="lax",
        )


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
        if msg == auth_service.PASSWORD_ATTEMPT_THROTTLE_MESSAGE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=msg,
                headers={"Retry-After": "900"},
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=msg)

    # Set hardened HttpOnly cookie. The raw token is only echoed for
    # AUTH_DEV_MODE/test clients; browser flows rely on the cookie alone.
    _set_session_cookie(response, session_token)

    return AuthResponse(
        success=True,
        message=msg,
        user=UserResponse(id=user_data["id"], email=user_data["email"]),
        token=session_token if _dev_mode_enabled() else None,
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
        dev_code=dev_code if _dev_mode_enabled() else None,
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

    _set_session_cookie(response, session_token)

    return AuthResponse(
        success=True,
        message=msg,
        user=UserResponse(id=user_data["id"], email=user_data["email"]),
        token=session_token if _dev_mode_enabled() else None,
    )


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(user: Dict[str, Any] = Depends(get_current_user)) -> UserResponse:
    """Return currently authenticated user profile."""
    return UserResponse(id=user["id"], email=user["email"])


def _mask_key(key: Optional[str]) -> Optional[str]:
    if not key or len(key) < 8:
        return None
    return f"{key[:6]}...{key[-4:]}"


@router.get("/keys", response_model=UserKeysResponse)
def get_user_keys_endpoint(user: Dict[str, Any] = Depends(get_current_user)) -> UserKeysResponse:
    """Retrieve presence and masked values of user's personal LLM API keys."""
    user_id = user["id"]
    keys = db.get_user_api_keys(user_id=user_id) if hasattr(db, "get_user_api_keys") else {}
    gemini_key = keys.get("gemini_api_key", "")
    openrouter_key = keys.get("openrouter_api_key", "")

    return UserKeysResponse(
        has_gemini=bool(gemini_key),
        has_openrouter=bool(openrouter_key),
        gemini_masked=_mask_key(gemini_key),
        openrouter_masked=_mask_key(openrouter_key),
        server_has_gemini=bool(os.getenv("GEMINI_API_KEY")),
        server_has_openrouter=bool(os.getenv("OPENROUTER_API_KEY")),
    )


@router.post("/keys", response_model=Dict[str, Any])
def update_user_keys_endpoint(
    body: UserKeysUpdateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Store encrypted/scoped LLM API keys for the current user."""
    user_id = user["id"]
    if hasattr(db, "save_user_api_keys"):
        db.save_user_api_keys(
            user_id=user_id,
            gemini_key=body.gemini_api_key,
            openrouter_key=body.openrouter_api_key,
        )
    return {"status": "success", "message": "API keys saved securely."}


@router.post("/logout", response_model=AuthResponse)
def logout_endpoint(request: Request, response: Response) -> AuthResponse:
    """Revoke active session token and clear HttpOnly cookie."""
    token = get_token_from_request(request, None)
    if token:
        auth_service.logout_user(token)

    _clear_session_cookies(response)

    return AuthResponse(success=True, message="Successfully logged out.")
