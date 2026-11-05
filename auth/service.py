"""High-level authentication service coordinating OTP, sessions, anti-enumeration, and audit logging.

Security guarantees:
1. Anti-Enumeration: request_otp returns an identical user message ("If this email can sign in, a code has been sent.")
   regardless of whether the email is registered or rejected by domain allowlists.
2. Sign-Up on First Verification: User accounts are created only upon successful OTP proof, preventing phantom account spam.
3. Audit Trail: All security events (REQUEST, VERIFY, FAILED_ATTEMPT, LOCKED, LOGOUT) logged with masked emails.
4. Dev Mode Safety: Plain code is exposed only in strictly configured AUTH_DEV_MODE.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional, Tuple, Dict, Any

from auth.config import load_auth_config
from auth.otp import normalize_email, mask_email, issue_otp_code, verify_otp_code
from auth.email_sender import get_email_sender
from auth.sessions import create_user_session, validate_session_token, revoke_session, revoke_all_user_sessions
from auth.rate_limit import (
    check_rate_limits,
    is_password_login_throttled,
    record_password_failure,
    PASSWORD_ATTEMPT_THROTTLE_MESSAGE,
)
import database as db

try:
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests
except ImportError:
    google_id_token = None
    google_requests = None

GENERIC_DISPATCH_MESSAGE = "If this email can sign in, a verification code has been sent."

GENERIC_INVALID_CREDENTIALS = "Invalid email or password."
INVALID_VERIFICATION_CODE = "Invalid verification code."
ACCOUNT_DISABLED_MESSAGE = "This account is currently disabled. Please contact support."


def extract_client_ip(headers: Optional[Dict[str, str]] = None) -> Optional[str]:
    """Extract client IP address from proxy headers if available."""
    if not headers:
        return None
    # Check X-Forwarded-For first
    xff = headers.get("x-forwarded-for") or headers.get("X-Forwarded-For")
    if xff:
        # First IP in comma-separated chain is original client
        return xff.split(",")[0].strip()
    return headers.get("remote-addr") or headers.get("Remote-Addr")


def request_otp(email: str, request_ip: Optional[str] = None) -> Tuple[bool, str, Optional[str]]:
    """Initiate an email OTP sign-in request with anti-enumeration protection.

    Returns:
        (success_bool, user_display_message, dev_mode_code_if_dev)
    """
    cfg = load_auth_config()

    try:
        norm_email = normalize_email(email)
    except ValueError:
        # Even on malformed email, return standard message to prevent format probing
        return True, GENERIC_DISPATCH_MESSAGE, None

    masked = mask_email(norm_email)

    # 1. Domain Allowlist Check
    if cfg.allowed_email_domains:
        domain = norm_email.split("@")[-1]
        if domain not in cfg.allowed_email_domains:
            db.save_security_event("AUTH_OTP_DOMAIN_REJECTED", f"Email: {masked} | Domain: {domain}")
            # Anti-enumeration: Return generic success without dispatching email
            return True, GENERIC_DISPATCH_MESSAGE, None

    # 2. Rate Limiting & Cooldown Check
    is_allowed, rate_msg, _ = check_rate_limits(norm_email, request_ip)
    if not is_allowed:
        db.save_security_event("AUTH_OTP_RATE_LIMITED", f"Email: {masked} | Reason: {rate_msg}")
        return False, rate_msg, None

    # 3. Issue Code
    code = issue_otp_code(norm_email, request_ip)

    # 4. Dispatch Email or Dev Mode Display
    dev_code = None
    if cfg.auth_dev_mode:
        # AUTH_DEV_MODE: use dev path so the request succeeds and we can return the code
        dev_code = code
        db.save_security_event("AUTH_OTP_DEV_DISPATCH", f"Email: {masked} | Dev mode active")
    else:
        sender = get_email_sender()
        ttl_minutes = max(1, cfg.otp_ttl_seconds // 60)
        try:
            sender.send_otp_email(norm_email, code, ttl_minutes)
            db.save_security_event("AUTH_OTP_DISPATCHED", f"Email: {masked}")
        except RuntimeError as e:
            db.save_security_event("AUTH_OTP_DELIVERY_FAILED", f"Email: {masked} | Error: {e}")
            return False, f"Could not send email: {e}", None

    return True, GENERIC_DISPATCH_MESSAGE, dev_code


def verify_otp_and_login(
    email: str,
    code: str,
    request_ip: Optional[str] = None,
) -> Tuple[bool, str, Optional[str], Optional[Dict[str, Any]]]:
    """Verify submitted OTP code and establish user session upon success.

    Returns:
        (success_bool, message, raw_session_token, user_dict)
    """
    try:
        norm_email = normalize_email(email)
    except ValueError as e:
        return False, str(e), None, None

    masked = mask_email(norm_email)

    is_valid, err_msg = verify_otp_code(norm_email, code)
    if not is_valid:
        db.save_security_event("AUTH_OTP_VERIFY_FAILED", f"Email: {masked} | Reason: {err_msg}")
        return False, err_msg, None, None

    # Retrieve or create user on first verified login (this now uses INSERT OR IGNORE)
    user = db.get_or_create_user(norm_email)
    if not user.get("is_active"):
        db.save_security_event("AUTH_ACCOUNT_DISABLED", f"Email: {masked}")
        return False, "This account is currently disabled. Please contact support.", None, None

    # Create new session token
    raw_token, _ = create_user_session(user["id"])
    db.save_security_event("AUTH_LOGIN_SUCCESS", f"Email: {masked} | UserID: {user['id']}")

    return True, "Login successful.", raw_token, user


def validate_session(raw_token: str) -> Optional[Dict[str, Any]]:
    """Validate presented session token and return user identity."""
    return validate_session_token(raw_token)


def logout_user(raw_token: str, user_id: Optional[int] = None):
    """Log out from current session."""
    revoke_session(raw_token)
    if user_id:
        db.save_security_event("AUTH_LOGOUT", f"UserID: {user_id}")


def logout_all_sessions(user_id: int):
    """Log out from all devices."""
    revoke_all_user_sessions(user_id)
    db.save_security_event("AUTH_LOGOUT_ALL", f"UserID: {user_id}")

def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with 100,000 iterations and random salt."""
    cfg = load_auth_config()
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", f"{password}_{cfg.otp_pepper}".encode("utf-8"), salt, 100_000)
    return f"pbkdf2_sha256${salt.hex()}${key.hex()}"


