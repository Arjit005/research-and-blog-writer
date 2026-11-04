"""Integration tests for FastAPI backend authentication and core endpoints."""

import os
import uuid
import pytest
from fastapi.testclient import TestClient
import database as db
from backend.main import app

from auth.config import load_auth_config

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """Ensure in-memory SQLite database and test auth mode."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.delenv("TIDB_HOST", raising=False)
    monkeypatch.setenv("AUTH_DEV_MODE", "true")
    monkeypatch.setenv("ALLOW_DEV_MODE_WITH_PROD_DB", "true")
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret-key-32-bytes-long-padding-ok")
    monkeypatch.setenv("OTP_PEPPER", "test_otp_pepper_secret_value_1234567890")
    monkeypatch.setenv("SESSION_SECRET", "test_session_secret_value_1234567890")
    monkeypatch.setenv("OTP_RESEND_COOLDOWN_SECONDS", "0")
    load_auth_config(reload=True)
    db.init_db()
    client.cookies.clear()
    yield
    client.cookies.clear()


def test_healthcheck():
    """Verify healthcheck endpoint reports healthy status and active backend."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "active_backend" in data
    assert "database_live" in data


def test_otp_flow_and_me_profile():
    """Test full passwordless auth cycle: request OTP -> verify -> access /me -> logout."""
    test_email = f"tester_{uuid.uuid4().hex[:8]}@example.com"

    # 1. Request OTP
    req_resp = client.post("/api/v1/auth/otp/request", json={"email": test_email})
    assert req_resp.status_code == 200
    req_data = req_resp.json()
    assert req_data["success"] is True
    dev_code = req_data.get("dev_code")
    assert dev_code is not None, "AUTH_DEV_MODE=true should return dev_code"

    # 2. Verify OTP
    verify_resp = client.post(
        "/api/v1/auth/otp/verify",
        json={"email": test_email, "code": dev_code},
    )
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["success"] is True
    assert verify_data["user"]["email"] == test_email
    token = verify_data["token"]
    assert token is not None

    # Verify cookie was set
    assert "session_token" in verify_resp.cookies or "__Host-session_token" in verify_resp.cookies

    # 3. Access /me profile using cookie
    me_resp = client.get("/api/v1/auth/me", cookies=verify_resp.cookies)
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == test_email

    # Access /me profile using Bearer Authorization Header
    bearer_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert bearer_resp.status_code == 200
    assert bearer_resp.json()["email"] == test_email

    # 4. Logout
    logout_resp = client.post("/api/v1/auth/logout", cookies=verify_resp.cookies)
    assert logout_resp.status_code == 200
    assert logout_resp.json()["success"] is True

    # 5. Accessing /me after logout should return 401
    unauth_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert unauth_resp.status_code == 401


def test_unauthenticated_me():
    """Unauthenticated access to /me should return 401."""
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_articles_crud_and_user_scoping():
    """Verify that articles are properly scoped to authenticated users."""
    uid = uuid.uuid4().hex[:8]
    user1_email = f"user1_{uid}@example.com"
    user2_email = f"user2_{uid}@example.com"

    # Register/login user 1
    r1 = client.post("/api/v1/auth/otp/request", json={"email": user1_email})
    v1 = client.post("/api/v1/auth/otp/verify", json={"email": user1_email, "code": r1.json()["dev_code"]})
    u1_token = v1.json()["token"]

    # Register/login user 2
    r2 = client.post("/api/v1/auth/otp/request", json={"email": user2_email})
    v2 = client.post("/api/v1/auth/otp/verify", json={"email": user2_email, "code": r2.json()["dev_code"]})
    u2_token = v2.json()["token"]

    # User 1 creates an article
    save_resp = client.post(
        "/api/v1/articles",
        headers={"Authorization": f"Bearer {u1_token}"},
        json={
            "topic": "Quantum Computing",
            "content": "# Quantum Computing\n\nIntro content...",
            "mermaid_code": "graph TD\nA-->B",
            "research_notes": "Notes here",
            "metadata": {"tags": ["quantum"]},
        },
    )
    assert save_resp.status_code == 200
    art_id = save_resp.json()["article_id"]

    # User 1 can list their article
    list_resp1 = client.get("/api/v1/articles", headers={"Authorization": f"Bearer {u1_token}"})
    assert list_resp1.status_code == 200
    assert len(list_resp1.json()) == 1
    assert list_resp1.json()[0]["topic"] == "Quantum Computing"

    # User 2 cannot see User 1's article in listing
    list_resp2 = client.get("/api/v1/articles", headers={"Authorization": f"Bearer {u2_token}"})
    assert list_resp2.status_code == 200
    assert len(list_resp2.json()) == 0

    # User 2 cannot access User 1's article by ID
    get_resp2 = client.get(f"/api/v1/articles/{art_id}", headers={"Authorization": f"Bearer {u2_token}"})
    assert get_resp2.status_code == 404

    # User 1 can access it
    get_resp1 = client.get(f"/api/v1/articles/{art_id}", headers={"Authorization": f"Bearer {u1_token}"})
    assert get_resp1.status_code == 200
    assert get_resp1.json()["topic"] == "Quantum Computing"


def test_telemetry_routes():
    """Verify telemetry stats and cache endpoints work."""
    admin_email = "admin@example.com"
    r = client.post("/api/v1/auth/otp/request", json={"email": admin_email})
    v = client.post("/api/v1/auth/otp/verify", json={"email": admin_email, "code": r.json()["dev_code"]})
    token = v.json()["token"]

    resp = client.get("/api/v1/telemetry/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "studio" in data
    assert "total_articles" in data["studio"]
    assert "database" in data

    cache_resp = client.get("/api/v1/telemetry/cache", headers={"Authorization": f"Bearer {token}"})
    assert cache_resp.status_code == 200
    cdata = cache_resp.json()
    assert "total_hits" in cdata
    assert "db_stats" in cdata
