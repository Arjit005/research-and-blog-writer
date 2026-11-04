"""Integration tests for Research Job Model, Concurrency Guards, and Resumable SSE Events."""

import os
import uuid
import pytest
from fastapi.testclient import TestClient

import database as db
from auth.config import load_auth_config
from backend.main import app

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


def _login_user():
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/v1/auth/otp/request", json={"email": email})
    code = r.json()["dev_code"]
    v = client.post("/api/v1/auth/otp/verify", json={"email": email, "code": code})
    return v.json()["token"], v.json()["user"]


def test_job_ledger_methods():
    """Verify database job model and event sequence numbering."""
    run_id = f"test_run_{uuid.uuid4().hex[:8]}"
    db.create_research_job(run_id=run_id, topic="Graph Neural Networks", user_id=1)

    job = db.get_research_job(run_id)
    assert job is not None
    assert job["topic"] == "Graph Neural Networks"
    assert job["status"] == "pending"

    # Append events
    seq1 = db.append_job_event(run_id, "step", {"detail": "Starting researcher"})
    seq2 = db.append_job_event(run_id, "step", {"detail": "Searching arXiv"})
    seq3 = db.append_job_event(run_id, "completed", {"article_id": 42})

    assert seq1 == 1
    assert seq2 == 2
    assert seq3 == 3

    # Fetch all events
    events = db.get_job_events(run_id, after_seq_id=0)
    assert len(events) == 3
    assert events[0]["seq_id"] == 1
    assert events[1]["payload"]["detail"] == "Searching arXiv"

    # Resume from seq 2
    resumed = db.get_job_events(run_id, after_seq_id=2)
    assert len(resumed) == 1
    assert resumed[0]["seq_id"] == 3
    assert resumed[0]["event_type"] == "completed"


def test_create_run_and_concurrency_guard(monkeypatch):
    """Test POST /api/v1/runs and verify 1 concurrent run per user enforcement."""
    token, user = _login_user()

    # Stub out _execute_run_worker so it doesn't invoke real CrewAI in fast unit tests
    def dummy_worker(run_id, topic, user_id, tone, audience, target_length):
        pass

    monkeypatch.setattr("backend.routes.research._execute_run_worker", dummy_worker)

    # 1. First run creates successfully
    resp1 = client.post(
        "/api/v1/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={"topic": "Autonomous AI Agents"},
    )
    assert resp1.status_code == 200
    run_id = resp1.json()["run_id"]
    assert run_id.startswith("run_")

    # Set status to running in DB to simulate active execution
    db.update_research_job(run_id, status="running")

    # 2. Second concurrent run request must return 409 Conflict
    resp2 = client.post(
        "/api/v1/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={"topic": "Another Topic"},
    )
    assert resp2.status_code == 409
    assert "already have a research run in progress" in resp2.json()["detail"]

    # 3. Once job is completed, new run is permitted
    db.update_research_job(run_id, status="completed")
    resp3 = client.post(
        "/api/v1/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={"topic": "Third Topic"},
    )
    assert resp3.status_code == 200


def test_run_events_sse_resumption():
    """Verify SSE streaming endpoint formats events and respects Last-Event-ID."""
    token, user = _login_user()
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    db.create_research_job(run_id=run_id, topic="SSE Test", user_id=user["id"])
    db.append_job_event(run_id, "step", {"detail": "Step 1"})
    db.append_job_event(run_id, "step", {"detail": "Step 2"})
    db.append_job_event(run_id, "completed", {"status": "done"})
    db.update_research_job(run_id, status="completed")

    # Full stream without Last-Event-ID
    with client.stream(
        "GET",
        f"/api/v1/runs/{run_id}/events",
        headers={"Authorization": f"Bearer {token}"},
    ) as response:
        assert response.status_code == 200
        content = response.read().decode("utf-8")
        assert "id: 1" in content
        assert "event: step" in content
        assert "id: 2" in content
        assert "id: 3" in content
        assert "event: completed" in content

    # Resumed stream starting after event ID 2
    with client.stream(
        "GET",
        f"/api/v1/runs/{run_id}/events",
        headers={"Authorization": f"Bearer {token}", "Last-Event-ID": "2"},
    ) as response:
        assert response.status_code == 200
        content = response.read().decode("utf-8")
        assert "id: 1" not in content
        assert "id: 2" not in content
        assert "id: 3" in content
        assert "event: completed" in content


def test_cancel_run():
    """Verify POST /api/v1/runs/{run_id}/cancel marks job as cancelled."""
    token, user = _login_user()
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    db.create_research_job(run_id=run_id, topic="Cancel Me", user_id=user["id"])

    # Cancel the run
    resp = client.post(
        f"/api/v1/runs/{run_id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Check status
    status_resp = client.get(
        f"/api/v1/runs/{run_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "cancelled"
