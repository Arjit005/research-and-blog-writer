"""Cryptographic OTP generation, hashing, and verification.

Security rules:
1. CSPRNG: Always secrets.randbelow(10**6), formatted with 6 digits.
2. Zero Plaintext: Stored only as HMAC-SHA256(OTP_PEPPER, email_norm:code).
3. Constant-Time Verification: hmac.compare_digest to prevent side-channel timing leaks.
4. Pre-Increment Attempts: attempts incremented BEFORE comparing to defeat race condition attacks.
5. Invalidate on Re-issuance: Previous codes invalidated immediately when a new code is issued.
"""

from __future__ import annotations

import re
import hmac
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, Any

from auth.config import load_auth_config
import database as db

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def normalize_email(email: str) -> str:
    """Normalize and strictly validate an email address."""
    if not email:
        raise ValueError("Email address cannot be empty.")
    norm = email.strip().lower()
    if len(norm) > 254:
        raise ValueError("Email address exceeds maximum length of 254 characters.")
    if not EMAIL_REGEX.match(norm) or ".." in norm:
        raise ValueError("Invalid email address format.")
    return norm


def mask_email(email: str) -> str:
    """Mask email for safe logging and UI display (e.g. a***@domain.com)."""
    try:
        norm = normalize_email(email)
        user_part, domain = norm.split("@", 1)
        if len(user_part) <= 1:
            masked_user = f"{user_part}***"
        elif len(user_part) <= 3:
            masked_user = f"{user_part[0]}***"
        else:
            masked_user = f"{user_part[0]}***{user_part[-1]}"
        return f"{masked_user}@{domain}"
    except Exception:
        return "invalid-email***"


def hash_otp_code(email: str, code: str, pepper: Optional[str] = None) -> str:
    """Compute HMAC-SHA256 hash of email:code using server OTP pepper."""
    cfg = load_auth_config()
    secret_pepper = pepper or cfg.otp_pepper
    payload = f"{email}:{code}".encode("utf-8")
    return hmac.new(secret_pepper.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def generate_otp_code() -> str:
    """Generate a cryptographically secure 6-digit one-time code."""
    return f"{secrets.randbelow(1_000_000):06d}"


def issue_otp_code(email: str, request_ip: Optional[str] = None) -> str:
    """Issue a new OTP code for an email, invalidating previous unused codes.

    Returns the plain 6-digit code ONLY for the purpose of dispatching via SMTP or Dev UI.
    It is never persisted or logged in plain text.
    """
    cfg = load_auth_config()
    norm_email = normalize_email(email)

    # 1. Invalidate all prior unused codes for this email
    db.invalidate_unused_otps_for_email(norm_email)

    # 2. Generate and hash code
    code = generate_otp_code()
    code_hash = hash_otp_code(norm_email, code, cfg.otp_pepper)

    # 3. Compute expiration time in UTC
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=cfg.otp_ttl_seconds)

    # 4. Save to database
    db.save_otp_code(norm_email, code_hash, expires_at, request_ip)

    return code


def verify_otp_code(email: str, submitted_code: str, now: Optional[datetime] = None) -> Tuple[bool, str]:
    """Verify submitted OTP code against active unexpired hash in database.

    Returns (is_valid, user_friendly_error_message).
    """
    cfg = load_auth_config()
    try:
        norm_email = normalize_email(email)
    except ValueError as e:
        return False, str(e)

    clean_code = submitted_code.strip()
    if not clean_code or len(clean_code) != 6 or not clean_code.isdigit():
        return False, "Please enter a valid 6-digit verification code."

    # 1. Fetch newest unused unexpired code
    otp_record = db.get_latest_otp_code(norm_email)
    if not otp_record:
        return False, "Verification code is invalid or has expired. Please request a new code."

    otp_id = otp_record["id"]
    current_attempts = otp_record["attempts"]

    # 2. Pre-increment attempt count BEFORE comparison (defeats race-conditions)
    new_attempts = db.increment_otp_attempts(otp_id)

    # 3. Check attempt limit cap
    if new_attempts > cfg.otp_max_attempts:
        db.mark_otp_used(otp_id)  # Lockout this code
        return False, "Too many incorrect attempts. This code has been deactivated. Please request a new code."

    # 4. Check expiration using server UTC clock or injected clock
    current_time = now or datetime.now(timezone.utc)
    exp_val = otp_record["expires_at"]
    if isinstance(exp_val, str):
        try:
            exp_time = datetime.fromisoformat(exp_val).replace(tzinfo=timezone.utc)
        except Exception:
            exp_time = datetime.now(timezone.utc)
    else:
        exp_time = exp_val.replace(tzinfo=timezone.utc) if exp_val.tzinfo is None else exp_val

    if current_time > exp_time:
        db.mark_otp_used(otp_id)
        return False, "Verification code has expired. Please request a new code."

    # 5. Constant-time hash comparison
    expected_hash = hash_otp_code(norm_email, clean_code, cfg.otp_pepper)
    stored_hash = otp_record["code_hash"]

    if not hmac.compare_digest(expected_hash, stored_hash):
        remaining = max(0, cfg.otp_max_attempts - new_attempts)
        if remaining == 0:
            db.mark_otp_used(otp_id)
            return False, "Too many incorrect attempts. Code locked. Please request a new code."
        return False, f"Incorrect verification code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."

    # 6. Mark used on success
    db.mark_otp_used(otp_id)
    return True, ""
