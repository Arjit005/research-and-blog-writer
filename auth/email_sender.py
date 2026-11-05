"""Email sending abstraction with Brevo HTTPS API implementation and testing fakes.

Security requirements:
1. HTTPS POST to https://api.brevo.com/v3/smtp/email using TLS (port 443).
2. Plain text + HTML multipart content.
3. Zero links in authentication emails (prevents phishing/link redirection attacks).
4. Error masking: Never leak API keys, response payloads, or credential details to users.
5. 10-second connect/read timeout.
6. Does not depend on outbound SMTP ports (25, 465, 587) blocked on cloud platforms like Render.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import requests

from auth.config import load_auth_config

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def _build_email_contents(code: str, ttl_minutes: int) -> tuple[str, str, str]:
    """Generate email subject, plain text body, and styled HTML body."""
    subject = "Your sign-in code"
    plain_body = (
        f"Your sign-in code is: {code}\n\n"
        f"This code will expire in {ttl_minutes} minutes.\n"
        "If you did not request this code, you can safely ignore this email.\n"
    )
    html_body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #0f172a; }}
  .card {{ max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; padding: 32px; }}
  .title {{ font-size: 20px; font-weight: 700; color: #1e293b; margin-bottom: 8px; }}
  .desc {{ font-size: 14px; color: #64748b; margin-bottom: 24px; }}
  .otp-box {{ background: #f1f5f9; border: 1px dashed #cbd5e1; border-radius: 6px; padding: 18px; text-align: center; font-size: 32px; font-family: monospace; font-weight: 700; letter-spacing: 6px; color: #4338ca; margin-bottom: 24px; }}
  .footer {{ font-size: 12px; color: #94a3b8; line-height: 1.5; }}
</style>
</head>
<body>
  <div class="card">
    <div class="title">AI Research & Visual Blog Studio</div>
    <div class="desc">Enter the 6-digit code below to securely verify your identity:</div>
    <div class="otp-box">{code}</div>
    <div class="footer">
      This code will expire in {ttl_minutes} minutes.<br>
      If you did not request this code, please ignore this message. Never share this code with anyone.
    </div>
  </div>
</body>
</html>
"""
    return subject, plain_body, html_body


class EmailSender:
    """Abstract interface for email dispatching."""

    def send_otp_email(self, to_email: str, code: str, ttl_minutes: int) -> bool:
        """Send verification code email. Returns True on success, raises RuntimeError on failure."""
        raise NotImplementedError


class FakeEmailSender(EmailSender):
    """Test fake capturing sent messages in memory for unit assertions."""

    def __init__(self, should_fail: bool = False):
        self.sent_messages: List[dict] = []
        self.should_fail = should_fail

    def send_otp_email(self, to_email: str, code: str, ttl_minutes: int) -> bool:
        if self.should_fail:
            raise RuntimeError("Simulated email delivery failure for testing.")
        self.sent_messages.append({
            "to": to_email,
            "code": code,
            "ttl_minutes": ttl_minutes,
        })
        return True


class BrevoApiEmailSender(EmailSender):
    """Production email sender using Brevo's HTTPS REST API (api.brevo.com/v3/smtp/email)."""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def send_otp_email(self, to_email: str, code: str, ttl_minutes: int) -> bool:
        cfg = load_auth_config()

        if not cfg.brevo_api_key:
            raise RuntimeError("Email delivery is not configured on this server. Please contact the administrator.")

        subject, plain_body, html_body = _build_email_contents(code, ttl_minutes)

        headers = {
            "accept": "application/json",
            "api-key": cfg.brevo_api_key.strip(),
            "content-type": "application/json",
        }

        payload = {
            "sender": {
                "name": cfg.email_sender_name or "Research & Blog Writer",
                "email": cfg.email_sender_address or "arjit04554@gmail.com",
            },
            "to": [
                {"email": to_email.strip()}
            ],
            "subject": subject,
            "htmlContent": html_body,
            "textContent": plain_body,
        }

        try:
            resp = requests.post(
                BREVO_API_URL,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout:
            logger.error("Brevo API request timed out after %s seconds", self.timeout)
            raise RuntimeError("Email delivery server timed out. Please try again shortly.")
        except requests.exceptions.RequestException as exc:
            logger.error("Brevo API request network error: %s", type(exc).__name__)
            raise RuntimeError("Unable to communicate with email delivery server.")

        # Brevo returns 201 Created on successful email dispatch
        if resp.status_code in (200, 201):
            return True

        # Error handling with credential masking
        status = resp.status_code
        logger.error("Brevo API delivery failed with HTTP %s", status)
        if status == 401:
            raise RuntimeError("Authentication failed with the email delivery service.")
        elif status == 400:
            raise RuntimeError("Invalid email delivery request. Please verify the recipient address.")
        else:
            raise RuntimeError(f"Email delivery service returned an error (HTTP {status}). Please try again shortly.")


# Backwards compatibility alias for any existing imports
SMTPEmailSender = BrevoApiEmailSender


# Global active sender instance (can be swapped in unit tests)
_global_sender: Optional[EmailSender] = None


def get_email_sender() -> EmailSender:
    """Retrieve active email sender implementation."""
    global _global_sender
    if _global_sender is not None:
        return _global_sender
    return BrevoApiEmailSender()


def set_email_sender_override(sender: Optional[EmailSender]):
    """Override active sender for unit testing."""
    global _global_sender
    _global_sender = sender
