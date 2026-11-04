"""Unit tests for auth service anti-enumeration, domain allowlists, audit trail, and sender handling."""

import pytest

from auth.config import load_auth_config, DEV_OTP_PEPPER, DEV_SESSION_SECRET
from auth.service import (
    request_otp,
    verify_otp_and_login,
    login_or_register_with_password,
    hash_password,
    verify_password,
    GENERIC_DISPATCH_MESSAGE,
    GENERIC_INVALID_CREDENTIALS,
    ACCOUNT_DISABLED_MESSAGE,
)
from auth.email_sender import FakeEmailSender, set_email_sender_override
from auth.otp import mask_email, issue_otp_code
from auth.rate_limit import PASSWORD_ATTEMPT_THROTTLE_MESSAGE, reset_password_attempt_cache
from auth.sessions import validate_session_token
import database as db


@pytest.fixture(autouse=True)
def setup_auth_env(monkeypatch):
    monkeypatch.setenv("OTP_PEPPER", "test_otp_pepper_secret_value_1234567890")
    monkeypatch.setenv("SESSION_SECRET", "test_session_secret_value_1234567890")
    monkeypatch.setenv("AUTH_DEV_MODE", "false")
    monkeypatch.setenv("OTP_RESEND_COOLDOWN_SECONDS", "0")  # Disable cooldown for service testing
    load_auth_config(reload=True)
    reset_password_attempt_cache()
    yield
    reset_password_attempt_cache()


def test_anti_enumeration_known_and_unknown_emails():
    """Verify known and unknown emails receive the exact same user response."""
    fake_sender = FakeEmailSender()
    set_email_sender_override(fake_sender)

    # Unknown email
    ok1, msg1, dev_code1 = request_otp("completely_unknown_user_123@example.com")
    assert ok1 is True
    assert msg1 == GENERIC_DISPATCH_MESSAGE

    # Known existing user
    db.get_or_create_user("known_existing_user@example.com")
    ok2, msg2, dev_code2 = request_otp("known_existing_user@example.com")
    assert ok2 is True
    assert msg2 == GENERIC_DISPATCH_MESSAGE
    assert msg1 == msg2

    set_email_sender_override(None)


def test_domain_allowlist_silently_rejects_with_same_message(monkeypatch):
    """Verify domain allowlist silently blocks unapproved domains with identical message."""
    monkeypatch.setenv("ALLOWED_EMAIL_DOMAINS", "company.com,approved.org")
    load_auth_config(reload=True)

    fake_sender = FakeEmailSender()
    set_email_sender_override(fake_sender)

    # Disallowed domain
    ok, msg, _ = request_otp("attacker@forbidden.com")
    assert ok is True
    assert msg == GENERIC_DISPATCH_MESSAGE
    # Sender must NOT have sent any email to the disallowed address
    assert len(fake_sender.sent_messages) == 0

    # Allowed domain
    ok_allowed, msg_allowed, _ = request_otp("engineer@company.com")
    assert ok_allowed is True
    assert msg_allowed == GENERIC_DISPATCH_MESSAGE
    assert len(fake_sender.sent_messages) == 1
    assert fake_sender.sent_messages[0]["to"] == "engineer@company.com"

    set_email_sender_override(None)


def test_audit_logs_mask_email_and_never_store_plain_code():
    """Verify audit logs record masked emails (e.g. e***@example.com) and zero plain OTPs or tokens."""
    fake_sender = FakeEmailSender()
    set_email_sender_override(fake_sender)

    test_email = "audit_security_check@example.com"
    request_otp(test_email)

    sent_code = fake_sender.sent_messages[0]["code"]
    logs = db.get_security_audit_logs(limit=10)

    found_event = False
    for log in logs:
        details = log["details"]
        # Code must NEVER appear anywhere in the audit logs
        assert sent_code not in details
        if "audit_security_check" in details:
            found_event = True
            # Must be masked
            assert mask_email(test_email) in details
            assert test_email not in details

    set_email_sender_override(None)


def test_email_sender_failure_returns_friendly_error():
    """Verify SMTP failure produces a clean user error without leaking credentials or stack traces."""
    failing_sender = FakeEmailSender(should_fail=True)
    set_email_sender_override(failing_sender)

    ok, msg, _ = request_otp("smtp_failure_target@example.com")
    assert ok is False
    assert "Could not send email" in msg
    assert "Simulated SMTP delivery failure" in msg

    set_email_sender_override(None)


# ---------------------------------------------------------------------------
# CRITICAL regression: password login must never take over an OTP-only account
# or auto-register an unknown email without proof of ownership.
# ---------------------------------------------------------------------------

