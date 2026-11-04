"""Integration tests for FastAPI backend authentication and core endpoints."""

import uuid
import pytest
from fastapi.testclient import TestClient
import database as db
from backend.main import app

from auth.config import load_auth_config
from auth.rate_limit import reset_password_attempt_cache

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
    monkeypatch.setenv("OTP_RESEND_COOLDOWN_SECONDS", "0")
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


def _unique_email(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


def _request_otp_code(email: str) -> str:
    resp = client.post("/api/v1/auth/otp/request", json={"email": email})
    assert resp.status_code == 200
    code = resp.json().get("dev_code")
    assert code is not None, "AUTH_DEV_MODE=true should return dev_code"
    return code


def _otp_login(email: str):
    """Create/sign in an OTP user; returns (verify_response, raw_token)."""
    code = _request_otp_code(email)
    resp = client.post("/api/v1/auth/otp/verify", json={"email": email, "code": code})
    assert resp.status_code == 200
    return resp, resp.json().get("token")


def _register_password_user(email: str, password: str = "SecurePassword123!"):
    """Register a password account (OTP proof is now mandatory for new emails)."""
    code = _request_otp_code(email)
    resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password, "otp_code": code}
    )
    assert resp.status_code == 200
    return resp


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
    test_email = _unique_email("tester")

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
    user1_email = _unique_email("user1")
    user2_email = _unique_email("user2")

    # Register/login user 1
    _, u1_token = _otp_login(user1_email)

    # Register/login user 2
    _, u2_token = _otp_login(user2_email)

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
    data1 = list_resp1.json()
    assert len(data1["items"]) == 1
    assert data1["items"][0]["topic"] == "Quantum Computing"

    # User 2 cannot see User 1's article in listing
    list_resp2 = client.get("/api/v1/articles", headers={"Authorization": f"Bearer {u2_token}"})
    assert list_resp2.status_code == 200
    assert len(list_resp2.json()["items"]) == 0

    # User 2 cannot access User 1's article by ID
    get_resp2 = client.get(f"/api/v1/articles/{art_id}", headers={"Authorization": f"Bearer {u2_token}"})
    assert get_resp2.status_code == 404

    # User 1 can access it
    get_resp1 = client.get(f"/api/v1/articles/{art_id}", headers={"Authorization": f"Bearer {u1_token}"})
    assert get_resp1.status_code == 200
    assert get_resp1.json()["topic"] == "Quantum Computing"


def test_telemetry_routes():
    """Verify telemetry stats and cache endpoints work."""
    admin_email = _unique_email("admin")
    _, token = _otp_login(admin_email)

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


def test_password_auth_flow():
    """Verify registration/login with password + mandatory OTP proof for new accounts."""
    email = _unique_email("pwd_user")
    pwd = "SecurePassword123!"

    # 1. New email without OTP proof must NOT auto-register.
    no_proof = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert no_proof.status_code == 401
    assert no_proof.json()["detail"] == "Invalid email or password."
    assert db.get_user_by_email(email) is None

    # 2. Registration with a valid OTP succeeds and sets the password.
    req = client.post("/api/v1/auth/otp/request", json={"email": email})
    dev_code = req.json().get("dev_code")
    assert dev_code is not None

    reg_resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": pwd, "otp_code": dev_code}
    )
    assert reg_resp.status_code == 200
    reg_data = reg_resp.json()
    assert reg_data["success"] is True
    assert reg_data["user"]["email"] == email
    token = reg_data["token"]
    assert token is not None
    assert db.get_user_by_email(email)["password_hash"] is not None

    # Verify access to /me with this token
    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == email

    # 3. Login again with correct password (no OTP needed once a password exists)
    login_resp = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert login_resp.status_code == 200
    assert login_resp.json()["success"] is True

    # 4. Wrong password should fail with 401 and no session token
    bad_resp = client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword!"})
    assert bad_resp.status_code == 401
    assert bad_resp.json()["detail"] == "Invalid email or password."

    # 5. Password login can require an extra valid OTP (2FA)
    otp_req = client.post("/api/v1/auth/otp/request", json={"email": email})
    dev_code = otp_req.json().get("dev_code")
    assert dev_code is not None

    otp_pwd_resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": pwd, "otp_code": dev_code}
    )
    assert otp_pwd_resp.status_code == 200
    assert otp_pwd_resp.json()["success"] is True

    # 6. A correct password with an invalid OTP must not mint a session.
    bad_otp_resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": pwd, "otp_code": "000000"}
    )
    assert bad_otp_resp.status_code == 401
    assert bad_otp_resp.json().get("token") is None


