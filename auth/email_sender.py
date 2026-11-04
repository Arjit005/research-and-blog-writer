"""Email sending abstraction with secure SMTP implementation and testing fakes.

Security requirements:
1. STARTTLS/SMTPS with strict SSL validation context (ssl.create_default_context()).
2. Plain text + HTML multipart message.
3. Zero links in authentication emails (prevents phishing/link redirection attacks).
4. Error masking: Never leak SMTP server responses or credential details to users.
5. 10-second connect/read timeout.
"""

from __future__ import annotations

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from auth.config import load_auth_config


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
            raise RuntimeError("Simulated SMTP delivery failure for testing.")
        self.sent_messages.append({
            "to": to_email,
            "code": code,
            "ttl_minutes": ttl_minutes,
        })
        return True


class SMTPEmailSender(EmailSender):
    """Production SMTP sender using STARTTLS/SSL with credential masking."""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def send_otp_email(self, to_email: str, code: str, ttl_minutes: int) -> bool:
        cfg = load_auth_config()

        if not cfg.smtp_host:
            raise RuntimeError("Email delivery is not configured on this server. Please contact the administrator.")

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

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = cfg.smtp_from or "noreply@research-studio.local"
        msg["To"] = to_email

        part1 = MIMEText(plain_body, "plain", "utf-8")
        part2 = MIMEText(html_body, "html", "utf-8")
        msg.attach(part1)
        msg.attach(part2)

        try:
            context = ssl.create_default_context()
            if cfg.smtp_port == 465 or not cfg.smtp_use_tls:
                with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=self.timeout, context=context) as server:
                    if cfg.smtp_user and cfg.smtp_password:
                        server.login(cfg.smtp_user, cfg.smtp_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=self.timeout) as server:
                    if cfg.smtp_use_tls:
                        server.starttls(context=context)
                    if cfg.smtp_user and cfg.smtp_password:
                        server.login(cfg.smtp_user, cfg.smtp_password)
                    server.send_message(msg)
            return True
        except smtplib.SMTPAuthenticationError:
            raise RuntimeError("Authentication failed with the email delivery server.")
        except (smtplib.SMTPException, OSError) as e:
            raise RuntimeError(f"Unable to send verification email. Please try again shortly. (Code: {type(e).__name__})")


# Global active sender instance (can be swapped in unit tests)
_global_sender: Optional[EmailSender] = None


def get_email_sender() -> EmailSender:
    """Retrieve active email sender implementation."""
    global _global_sender
    if _global_sender is not None:
        return _global_sender
    return SMTPEmailSender()


def set_email_sender_override(sender: Optional[EmailSender]):
    """Override active sender for unit testing."""
    global _global_sender
    _global_sender = sender
