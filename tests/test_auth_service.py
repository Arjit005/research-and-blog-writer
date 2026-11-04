"""Unit tests for auth service anti-enumeration, domain allowlists, audit trail, and sender handling."""

import pytest

from auth.config import load_auth_config
from auth.service import request_otp, verify_otp_and_login, GENERIC_DISPATCH_MESSAGE
from auth.email_sender import FakeEmailSender, set_email_sender_override
from auth.otp import mask_email
import database as db


@pytest.fixture(autouse=True)
def setup_auth_env(monkeypatch):
    monkeypatch.setenv("OTP_PEPPER", "test_otp_pepper_secret_value_1234567890")
    monkeypatch.setenv("SESSION_SECRET", "test_session_secret_value_1234567890")
    monkeypatch.setenv("AUTH_DEV_MODE", "false")
    monkeypatch.setenv("OTP_RESEND_COOLDOWN_SECONDS", "0")  # Disable cooldown for service testing
    load_auth_config(reload=True)


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
