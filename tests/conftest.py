"""Global pytest configuration: hermetic, isolated database for the test suite.

Historically the suite set ``DATABASE_URL``, which ``database.py`` never read, so
every run wrote into the developer's real ``research_studio.db`` (and would have
mutated a TiDB database if ``TIDB_*`` were configured). This conftest pins the
whole suite to a throwaway SQLite file and resets it before every test, so tests
are independent of execution order and never touch real data.

Environment variables are set at import time, before any test module imports
``database`` (which resolves ``DB_PATH`` and runs ``init_db()`` at import).
"""

from __future__ import annotations

import os

# Use a flat file directly in the project root.  tempfile.mkdtemp() creates
# subdirectories that cannot be written to inside the DSH file sandbox, but
# direct paths in the workspace are writable.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TEST_DB_PATH = os.path.join(_PROJECT_ROOT, "research_studio_test.db")

# --- Pin the database to an isolated temp file (must precede database import) ---
os.environ["RESEARCH_STUDIO_DB_PATH"] = _TEST_DB_PATH
os.environ.pop("DATABASE_PATH", None)

# --- Never let the suite reach a real TiDB cluster ---
for _var in (
    "TIDB_HOST",
    "TIDB_USER",
    "TIDB_PASSWORD",
    "TIDB_DATABASE",
    "TIDB_PORT",
    "TIDB_SSL_CA",
    "TIDB_SSL_INSECURE",
    "ALLOW_SQLITE_FALLBACK",
    "ALLOW_DEV_MODE_WITH_PROD_DB",
    "ALLOW_LEGACY_UNOWNED_ROWS",
):
    os.environ.pop(_var, None)

# --- Deterministic, safe auth configuration for tests ---
os.environ["AUTH_DEV_MODE"] = "true"
os.environ["OTP_PEPPER"] = "test_otp_pepper_secret_value_1234567890"
os.environ["SESSION_SECRET"] = "test_session_secret_value_1234567890"
os.environ["OTP_RESEND_COOLDOWN_SECONDS"] = "0"
os.environ.setdefault("LANGSMITH_TRACING", "false")
os.environ.pop("LANGSMITH_API_KEY", None)

# Keep tests offline/deterministic unless a test explicitly opts in.
os.environ.setdefault("LLM_DISABLED", "true")

import pytest  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def crewai_storage_dir(tmp_path_factory):
    """Give CrewAI a writable temp storage dir so its SQLite task-output DB
    does not touch %LOCALAPPDATA% / user profile paths (which can be
    unwritable in CI/sandboxes) and does not pollute developer state."""
    path = tmp_path_factory.mktemp("crewai_storage")
    mp = pytest.MonkeyPatch()
    mp.setenv("CREWAI_STORAGE_DIR", str(path))
    yield path
    mp.undo()


def _remove_test_db_files() -> None:
    import gc
    gc.collect()
    for suffix in ("", "-wal", "-shm"):
        try:
            target = _TEST_DB_PATH + suffix
            if os.path.exists(target):
                os.remove(target)
        except (FileNotFoundError, PermissionError, OSError):
            pass


@pytest.fixture(autouse=True)
def isolated_database():
    """Give every test a fresh, empty database and reset in-process state."""
    import database as db

    _remove_test_db_files()
    db.init_db()

    # Reset the API rate-limit store so tests don't exhaust the budget
    # from prior tests sharing the same process.
    try:
        import backend.main as _bm
        with _bm._rate_limit_lock:
            _bm._rate_limit_store.clear()
    except Exception:
        pass

    yield


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """Clean up the test database file after the whole suite finishes."""
    _remove_test_db_files()
