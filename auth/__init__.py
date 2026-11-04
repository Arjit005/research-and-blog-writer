"""Authentication and Per-User Data Isolation Package.

Provides email-OTP authentication, session validation, rate limiting, and data gating.
Framework-agnostic core with zero dependencies on Streamlit.
"""

from auth.config import load_auth_config, AuthConfig
from auth.otp import normalize_email, mask_email, generate_otp_code, issue_otp_code, verify_otp_code
from auth.sessions import create_user_session, validate_session_token, revoke_session, revoke_all_user_sessions
from auth.service import request_otp, verify_otp_and_login, validate_session, logout_user, logout_all_sessions
from auth.email_sender import EmailSender, FakeEmailSender, SMTPEmailSender, get_email_sender, set_email_sender_override

# Dynamic attribute loader for require_login so backend imports never load Streamlit
def __getattr__(name: str):
    if name == "require_login":
        from auth.ui import require_login
        return require_login
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "load_auth_config",
    "AuthConfig",
    "normalize_email",
    "mask_email",
    "generate_otp_code",
    "issue_otp_code",
    "verify_otp_code",
    "create_user_session",
    "validate_session_token",
    "revoke_session",
    "revoke_all_user_sessions",
    "request_otp",
    "verify_otp_and_login",
    "validate_session",
    "logout_user",
    "logout_all_sessions",
    "EmailSender",
    "FakeEmailSender",
    "SMTPEmailSender",
    "get_email_sender",
    "set_email_sender_override",
    "require_login",
]