def test_unknown_email_password_login_requires_otp_proof():
    """Unknown email + password (no OTP) must fail generically and register nothing."""
    email = "unknown_pwd_user@example.com"

    ok, msg, token, user = login_or_register_with_password(email, "Password123!")

    assert ok is False
    assert token is None
    assert user is None
    assert msg == GENERIC_INVALID_CREDENTIALS
    assert db.get_user_by_email(email) is None, "Unknown email must not be auto-registered"


def test_unknown_email_registration_requires_valid_otp():
    """Unknown email can register only after presenting a valid OTP code."""
    email = "new_verified_user@example.com"
    code = issue_otp_code(email)

    ok, msg, token, user = login_or_register_with_password(
        email, "Password123!", otp_code=code
    )

    assert ok is True
    assert token is not None
    assert user is not None
    stored = db.get_user_by_email(email)
    assert stored is not None
    assert stored["password_hash"] is not None
    assert verify_password("Password123!", stored["password_hash"])


def test_otp_only_account_cannot_be_hijacked_with_arbitrary_password():
    """An existing OTP-only user (password_hash NULL) must not be logged in by password alone."""
    email = "otp_only_victim@example.com"
    db.get_or_create_user(email)

    ok, msg, token, user = login_or_register_with_password(email, "AttackerPassword1!")

    assert ok is False
    assert token is None
    assert user is None
    assert msg == GENERIC_INVALID_CREDENTIALS
    stored = db.get_user_by_email(email)
    assert stored["password_hash"] is None, "Password must not be set without OTP proof"

    # With a valid OTP the OTP-only user may set their password and sign in.
    code = issue_otp_code(email)
    ok2, _msg2, token2, user2 = login_or_register_with_password(
        email, "ChosenPassword1!", otp_code=code
    )
    assert ok2 is True
    assert token2 is not None
    assert validate_session_token(token2) is not None
    assert verify_password("ChosenPassword1!", db.get_user_by_email(email)["password_hash"])


def test_password_account_login_and_wrong_password():
    """A password account verifies the password in constant time and rejects wrong passwords."""
    email = "password_account@example.com"
    code = issue_otp_code(email)
    ok, _, _, _ = login_or_register_with_password(email, "CorrectPassword1!", otp_code=code)
    assert ok is True

    # Wrong password: no session, generic message, no hash rewrites.
    ok_bad, msg_bad, token_bad, user_bad = login_or_register_with_password(
        email, "WrongPassword1!"
    )
    assert ok_bad is False
    assert token_bad is None
    assert user_bad is None
    assert msg_bad == GENERIC_INVALID_CREDENTIALS

    # Correct password without OTP: succeeds (password is the second factor here).
    ok_good, _, token_good, user_good = login_or_register_with_password(
        email, "CorrectPassword1!"
    )
    assert ok_good is True
    assert token_good is not None
    assert user_good["email"] == email


def test_password_login_with_otp_code_requires_valid_otp():
    """When an OTP is supplied as 2FA it must be valid even if the password is correct."""
    email = "two_factor_user@example.com"
    code = issue_otp_code(email)
    ok, _, _, _ = login_or_register_with_password(email, "CorrectPassword1!", otp_code=code)
    assert ok is True

    ok_bad, _, token_bad, user_bad = login_or_register_with_password(
        email, "CorrectPassword1!", otp_code="000000"
    )
    assert ok_bad is False
    assert token_bad is None
    assert user_bad is None


def test_password_attempts_are_throttled_per_email():
    """After 8 failed password attempts the account is throttled (even for correct passwords)."""
    email = "throttled_user@example.com"
    code = issue_otp_code(email)
    ok, _, _, _ = login_or_register_with_password(email, "CorrectPassword1!", otp_code=code)
    assert ok is True

    for _ in range(8):
        ok_attempt, msg_attempt, token_attempt, _ = login_or_register_with_password(
            email, "WrongPassword1!"
        )
        assert ok_attempt is False
        assert token_attempt is None
        assert msg_attempt == GENERIC_INVALID_CREDENTIALS

    ok_blocked, msg_blocked, token_blocked, user_blocked = login_or_register_with_password(
        email, "CorrectPassword1!"
    )
    assert ok_blocked is False
    assert token_blocked is None
    assert user_blocked is None
    assert msg_blocked == PASSWORD_ATTEMPT_THROTTLE_MESSAGE