def verify_password(password: str, hashed_value: str) -> bool:
    """Verify candidate password against stored PBKDF2-HMAC-SHA256 hash."""
    if not hashed_value or not hashed_value.startswith("pbkdf2_sha256$"):
        return False
    try:
        cfg = load_auth_config()
        parts = hashed_value.split("$")
        if len(parts) != 3:
            return False
        salt = bytes.fromhex(parts[1])
        expected_key = bytes.fromhex(parts[2])
        actual_key = hashlib.pbkdf2_hmac("sha256", f"{password}_{cfg.otp_pepper}".encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(actual_key, expected_key)
    except Exception:
        return False


def login_or_register_with_password(
    email: str,
    password: str,
    otp_code: Optional[str] = None,
    request_ip: Optional[str] = None,
) -> Tuple[bool, str, Optional[str], Optional[Dict[str, Any]]]:
    """Authenticate or register a user using a password (with optional OTP 2FA).

    Security rules (fail closed):
    1. Password sign-in only authenticates accounts that already store a password
       hash; the password is compared in constant time.
    2. Accounts without a password hash (OTP-only) and unknown emails MUST present
       a valid OTP code before a password is set or a session is created.
    3. Unknown emails are never auto-registered without proof of email ownership.
    4. No code path mints a session without a verified password or a verified OTP.
    5. Failed attempts are throttled per email and per client IP.

    Returns:
        (success_bool, message, raw_session_token, user_dict)
    """
    try:
        norm_email = normalize_email(email)
    except ValueError as e:
        return False, str(e), None, None

    masked = mask_email(norm_email)
    if not password or len(password) < 6:
        return False, "Password must be at least 6 characters long.", None, None

    # 1. Throttle check happens BEFORE any credential verification.
    if is_password_login_throttled(norm_email, request_ip):
        db.save_security_event("AUTH_PASSWORD_THROTTLED", f"Email: {masked}")
        return False, PASSWORD_ATTEMPT_THROTTLE_MESSAGE, None, None

    user = db.get_user_by_email(norm_email)

    # 2. Optional OTP proof (also serves as 2FA for password accounts).
    otp_valid = False
    if otp_code:
        otp_valid, otp_err = verify_otp_code(norm_email, otp_code)
        if not otp_valid:
            db.save_security_event("AUTH_PASSWORD_OTP_FAILED", f"Email: {masked} | Reason: {otp_err}")

    password_valid = bool(
        user and user.get("password_hash") and verify_password(password, user["password_hash"])
    )

    if user is None:
        # 3a. Unknown email: registration requires a valid OTP proof.
        if not otp_valid:
            record_password_failure(norm_email, request_ip)
            db.save_security_event(
                "AUTH_LOGIN_FAILED", f"Email: {masked} | Reason: unknown email without OTP proof"
            )
            return False, GENERIC_INVALID_CREDENTIALS, None, None

        user = db.get_or_create_user(norm_email)
        if not user.get("is_active"):
            return False, ACCOUNT_DISABLED_MESSAGE, None, None
        db.set_user_password(user["id"], hash_password(password))
        db.save_security_event("AUTH_REGISTER_SUCCESS", f"Email: {masked} | UserID: {user['id']}")
    elif user.get("password_hash"):
        # 3b. Existing password account: verify the password, and the OTP if supplied.
        if not password_valid:
            record_password_failure(norm_email, request_ip)
            db.save_security_event("AUTH_PASSWORD_INVALID", f"Email: {masked}")
            return False, GENERIC_INVALID_CREDENTIALS, None, None
        if otp_code and not otp_valid:
            return False, INVALID_VERIFICATION_CODE, None, None
        if not user.get("is_active"):
            db.save_security_event("AUTH_ACCOUNT_DISABLED", f"Email: {masked}")
            return False, ACCOUNT_DISABLED_MESSAGE, None, None
    else:
        # 3c. Existing OTP-only account: require OTP proof BEFORE setting a password.
        if otp_code and not otp_valid:
            return False, INVALID_VERIFICATION_CODE, None, None
        if not otp_valid:
            record_password_failure(norm_email, request_ip)
            db.save_security_event(
                "AUTH_LOGIN_FAILED", f"Email: {masked} | Reason: OTP-only account requires OTP proof"
            )
            return False, GENERIC_INVALID_CREDENTIALS, None, None
        if not user.get("is_active"):
            db.save_security_event("AUTH_ACCOUNT_DISABLED", f"Email: {masked}")
            return False, ACCOUNT_DISABLED_MESSAGE, None, None
        db.set_user_password(user["id"], hash_password(password))
        db.save_security_event("AUTH_PASSWORD_SET", f"Email: {masked} | UserID: {user['id']}")

    # 4. Credentials verified (password and/or OTP): establish the session.
    raw_token, _ = create_user_session(user["id"])
    db.save_security_event("AUTH_LOGIN_SUCCESS", f"Email: {masked} | Method: Password")
    return True, "Login successful.", raw_token, user


def verify_google_token_and_login(
    id_token: str,
    request_ip: Optional[str] = None,
) -> Tuple[bool, str, Optional[str], Optional[Dict[str, Any]]]:
    """Verify submitted Firebase Google ID token and establish user session.

    Security guarantees:
    - Grounded verification using google.oauth2.id_token.verify_firebase_token.
    - Matches audience against configured firebase_project_id.
    - Requires email_verified == True.
    - Enforces configured allowed_email_domains.
    - Atomic account linking / creation handling IntegrityError and race conditions.
    - Preserves existing user data, passwords, and sessions.

    Returns:
        (success_bool, message, raw_session_token, user_dict)
    """
    if not id_token or not str(id_token).strip():
        return False, "Google token is required.", None, None

    if google_id_token is None or google_requests is None:
        return False, "Google authentication dependencies (google-auth, requests) not installed.", None, None

    cfg = load_auth_config()

    try:
        request_adapter = google_requests.Request()
        decoded = google_id_token.verify_firebase_token(
            id_token.strip(),
            request_adapter,
            audience=cfg.firebase_project_id,
        )
    except Exception as exc:
        db.save_security_event("AUTH_GOOGLE_TOKEN_INVALID", f"Reason: {exc}")
        return False, f"Invalid or expired Google authentication token: {exc}", None, None

    google_id = decoded.get("sub") or decoded.get("user_id")
    raw_email = decoded.get("email")
    email_verified = decoded.get("email_verified")

    if not google_id:
        db.save_security_event("AUTH_GOOGLE_TOKEN_INVALID", "Reason: Missing sub/user_id in token")
        return False, "Google token does not contain a valid user identity.", None, None

    if not raw_email:
        db.save_security_event("AUTH_GOOGLE_TOKEN_INVALID", "Reason: Missing email in token")
        return False, "Google token does not contain an email address.", None, None

    if email_verified is not True:
        db.save_security_event("AUTH_GOOGLE_UNVERIFIED_EMAIL", f"GoogleID: {google_id}")
        return False, "Google account email is not verified.", None, None

    try:
        norm_email = normalize_email(raw_email)
    except ValueError as e:
        return False, str(e), None, None

    masked = mask_email(norm_email)

    if cfg.allowed_email_domains:
        domain = norm_email.split("@")[1]
        if domain not in cfg.allowed_email_domains:
            db.save_security_event("AUTH_GOOGLE_DOMAIN_REJECTED", f"Email: {masked} | Domain: {domain}")
            return False, f"Email domain '@{domain}' is not permitted to sign in.", None, None

    # Check if a user is already associated with this Google ID
    user_by_gid = db.get_user_by_google_id(google_id)
    if user_by_gid:
        if user_by_gid.get("email", "").lower() != norm_email:
            db.save_security_event(
                "AUTH_GOOGLE_COLLISION_REJECTED",
                f"GoogleID: {google_id} | Existing: {mask_email(user_by_gid.get('email', ''))} | Attempted: {masked}"
            )
            return False, "This Google identity is already linked to a different email address.", None, None
        if not user_by_gid.get("is_active"):
            db.save_security_event("AUTH_ACCOUNT_DISABLED", f"Email: {masked}")
            return False, ACCOUNT_DISABLED_MESSAGE, None, None
        user = user_by_gid
    else:
        # Check if existing user by email
        user_by_email = db.get_user_by_email(norm_email)
        if user_by_email:
            if not user_by_email.get("is_active"):
                db.save_security_event("AUTH_ACCOUNT_DISABLED", f"Email: {masked}")
                return False, ACCOUNT_DISABLED_MESSAGE, None, None
            # Link Google ID transactionally
            linked, reason = db.link_user_google_id(user_by_email["id"], google_id)
            if not linked:
                db.save_security_event("AUTH_GOOGLE_LINK_FAILED", f"Email: {masked} | Reason: {reason}")
                return False, "Unable to link Google identity to existing account.", None, None
            user_by_email["google_id"] = google_id
            user = user_by_email
            db.save_security_event("AUTH_GOOGLE_LINK_SUCCESS", f"Email: {masked} | UserID: {user['id']}")
        else:
            # Create new user transactionally
            user, reason = db.create_google_user(norm_email, google_id)
            if not user:
                db.save_security_event("AUTH_GOOGLE_CREATE_FAILED", f"Email: {masked} | Reason: {reason}")
                return False, "Unable to create account with Google identity.", None, None
            db.save_security_event("AUTH_GOOGLE_REGISTER_SUCCESS", f"Email: {masked} | UserID: {user['id']}")

    # Establish authenticated session
    raw_token, _ = create_user_session(user["id"])
    db.save_security_event("AUTH_LOGIN_SUCCESS", f"Email: {masked} | Method: Google | UserID: {user['id']}")
    return True, "Login successful.", raw_token, user

