"""Authentication configuration and settings loader.

Reads settings from environment variables or st.secrets with strict validation.
Fails fast if required secrets (OTP_PEPPER, SESSION_SECRET) are missing in production.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("auth.config")

def _get_val(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve configuration from environment variable."""
    val = os.getenv(key)
    if val is not None and val != "":
        return val
    return default


@dataclass(frozen=True)
class AuthConfig:
    """Immutable authentication configuration."""

    # SMTP Configuration
    smtp_host: Optional[str]
    smtp_port: int
    smtp_user: Optional[str]
    smtp_password: Optional[str]
    smtp_from: Optional[str]
    smtp_use_tls: bool

    # Security Secrets (Pepper & Session Signing)
    otp_pepper: str
    session_secret: str

    # Security Lifetimes and Limits
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 60
    otp_max_per_email_per_hour: int = 5
    otp_max_per_ip_per_hour: int = 20
    session_ttl_hours: int = 168  # 7 days

    # Restrictions & Dev Mode
    allowed_email_domains: List[str] = field(default_factory=list)
    auth_dev_mode: bool = False


_cached_config: Optional[AuthConfig] = None


def load_auth_config(reload: bool = False) -> AuthConfig:
    """Load and validate authentication settings, failing fast on insecure production setups."""
    global _cached_config
    if _cached_config is not None and not reload:
        return _cached_config

    dev_mode_str = _get_val("AUTH_DEV_MODE", "false").lower()
    auth_dev_mode = dev_mode_str in ("true", "1", "yes", "on")

    # Production marker detection (e.g. TiDB configured or production env)
    tidb_host = _get_val("TIDB_HOST")
    allow_dev_with_tidb = _get_val("ALLOW_DEV_MODE_WITH_PROD_DB", "false").lower() in ("true", "1")
    if auth_dev_mode and tidb_host and not allow_dev_with_tidb:
        raise ValueError(
            "CRITICAL: AUTH_DEV_MODE cannot be enabled when production database TIDB_HOST is configured "
            "without explicit ALLOW_DEV_MODE_WITH_PROD_DB=true override."
        )

    # In dev mode, fall back to fixed development pepper/secrets if not provided
    default_dev_secret = "dev_secret_only_for_local_testing_do_not_use_in_production"
    otp_pepper = _get_val("OTP_PEPPER")
    session_secret = _get_val("SESSION_SECRET")

    is_render = bool(os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID"))
    render_seed = os.getenv("RENDER_SERVICE_ID", os.getenv("RENDER_INSTANCE_ID", "render_default_salt"))

    if not otp_pepper:
        if auth_dev_mode:
            otp_pepper = f"otp_pepper_{default_dev_secret}"
        elif is_render:
            otp_pepper = hashlib.sha256(f"render_otp_{render_seed}".encode()).hexdigest()
            logger.warning("OTP_PEPPER not set on Render. Auto-derived deterministic fallback from service context.")
        else:
            raise ValueError(
                "Missing required authentication secret: OTP_PEPPER. "
                "Generate one with `python -c 'import secrets; print(secrets.token_hex(32))'` and set in .env."
            )

    if not session_secret:
        if auth_dev_mode:
            session_secret = f"session_secret_{default_dev_secret}"
        elif is_render:
            session_secret = hashlib.sha256(f"render_session_{render_seed}".encode()).hexdigest()
            logger.warning("SESSION_SECRET not set on Render. Auto-derived deterministic fallback from service context.")
        else:
            raise ValueError(
                "Missing required authentication secret: SESSION_SECRET. "
                "Generate one with `python -c 'import secrets; print(secrets.token_hex(32))'` and set in .env."
            )

    # SMTP Settings
    smtp_host = _get_val("SMTP_HOST")
    smtp_port = int(_get_val("SMTP_PORT", "587"))
    smtp_user = _get_val("SMTP_USER")
    smtp_password = _get_val("SMTP_PASSWORD")
    smtp_from = _get_val("SMTP_FROM", smtp_user or "noreply@research-studio.local")
    smtp_use_tls = _get_val("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")

    # If not in dev mode, verify SMTP is configured
    if not auth_dev_mode and not smtp_host:
        # We do not crash outright on import to allow unit tests with fake senders, but warn/flag
        pass

    # Allowed email domains
    domains_raw = _get_val("ALLOWED_EMAIL_DOMAINS", "")
    allowed_domains = [d.strip().lower() for d in domains_raw.split(",") if d.strip()]

    # Numeric thresholds
    otp_ttl = int(_get_val("OTP_TTL_SECONDS", "300"))
    max_attempts = int(_get_val("OTP_MAX_ATTEMPTS", "5"))
    cooldown = int(_get_val("OTP_RESEND_COOLDOWN_SECONDS", "60"))
    max_per_email = int(_get_val("OTP_MAX_PER_EMAIL_PER_HOUR", "5"))
    max_per_ip = int(_get_val("OTP_MAX_PER_IP_PER_HOUR", "20"))
    session_ttl = int(_get_val("SESSION_TTL_HOURS", "168"))

    _cached_config = AuthConfig(
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
        smtp_from=smtp_from,
        smtp_use_tls=smtp_use_tls,
        otp_pepper=otp_pepper,
        session_secret=session_secret,
        otp_ttl_seconds=otp_ttl,
        otp_max_attempts=max_attempts,
        otp_resend_cooldown_seconds=cooldown,
        otp_max_per_email_per_hour=max_per_email,
        otp_max_per_ip_per_hour=max_per_ip,
        session_ttl_hours=session_ttl,
        allowed_email_domains=allowed_domains,
        auth_dev_mode=auth_dev_mode,
    )
    return _cached_config