def test_password_attempts_are_throttled_per_ip():
    """Distributed email guessing from one IP is capped by the shared IP counter."""
    request_ip = "198.51.100.7"

    for idx in range(20):
        ok, msg, token, _ = login_or_register_with_password(
            f"ip_attack_{idx}@example.com", "WrongPassword1!", request_ip=request_ip
        )
        assert ok is False
        assert token is None
        assert msg == GENERIC_INVALID_CREDENTIALS

    ok_blocked, msg_blocked, token_blocked, _ = login_or_register_with_password(
        "ip_attack_final@example.com", "WrongPassword1!", request_ip=request_ip
    )
    assert ok_blocked is False
    assert token_blocked is None
    assert msg_blocked == PASSWORD_ATTEMPT_THROTTLE_MESSAGE


# ---------------------------------------------------------------------------
# HIGH regression: no deterministic production secrets and no dev-mode bypass
# against a real production database.
# ---------------------------------------------------------------------------

def test_production_requires_explicit_otp_pepper_and_session_secret(monkeypatch):
    """Missing secrets outside dev mode must raise ValueError instead of deriving secrets."""
    monkeypatch.setenv("AUTH_DEV_MODE", "false")
    monkeypatch.delenv("OTP_PEPPER", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)

    with pytest.raises(ValueError, match="OTP_PEPPER"):
        load_auth_config(reload=True)

    monkeypatch.setenv("OTP_PEPPER", "explicit_pepper_value_1234567890")
    with pytest.raises(ValueError, match="SESSION_SECRET"):
        load_auth_config(reload=True)


def test_render_deployment_context_never_derives_secrets(monkeypatch):
    """Render service metadata must not be used to synthesize predictable secrets."""
    monkeypatch.setenv("AUTH_DEV_MODE", "false")
    monkeypatch.delenv("OTP_PEPPER", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-predictable-id")
    monkeypatch.setenv("RENDER_INSTANCE_ID", "instance-predictable-id")

    with pytest.raises(ValueError, match="OTP_PEPPER"):
        load_auth_config(reload=True)


def test_dev_mode_uses_fixed_public_dev_secrets_only_when_explicit(monkeypatch):
    """Dev mode may fall back to fixed dev secrets; they are clearly non-production."""
    monkeypatch.setenv("AUTH_DEV_MODE", "true")
    monkeypatch.delenv("OTP_PEPPER", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.delenv("TIDB_USER", raising=False)

    cfg = load_auth_config(reload=True)

    assert cfg.auth_dev_mode is True
    assert cfg.otp_pepper == DEV_OTP_PEPPER
    assert cfg.session_secret == DEV_SESSION_SECRET


def test_dev_mode_allowed_with_partial_tidb_config(monkeypatch):
    """A TIDB_HOST without TIDB_USER is not a usable production DB and must not block dev mode."""
    monkeypatch.setenv("AUTH_DEV_MODE", "true")
    monkeypatch.setenv("TIDB_HOST", "gateway01.example.tidbcloud.com")
    monkeypatch.delenv("TIDB_USER", raising=False)
    monkeypatch.delenv("ALLOW_DEV_MODE_WITH_PROD_DB", raising=False)

    cfg = load_auth_config(reload=True)
    assert cfg.auth_dev_mode is True


def test_dev_mode_blocked_when_production_db_configured(monkeypatch):
    """Dev mode must be refused when both TIDB_HOST and TIDB_USER are configured."""
    monkeypatch.setenv("AUTH_DEV_MODE", "true")
    monkeypatch.setenv("TIDB_HOST", "gateway01.example.tidbcloud.com")
    monkeypatch.setenv("TIDB_USER", "root")
    monkeypatch.delenv("ALLOW_DEV_MODE_WITH_PROD_DB", raising=False)

    with pytest.raises(ValueError, match="AUTH_DEV_MODE"):
        load_auth_config(reload=True)

    # Explicit override still permits it (operator decision).
    monkeypatch.setenv("ALLOW_DEV_MODE_WITH_PROD_DB", "true")
    cfg = load_auth_config(reload=True)
    assert cfg.auth_dev_mode is True


def test_hash_password_and_verify_password_roundtrip():
    """Password hashing uses a random salt and constant-time verification."""
    hashed = hash_password("RoundTripPassword1!")
    assert hashed.startswith("pbkdf2_sha256$")
    assert verify_password("RoundTripPassword1!", hashed) is True
    assert verify_password("wrong-password", hashed) is False
    assert verify_password("RoundTripPassword1!", hash_password("RoundTripPassword1!")) is True
    assert hash_password("same") != hash_password("same")