def test_otp_only_account_cannot_be_hijacked_with_password():
    """CRITICAL: existing OTP-only users (password_hash NULL) must not be taken over."""
    email = _unique_email("otp_only")
    # OTP-only account: first verified login creates the user without a password.
    _, _ = _otp_login(email)
    assert db.get_user_by_email(email)["password_hash"] is None

    hijack = client.post("/api/v1/auth/login", json={"email": email, "password": "Attacker123!"})
    assert hijack.status_code == 401
    assert db.get_user_by_email(email)["password_hash"] is None

    # With OTP proof the owner may set a password, then sign in with it.
    code = _request_otp_code(email)
    set_pwd = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "OwnerPassword123!", "otp_code": code}
    )
    assert set_pwd.status_code == 200
    assert db.get_user_by_email(email)["password_hash"] is not None

    login_with_pwd = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "OwnerPassword123!"}
    )
    assert login_with_pwd.status_code == 200


def test_password_login_throttled_after_repeated_failures():
    """DB-backed throttling returns 429 after too many failed password attempts."""
    email = _unique_email("throttle")
    pwd = "SecurePassword123!"
    _register_password_user(email, pwd)

    for _ in range(8):
        bad = client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword123!"})
        assert bad.status_code == 401

    blocked = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert blocked.status_code == 429
    detail = blocked.json()["detail"]
    assert "too many" in detail.lower()


# ---------------------------------------------------------------------------
# CSRF Origin / Referer validation (exact origin matches only)
# ---------------------------------------------------------------------------

def test_csrf_allows_same_origin_post():
    """Same-origin (Origin matches Host) requests must pass."""
    email = _unique_email("csrf_same_origin")
    resp = client.post(
        "/api/v1/auth/otp/request",
        json={"email": email},
        headers={"Origin": "http://testserver"},
    )
    assert resp.status_code == 200


def test_csrf_allows_allowlisted_dev_origin():
    """Explicit localhost dev origins in the allowlist must keep working."""
    email = _unique_email("csrf_localhost")
    resp = client.post(
        "/api/v1/auth/otp/request",
        json={"email": email},
        headers={"Origin": "http://localhost:3000"},
    )
    assert resp.status_code == 200


