"""Database-backed rate limiting for OTP issuance and password authentication.

Security rules:
1. Resend Cooldown: Prevents rapid-fire email spamming by enforcing a mandatory wait time.
2. Hourly Caps: Restricts OTP issuance per email and per client IP to stop abuse.
3. Database Grounded: Survives application restarts and multi-worker setups.
4. Password throttling: Failed password sign-ins are counted per email and per
   client IP in a rolling window. The database is the source of truth, with a
   bounded in-process fallback so throttling still applies if the persistence
   hook is unavailable or temporarily erroring.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from auth.config import load_auth_config
import database as db

logger = logging.getLogger("auth.rate_limit")

# --- Password authentication throttling -------------------------------------
# 8 failed attempts per email / 20 per IP within 15 minutes before lockout.
PASSWORD_ATTEMPT_WINDOW_SECONDS = 900
PASSWORD_MAX_FAILED_ATTEMPTS_PER_EMAIL = 8
PASSWORD_MAX_FAILED_ATTEMPTS_PER_IP = 20
PASSWORD_ATTEMPT_THROTTLE_MESSAGE = (
    "Too many failed sign-in attempts. Please try again later."
)

_fallback_lock = threading.Lock()
# (normalized_email, request_ip, monotonic_timestamp)
_fallback_attempts: List[Tuple[str, Optional[str], float]] = []
_FALLBACK_MAX_ENTRIES = 10_000


def check_rate_limits(email: str, request_ip: Optional[str] = None, now: Optional[datetime] = None) -> Tuple[bool, str, int]:
    """Check whether OTP issuance is permitted under cooldown and hourly caps.

    Returns:
        (is_allowed, failure_message, cooldown_remaining_seconds)
    """
    cfg = load_auth_config()
    current_time = now or datetime.now(timezone.utc)
    norm_email = email.strip().lower()

    # 1. Check Resend Cooldown
    last_created = db.get_latest_otp_created_at(norm_email)
    if last_created:
        elapsed = (current_time - last_created).total_seconds()
        if elapsed < cfg.otp_resend_cooldown_seconds:
            remaining = int(cfg.otp_resend_cooldown_seconds - elapsed)
            return False, f"Please wait {remaining} seconds before requesting another code.", remaining

    # 2. Check Hourly Cap per Email
    recent_email_count = db.count_recent_otps_by_email(norm_email, window_seconds=3600)
    if recent_email_count >= cfg.otp_max_per_email_per_hour:
        return False, "Too many code requests for this email. Please try again in an hour.", 3600

    # 3. Check Hourly Cap per IP (if IP available)
    if request_ip:
        recent_ip_count = db.count_recent_otps_by_ip(request_ip, window_seconds=3600)
        if recent_ip_count >= cfg.otp_max_per_ip_per_hour:
            return False, "Too many code requests from your network. Please try again later.", 3600

    return True, "", 0


# ---------------------------------------------------------------------------
# Password authentication attempt throttling
# ---------------------------------------------------------------------------

def _fallback_record(email: str, request_ip: Optional[str], now: float) -> None:
    """Record a failed attempt in the bounded in-process fallback list."""
    cutoff = now - PASSWORD_ATTEMPT_WINDOW_SECONDS
    with _fallback_lock:
        _fallback_attempts[:] = [entry for entry in _fallback_attempts if entry[2] > cutoff]
        _fallback_attempts.append((email, request_ip, now))
        overflow = len(_fallback_attempts) - _FALLBACK_MAX_ENTRIES
        if overflow > 0:
            del _fallback_attempts[:overflow]


def _fallback_count(email: Optional[str], request_ip: Optional[str]) -> int:
    """Count recent failed attempts in the in-process fallback list."""
    now = time.monotonic()
    cutoff = now - PASSWORD_ATTEMPT_WINDOW_SECONDS
    with _fallback_lock:
        _fallback_attempts[:] = [entry for entry in _fallback_attempts if entry[2] > cutoff]
        return sum(
            1
            for entry_email, entry_ip, _ in _fallback_attempts
            if (email is None or entry_email == email)
            and (request_ip is None or entry_ip == request_ip)
        )


def _db_recent_count(email: Optional[str], request_ip: Optional[str]) -> int:
    """Query the database counter; returns 0 if the hook is missing or erroring.

    ``database.count_recent_password_attempts`` returns 0 when ``email`` is
    missing, so every call passes an email. When an IP is supplied the DB helper
    counts attempts matching the email OR the IP, which is what the combined
    threshold below relies on.
    """
    counter = getattr(db, "count_recent_password_attempts", None)
    if counter is None:
        logger.warning(
            "database.count_recent_password_attempts() is unavailable; "
            "password throttling is using the in-process fallback only."
        )
        return 0
    try:
        try:
            return int(
                counter(
                    email=email,
                    ip=request_ip,
                    window_seconds=PASSWORD_ATTEMPT_WINDOW_SECONDS,
                )
                or 0
            )
        except TypeError:
            # Tolerate positional-only implementations of the documented signature.
            return int(counter(email, request_ip, PASSWORD_ATTEMPT_WINDOW_SECONDS) or 0)
    except Exception:
        logger.warning("Password attempt counter failed; falling back to in-process counting.", exc_info=True)
        return 0


def _count_recent_attempts(email: Optional[str], request_ip: Optional[str]) -> int:
    """Return the largest of the DB-backed and in-process counters for a filter."""
    return max(_db_recent_count(email, request_ip), _fallback_count(email, request_ip))


def record_password_failure(email: str, request_ip: Optional[str] = None) -> None:
    """Record one failed password sign-in attempt for throttling purposes."""
    norm_email = (email or "").strip().lower()
    if not norm_email:
        return
    _fallback_record(norm_email, request_ip, time.monotonic())
    recorder = getattr(db, "record_password_attempt", None)
    if recorder is None:
        logger.warning(
            "database.record_password_attempt() is unavailable; "
            "password attempts are only counted in-process for this worker."
        )
        return
    try:
        try:
            recorder(email=norm_email, ip=request_ip)
        except TypeError:
            # Tolerate positional-only implementations of the documented signature.
            recorder(norm_email, request_ip)
    except Exception:
        logger.warning("Failed to persist password attempt; in-process fallback still applies.", exc_info=True)


def is_password_login_throttled(email: str, request_ip: Optional[str] = None) -> bool:
    """Return True when this email or client IP has exhausted failed-attempt limits."""
    norm_email = (email or "").strip().lower()
    if not norm_email:
        return False
    # Per-account limit: attempts recorded against this email.
    if _count_recent_attempts(norm_email, None) >= PASSWORD_MAX_FAILED_ATTEMPTS_PER_EMAIL:
        return True
    if request_ip:
        # Combined (email OR IP) attempts from the DB, plus the exact per-IP count
        # maintained in-process, both cap abusive networks.
        if _count_recent_attempts(norm_email, request_ip) >= PASSWORD_MAX_FAILED_ATTEMPTS_PER_IP:
            return True
        if _fallback_count(None, request_ip) >= PASSWORD_MAX_FAILED_ATTEMPTS_PER_IP:
            return True
    return False


def reset_password_attempt_cache() -> None:
    """Clear the in-process fallback counters (test isolation / process lifecycle)."""
    with _fallback_lock:
        _fallback_attempts.clear()
