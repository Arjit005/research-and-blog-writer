"""Unit tests for BrevoApiEmailSender HTTPS REST API implementation."""

from unittest.mock import MagicMock, patch
import pytest
import requests

from auth.config import load_auth_config
from auth.email_sender import BrevoApiEmailSender, BREVO_API_URL


@pytest.fixture(autouse=True)
def setup_brevo_config(monkeypatch):
    """Provide configured Brevo API environment for unit tests."""
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test-mock-api-key-12345")
    monkeypatch.setenv("BREVO_SENDER_NAME", "Research & Blog Writer")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "arjit04554@gmail.com")
    monkeypatch.setenv("AUTH_DEV_MODE", "false")
    monkeypatch.setenv("OTP_PEPPER", "test_otp_pepper_secret_value_1234567890")
    monkeypatch.setenv("SESSION_SECRET", "test_session_secret_value_1234567890")
    load_auth_config(reload=True)
    yield
    load_auth_config(reload=True)


class TestBrevoApiEmailSender:
    """Test suite for Brevo HTTPS API email delivery."""

    @patch("auth.email_sender.requests.post")
    def test_send_otp_email_success_201(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"messageId": "<mock-message-id-123@brevo.com>"}
        mock_post.return_value = mock_resp

        sender = BrevoApiEmailSender(timeout=5.0)
        result = sender.send_otp_email("user@example.com", "123456", 5)

        assert result is True
        mock_post.assert_called_once()
        call_args, call_kwargs = mock_post.call_args
        assert call_args[0] == BREVO_API_URL

        payload = call_kwargs["json"]
        assert payload["sender"]["name"] == "Research & Blog Writer"
        assert payload["sender"]["email"] == "arjit04554@gmail.com"
        assert payload["to"] == [{"email": "user@example.com"}]
        assert payload["subject"] == "Your sign-in code"
        assert "123456" in payload["textContent"]
        assert "123456" in payload["htmlContent"]

        headers = call_kwargs["headers"]
        assert headers["accept"] == "application/json"
        assert headers["api-key"] == "xkeysib-test-mock-api-key-12345"

    @patch("auth.email_sender.requests.post")
    def test_send_otp_email_success_200(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"messageId": "<mock-message-id-200@brevo.com>"}
        mock_post.return_value = mock_resp

        sender = BrevoApiEmailSender(timeout=5.0)
        assert sender.send_otp_email("user2@example.com", "654321", 10) is True

    @patch("auth.email_sender.requests.post")
    def test_send_otp_email_timeout_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")

        sender = BrevoApiEmailSender(timeout=5.0)
        with pytest.raises(RuntimeError, match="Email delivery server timed out"):
            sender.send_otp_email("user@example.com", "123456", 5)

    @patch("auth.email_sender.requests.post")
    def test_send_otp_email_network_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

        sender = BrevoApiEmailSender(timeout=5.0)
        with pytest.raises(RuntimeError, match="Unable to communicate with email delivery server"):
            sender.send_otp_email("user@example.com", "123456", 5)

    @patch("auth.email_sender.requests.post")
    def test_send_otp_email_unauthorized_401(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Key not found"
        mock_post.return_value = mock_resp

        sender = BrevoApiEmailSender(timeout=5.0)
        with pytest.raises(RuntimeError, match="Authentication failed with the email delivery service"):
            sender.send_otp_email("user@example.com", "123456", 5)

    @patch("auth.email_sender.requests.post")
    def test_send_otp_email_bad_request_400(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Invalid email"
        mock_post.return_value = mock_resp

        sender = BrevoApiEmailSender(timeout=5.0)
        with pytest.raises(RuntimeError, match="Invalid email delivery request"):
            sender.send_otp_email("invalid-email", "123456", 5)

    def test_missing_api_key_raises_runtime_error(self, monkeypatch):
        monkeypatch.delenv("BREVO_API_KEY", raising=False)
        load_auth_config(reload=True)

        sender = BrevoApiEmailSender(timeout=5.0)
        with pytest.raises(RuntimeError, match="Email delivery is not configured on this server"):
            sender.send_otp_email("user@example.com", "123456", 5)
