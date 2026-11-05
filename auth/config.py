"""Authentication configuration and settings loader.

Reads settings from environment variables with strict validation.
Fails fast if required secrets (OTP_PEPPER, SESSION_SECRET) are missing outside of
explicit local development mode. There are deliberately NO derived/fallback
production secrets: deterministic secrets derived from public deployment context
(e.g. a Render service id) would let anyone forge OTPs or session tokens.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# Fixed, clearly-named secrets used ONLY when AUTH_DEV_MODE=true and the operator
# has not provided real values. They are public knowledge and must never be used
# to protect production data.
DEV_OTP_PEPPER = "dev_mode_otp_pepper_only_for_local_testing_do_not_use_in_production"
DEV_SESSION_SECRET = "dev_mode_session_secret_only_for_local_testing_do_not_use_in_production"


def _get_val(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve configuration from environment variable."""
    val = os.getenv(key)
    if val is not None and val != "":
        return val
    return default


def _is_truthy(value: Optional[str]) -> bool:
    """Interpret common truthy environment variable spellings."""
    return (value or "").strip().lower() in ("true", "1", "yes", "on")


def _secret_generation_hint(name: str) -> str:
    return (
        f"Missing required authentication secret: {name}. "
        "Generate one with `python -c 'import secrets; print(secrets.token_hex(32))'` and set it in .env. "
        "Set AUTH_DEV_MODE=true only for local development."
    )


@dataclass(frozen=True)
class AuthConfig:
    """Immutable authentication configuration."""

    # Brevo HTTP API & Email Configuration
    brevo_api_key: Optional[str]
    email_sender_name: str
    email_sender_address: str
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
    firebase_project_id: str = "loyal-synthesis-477817-e7"


def get_auth_config() -> AuthConfig:
    """Convenience accessor for the AuthConfig instance returned by load_auth_config()."""
    return load_auth_config()


_cached_config: Optional[AuthConfig] = None


def load_auth_config(reload: bool = False) -> AuthConfig:
    """Load and validate authentication settings, failing fast on insecure production setups."""
    global _cached_config
    if _cached_config is not None and not reload:
        return _cached_config

    # DEV MODE: Enabled only by explicit AUTH_DEV_MODE=true.
    # Legacy environments (ENVIRONMENT not set, or ENVIRONMENT=production/render) do NOT auto-enable
    # dev mode. This prevents accidental production deployments from activating insecure OTP
    # responses and plaintext cookies.
    auth_dev_mode = _is_truthy(_get_val("AUTH_DEV_MODE"))

    # Production marker detection:
    # A TiDB database is only usable when BOTH the host and a user are configured.
    # A host alone (e.g., a partially-filled local .env) is not a production database and must not block local dev mode.
    tidb_host = _get_val("TIDB_HOST")
    tidb_user = _get_val("TIDB_USER")
    allow_dev_with_prod_db = _is_truthy(_get_val("ALLOW_DEV_MODE_WITH_PROD_DB", "false"))
    if auth_dev_mode and tidb_host and tidb_user and not allow_dev_with_prod_db:
        raise ValueError(
            "CRITICAL: AUTH_DEV_MODE cannot be enabled when a production database is configured "
            "(TIDB_HOST and TIDB_USER are both set) without the explicit "
            "ALLOW_DEV_MODE_WITH_PROD_DB=true override."
        )

    # ------------------------------------------------------------------------
    # Authentication Secret Resolution (default to DEV fallbacks ONLY when dev mode is explicitly on)
    # ------------------------------------------------------------------------
    if auth_dev_mode:
        # Explicitly safe defaults for LOCAL DEVELOPMENT only
        otp_pepper = _get_val("OTP_PEPPER", DEV_OTP_PEPPER)
        session_secret = _get_val("SESSION_SECRET", DEV_SESSION_SECRET)
        if not _get_val("OTP_PEPPER"):
            logger.warning(
                "OTP_PEPPER not provided; using DEV_OTP_PEPPER for dev-only usage. "
                "Remove AUTH_DEV_MODE or set a proper OTP_PEPPER secret for production."
            )
        if not _get_val("SESSION_SECRET"):
            logger.warning(
                "SESSION_SECRET not provided; using DEV_SESSION_SECRET for dev-only usage. "
                "Remove AUTH_DEV_MODE or set a proper SESSION_SECRET secret for production."
            )
    else:
        # STRICT PRODUCTION: real secrets are required
        otp_pepper = _get_val("OTP_PEPPER")
        session_secret = _get_val("SESSION_SECRET")

        if not otp_pepper:
            raise ValueError(_secret_generation_hint("OTP_PEPPER"))

        if not session_secret:
            raise ValueError(_secret_generation_hint("SESSION_SECRET"))

    # ------------------------------------------------------------------------
    # Rest of config (identical to original, except the literal "true" above)
    # ------------------------------------------------------------------------
    # Brevo HTTP API & Sender Settings
    brevo_api_key = _get_val("BREVO_API_KEY")
    email_sender_name = _get_val("BREVO_SENDER_NAME", _get_val("EMAIL_SENDER_NAME", "Research & Blog Writer"))
    email_sender_address = _get_val(
        "BREVO_SENDER_EMAIL",
        _get_val("EMAIL_SENDER_ADDRESS", _get_val("SMTP_FROM", "arjit04554@gmail.com"))
    )

    # Legacy SMTP Settings (fallback if Brevo API key is not configured)
    smtp_host = _get_val("SMTP_HOST")
    smtp_port = int(_get_val("SMTP_PORT", "587"))
    smtp_user = _get_val("SMTP_USER")
    smtp_password = _get_val("SMTP_PASSWORD")
    smtp_from = _get_val("SMTP_FROM", email_sender_address)
    smtp_use_tls = _is_truthy(_get_val("SMTP_USE_TLS", "true"))

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

    firebase_project_id = _get_val("FIREBASE_PROJECT_ID", "loyal-synthesis-477817-e7").strip()

    _cached_config = AuthConfig(
        brevo_api_key=brevo_api_key,
        email_sender_name=email_sender_name,
        email_sender_address=email_sender_address,
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
        firebase_project_id=firebase_project_id,
    )
    return _cached_config
