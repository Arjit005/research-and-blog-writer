"""Database-backed rate limiting and cooldown enforcement for OTP issuance.

Security rules:
1. Resend Cooldown: Prevents rapid-fire email spamming by enforcing a mandatory wait time.
2. Hourly Caps: Restricts OTP issuance per email and per client IP to stop abuse.
3. Database Grounded: Survives application restarts and multi-worker setups.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Tuple

from auth.config import load_auth_config
import database as db


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