@pytest.mark.parametrize(
    "evil_origin",
    [
        "http://localhost:3000.evil.com",
        "https://research-studio.onrender.com.attacker.com",
        "http://testserver.evil.com",
        "https://testserver.evil.com:443",
        "null",
    ],
)
def test_csrf_rejects_lookalike_and_malformed_origins(evil_origin):
    """Prefix/lookalike/malformed origins must be rejected with 403 (no startswith bypass)."""
    email = _unique_email("csrf_evil")
    resp = client.post(
        "/api/v1/auth/otp/request",
        json={"email": email},
        headers={"Origin": evil_origin},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "CSRF_ORIGIN_INVALID"


def test_csrf_honors_referer_when_origin_absent():
    """Unsafe requests without Origin are validated via Referer when present."""
    email = _unique_email("csrf_referer")

    same_origin = client.post(
        "/api/v1/auth/otp/request",
        json={"email": email},
        headers={"Referer": "http://testserver/login"},
    )
    assert same_origin.status_code == 200

    evil_referer = client.post(
        "/api/v1/auth/otp/request",
        json={"email": email},
        headers={"Referer": "http://testserver.evil.com/login"},
    )
    assert evil_referer.status_code == 403


def test_csrf_allows_missing_origin_for_header_token_clients():
    """Non-browser clients (no Origin/Referer) using bearer tokens must keep working."""
    email = _unique_email("csrf_token_client")
    _, token = _otp_login(email)

    resp = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Cookie hardening
# ---------------------------------------------------------------------------

def test_default_session_cookie_is_plain_and_not_secure():
    """Local HTTP development uses the plain cookie name without the Secure flag."""
    email = _unique_email("cookie_dev")
    resp = _register_password_user(email)

    set_cookie = resp.headers.get("set-cookie", "")
    assert "session_token=" in set_cookie
    assert "__Host-session_token" not in set_cookie
    assert "Secure" not in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/" in set_cookie


def test_production_environment_sets_host_secure_cookie(monkeypatch):
    """ENVIRONMENT=production must switch to a Secure __Host- cookie."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    email = _unique_email("cookie_prod")
    resp = _register_password_user(email)

    set_cookie = resp.headers.get("set-cookie", "")
    assert "__Host-session_token=" in set_cookie
    assert "Secure" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/" in set_cookie
    assert "Domain=" not in set_cookie

    # Logout must actually clear the __Host- cookie (matching Secure/Path/HttpOnly).
    logout = client.post("/api/v1/auth/logout")
    delete_headers = "; ".join(logout.headers.get_list("set-cookie"))
    assert "__Host-session_token=" in delete_headers
    assert "Secure" in delete_headers
    assert "Max-Age=0" in delete_headers


def test_auth_cookie_secure_flag_alone_enables_host_cookie(monkeypatch):
    """AUTH_COOKIE_SECURE=true is an explicit opt-in for Secure cookies."""
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    email = _unique_email("cookie_flag")
    resp = _register_password_user(email)

    set_cookie = resp.headers.get("set-cookie", "")
    assert "__Host-session_token=" in set_cookie
    assert "Secure" in set_cookie


def test_cookie_max_age_derived_from_session_ttl(monkeypatch):
    """Cookie Max-Age must come from SESSION_TTL_HOURS, not a hardcoded 7 days."""
    monkeypatch.setenv("SESSION_TTL_HOURS", "2")
    load_auth_config(reload=True)

    email = _unique_email("cookie_ttl")
    resp = _register_password_user(email)

    set_cookie = resp.headers.get("set-cookie", "")
    assert "Max-Age=7200" in set_cookie


def test_raw_session_token_hidden_outside_dev_mode(monkeypatch):
    """Browser flows must not receive the raw session token in JSON once dev mode is off."""
    email = _unique_email("token_hidden")
    pwd = "SecurePassword123!"
    reg = _register_password_user(email, pwd)
    assert reg.json()["token"] is not None  # dev mode exposes it for tooling/tests

    monkeypatch.setenv("AUTH_DEV_MODE", "false")
    load_auth_config(reload=True)

    login = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert login.status_code == 200
    assert login.json()["token"] is None
    assert "set-cookie" in login.headers


# ---------------------------------------------------------------------------
# Startup validation (#4): fail fast instead of failing per-request
# ---------------------------------------------------------------------------

def test_lifespan_fails_fast_when_required_secrets_missing(monkeypatch):
    """The lifespan must validate auth config at startup and refuse to boot."""
    import asyncio
    import auth.config as auth_config
    from backend.main import app as fastapi_app, lifespan

    monkeypatch.setenv("AUTH_DEV_MODE", "false")
    monkeypatch.delenv("OTP_PEPPER", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    auth_config._cached_config = None

    async def _start_app():
        async with lifespan(fastapi_app):
            pass

    with pytest.raises(ValueError, match="OTP_PEPPER"):
        asyncio.run(_start_app())


def test_render_domain_allowed_by_csrf():
    """Cloud domains on .onrender.com and .vercel.app must pass CSRF origin check."""
    email = _unique_email("csrf_render")
    resp = client.post(
        "/api/v1/auth/otp/request",
        json={"email": email},
        headers={"Origin": "https://research-and-blog-studio.onrender.com"},
    )
    assert resp.status_code == 200


def test_user_api_keys_endpoints():
    """Authenticated users can save and fetch their masked API keys."""
    email = _unique_email("keys_test")
    pwd = "SecurePassword123!"
    reg = _register_password_user(email, pwd)
    token = reg.json()["token"]

    # 1. Fetch initial keys
    get_res = client.get("/api/v1/auth/keys", headers={"Authorization": f"Bearer {token}"})
    assert get_res.status_code == 200
    data = get_res.json()
    assert "has_gemini" in data
    assert "has_openrouter" in data

    # 2. Save new keys
    post_res = client.post(
        "/api/v1/auth/keys",
        json={"gemini_api_key": "AIzaSyTestGeminiKey123456", "openrouter_api_key": "sk-or-v1-TestKey123456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert post_res.status_code == 200
    assert post_res.json()["status"] == "success"

    # 3. Verify saved and masked keys
    get_res2 = client.get("/api/v1/auth/keys", headers={"Authorization": f"Bearer {token}"})
    assert get_res2.status_code == 200
    data2 = get_res2.json()
    assert data2["has_gemini"] is True
    assert data2["has_openrouter"] is True
    assert "..." in data2["gemini_masked"]
    assert "..." in data2["openrouter_masked"]
