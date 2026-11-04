"""Regression tests for database hardening.

Covers verified findings:
1. job_events (run_id, seq_id) uniqueness + atomic sequence allocation.
3. Job lifecycle: terminal-state freeze, restart recovery, terminal event ordering.
4. revision_num allocation race retry.
8. TiDB hazards: datetime normalization, honest fallback, no blind write replay.
10. List/pagination bounds and summary-only article listing.
11. Legacy unowned (user_id IS NULL) row exposure gating + one-shot claim.
Plus the auth password-attempt rate-limit primitives consumed by auth/service.py.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

import database as db


# ---------------------------------------------------------------------------
# 1. job_events sequence integrity
# ---------------------------------------------------------------------------

def test_job_event_duplicate_sequence_is_rejected():
    """UNIQUE(run_id, seq_id) must be enforced by the schema (not just an index)."""
    db.append_job_event("run_dup", "step", {"n": 1})

    with db.get_connection() as (conn, is_tidb):
        assert is_tidb is False
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO job_events (run_id, seq_id, event_type, payload) "
                "VALUES ('run_dup', 1, 'step', '{}')"
            )


def test_append_job_event_concurrent_sequences_are_unique_and_monotonic():
    """N threads appending concurrently must yield exactly 1..N without collisions."""
    run_id = "run_concurrent_seq"
    n_threads, per_thread = 6, 2
    sequences: list[int] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            for i in range(per_thread):
                seq = db.append_job_event(run_id, "step", {"thread": threading.get_ident(), "i": i})
                with lock:
                    sequences.append(seq)
        except BaseException as exc:  # pragma: no cover - surfaced below
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(n_threads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "concurrent append_job_event deadlocked"

    assert not errors, f"append_job_event raised under concurrency: {errors}"
    expected_total = n_threads * per_thread
    assert sorted(sequences) == list(range(1, expected_total + 1))
    # Durable ledger must agree with the numbers returned to callers.
    stored = [ev["seq_id"] for ev in db.get_job_events(run_id)]
    assert stored == sorted(sequences)


# ---------------------------------------------------------------------------
# 3. Job lifecycle hardening
# ---------------------------------------------------------------------------

def test_update_research_job_cannot_resurrect_terminal_jobs():
    db.create_research_job(run_id="run_cancel", topic="Cancel lifecycle")
    assert db.update_research_job("run_cancel", status="cancelled") is True

    # A late worker callback must not flip a cancelled job back to running.
    assert db.update_research_job("run_cancel", status="running") is False
    job = db.get_research_job("run_cancel")
    assert job["status"] == "cancelled"

    # Metadata-only updates remain allowed for terminal jobs.
    assert db.update_research_job("run_cancel", trace_url="https://trace.example/run") is True
    assert db.get_research_job("run_cancel")["trace_url"] == "https://trace.example/run"

    # Failed/completed are equally frozen for status transitions.
    db.create_research_job(run_id="run_done", topic="Done lifecycle")
    db.update_research_job("run_done", status="completed")
    assert db.update_research_job("run_done", status="running") is False
    assert db.update_research_job("run_done", status="failed") is False

    # Unknown run ids report no update.
    assert db.update_research_job("run_missing", status="running") is False


def test_recover_interrupted_jobs_fails_orphaned_jobs_and_logs_terminal_event():
    db.create_research_job(run_id="run_orphan_pending", topic="Orphan pending")
    db.create_research_job(run_id="run_orphan_running", topic="Orphan running")
    db.update_research_job("run_orphan_running", status="running")
    db.create_research_job(run_id="run_finished", topic="Finished")
    db.update_research_job("run_finished", status="completed")

    recovered = db.recover_interrupted_jobs()
    assert recovered == 2

    for run_id in ("run_orphan_pending", "run_orphan_running"):
        job = db.get_research_job(run_id)
        assert job["status"] == "failed"
        assert "interrupted by server restart" in job["error_message"]
        events = db.get_job_events(run_id)
        assert events[-1]["event_type"] == "error"
        assert "server restart" in events[-1]["payload"]["message"]

    assert db.get_research_job("run_finished")["status"] == "completed"


def test_recover_interrupted_jobs_respects_staleness_window():
    db.create_research_job(run_id="run_fresh", topic="Fresh job")
    db.update_research_job("run_fresh", status="running")

    # Fresh job is not stale: nothing recovered.
    assert db.recover_interrupted_jobs(stale_after_seconds=3600) == 0
    assert db.get_research_job("run_fresh")["status"] == "running"

    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    with db.get_connection() as (conn, is_tidb):
        assert is_tidb is False
        conn.execute("UPDATE research_jobs SET updated_at = ? WHERE run_id = 'run_fresh'", (stale_ts,))

    assert db.recover_interrupted_jobs(stale_after_seconds=60) == 1
    assert db.get_research_job("run_fresh")["status"] == "failed"


def test_save_article_with_initial_revision_is_atomic_pair():
    article_id, revision_num = db.save_article_with_initial_revision(
        topic="Atomic pair", content="# Atomic\n\nBody text", user_id=1
    )
    assert revision_num == 1
    revisions = db.get_article_revisions(article_id)
    assert len(revisions) == 1
    assert revisions[0]["revision_num"] == 1
    assert revisions[0]["content"] == "# Atomic\n\nBody text"
    assert db.get_article(article_id)["content"] == "# Atomic\n\nBody text"


# ---------------------------------------------------------------------------
# 4. revision_num race
# ---------------------------------------------------------------------------

def test_concurrent_revision_inserts_do_not_lose_snapshots():
    """Concurrent MAX+1 allocations must retry and produce contiguous unique nums."""
    article_id = db.save_article("Revision race", "initial content")
    n_threads, per_thread = 6, 2
    numbers: list[int] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            for i in range(per_thread):
                num = db.save_article_revision(
                    article_id, f"content {threading.get_ident()}-{i}", summary="concurrent"
                )
                with lock:
                    numbers.append(num)
        except BaseException as exc:  # pragma: no cover - surfaced below
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(n_threads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "concurrent revision insert deadlocked"

    assert not errors, f"save_article_revision raised under concurrency: {errors}"
    expected_total = n_threads * per_thread
    assert sorted(numbers) == list(range(1, expected_total + 1))
    stored = [r["revision_num"] for r in db.get_article_revisions(article_id, limit=100)]
    assert sorted(stored) == list(range(1, expected_total + 1))


# ---------------------------------------------------------------------------
# 8. TiDB hazards
# ---------------------------------------------------------------------------

def test_row_normalization_converts_datetimes_decimals_and_bytes():
    normalized = db._row_to_dict({
        "created_at": datetime(2026, 1, 2, 3, 4, 5),
        "duration": Decimal("12.5"),
        "count": Decimal("7"),
        "blob": b"hello",
        "plain": "text",
    })
    assert normalized["created_at"] == "2026-01-02 03:04:05"
    assert normalized["duration"] == 12.5
    assert normalized["count"] == 7
    assert normalized["blob"] == "hello"
    assert normalized["plain"] == "text"


def test_reader_normalizes_tidb_dictcursor_datetimes_to_iso(monkeypatch):
    """A TiDB DictCursor row must surface datetimes as ISO strings (str Pydantic fields)."""
    from contextlib import contextmanager

    class _Cursor:
        def execute(self, sql, params=()):  # noqa: ARG002
            return self

        def fetchone(self):
            return {
                "id": 7,
                "user_id": 1,
                "topic": "TiDB topic",
                "content": "content",
                "word_count": 1,
                "tone": "Professional",
                "audience": "Engineers",
                "target_length": "Standard",
                "generation_time_sec": 1.5,
                "tokens_used": Decimal("5"),
                "created_at": datetime(2026, 1, 2, 3, 4, 5),
                "updated_at": datetime(2026, 1, 2, 3, 4, 6),
            }

    class _Conn:
        def cursor(self):
            return _Cursor()

    @contextmanager
    def _fake_connection():
        yield _Conn(), True  # is_tidb=True -> pymysql-style dict rows

    monkeypatch.setattr(db, "get_connection", _fake_connection)
    row = db.get_article(7)
    assert row["created_at"] == "2026-01-02 03:04:05"
    assert row["updated_at"] == "2026-01-02 03:04:06"
    assert row["tokens_used"] == 5


class _FakeOperationalError(Exception):
    """Stands in for pymysql.err.OperationalError without requiring pymysql."""


class _FakeCursor:
    def __init__(self, fail_times: int, exc: BaseException):
        self.calls = 0
        self.fail_times = fail_times
        self.exc = exc

    def execute(self, sql, params=()):  # noqa: ARG002
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        return self


class _FakeConn:
    def __init__(self, cursor: _FakeCursor):
        self._cursor = cursor
        self.pings = 0

    def cursor(self):
        return self._cursor

    def ping(self, reconnect=False):  # noqa: ARG002
        self.pings += 1


def test_exec_retries_read_only_statements_once_but_never_writes():
    # Read-only statement: one reconnect retry is allowed.
    read_cursor = _FakeCursor(1, _FakeOperationalError("Lost connection (2013)"))
    read_conn = _FakeConn(read_cursor)
    db._exec(read_conn, True, "SELECT 1 AS alive")
    assert read_cursor.calls == 2
    assert read_conn.pings == 1

    # INSERT: never replayed blindly after a transport error.
    write_cursor = _FakeCursor(1, _FakeOperationalError("Lost connection (2013)"))
    write_conn = _FakeConn(write_cursor)
    with pytest.raises(_FakeOperationalError):
        db._exec(write_conn, True, "INSERT INTO job_events (run_id) VALUES (?)")
    assert write_cursor.calls == 1
    assert write_conn.pings == 0

    # Non-connection errors are not treated as reconnect-worthy.
    other_cursor = _FakeCursor(1, ValueError("syntax error"))
    other_conn = _FakeConn(other_cursor)
    with pytest.raises(ValueError):
        db._exec(other_conn, True, "SELECT 1")
    assert other_cursor.calls == 1


def test_tidb_configured_does_not_silently_fall_back_to_sqlite(monkeypatch):
    monkeypatch.setenv("TIDB_HOST", "fake-tidb.example.com")
    monkeypatch.setenv("TIDB_USER", "fake-user")
    monkeypatch.delenv("ALLOW_SQLITE_FALLBACK", raising=False)

    def _boom():
        raise RuntimeError("cluster unreachable")

    monkeypatch.setattr(db, "_connect_tidb", _boom)

    with pytest.raises(db.DatabaseConnectionError) as excinfo:
        with db.get_connection() as (_conn, _is_tidb):
            pass
    assert "ALLOW_SQLITE_FALLBACK" in str(excinfo.value)

    # healthcheck must be honest rather than claiming a live (SQLite) database.
    is_live, message = db.check_tidb_live_status()
    assert is_live is False
    assert "error" in message.lower()


def test_tidb_fallback_allowed_only_with_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("TIDB_HOST", "fake-tidb.example.com")
    monkeypatch.setenv("TIDB_USER", "fake-user")
    monkeypatch.setenv("ALLOW_SQLITE_FALLBACK", "true")
    monkeypatch.setattr(db, "_connect_tidb", lambda: (_ for _ in ()).throw(RuntimeError("down")))

    with db.get_connection() as (_conn, is_tidb):
        assert is_tidb is False


# ---------------------------------------------------------------------------
# 10. Lists / pagination bounds
# ---------------------------------------------------------------------------

def test_article_summaries_exclude_content_and_support_offset_pagination():
    article_ids = [db.save_article(f"Topic {i}", f"Content {i} " * 20, user_id=1) for i in range(5)]

    first_page = db.get_article_summaries(limit=2, offset=0, user_id=1)
    second_page = db.get_article_summaries(limit=2, offset=2, user_id=1)
    assert len(first_page) == 2
    assert len(second_page) == 2
    assert all("content" not in row for row in first_page + second_page)
    assert {row["id"] for row in first_page}.isdisjoint({row["id"] for row in second_page})
    assert {row["id"] for row in first_page + second_page}.issubset(set(article_ids))

    full_rows = db.get_articles(limit=1, user_id=1)
    assert "content" in full_rows[0]


def test_revisions_and_job_events_are_bounded():
    article_id = db.save_article("Bounded", "content")
    for index in range(3):
        db.save_article_revision(article_id, f"snapshot {index}", summary="s")

    assert [r["revision_num"] for r in db.get_article_revisions(article_id)] == [3, 2, 1]
    assert len(db.get_article_revisions(article_id, limit=2)) == 2

    run_id = "run_bounded_events"
    for index in range(5):
        db.append_job_event(run_id, "step", {"i": index})
    assert len(db.get_job_events(run_id)) == 5
    assert len(db.get_job_events(run_id, limit=2)) == 2


# ---------------------------------------------------------------------------
# 11. Legacy unowned rows
# ---------------------------------------------------------------------------

def test_legacy_unowned_rows_hidden_unless_explicitly_enabled(monkeypatch):
    user = db.get_or_create_user("legacy-viewer@example.com")
    legacy_article_id = db.save_article("Legacy topic", "legacy content", user_id=None)
    legacy_revision_num = db.save_article_revision(
        legacy_article_id, "legacy revision content", summary="legacy", user_id=None
    )
    db.save_chat_message(legacy_article_id, "user", "legacy chat", user_id=None)

    monkeypatch.delenv("ALLOW_LEGACY_UNOWNED_ROWS", raising=False)
    assert db.get_article_revisions(legacy_article_id, user_id=user["id"]) == []
    assert db.get_article_revision(legacy_article_id, legacy_revision_num, user_id=user["id"]) is None
    assert db.get_chat_history(legacy_article_id, user_id=user["id"]) == []

    monkeypatch.setenv("ALLOW_LEGACY_UNOWNED_ROWS", "true")
    assert len(db.get_article_revisions(legacy_article_id, user_id=user["id"])) == 1
    assert db.get_article_revision(legacy_article_id, legacy_revision_num, user_id=user["id"]) is not None
    assert len(db.get_chat_history(legacy_article_id, user_id=user["id"])) == 1

    # Claiming is explicit and one-shot: a second call finds nothing left to claim.
    claimed = db.claim_legacy_data(user["id"])
    assert claimed >= 1
    assert db.claim_legacy_data(user["id"]) == 0


# ---------------------------------------------------------------------------
# Auth password-attempt rate limiting primitives (consumed by auth/service.py)
# ---------------------------------------------------------------------------

def test_password_attempt_recording_and_windowed_counts():
    db.record_password_attempt("Victim@Example.com", "10.0.0.1")
    db.record_password_attempt("victim@example.com", "10.0.0.2")
    db.record_password_attempt("other@example.com", "10.0.0.9")

    # Email is normalized; per-email count only sees this account's attempts.
    assert db.count_recent_password_attempts("victim@example.com") == 2
    assert db.count_recent_password_attempts("VICTIM@example.com") == 2
    assert db.count_recent_password_attempts("nobody@example.com") == 0

    # IP-aware counting covers credential stuffing across emails from one address.
    db.record_password_attempt("sprayed@example.com", "10.0.0.2")
    assert db.count_recent_password_attempts("victim@example.com", ip="10.0.0.2") >= 3
    # For the sprayed account itself, both its own row and the same-IP rows count.
    assert db.count_recent_password_attempts("sprayed@example.com", ip="10.0.0.2") == 2

    # Attempts outside the window are ignored.
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    with db.get_connection() as (conn, is_tidb):
        assert is_tidb is False
        conn.execute(
            "INSERT INTO password_attempts (email, ip, attempted_at) VALUES (?, ?, ?)",
            ("victim@example.com", "10.0.0.3", old_ts),
        )
    assert db.count_recent_password_attempts("victim@example.com", window_seconds=900) == 2
