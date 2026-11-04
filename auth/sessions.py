"""Session lifecycle management with hashed storage and revocation.

Security rules:
1. CSPRNG Token Generation: secrets.token_urlsafe(32) (256 bits of entropy).
2. Keyed Hashing: Database stores HMAC-SHA256(SESSION_SECRET, raw_token). A database compromise reveals no usable session tokens.
3. Debounced Activity Tracking: last_seen_at updated at most once every 5 minutes.
4. Instant Revocation: Token deletion revokes session immediately across all devices.
"""

from __future__ import annotations

import hmac
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple

from auth.config import load_auth_config
import database as db


def hash_session_token(token: str, secret: Optional[str] = None) -> str:
    """Compute HMAC-SHA256 hash of a raw session token."""
    cfg = load_auth_config()
    secret_key = secret or cfg.session_secret
    return hmac.new(secret_key.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def create_user_session(user_id: int) -> Tuple[str, datetime]:
    """Create a new authenticated session for a verified user.

    Returns:
        (raw_token, expires_at_utc)
    """
    cfg = load_auth_config()
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_session_token(raw_token, cfg.session_secret)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=cfg.session_ttl_hours)

    db.save_auth_session(user_id, token_hash, expires_at)
    db.update_user_last_login(user_id)

    # Periodic cleanup of expired rows
    try:
        db.cleanup_expired_auth_data()
    except Exception:
        pass

    return raw_token, expires_at


def validate_session_token(raw_token: str, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Validate a raw session token presented by client.

    Returns user dictionary if valid and active, else None.
    """
    if not raw_token or len(raw_token) < 20:
        return None

    cfg = load_auth_config()
    token_hash = hash_session_token(raw_token, cfg.session_secret)
    session_row = db.get_auth_session_by_token_hash(token_hash)
    if not session_row:
        return None

    current_time = now or datetime.now(timezone.utc)
    exp_val = session_row["expires_at"]
    if isinstance(exp_val, str):
        try:
            exp_time = datetime.fromisoformat(exp_val).replace(tzinfo=timezone.utc)
        except Exception:
            return None
    else:
        exp_time = exp_val.replace(tzinfo=timezone.utc) if exp_val.tzinfo is None else exp_val

    if current_time > exp_time:
        db.delete_auth_session(token_hash)
        return None

    # Debounced last_seen_at update (if last seen > 300 seconds ago)
    last_seen = session_row.get("last_seen_at")
    should_update = True
    if last_seen:
        try:
            if isinstance(last_seen, str):
                dt_seen = datetime.fromisoformat(last_seen).replace(tzinfo=timezone.utc)
            else:
                dt_seen = last_seen.replace(tzinfo=timezone.utc) if last_seen.tzinfo is None else last_seen
            if (current_time - dt_seen).total_seconds() < 300:
                should_update = False
        except Exception:
            pass

    if should_update:
        try:
            db.update_session_last_seen(session_row["id"])
        except Exception:
            pass

    return {
        "id": session_row["user_id"],
        "email": session_row["email"],
        "is_active": session_row["is_active"],
        "session_id": session_row["id"],
    }


def revoke_session(raw_token: str):
    """Revoke a single session token."""
    if not raw_token:
        return
    cfg = load_auth_config()
    token_hash = hash_session_token(raw_token, cfg.session_secret)
    db.delete_auth_session(token_hash)


def revoke_all_user_sessions(user_id: int):
    """Revoke all active sessions for a user (log out everywhere)."""
    db.delete_all_user_sessions(user_id)
