"""Unit tests for session token creation, validation, expiration, and revocation."""

from datetime import datetime, timedelta, timezone
import pytest

from auth.config import load_auth_config
from auth.sessions import (
    create_user_session,
    validate_session_token,
    revoke_session,
    revoke_all_user_sessions,
    hash_session_token,
)
import database as db


@pytest.fixture(autouse=True)
def setup_auth_env(monkeypatch):
    monkeypatch.setenv("OTP_PEPPER", "test_otp_pepper_secret_value_1234567890")
    monkeypatch.setenv("SESSION_SECRET", "test_session_secret_value_1234567890")
    monkeypatch.setenv("AUTH_DEV_MODE", "false")
    load_auth_config(reload=True)


def test_session_lifecycle_create_validate_and_revoke():
    """Verify session is created, hashed in database, validated, and revoked."""
    user = db.get_or_create_user("session_tester@example.com")
    raw_token, exp_time = create_user_session(user["id"])

    assert len(raw_token) >= 32

    # Database must store ONLY HMAC-SHA256 hash, never raw token
    expected_hash = hash_session_token(raw_token)
    session_row = db.get_auth_session_by_token_hash(expected_hash)
    assert session_row is not None
    assert session_row["token_hash"] == expected_hash

    # Validate active session
    validated_user = validate_session_token(raw_token)
    assert validated_user is not None
    assert validated_user["id"] == user["id"]
    assert validated_user["email"] == "session_tester@example.com"

    # Revoke session
    revoke_session(raw_token)

    # Validating revoked token returns None
    assert validate_session_token(raw_token) is None


def test_tampered_and_expired_session_fails():
    """Verify tampered token fails, and expired token fails with injected clock."""
    user = db.get_or_create_user("expiry_tester@example.com")
    raw_token, _ = create_user_session(user["id"])

    # Tampered token
    tampered_token = raw_token[:-4] + "XXXX"
    assert validate_session_token(tampered_token) is None

    # Expired token in the future
    future_time = datetime.now(timezone.utc) + timedelta(days=8)
    assert validate_session_token(raw_token, now=future_time) is None


def test_revoke_all_user_sessions():
    """Verify logout-everywhere revokes all active sessions for a user."""
    user = db.get_or_create_user("multi_device@example.com")
    token_device1, _ = create_user_session(user["id"])
    token_device2, _ = create_user_session(user["id"])

    assert validate_session_token(token_device1) is not None
    assert validate_session_token(token_device2) is not None

    revoke_all_user_sessions(user["id"])

    assert validate_session_token(token_device1) is None
    assert validate_session_token(token_device2) is None
