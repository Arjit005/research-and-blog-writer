"""Tests for Google Sign-In with Firebase Authentication, account linking,
and database constraint handling.
"""

import uuid
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

import database as db
import db_schema
from auth.config import load_auth_config
from auth.rate_limit import reset_password_attempt_cache
from auth.service import verify_google_token_and_login
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """Ensure in-memory SQLite database and test auth mode."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.delenv("TIDB_HOST", raising=False)
    monkeypatch.delenv("TIDB_USER", raising=False)
    monkeypatch.setenv("AUTH_DEV_MODE", "true")
    monkeypatch.setenv("ALLOW_DEV_MODE_WITH_PROD_DB", "true")
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret-key-32-bytes-long-padding-ok")
    monkeypatch.setenv("OTP_PEPPER", "test_otp_pepper_secret_value_1234567890")
    monkeypatch.setenv("SESSION_SECRET", "test_session_secret_value_1234567890")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "loyal-synthesis-477817-e7")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)
    monkeypatch.delenv("AUTH_COOKIE_SECURE", raising=False)
    load_auth_config(reload=True)
    reset_password_attempt_cache()
    db.init_db()
    client.cookies.clear()
    yield
    client.cookies.clear()
    reset_password_attempt_cache()


def _unique_email(prefix: str = "google_user") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


class TestGoogleAuthService:
    """Unit tests for verify_google_token_and_login service."""

    @patch("auth.service.google_id_token.verify_firebase_token")
    def test_new_user_creation_success(self, mock_verify):
        email = _unique_email("new_google")
        google_id = f"gid_{uuid.uuid4().hex[:12]}"
        mock_verify.return_value = {
            "sub": google_id,
            "email": email,
            "email_verified": True,
            "aud": "loyal-synthesis-477817-e7",
        }

        success, msg, token, user = verify_google_token_and_login("fake-token-1234567890")
        assert success is True
        assert user["email"] == email
        assert user["google_id"] == google_id
        assert bool(token) is True

        # Check DB record
        db_user = db.get_user_by_google_id(google_id)
        assert db_user is not None
        assert db_user["email"] == email

    @patch("auth.service.google_id_token.verify_firebase_token")
    def test_existing_user_linking(self, mock_verify):
        email = _unique_email("existing_otp")
        google_id = f"gid_{uuid.uuid4().hex[:12]}"

        # Existing user created via OTP (no google_id)
        created = db.get_or_create_user(email)
        assert created.get("google_id") is None

        mock_verify.return_value = {
            "sub": google_id,
            "email": email,
            "email_verified": True,
            "aud": "loyal-synthesis-477817-e7",
        }

        success, msg, token, user = verify_google_token_and_login("fake-token-4567890123")
        assert success is True
        assert user["id"] == created["id"]
        assert user["email"] == email
        assert user["google_id"] == google_id

        # Verify google_id is persisted
        db_user = db.get_user_by_google_id(google_id)
        assert db_user is not None
        assert db_user["id"] == created["id"]

    @patch("auth.service.google_id_token.verify_firebase_token")
    def test_unverified_email_fails(self, mock_verify):
        email = _unique_email("unverified")
        mock_verify.return_value = {
            "sub": "gid_unverified",
            "email": email,
            "email_verified": False,
        }

        success, msg, token, user = verify_google_token_and_login("fake-token-unverified-123")
        assert success is False
        assert "not verified" in msg

    @patch("auth.service.google_id_token.verify_firebase_token")
    def test_invalid_token_fails(self, mock_verify):
        mock_verify.side_effect = ValueError("Token has expired")

        success, msg, token, user = verify_google_token_and_login("fake-expired-token-123")
        assert success is False
        assert "Invalid or expired" in msg

    @patch("auth.service.google_id_token.verify_firebase_token")
    def test_disabled_account_fails(self, mock_verify):
        email = _unique_email("disabled")
        google_id = f"gid_{uuid.uuid4().hex[:12]}"
        user = db.get_or_create_user(email)
        with db.get_connection() as (conn, is_tidb):
            conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user["id"],))
            conn.commit()

        mock_verify.return_value = {
            "sub": google_id,
            "email": email,
            "email_verified": True,
            "aud": "loyal-synthesis-477817-e7",
        }

        success, msg, token, user = verify_google_token_and_login("fake-token-disabled-123")
        assert success is False
        assert "disabled" in msg.lower()

    @patch("auth.service.google_id_token.verify_firebase_token")
    def test_google_id_collision_prevention(self, mock_verify):
        # User A linked to google_id_1
        email_a = _unique_email("user_a")
        google_id_1 = f"gid_{uuid.uuid4().hex[:12]}"
        u_a = db.get_or_create_user(email_a)
        db.link_user_google_id(u_a["id"], google_id_1)

        # Attacker tries to use google_id_1 with User B's email
        email_b = _unique_email("user_b")
        mock_verify.return_value = {
            "sub": google_id_1,
            "email": email_b,
            "email_verified": True,
            "aud": "loyal-synthesis-477817-e7",
        }

        success, msg, token, user = verify_google_token_and_login("fake-token-collision-123")
        assert success is False
        assert "already linked to a different email" in msg


class TestGoogleAuthEndpoint:
    """Integration tests for POST /api/v1/auth/google."""

    @patch("auth.service.google_id_token.verify_firebase_token")
    def test_endpoint_login_success(self, mock_verify):
        email = _unique_email("endpoint_user")
        google_id = f"gid_{uuid.uuid4().hex[:12]}"
        mock_verify.return_value = {
            "sub": google_id,
            "email": email,
            "email_verified": True,
            "aud": "loyal-synthesis-477817-e7",
        }

        resp = client.post("/api/v1/auth/google", json={"id_token": "valid-id-token-12345"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["user"]["email"] == email
        assert "auth_session" in resp.cookies or "token" in data

    @patch("auth.service.google_id_token.verify_firebase_token")
    def test_endpoint_invalid_token(self, mock_verify):
        mock_verify.side_effect = ValueError("Invalid signature")

        resp = client.post("/api/v1/auth/google", json={"id_token": "bad-token-invalid-signature"})
        assert resp.status_code == 401
        assert "Invalid or expired" in resp.json()["detail"]

    @patch("auth.service.google_id_token.verify_firebase_token")
    def test_endpoint_unverified_email(self, mock_verify):
        mock_verify.return_value = {
            "sub": "gid_bad",
            "email": "unverified@example.com",
            "email_verified": False,
        }

        resp = client.post("/api/v1/auth/google", json={"id_token": "unverified-token-12345"})
        assert resp.status_code == 400
        assert "not verified" in resp.json()["detail"]


class TestDatabaseGoogleIdSafety:
    """Verify unique constraint and concurrency handling."""

    def test_single_unique_constraint_schema(self):
        """Ensure only one UNIQUE constraint/index exists for google_id."""
        user_def = [t for t in db_schema.TABLE_DEFINITIONS if t[0] == "users"][0]
        tidb_ddl = user_def[1]
        sqlite_ddl = user_def[2]

        assert "google_id     VARCHAR(255) NULL UNIQUE" in tidb_ddl
        assert "google_id     TEXT NULL UNIQUE" in sqlite_ddl
        # TiDB DDL must define google_id exactly once
        assert tidb_ddl.count("google_id") == 1

    def test_link_user_google_id_atomic(self):
        email = _unique_email("link_atomic")
        u = db.get_or_create_user(email)
        gid = f"gid_{uuid.uuid4().hex[:10]}"

        ok, msg = db.link_user_google_id(u["id"], gid)
        assert ok is True
        assert msg == "LINKED_SUCCESSFULLY"

        # Linking again with same gid is idempotent
        ok2, msg2 = db.link_user_google_id(u["id"], gid)
        assert ok2 is True
        assert msg2 == "ALREADY_LINKED"

        # Linking another user to the same gid fails safely
        u2 = db.get_or_create_user(_unique_email("other"))
        ok3, msg3 = db.link_user_google_id(u2["id"], gid)
        assert ok3 is False
        assert msg3 == "GOOGLE_ACCOUNT_ALREADY_LINKED"
