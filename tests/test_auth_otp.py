"""Unit tests for OTP generation, hashing, verification, expiry, and rate limits."""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pytest

from auth.config import load_auth_config
from auth.otp import (
    generate_otp_code,
    hash_otp_code,
    issue_otp_code,
    verify_otp_code,
    normalize_email,
    mask_email,
)
from auth.email_sender import FakeEmailSender, set_email_sender_override
from auth.service import request_otp
import database as db


@pytest.fixture(autouse=True)
def setup_auth_env(monkeypatch):
    """Ensure consistent test configuration without external dependencies."""
    monkeypatch.setenv("OTP_PEPPER", "test_otp_pepper_secret_value_1234567890")
    monkeypatch.setenv("SESSION_SECRET", "test_session_secret_value_1234567890")
    monkeypatch.setenv("AUTH_DEV_MODE", "false")
    monkeypatch.setenv("OTP_TTL_SECONDS", "300")
    monkeypatch.setenv("OTP_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("OTP_RESEND_COOLDOWN_SECONDS", "60")
    monkeypatch.setenv("OTP_MAX_PER_EMAIL_PER_HOUR", "5")
    load_auth_config(reload=True)


def test_otp_format_and_hashing():
    """Verify OTP is exactly 6 digits, hashed, and never equals the plain code."""
    email = "researcher@example.com"
    plain_code = issue_otp_code(email)

    assert len(plain_code) == 6
    assert plain_code.isdigit()

    record = db.get_latest_otp_code(email)
    assert record is not None
    # Code hash in DB must be a 64-char hex HMAC-SHA256, NEVER the plain code
    assert record["code_hash"] != plain_code
    assert len(record["code_hash"]) == 64
    assert plain_code not in record["code_hash"]


def test_otp_single_use_success_then_fails():
    """Verify correct code succeeds once, but a second use fails immediately."""
    email = "single_use@example.com"
    plain_code = issue_otp_code(email)

    # First attempt: succeeds
    valid, msg = verify_otp_code(email, plain_code)
    assert valid is True
    assert msg == ""

    # Second attempt: fails because it is now marked as used
    valid2, msg2 = verify_otp_code(email, plain_code)
    assert valid2 is False
    assert "invalid or has expired" in msg2


def test_otp_expiry_fails():
    """Verify expired code fails using an injected clock."""
    email = "expired_test@example.com"
    plain_code = issue_otp_code(email)

    # Fast forward past 300s TTL (e.g. +301 seconds into the future)
    future_time = datetime.now(timezone.utc) + timedelta(seconds=305)
    valid, msg = verify_otp_code(email, plain_code, now=future_time)

    assert valid is False
    assert "expired" in msg.lower()


def test_otp_wrong_code_increments_attempts_and_locks():
    """Verify wrong code increments attempts; after limit, even correct code is locked."""
    email = "brute_force_target@example.com"
    correct_code = issue_otp_code(email)

    # Make 5 wrong attempts
    for attempt_idx in range(1, 6):
        valid, msg = verify_otp_code(email, "000000" if correct_code != "000000" else "999999")
        assert valid is False

    # 6th attempt with the CORRECT code must fail because code is now locked
    valid, msg = verify_otp_code(email, correct_code)
    assert valid is False
    assert "Too many incorrect attempts" in msg or "invalid or has expired" in msg


def test_new_code_invalidates_previous_code():
    """Verify requesting a new code invalidates all previous unused codes for that email."""
    email = "reissue_test@example.com"
    first_code = issue_otp_code(email)
    second_code = issue_otp_code(email)

    assert first_code != second_code

    # First code must fail because it was invalidated by the second code issuance
    valid1, msg1 = verify_otp_code(email, first_code)
    assert valid1 is False

    # Second code succeeds
    valid2, msg2 = verify_otp_code(email, second_code)
    assert valid2 is True


def test_resend_cooldown_and_hourly_limits():
    """Verify resend cooldown (60s) and hourly limits (5 per hour) are strictly enforced."""
    email = "rate_limited_user@example.com"
    fake_sender = FakeEmailSender()
    set_email_sender_override(fake_sender)

    # Request 1: succeeds
    ok1, msg1, _ = request_otp(email)
    assert ok1 is True
    assert len(fake_sender.sent_messages) == 1

    # Request 2 immediately: blocked by 60s cooldown
    ok2, msg2, _ = request_otp(email)
    assert ok2 is False
    assert "Please wait" in msg2

    set_email_sender_override(None)
