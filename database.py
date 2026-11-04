"""Database layer supporting TiDB Cloud (MySQL-compatible) with SQLite fallback.

If TiDB Cloud environment variables (TIDB_HOST, TIDB_USER, TIDB_PASSWORD) are set,
the application connects to TiDB Cloud with TLS/SSL encryption.
Otherwise, it falls back to local SQLite (research_studio.db) with WAL mode.
"""

from __future__ import annotations

import os
import re
import time
import json
import decimal
import sqlite3
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Maximum number of automatic retries for optimistic concurrency helpers.
_MAX_WRITE_RETRIES = 8

# SQLite/TiDB "stuck write" errors that are safe to retry on a fresh attempt.
_RETRYABLE_WRITE_MARKERS = (
    "UNIQUE",
    "DUPLICATE",
    "INTEGRITY",
    "PRIMARY KEY",
    "DATABASE IS LOCKED",
    "DATABASE LOCKED",
    "SQLITE_BUSY",
    "LOCK WAIT TIMEOUT",
    "DEADLOCK",
)

_READ_ONLY_SQL_PREFIXES = ("SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "WITH")


class DatabaseConnectionError(RuntimeError):
    """Raised when the configured TiDB backend cannot be reached.

    Previously a failed TiDB connection silently degraded to a *separate* local
    SQLite database, which created split-brain data (writes landing in different
    stores). When TiDB is configured we now fail loudly unless the operator
    explicitly opts into SQLite fallback via ``ALLOW_SQLITE_FALLBACK=true``.
    """


# Local SQLite database path — resolved lazily at connection time so that
# tests can set RESEARCH_STUDIO_DB_PATH in conftest.py *before* the first
# connection is opened, without racing against module-level evaluation.
# The module-level DB_PATH is kept as a readable default for callers that
# inspect it directly (e.g. health-check logging), but get_connection() always
# re-reads the env vars so overrides applied after import still take effect.
_DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "research_studio.db")


def _resolve_db_path() -> str:
    """Return the effective SQLite database path, re-reading env vars each call."""
    return (
        os.getenv("RESEARCH_STUDIO_DB_PATH")
        or os.getenv("DATABASE_PATH")
        or _DEFAULT_DB_PATH
    )


# Kept for backward-compat (e.g. health-check display). Always use
# _resolve_db_path() inside connection code.
DB_PATH = _DEFAULT_DB_PATH


def _env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean environment flag (``true/1/yes/on``)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("true", "1", "yes", "on")


def allow_sqlite_fallback() -> bool:
    """Whether a configured-but-unreachable TiDB may degrade to local SQLite.

    Defaults to False: once TiDB is configured, silently writing to a different
    SQLite database would split the data across two stores.
    """
    return _env_flag("ALLOW_SQLITE_FALLBACK", False)


def legacy_unowned_rows_enabled() -> bool:
    """Whether readers automatically include pre-auth rows (``user_id IS NULL``).

    Defaults to False so legacy rows are never exposed to every tenant. Operators
    that need a transition window can set ``ALLOW_LEGACY_UNOWNED_ROWS=true`` and
    then use the explicit, one-shot ``claim_legacy_data()`` helper.
    """
    return _env_flag("ALLOW_LEGACY_UNOWNED_ROWS", False)


def _legacy_sql(user_column: str = "user_id") -> str:
    """Return an optional SQL fragment that includes unowned legacy rows."""
    return f" OR {user_column} IS NULL" if legacy_unowned_rows_enabled() else ""


def is_tidb_configured() -> bool:
    """Check if TiDB Cloud credentials are provided."""
    return bool(os.getenv("TIDB_HOST") and os.getenv("TIDB_USER"))


def get_active_backend() -> str:
    """Return 'tidb' if TiDB Cloud is active, otherwise 'sqlite'."""
    return "tidb" if is_tidb_configured() else "sqlite"


def _get_tidb_ssl() -> Dict[str, Any]:
    """Build secure SSL parameters for TiDB Cloud connections."""
    ca_file = os.getenv("TIDB_SSL_CA")
    if ca_file and os.path.exists(ca_file):
        return {"ca": ca_file, "check_hostname": True}

    if os.getenv("TIDB_SSL_INSECURE", "").lower() in ("true", "1"):
        return {"check_hostname": False}

    try:
        import certifi
        return {"ca": certifi.where(), "check_hostname": True}
    except Exception:
        return {"check_hostname": False}


class TiDBConnectionPool:
    """Thread-safe connection pool for TiDB Cloud Serverless to eliminate per-query TLS handshakes."""

    def __init__(self, max_size: int = 8):
        import queue
        self.max_size = max_size
        self._pool: queue.Queue = queue.Queue(maxsize=max_size)

    def get_connection(self) -> Any:
        import queue
        try:
            conn = self._pool.get_nowait()
            try:
                conn.ping(reconnect=True)
                return conn
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
        except queue.Empty:
            pass

        return _connect_tidb()

    def release_connection(self, conn: Any) -> None:
        import queue
        if conn is None:
            return
        try:
            conn.rollback()
            self._pool.put_nowait(conn)
        except (queue.Full, Exception):
            try:
                conn.close()
            except Exception:
                pass


_tidb_pool = TiDBConnectionPool(max_size=8)


def _connect_tidb():
    """Attempt to establish a connection to TiDB Cloud."""
    import pymysql
    from pymysql.cursors import DictCursor

    host = os.getenv("TIDB_HOST")
    port = int(os.getenv("TIDB_PORT", 4000))
    user = os.getenv("TIDB_USER")
    password = os.getenv("TIDB_PASSWORD", "")
    database = os.getenv("TIDB_DATABASE", "test")
    ssl_config = _get_tidb_ssl()

    try:
        return pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            cursorclass=DictCursor,
            ssl=ssl_config,
            connect_timeout=10,
            autocommit=False,
        )
    except pymysql.err.OperationalError as db_err:
        # Error 1049: ER_BAD_DB_ERROR (Unknown database)
        if db_err.args and db_err.args[0] == 1049:
            logger.info("Database '%s' does not exist on TiDB Cloud. Attempting auto-creation...", database)
            safe_db = "".join(c for c in database if c.isalnum() or c == "_")
            admin_conn = pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                cursorclass=DictCursor,
                ssl=ssl_config,
                connect_timeout=10,
                autocommit=True,
            )
            try:
                with admin_conn.cursor() as cur:
                    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{safe_db}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            finally:
                admin_conn.close()

            return pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                cursorclass=DictCursor,
                ssl=ssl_config,
                connect_timeout=10,
                autocommit=False,
            )
        raise


def _connect_tidb_with_retry(attempts: int = 2, delay: float = 0.1) -> Any:
    """Attempt to acquire a TiDB connection, retrying transient failures once."""
    last_error: Optional[Exception] = None
    for attempt in range(max(1, attempts)):
        try:
            return _tidb_pool.get_connection()
        except Exception as exc:  # pragma: no cover - depends on live backend
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(delay * (attempt + 1))
    raise DatabaseConnectionError(
        f"TiDB is configured (TIDB_HOST={os.getenv('TIDB_HOST')!r}) but unreachable: {last_error}. "
        "Refusing to fall back to local SQLite (split-brain). "
        "Set ALLOW_SQLITE_FALLBACK=true to explicitly opt into SQLite fallback."
    ) from last_error


@contextmanager
def get_connection():
    """Yield a database connection and a helper execute wrapper.

    Uses thread-safe connection pooling for TiDB Cloud to minimize latency.
    A reachable SQLite fallback is only used when TiDB is *not* configured, or
    when ``ALLOW_SQLITE_FALLBACK=true`` explicitly opts into degraded mode.
    """
    conn = None
    is_tidb = False
    from_pool = False

    if is_tidb_configured():
        if allow_sqlite_fallback():
            try:
                conn = _connect_tidb_with_retry(attempts=2)
                is_tidb = True
                from_pool = True
            except DatabaseConnectionError as exc:
                logger.warning("%s Falling back to local SQLite (ALLOW_SQLITE_FALLBACK=true).", exc)
                conn = None
        else:
            conn = _connect_tidb_with_retry(attempts=2)
            is_tidb = True
            from_pool = True

    if conn is None:
        conn = sqlite3.connect(_resolve_db_path(), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        is_tidb = False

    try:
        yield conn, is_tidb
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        if is_tidb and from_pool:
            _tidb_pool.release_connection(conn)
        else:
            try:
                conn.close()
            except Exception:
                pass


def _is_connection_error(exc: BaseException) -> bool:
    """Best-effort detection of a pymysql connection/transport failure."""
    name = type(exc).__name__.lower()
    if "operationalerror" in name or "interfaceerror" in name:
        return True
    message = str(exc).lower()
    markers = (
        "lost connection",
        "server has gone away",
        "connection reset",
        "broken pipe",
        "can't connect",
        "connection refused",
        "(2013",
        "(2006",
        "(2003",
        "(2055",
    )
    return any(marker in message for marker in markers)


def _is_read_only_sql(sql: str) -> bool:
    """Whether a statement is safe to replay after a reconnect (no side effects)."""
    stripped = sql.lstrip()
    while stripped.startswith("("):
        stripped = stripped[1:].lstrip()
    return stripped.upper().startswith(_READ_ONLY_SQL_PREFIXES)


def _exec(conn: Any, is_tidb: bool, sql: str, params: Tuple = ()) -> Any:
    """Execute SQL query handling placeholder differences (? for SQLite, %s for TiDB).

    A dropped TiDB connection is retried **once** and only for read-only
    statements issued before any commit. Non-idempotent writes (INSERT/UPDATE/
    DELETE/REPLACE) are never replayed blindly: replaying them could duplicate
    rows or corrupt a transaction that the server may already have applied.
    """
    if not is_tidb:
        return conn.execute(sql, params)

    tidb_sql = sql.replace("?", "%s")
    cursor = conn.cursor()
    try:
        cursor.execute(tidb_sql, params)
    except Exception as exc:
        if not (_is_read_only_sql(sql) and _is_connection_error(exc)):
            raise
        logger.warning("TiDB connection dropped on read query; reconnecting once: %s", exc)
        try:
            conn.ping(reconnect=True)
            cursor = conn.cursor()
            cursor.execute(tidb_sql, params)
        except Exception:
            raise
    return cursor


def _normalize_value(value: Any) -> Any:
    """Normalize backend-native values to JSON/Pydantic friendly Python types.

    pymysql's ``DictCursor`` returns ``datetime`` objects (and ``Decimal`` for
    DECIMAL aggregates), which a ``str`` Pydantic field rejects with a 500 —
    SQLite, by contrast, returns ISO strings. This helper makes every reader
    return the same dialect-independent representation.
    """
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, decimal.Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except Exception:
            return bytes(value).decode("utf-8", errors="replace")
    return value


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """Convert a DB row (dict or sqlite3.Row) to a normalized dict."""
    if row is None:
        return {}
    return {key: _normalize_value(value) for key, value in dict(row).items()}


def _rows_to_dicts(rows: Any) -> List[Dict[str, Any]]:
    """Convert DB rows to normalized dicts."""
    return [_row_to_dict(row) for row in rows]


def _get_value(row: Any, is_tidb: bool, key: str, index: int) -> Any:
    """Read a column from a TiDB dict row or a SQLite tuple row."""
    if row is None:
        return None
    if is_tidb:
        try:
            return row[key]
        except (KeyError, TypeError):
            return row[index]
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        try:
            return row[index]
        except Exception:
            return None


def _is_retryable_write_error(exc: BaseException) -> bool:
    """Whether a write failed for a transient duplicate/lock reason and may retry."""
    message = f"{type(exc).__name__} {exc}".upper()
    return any(marker in message for marker in _RETRYABLE_WRITE_MARKERS)


def check_tidb_live_status() -> Tuple[bool, str]:
    """Test TiDB connectivity with an explicit SELECT 1 ping.

    Returns:
        (is_connected, status_message)
    """
    if not is_tidb_configured():
        return False, "TiDB credentials not configured. Running on local SQLite."
    try:
        with get_connection() as (conn, is_tidb):
            if not is_tidb:
                return False, "Connection to TiDB failed. Falling back to local SQLite (ALLOW_SQLITE_FALLBACK=true)."
            cursor = _exec(conn, True, "SELECT 1 AS alive")
            row = cursor.fetchone()
            if row:
                return True, "TiDB Cloud Serverless connected and healthy."
            return False, "TiDB returned empty response to ping."
    except Exception as e:
        return False, f"TiDB connection error: {e}"


def _validate_sql_identifier(identifier: str) -> str:
    """Validate SQL identifier (table/column) contains only safe alphanumeric characters and underscores."""
    if not identifier or not re.match(r"^[a-zA-Z0-9_]+$", identifier):
        raise ValueError(f"Unsafe SQL identifier: {identifier!r}")
    return identifier


def _validate_sql_col_type(col_type: str) -> str:
    """Validate column type definition contains only safe type syntax."""
    if not col_type or not re.match(r"^[a-zA-Z0-9_(),\s]+$", col_type) or ";" in col_type or "--" in col_type:
        raise ValueError(f"Unsafe SQL column type: {col_type!r}")
    return col_type


def _ensure_column_exists(conn: Any, is_tidb: bool, table: str, col: str, col_type: str):
    """Safely and idempotently ensure a column exists in a table across TiDB and SQLite with identifier sanitization."""
    safe_table = _validate_sql_identifier(table)
    safe_col = _validate_sql_identifier(col)
    safe_type = _validate_sql_col_type(col_type)

    if is_tidb:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) AS cnt 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
            """,
            (safe_table, safe_col),
        )
        res = cursor.fetchone()
        cnt = res["cnt"] if isinstance(res, dict) else res[0]
        if cnt == 0:
            cursor.execute(f"ALTER TABLE `{safe_table}` ADD COLUMN `{safe_col}` {safe_type}")
    else:
        cursor = conn.execute(f"PRAGMA table_info({safe_table})")
        existing_cols = [row[1] for row in cursor.fetchall()]
        if safe_col not in existing_cols:
            conn.execute(f"ALTER TABLE {safe_table} ADD COLUMN {safe_col} {safe_type}")


def _ensure_job_event_unique_index(conn: Any, is_tidb: bool) -> None:
    """Idempotently enforce UNIQUE(run_id, seq_id) on the job event ledger.

    The original schema only created a *non-unique* index, so the duplicate-key
    retry in ``append_job_event`` could never fire and concurrent workers could
    persist duplicate ``seq_id`` values (breaking resumable SSE).
    """
    try:
        if is_tidb:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'job_events'
                ORDER BY INDEX_NAME, SEQ_IN_INDEX
                """
            )
            indexes: Dict[str, Dict[str, Any]] = {}
            for row in cursor.fetchall():
                name = row["INDEX_NAME"] if isinstance(row, dict) else row[0]
                non_unique = row["NON_UNIQUE"] if isinstance(row, dict) else row[1]
                column = row["COLUMN_NAME"] if isinstance(row, dict) else row[3]
                entry = indexes.setdefault(name, {"non_unique": non_unique, "columns": []})
                entry["columns"].append(column)
            if "uk_event_run_seq" in indexes or any(e["columns"] == ["run_id", "seq_id"] for e in indexes.values()):
                return
            try:
                cursor.execute("ALTER TABLE job_events ADD UNIQUE KEY uk_event_run_seq (run_id, seq_id)")
            except Exception as exc:
                if "1061" in str(exc) or "Duplicate key name" in str(exc):
                    return
                logger.warning("Could not add UNIQUE(run_id, seq_id) to job_events: %s", exc)
        else:
            cursor = conn.execute("PRAGMA index_list(job_events)")
            for idx_row in cursor.fetchall():
                index_name = idx_row[1]
                is_unique = bool(idx_row[2])
                if not is_unique:
                    continue
                cols_cursor = conn.execute(f"PRAGMA index_info({index_name})")
                columns = [r[2] for r in cols_cursor.fetchall()]
                if columns == ["run_id", "seq_id"]:
                    return
            conn.execute("DROP INDEX IF EXISTS idx_event_run_seq")
            try:
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uk_event_run_seq ON job_events(run_id, seq_id)"
                )
            except sqlite3.IntegrityError:
                logger.warning(
                    "job_events already contains duplicate (run_id, seq_id) rows; "
                    "cannot create unique index until ledger is de-duplicated."
                )
    except Exception as exc:  # pragma: no cover - defensive migration path
        logger.warning("Job event unique-index migration skipped: %s", exc)


def init_db():
    """Initialize database schemas and apply idempotent migrations on TiDB Cloud or SQLite.

    All table definitions live in ``db_schema.py`` (single source of truth).
    Both backends are driven from the same spec so they stay in sync automatically.
    """
    from db_schema import build_tidb_ddl, build_sqlite_ddl, SQLITE_EXTRA_INDEXES, MIGRATION_COLUMNS

    with get_connection() as (conn, is_tidb):
        if is_tidb:
            cursor = conn.cursor()
            for ddl in build_tidb_ddl():
                cursor.execute(ddl + ";")

            # Idempotent column migrations for pre-existing databases
            for table, col, tidb_type, _sqlite_type in MIGRATION_COLUMNS:
                _ensure_column_exists(conn, is_tidb, table, col, tidb_type)

        else:
            # SQLite: execute all CREATE TABLE statements individually then indexes
            for ddl in build_sqlite_ddl():
                conn.execute(ddl)

            for idx_sql in SQLITE_EXTRA_INDEXES:
                try:
                    conn.execute(idx_sql)
                except Exception:
                    pass  # index already exists or table not yet present

            # Idempotent column migrations for pre-existing databases
            for table, col, _tidb_type, sqlite_type in MIGRATION_COLUMNS:
                _ensure_column_exists(conn, is_tidb, table, col, sqlite_type)

        _ensure_job_event_unique_index(conn, is_tidb)


# ---------------------------------------------------------------------------
# Auth CRUD (Users, OTP Codes, Auth Sessions, Legacy Claiming)
# ---------------------------------------------------------------------------

def get_or_create_user(email: str) -> Dict[str, Any]:
    """Retrieve existing user by normalized email, or create a new user on first verified login.

    Uses INSERT OR IGNORE / INSERT IGNORE to eliminate the SELECT-then-INSERT
    race condition where two concurrent OTP verifications for the same new email
    could both see no existing row and both attempt an INSERT, causing a duplicate
    key error on the unique email column.
    """
    norm_email = email.strip().lower()
    with get_connection() as (conn, is_tidb):
        if is_tidb:
            # MySQL / TiDB: INSERT IGNORE silently skips on duplicate key
            _exec(conn, is_tidb, "INSERT IGNORE INTO users (email, is_active) VALUES (?, 1)", (norm_email,))
        else:
            # SQLite: INSERT OR IGNORE does the same
            _exec(conn, is_tidb, "INSERT OR IGNORE INTO users (email, is_active) VALUES (?, 1)", (norm_email,))

        # Always fetch the canonical row (works for both the newly inserted and
        # the already-existing case).
        cursor = _exec(
            conn, is_tidb,
            "SELECT id, email, password_hash, created_at, last_login_at, is_active FROM users WHERE email = ?",
            (norm_email,),
        )
        row = cursor.fetchone()
        return _row_to_dict(row)


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve user record by user_id."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(conn, is_tidb, "SELECT id, email, password_hash, created_at, last_login_at, is_active FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Retrieve user record by email, or None if non-existent."""
    norm_email = email.strip().lower()
    with get_connection() as (conn, is_tidb):
        cursor = _exec(conn, is_tidb, "SELECT id, email, password_hash, created_at, last_login_at, is_active FROM users WHERE email = ?", (norm_email,))
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None


def set_user_password(user_id: int, password_hash: str) -> None:
    """Store or update PBKDF2 hashed password for a user."""
    with get_connection() as (conn, is_tidb):
        _exec(conn, is_tidb, "UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))


def update_user_last_login(user_id: int):
    """Update last_login_at timestamp in UTC."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as (conn, is_tidb):
        _exec(conn, is_tidb, "UPDATE users SET last_login_at = ? WHERE id = ?", (now_utc, user_id))


def save_otp_code(email: str, code_hash: str, expires_at: datetime, request_ip: Optional[str] = None) -> int:
    """Store hashed OTP code with expiration in UTC."""
    norm_email = email.strip().lower()
    exp_str = expires_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            """INSERT INTO otp_codes (email, code_hash, expires_at, attempts, used, created_at, request_ip)
               VALUES (?, ?, ?, 0, 0, ?, ?)""",
            (norm_email, code_hash, exp_str, now_str, request_ip),
        )
        return cursor.lastrowid


def get_latest_otp_code(email: str) -> Optional[Dict[str, Any]]:
    """Fetch the newest unused, unexpired OTP code entry for an email."""
    norm_email = email.strip().lower()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            """SELECT id, email, code_hash, expires_at, attempts, used, created_at, request_ip
               FROM otp_codes
               WHERE email = ? AND used = 0 AND expires_at > ?
               ORDER BY id DESC LIMIT 1""",
            (norm_email, now_str),
        )
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None


def increment_otp_attempts(otp_id: int) -> int:
    """Atomically increment attempts counter for an OTP code and return new count."""
    with get_connection() as (conn, is_tidb):
        _exec(conn, is_tidb, "UPDATE otp_codes SET attempts = attempts + 1 WHERE id = ?", (otp_id,))
        cursor = _exec(conn, is_tidb, "SELECT attempts FROM otp_codes WHERE id = ?", (otp_id,))
        row = cursor.fetchone()
        return (row["attempts"] if is_tidb else row[0]) if row else 1


def mark_otp_used(otp_id: int):
    """Mark an OTP code as consumed."""
    with get_connection() as (conn, is_tidb):
        _exec(conn, is_tidb, "UPDATE otp_codes SET used = 1 WHERE id = ?", (otp_id,))


def invalidate_unused_otps_for_email(email: str):
    """Invalidate all prior unused OTP codes for an email when a new code is requested."""
    norm_email = email.strip().lower()
    with get_connection() as (conn, is_tidb):
        _exec(conn, is_tidb, "UPDATE otp_codes SET used = 1 WHERE email = ? AND used = 0", (norm_email,))


def get_latest_otp_created_at(email: str) -> Optional[datetime]:
    """Get created_at timestamp of the most recent OTP code sent to this email."""
    norm_email = email.strip().lower()
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            "SELECT created_at FROM otp_codes WHERE email = ? ORDER BY id DESC LIMIT 1",
            (norm_email,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        val = row["created_at"] if is_tidb else row[0]
        if isinstance(val, datetime):
            return val.replace(tzinfo=timezone.utc) if val.tzinfo is None else val
        try:
            return datetime.fromisoformat(str(val)).replace(tzinfo=timezone.utc)
        except Exception:
            return None


def count_recent_otps_by_email(email: str, window_seconds: int = 3600) -> int:
    """Count OTP requests sent to this email in the last window_seconds."""
    norm_email = email.strip().lower()
    cutoff = datetime.now(timezone.utc).timestamp() - window_seconds
    cutoff_str = datetime.fromtimestamp(cutoff, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            "SELECT COUNT(*) AS cnt FROM otp_codes WHERE email = ? AND created_at >= ?",
            (norm_email, cutoff_str),
        )
        row = cursor.fetchone()
        return (row["cnt"] if is_tidb else row[0]) if row else 0


def count_recent_otps_by_ip(ip: str, window_seconds: int = 3600) -> int:
    """Count OTP requests originating from an IP in the last window_seconds."""
    if not ip:
        return 0
    cutoff = datetime.now(timezone.utc).timestamp() - window_seconds
    cutoff_str = datetime.fromtimestamp(cutoff, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            "SELECT COUNT(*) AS cnt FROM otp_codes WHERE request_ip = ? AND created_at >= ?",
            (ip, cutoff_str),
        )
        row = cursor.fetchone()
        return (row["cnt"] if is_tidb else row[0]) if row else 0


def record_password_attempt(email: str, ip: Optional[str] = None) -> None:
    """Record a failed password authentication attempt for rate limiting/lockout.

    Callers (auth service) invoke this for rejected logins; ``count_recent_password_attempts``
    then performs honest, DB-grounded lockout checks that survive restarts and
    multi-process deployments.
    """
    norm_email = (email or "").strip().lower()
    if not norm_email:
        return
    ip_value = (ip or "").strip() or None
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as (conn, is_tidb):
        _exec(
            conn,
            is_tidb,
            "INSERT INTO password_attempts (email, ip, attempted_at) VALUES (?, ?, ?)",
            (norm_email, ip_value, now_str),
        )


def count_recent_password_attempts(
    email: str,
    ip: Optional[str] = None,
    window_seconds: int = 900,
) -> int:
    """Count failed password attempts within ``window_seconds``.

    When ``ip`` is supplied, attempts are counted per-email *or* per-IP so both
    credential stuffing from one address and distributed guessing against one
    account are visible to the caller.
    """
    norm_email = (email or "").strip().lower()
    if not norm_email:
        return 0
    try:
        window = max(0, int(window_seconds))
    except (TypeError, ValueError):
        window = 900
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    ip_value = (ip or "").strip() or None

    with get_connection() as (conn, is_tidb):
        if ip_value:
            cursor = _exec(
                conn,
                is_tidb,
                "SELECT COUNT(*) AS cnt FROM password_attempts WHERE attempted_at >= ? AND (email = ? OR ip = ?)",
                (cutoff_str, norm_email, ip_value),
            )
        else:
            cursor = _exec(
                conn,
                is_tidb,
                "SELECT COUNT(*) AS cnt FROM password_attempts WHERE attempted_at >= ? AND email = ?",
                (cutoff_str, norm_email),
            )
        row = cursor.fetchone()
        return int(_get_value(row, is_tidb, "cnt", 0) or 0)


def save_auth_session(user_id: int, token_hash: str, expires_at: datetime) -> int:
    """Store hashed session token with user reference and expiry in UTC."""
    exp_str = expires_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            """INSERT INTO auth_sessions (user_id, token_hash, expires_at, created_at, last_seen_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, token_hash, exp_str, now_str, now_str),
        )
        return cursor.lastrowid


def get_auth_session_by_token_hash(token_hash: str) -> Optional[Dict[str, Any]]:
    """Look up active session by hashed token; checks expiry and user is_active."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            """SELECT s.id, s.user_id, s.token_hash, s.expires_at, s.created_at, s.last_seen_at,
                      u.email, u.is_active
               FROM auth_sessions s
               JOIN users u ON s.user_id = u.id
               WHERE s.token_hash = ? AND s.expires_at > ? AND u.is_active = 1""",
            (token_hash, now_str),
        )
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None


def update_session_last_seen(session_id: int):
    """Debounced update of last_seen_at timestamp."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as (conn, is_tidb):
        _exec(conn, is_tidb, "UPDATE auth_sessions SET last_seen_at = ? WHERE id = ?", (now_str, session_id))


def delete_auth_session(token_hash: str):
    """Revoke a single session by token hash."""
    with get_connection() as (conn, is_tidb):
        _exec(conn, is_tidb, "DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))


def delete_all_user_sessions(user_id: int):
    """Revoke all sessions for a user (log out everywhere)."""
    with get_connection() as (conn, is_tidb):
        _exec(conn, is_tidb, "DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))


def cleanup_expired_auth_data():
    """Prune expired OTP codes and expired sessions."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as (conn, is_tidb):
        _exec(conn, is_tidb, "DELETE FROM otp_codes WHERE expires_at < ?", (now_str,))
        _exec(conn, is_tidb, "DELETE FROM auth_sessions WHERE expires_at < ?", (now_str,))


def claim_legacy_data(user_id: int) -> int:
    """Explicit one-time helper to claim unowned (user_id IS NULL) legacy data for a verified user."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(conn, is_tidb, "SELECT COUNT(*) AS cnt FROM articles WHERE user_id IS NULL")
        row = cursor.fetchone()
        unowned_count = (row["cnt"] if is_tidb else row[0]) if row else 0

        _exec(conn, is_tidb, "UPDATE articles SET user_id = ? WHERE user_id IS NULL", (user_id,))
        _exec(conn, is_tidb, "UPDATE chat_history SET user_id = ? WHERE user_id IS NULL", (user_id,))
        _exec(conn, is_tidb, "UPDATE chat_sessions SET user_id = ? WHERE user_id IS NULL", (user_id,))
        _exec(conn, is_tidb, "UPDATE article_revisions SET user_id = ? WHERE user_id IS NULL", (user_id,))
        _exec(conn, is_tidb, "UPDATE telemetry_runs SET user_id = ? WHERE user_id IS NULL", (user_id,))
        _exec(conn, is_tidb, "UPDATE security_audit_logs SET user_id = ? WHERE user_id IS NULL", (user_id,))
        _exec(conn, is_tidb, "UPDATE user_memory SET user_id = ? WHERE user_id IS NULL", (user_id,))
        return unowned_count


def count_unclaimed_legacy_articles() -> int:
    """Return count of unowned legacy articles."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(conn, is_tidb, "SELECT COUNT(*) AS cnt FROM articles WHERE user_id IS NULL")
        row = cursor.fetchone()
        return (row["cnt"] if is_tidb else row[0]) if row else 0


# ---------------------------------------------------------------------------
# Article CRUD (User Scoped)
# ---------------------------------------------------------------------------

def save_article(topic, content, tone=None, audience=None, target_length=None, generation_time=0, tokens_used=0, user_id: Optional[int] = None):
    """Insert a new article and return its generated ID, associated with user_id."""
    word_count = len(content.split())
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            """INSERT INTO articles
               (topic, content, word_count, tone, audience, target_length, generation_time_sec, tokens_used, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (topic, content, word_count, tone, audience, target_length, generation_time, tokens_used, user_id),
        )
        return cursor.lastrowid


def _clamp_limit(limit: int, default: int = 100, maximum: int = 500) -> int:
    """Clamp a LIMIT value into a sane, injection-safe integer range."""
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    return max(0, min(value, maximum))


def _clamp_offset(offset: int) -> int:
    """Clamp an OFFSET value to a non-negative integer."""
    try:
        return max(0, int(offset))
    except (TypeError, ValueError):
        return 0


def save_article_with_initial_revision(
    topic,
    content,
    tone=None,
    audience=None,
    target_length=None,
    generation_time=0,
    tokens_used=0,
    user_id: Optional[int] = None,
    summary: str = "Initial AI Squad Generation",
    author: str = "AI Squad",
) -> Tuple[int, int]:
    """Atomically insert an article and its revision #1 in a single transaction.

    Returns ``(article_id, revision_num)``. Keeping the article row and its first
    snapshot in one transaction avoids orphaned articles (and lets callers write
    the terminal job status last).
    """
    word_count = len(content.split())
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn,
            is_tidb,
            """INSERT INTO articles
               (topic, content, word_count, tone, audience, target_length, generation_time_sec, tokens_used, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (topic, content, word_count, tone, audience, target_length, generation_time, tokens_used, user_id),
        )
        article_id = cursor.lastrowid
        revision_num = _insert_article_revision_with_retry(
            conn, is_tidb, article_id, content, summary, user_id
        )
        return article_id, revision_num


def get_articles(limit=50, user_id: Optional[int] = None, offset: int = 0, include_content: bool = True):
    """Fetch recent articles ordered by creation date, scoped to user_id if provided.

    ``include_content=False`` returns summary rows only (list endpoints should not
    ship up to 100 full articles over the wire just to drop the content in Pydantic).
    """
    safe_limit = _clamp_limit(limit, default=50, maximum=500)
    safe_offset = _clamp_offset(offset)
    columns = (
        "id, user_id, topic, content, word_count, tone, audience, target_length,"
        " generation_time_sec, tokens_used, created_at, updated_at"
        if include_content
        else "id, user_id, topic, word_count, tone, audience, target_length,"
        " generation_time_sec, tokens_used, created_at, updated_at"
    )
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                f"SELECT {columns} FROM articles WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                (user_id, safe_limit, safe_offset),
            )
        else:
            cursor = _exec(
                conn, is_tidb,
                f"SELECT {columns} FROM articles ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                (safe_limit, safe_offset),
            )
        rows = cursor.fetchall()
        return _rows_to_dicts(rows)


def get_article_summaries(
    limit: int = 20,
    offset: int = 0,
    user_id: Optional[int] = None,
    before_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch lightweight article summaries (no ``content`` column) for list endpoints.

    Supports keyset (cursor) pagination via ``before_id``: when supplied, only
    rows with ``id < before_id`` are returned, ordered newest-first.  This is
    O(1) regardless of page depth, unlike OFFSET which degrades linearly.
    ``offset`` is still accepted for backward-compat callers but is ignored when
    ``before_id`` is provided.
    """
    safe_limit = _clamp_limit(limit, default=20, maximum=101)  # +1 so caller can detect has_more
    columns = (
        "id, user_id, topic, word_count, tone, audience, target_length,"
        " generation_time_sec, tokens_used, created_at, updated_at"
    )
    with get_connection() as (conn, is_tidb):
        if before_id is not None:
            if user_id is not None:
                cursor = _exec(
                    conn, is_tidb,
                    f"SELECT {columns} FROM articles WHERE user_id = ? AND id < ?"
                    f" ORDER BY id DESC LIMIT ?",
                    (user_id, before_id, safe_limit),
                )
            else:
                cursor = _exec(
                    conn, is_tidb,
                    f"SELECT {columns} FROM articles WHERE id < ?"
                    f" ORDER BY id DESC LIMIT ?",
                    (before_id, safe_limit),
                )
        else:
            safe_offset = _clamp_offset(offset)
            if user_id is not None:
                cursor = _exec(
                    conn, is_tidb,
                    f"SELECT {columns} FROM articles WHERE user_id = ?"
                    f" ORDER BY id DESC LIMIT ? OFFSET ?",
                    (user_id, safe_limit, safe_offset),
                )
            else:
                cursor = _exec(
                    conn, is_tidb,
                    f"SELECT {columns} FROM articles ORDER BY id DESC LIMIT ? OFFSET ?",
                    (safe_limit, safe_offset),
                )
        rows = cursor.fetchall()
        return _rows_to_dicts(rows)


def count_articles(user_id: Optional[int] = None) -> int:
    """Return the total number of articles owned by the given user (or all articles)."""
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(conn, is_tidb, "SELECT COUNT(*) AS cnt FROM articles WHERE user_id = ?", (user_id,))
        else:
            cursor = _exec(conn, is_tidb, "SELECT COUNT(*) AS cnt FROM articles", ())
        row = cursor.fetchone()
        return int(_get_value(row, is_tidb, "cnt", 0) or 0)


# Alias for backward compatibility
get_all_articles = get_articles


def get_article(article_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Fetch a single article by ID. If user_id is provided, strictly enforces ownership."""
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                """SELECT id, user_id, topic, content, word_count, tone, audience, target_length,
                          generation_time_sec, tokens_used, created_at, updated_at
                   FROM articles WHERE id = ? AND user_id = ?""",
                (article_id, user_id),
            )
        else:
            cursor = _exec(
                conn, is_tidb,
                """SELECT id, user_id, topic, content, word_count, tone, audience, target_length,
                          generation_time_sec, tokens_used, created_at, updated_at
                   FROM articles WHERE id = ?""",
                (article_id,),
            )
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None


def update_article_content(article_id: int, new_content: str, user_id: Optional[int] = None):
    """Update article content after an AI Copilot revision, respecting ownership."""
    word_count = len(new_content.split())
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            if is_tidb:
                sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = NOW() WHERE id = ? AND user_id = ?"
            else:
                sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = datetime('now') WHERE id = ? AND user_id = ?"
            _exec(conn, is_tidb, sql, (new_content, word_count, article_id, user_id))
        else:
            if is_tidb:
                sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = NOW() WHERE id = ?"
            else:
                sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = datetime('now') WHERE id = ?"
            _exec(conn, is_tidb, sql, (new_content, word_count, article_id))


# ---------------------------------------------------------------------------
# Revisions CRUD & Atomic Transactions (User Scoped)
# ---------------------------------------------------------------------------

def _insert_article_revision_with_retry(
    conn: Any,
    is_tidb: bool,
    article_id: int,
    content: str,
    summary: Optional[str] = None,
    user_id: Optional[int] = None,
    max_attempts: int = _MAX_WRITE_RETRIES,
) -> int:
    """Insert a revision allocating ``MAX(revision_num)+1`` with bounded retry.

    ``SELECT MAX(...) + 1`` followed by an INSERT is racy under concurrent edits:
    both writers compute the same number, the UNIQUE(article_id, revision_num)
    constraint rejects one, and previously that surfaced as a 500 / lost snapshot.
    On a duplicate-key (or transient lock) error we recompute MAX and retry.
    """
    last_error: Optional[BaseException] = None
    for attempt in range(max(1, max_attempts)):
        cursor = _exec(
            conn,
            is_tidb,
            "SELECT COALESCE(MAX(revision_num), 0) + 1 AS next_rev FROM article_revisions WHERE article_id = ?",
            (article_id,),
        )
        row = cursor.fetchone()
        next_rev = int(_get_value(row, is_tidb, "next_rev", 0) or 1)
        try:
            _exec(
                conn,
                is_tidb,
                "INSERT INTO article_revisions (article_id, revision_num, content, summary, user_id) VALUES (?, ?, ?, ?, ?)",
                (article_id, next_rev, content, summary if summary is not None else "Revision", user_id),
            )
            return next_rev
        except Exception as exc:
            last_error = exc
            if attempt < max_attempts - 1 and _is_retryable_write_error(exc):
                time.sleep(0.01 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"Could not allocate a revision number for article {article_id}: {last_error}")


def get_article_revisions(
    article_id: int,
    user_id: Optional[int] = None,
    limit: int = 200,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Fetch stored revisions for an article, newest first, bounded by ``limit``."""
    safe_limit = _clamp_limit(limit, default=200, maximum=1000)
    safe_offset = _clamp_offset(offset)
    legacy = _legacy_sql()
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                f"""SELECT id, user_id, article_id, revision_num, content, summary, created_at
                   FROM article_revisions WHERE article_id = ? AND (user_id = ?{legacy})
                   ORDER BY revision_num DESC LIMIT ? OFFSET ?""",
                (article_id, user_id, safe_limit, safe_offset),
            )
        else:
            cursor = _exec(
                conn, is_tidb,
                """SELECT id, user_id, article_id, revision_num, content, summary, created_at
                   FROM article_revisions WHERE article_id = ? ORDER BY revision_num DESC LIMIT ? OFFSET ?""",
                (article_id, safe_limit, safe_offset),
            )
        rows = cursor.fetchall()
        return _rows_to_dicts(rows)


def get_single_revision(revision_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Fetch a specific revision by ID."""
    legacy = _legacy_sql()
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                f"""SELECT id, user_id, article_id, revision_num, content, summary, created_at
                   FROM article_revisions WHERE id = ? AND (user_id = ?{legacy})""",
                (revision_id, user_id),
            )
        else:
            cursor = _exec(
                conn, is_tidb,
                """SELECT id, user_id, article_id, revision_num, content, summary, created_at
                   FROM article_revisions WHERE id = ?""",
                (revision_id,),
            )
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None


def apply_article_edit_transaction(article_id: int, new_content: str, summary: str = "Copilot revision", user_id: Optional[int] = None) -> int:
    """Atomic transaction: snapshots current article content into article_revisions, then updates articles.content.

    Returns the new revision number. Scoped to user_id if provided. The revision
    number allocation is retried on duplicate-key races so concurrent edits cannot
    500 or drop a snapshot.
    """
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(conn, is_tidb, "SELECT content FROM articles WHERE id = ? AND user_id = ?", (article_id, user_id))
        else:
            cursor = _exec(conn, is_tidb, "SELECT content FROM articles WHERE id = ?", (article_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Article {article_id} not found or access denied.")

        current_content = _get_value(row, is_tidb, "content", 0)

        next_rev = _insert_article_revision_with_retry(
            conn, is_tidb, article_id, current_content, summary, user_id
        )

        word_count = len(new_content.split())
        if is_tidb:
            sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = NOW() WHERE id = ?"
        else:
            sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = datetime('now') WHERE id = ?"
        _exec(conn, is_tidb, sql, (new_content, word_count, article_id))

        return next_rev


def rollback_article_revision_transaction(article_id: int, target_revision_id: int, user_id: Optional[int] = None) -> bool:
    """Atomic rollback: snapshots current content as 'Before rollback to N', then restores target revision content."""
    legacy = _legacy_sql()
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                f"SELECT revision_num, content FROM article_revisions WHERE id = ? AND article_id = ? AND (user_id = ?{legacy})",
                (target_revision_id, article_id, user_id),
            )
        else:
            cursor = _exec(
                conn, is_tidb,
                "SELECT revision_num, content FROM article_revisions WHERE id = ? AND article_id = ?",
                (target_revision_id, article_id),
            )
        target_row = cursor.fetchone()
        if not target_row:
            return False

        target_rev_num = _get_value(target_row, is_tidb, "revision_num", 0)
        target_content = _get_value(target_row, is_tidb, "content", 1)

        if user_id is not None:
            cursor = _exec(conn, is_tidb, "SELECT content FROM articles WHERE id = ? AND user_id = ?", (article_id, user_id))
        else:
            cursor = _exec(conn, is_tidb, "SELECT content FROM articles WHERE id = ?", (article_id,))
        curr_row = cursor.fetchone()
        if not curr_row:
            return False
        current_content = _get_value(curr_row, is_tidb, "content", 0)

        _insert_article_revision_with_retry(
            conn, is_tidb, article_id, current_content, f"Before rollback to revision {target_rev_num}", user_id
        )

        word_count = len(target_content.split())
        if is_tidb:
            sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = NOW() WHERE id = ?"
        else:
            sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = datetime('now') WHERE id = ?"
        _exec(conn, is_tidb, sql, (target_content, word_count, article_id))

        return True


def save_article_revision(
    article_id: int,
    content: str,
    summary: str = "Revision",
    author: str = "User",
    user_id: Optional[int] = None,
) -> int:
    """Save an explicit revision snapshot for an article (retry-safe numbering)."""
    with get_connection() as (conn, is_tidb):
        return _insert_article_revision_with_retry(
            conn, is_tidb, article_id, content, summary, user_id
        )


def get_article_revision(
    article_id: int,
    revision_num: int,
    user_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve a single revision by article_id and revision_num."""
    legacy = _legacy_sql()
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                f"""SELECT id, article_id, revision_num, content, summary, created_at, user_id
                   FROM article_revisions
                   WHERE article_id = ? AND revision_num = ? AND (user_id = ?{legacy})""",
                (article_id, revision_num, user_id),
            )
        else:
            cursor = _exec(
                conn, is_tidb,
                """SELECT id, article_id, revision_num, content, summary, created_at, user_id
                   FROM article_revisions
                   WHERE article_id = ? AND revision_num = ?""",
                (article_id, revision_num),
            )
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None


def restore_article_revision(
    article_id: int,
    revision_num: int,
    user_id: Optional[int] = None,
) -> bool:
    """Restore target revision by revision_num, snapshotting current state."""
    rev = get_article_revision(article_id, revision_num, user_id=user_id)
    if not rev:
        return False
    return rollback_article_revision_transaction(article_id, rev["id"], user_id=user_id)


def delete_article(article_id: int, user_id: Optional[int] = None) -> bool:
    """Delete an article and its associated chat history, respecting user ownership."""
    legacy = _legacy_sql()
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(conn, is_tidb, "DELETE FROM articles WHERE id = ? AND user_id = ?", (article_id, user_id))
            affected = cursor.rowcount if hasattr(cursor, "rowcount") else 1
            _exec(conn, is_tidb, f"DELETE FROM chat_history WHERE article_id = ? AND (user_id = ?{legacy})", (article_id, user_id))
            _exec(conn, is_tidb, f"DELETE FROM article_revisions WHERE article_id = ? AND (user_id = ?{legacy})", (article_id, user_id))
            return bool(affected and affected > 0)
        else:
            cursor = _exec(conn, is_tidb, "DELETE FROM articles WHERE id = ?", (article_id,))
            affected = cursor.rowcount if hasattr(cursor, "rowcount") else 1
            _exec(conn, is_tidb, "DELETE FROM chat_history WHERE article_id = ?", (article_id,))
            _exec(conn, is_tidb, "DELETE FROM article_revisions WHERE article_id = ?", (article_id,))
            return bool(affected and affected > 0)


# ---------------------------------------------------------------------------
# Chat History CRUD (User Scoped)
# ---------------------------------------------------------------------------

def save_chat_message(article_id: int, role: str, content: str, user_id: Optional[int] = None):
    """Insert a single chat message for an article, tagged with user_id."""
    with get_connection() as (conn, is_tidb):
        _exec(
            conn, is_tidb,
            "INSERT INTO chat_history (article_id, role, content, user_id) VALUES (?, ?, ?, ?)",
            (article_id, role, content, user_id),
        )


def get_chat_history(article_id: int, user_id: Optional[int] = None):
    """Fetch all chat messages for an article in order, scoped to user_id."""
    legacy = _legacy_sql()
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                f"SELECT role, content, created_at FROM chat_history WHERE article_id = ? AND (user_id = ?{legacy}) ORDER BY id ASC",
                (article_id, user_id),
            )
        else:
            cursor = _exec(
                conn, is_tidb,
                "SELECT role, content, created_at FROM chat_history WHERE article_id = ? ORDER BY id ASC",
                (article_id,),
            )
        rows = cursor.fetchall()
        return _rows_to_dicts(rows)


def clear_chat_history(article_id: int, user_id: Optional[int] = None):
    """Delete all chat messages for an article."""
    legacy = _legacy_sql()
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            _exec(conn, is_tidb, f"DELETE FROM chat_history WHERE article_id = ? AND (user_id = ?{legacy})", (article_id, user_id))
        else:
            _exec(conn, is_tidb, "DELETE FROM chat_history WHERE article_id = ?", (article_id,))


# ---------------------------------------------------------------------------
# LLMOps & Security Telemetry CRUD (User Scoped)
# ---------------------------------------------------------------------------

def save_telemetry_run(article_id: Optional[int], telemetry_data: Dict[str, Any], user_id: Optional[int] = None):
    """Save pipeline run telemetry for LLMOps observability, scoped to user_id."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            """INSERT INTO telemetry_runs
               (article_id, topic, duration_sec, tokens_estimated, models_used,
                fallback_count, fallback_events, readability_score, readability_grade, trace_url, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                article_id,
                telemetry_data.get("topic", "Unknown"),
                telemetry_data.get("duration_sec", 0.0),
                telemetry_data.get("tokens_estimated", 0),
                json.dumps(telemetry_data.get("models_used", [])),
                telemetry_data.get("fallback_count", 0),
                json.dumps(telemetry_data.get("fallback_events", [])),
                telemetry_data.get("readability", {}).get("score", 0.0),
                telemetry_data.get("readability", {}).get("grade", "N/A"),
                telemetry_data.get("trace_url"),
                user_id,
            ),
        )
        return cursor.lastrowid


def save_security_event(event_type: str, details: Any, user_id: Optional[int] = None):
    """Record a security audit log event, scoped to user_id."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            "INSERT INTO security_audit_logs (event_type, details, user_id) VALUES (?, ?, ?)",
            (event_type, str(details), user_id),
        )
        return cursor.lastrowid


def get_telemetry_history(limit=10, user_id: Optional[int] = None):
    """Fetch recent telemetry runs."""
    safe_limit = _clamp_limit(limit, default=10, maximum=500)
    legacy = _legacy_sql()
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                f"""SELECT id, user_id, article_id, topic, duration_sec, tokens_estimated,
                          models_used, fallback_count, fallback_events,
                          readability_score, readability_grade, trace_url, created_at
                   FROM telemetry_runs WHERE user_id = ?{legacy} ORDER BY created_at DESC LIMIT ?""",
                (user_id, safe_limit),
            )
        else:
            cursor = _exec(
                conn, is_tidb,
                """SELECT id, user_id, article_id, topic, duration_sec, tokens_estimated,
                          models_used, fallback_count, fallback_events,
                          readability_score, readability_grade, trace_url, created_at
                   FROM telemetry_runs ORDER BY created_at DESC LIMIT ?""",
                (safe_limit,),
            )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = _row_to_dict(r)
            if isinstance(d.get("models_used"), str):
                try:
                    d["models_used"] = json.loads(d["models_used"])
                except Exception:
                    pass
            if isinstance(d.get("fallback_events"), str):
                try:
                    d["fallback_events"] = json.loads(d["fallback_events"])
                except Exception:
                    pass
            result.append(d)
        return result


def get_security_audit_logs(limit=20, user_id: Optional[int] = None):
    """Fetch recent security audit events."""
    safe_limit = _clamp_limit(limit, default=20, maximum=500)
    legacy = _legacy_sql()
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                f"SELECT id, user_id, event_type, details, created_at FROM security_audit_logs WHERE user_id = ?{legacy} ORDER BY created_at DESC LIMIT ?",
                (user_id, safe_limit),
            )
        else:
            cursor = _exec(
                conn, is_tidb,
                "SELECT id, user_id, event_type, details, created_at FROM security_audit_logs ORDER BY created_at DESC LIMIT ?",
                (safe_limit,),
            )
        rows = cursor.fetchall()
        return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# Unified Hybrid System Cache CRUD (L2 Persistence with Fail-Open Safety)
# ---------------------------------------------------------------------------

def _format_datetime(dt: Optional[datetime]) -> str:
    """Format datetime to standard UTC string format."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    elif dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _parse_datetime(val: Any) -> datetime:
    """Safely parse string or datetime to UTC datetime."""
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)
    if isinstance(val, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                return datetime.strptime(val.split(".")[0], fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    return datetime.now(timezone.utc)


def set_cache_entry(
    cache_key: str,
    namespace: str,
    payload: str,
    expires_at: datetime,
    meta_info: Optional[Dict[str, Any]] = None,
    user_id: Optional[int] = None,
    created_at: Optional[datetime] = None,
) -> bool:
    """Store or update an entry in system_cache with fail-open safety.

    Enforces 1 MB payload limit.
    """
    if len(payload.encode("utf-8")) > 1024 * 1024:
        logger.warning(f"Payload for cache_key {cache_key} exceeds 1 MB limit; skipping cache.")
        return False

    created_str = _format_datetime(created_at)
    expires_str = _format_datetime(expires_at)
    meta_json = json.dumps(meta_info) if meta_info is not None else None

    try:
        with get_connection() as (conn, is_tidb):
            if is_tidb:
                sql = """
                    INSERT INTO system_cache (cache_key, namespace, payload, meta_info, user_id, created_at, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        namespace = VALUES(namespace),
                        payload = VALUES(payload),
                        meta_info = VALUES(meta_info),
                        user_id = VALUES(user_id),
                        created_at = VALUES(created_at),
                        expires_at = VALUES(expires_at)
                """
                cursor = conn.cursor()
                cursor.execute(sql, (cache_key, namespace, payload, meta_json, user_id, created_str, expires_str))
            else:
                sql = """
                    INSERT INTO system_cache (cache_key, namespace, payload, meta_info, user_id, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        namespace = excluded.namespace,
                        payload = excluded.payload,
                        meta_info = excluded.meta_info,
                        user_id = excluded.user_id,
                        created_at = excluded.created_at,
                        expires_at = excluded.expires_at
                """
                conn.execute(sql, (cache_key, namespace, payload, meta_json, user_id, created_str, expires_str))
            return True
    except Exception as e:
        logger.warning(f"Failed to set cache entry for {cache_key} (fail-open): {e}")
        return False


def get_cache_entry(
    cache_key: str,
    namespace: Optional[str] = None,
    allow_stale: bool = False,
    now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve an entry from system_cache with fail-open safety.

    Args:
        cache_key: Unique SHA-256 key.
        namespace: Optional namespace filter.
        allow_stale: If True, returns expired entry flagged with is_stale=True.
        now: Injectable current UTC datetime for testing.

    Returns:
        Dict with keys: cache_key, namespace, payload, meta_info, user_id, created_at, expires_at, is_stale.
        Returns None on miss or error.
    """
    curr_time = now or datetime.now(timezone.utc)
    try:
        with get_connection() as (conn, is_tidb):
            if namespace:
                sql = "SELECT cache_key, namespace, payload, meta_info, user_id, created_at, expires_at FROM system_cache WHERE cache_key = ? AND namespace = ?"
                cursor = _exec(conn, is_tidb, sql, (cache_key, namespace))
            else:
                sql = "SELECT cache_key, namespace, payload, meta_info, user_id, created_at, expires_at FROM system_cache WHERE cache_key = ?"
                cursor = _exec(conn, is_tidb, sql, (cache_key,))

            row = cursor.fetchone()
            if not row:
                return None

            if is_tidb and isinstance(row, dict):
                r_key = row["cache_key"]
                r_ns = row["namespace"]
                r_payload = row["payload"]
                r_meta = row["meta_info"]
                r_uid = row["user_id"]
                r_created = _parse_datetime(row["created_at"])
                r_expires = _parse_datetime(row["expires_at"])
            else:
                r_key = row[0]
                r_ns = row[1]
                r_payload = row[2]
                r_meta = row[3]
                r_uid = row[4]
                r_created = _parse_datetime(row[5])
                r_expires = _parse_datetime(row[6])

            if isinstance(r_meta, str):
                try:
                    r_meta = json.loads(r_meta)
                except Exception:
                    pass

            is_stale = r_expires < curr_time
            if is_stale and not allow_stale:
                return None

            return {
                "cache_key": r_key,
                "namespace": r_ns,
                "payload": r_payload,
                "meta_info": r_meta,
                "user_id": r_uid,
                "created_at": r_created,
                "expires_at": r_expires,
                "is_stale": is_stale,
            }
    except Exception as e:
        logger.warning(f"Failed to read cache entry {cache_key} (fail-open): {e}")
        return None


def delete_cache_entry(cache_key: str) -> bool:
    """Delete a single entry from system_cache."""
    try:
        with get_connection() as (conn, is_tidb):
            _exec(conn, is_tidb, "DELETE FROM system_cache WHERE cache_key = ?", (cache_key,))
            return True
    except Exception as e:
        logger.warning(f"Failed to delete cache entry {cache_key}: {e}")
        return False


def prune_expired_cache(namespace: Optional[str] = None, limit: int = 500, now: Optional[datetime] = None) -> int:
    """Prune expired cache entries in batches with dual-dialect SQL."""
    curr_str = _format_datetime(now)
    try:
        with get_connection() as (conn, is_tidb):
            if is_tidb:
                if namespace:
                    sql = "DELETE FROM system_cache WHERE namespace = %s AND expires_at < %s LIMIT %s"
                    cursor = conn.cursor()
                    cursor.execute(sql, (namespace, curr_str, limit))
                    return cursor.rowcount
                else:
                    sql = "DELETE FROM system_cache WHERE expires_at < %s LIMIT %s"
                    cursor = conn.cursor()
                    cursor.execute(sql, (curr_str, limit))
                    return cursor.rowcount
            else:
                if namespace:
                    sql = """
                        DELETE FROM system_cache 
                        WHERE rowid IN (
                            SELECT rowid FROM system_cache 
                            WHERE namespace = ? AND expires_at < ? 
                            LIMIT ?
                        )
                    """
                    cursor = conn.execute(sql, (namespace, curr_str, limit))
                    return cursor.rowcount
                else:
                    sql = """
                        DELETE FROM system_cache 
                        WHERE rowid IN (
                            SELECT rowid FROM system_cache 
                            WHERE expires_at < ? 
                            LIMIT ?
                        )
                    """
                    cursor = conn.execute(sql, (curr_str, limit))
                    return cursor.rowcount
    except Exception as e:
        logger.warning(f"Failed to prune expired cache: {e}")
        return 0


def get_cache_stats() -> Dict[str, Any]:
    """Retrieve aggregate cache statistics."""
    now_str = _format_datetime(None)
    stats: Dict[str, Any] = {"total_entries": 0, "active_entries": 0, "expired_entries": 0, "by_namespace": {}}
    try:
        with get_connection() as (conn, is_tidb):
            c1 = _exec(conn, is_tidb, "SELECT COUNT(*) AS total, SUM(CASE WHEN expires_at < ? THEN 1 ELSE 0 END) AS expired FROM system_cache", (now_str,))
            r1 = c1.fetchone()
            if r1:
                total = (r1["total"] if is_tidb else r1[0]) or 0
                expired = (r1["expired"] if is_tidb else r1[1]) or 0
                stats["total_entries"] = total
                stats["expired_entries"] = expired
                stats["active_entries"] = max(0, total - expired)

            c2 = _exec(conn, is_tidb, "SELECT namespace, COUNT(*) AS cnt FROM system_cache GROUP BY namespace")
            rows = c2.fetchall()
            for r in rows:
                ns = r["namespace"] if is_tidb else r[0]
                cnt = r["cnt"] if is_tidb else r[1]
                stats["by_namespace"][ns] = cnt
    except Exception as e:
        logger.warning(f"Failed to get cache stats: {e}")
    return stats


def clear_cache(namespace: Optional[str] = None, user_id: Optional[int] = None) -> int:
    """Clear cache entries filtered optionally by namespace and user_id."""
    try:
        with get_connection() as (conn, is_tidb):
            if namespace and user_id is not None:
                cursor = _exec(conn, is_tidb, "DELETE FROM system_cache WHERE namespace = ? AND user_id = ?", (namespace, user_id))
            elif namespace:
                cursor = _exec(conn, is_tidb, "DELETE FROM system_cache WHERE namespace = ?", (namespace,))
            elif user_id is not None:
                cursor = _exec(conn, is_tidb, "DELETE FROM system_cache WHERE user_id = ?", (user_id,))
            else:
                cursor = _exec(conn, is_tidb, "DELETE FROM system_cache")
            return cursor.rowcount if hasattr(cursor, "rowcount") else 0
    except Exception as e:
        logger.warning(f"Failed to clear cache: {e}")
        return 0



# ---------------------------------------------------------------------------
# Context & Memory Layer CRUD (Global Research Cache, Per-User Preferences)
# ---------------------------------------------------------------------------

def get_cached_scrape_with_ttl(url: str, ttl_hours: int = 24) -> Optional[str]:
    """Retrieve compact scraped text from hybrid cache or legacy research_cache."""
    try:
        from cache import HybridCacheManager, normalize_url, make_cache_key
        clean_url = normalize_url(url)
        key = make_cache_key("web_scrape", clean_url)
        mgr = HybridCacheManager.get_instance()
        entry = mgr.get(key, namespace="web_scrape")
        if entry and not entry.get("is_stale"):
            return entry["payload"]
    except Exception:
        clean_url = url.strip()
        key = None

    url_hash = hashlib.sha256(clean_url.encode("utf-8")).hexdigest()
    with get_connection() as (conn, is_tidb):
        if is_tidb:
            cursor = _exec(
                conn, is_tidb,
                "SELECT compact_content FROM research_cache WHERE url_hash = ? AND created_at >= (NOW() - INTERVAL ? HOUR)",
                (url_hash, ttl_hours),
            )
        else:
            cutoff = datetime.now(timezone.utc).timestamp() - (ttl_hours * 3600)
            cutoff_str = datetime.fromtimestamp(cutoff, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            cursor = _exec(
                conn, is_tidb,
                "SELECT compact_content FROM research_cache WHERE url_hash = ? AND created_at >= ?",
                (url_hash, cutoff_str),
            )
        row = cursor.fetchone()
        if row:
            content = row["compact_content"] if is_tidb else row[0]
            if key:
                try:
                    mgr.set(key, "web_scrape", content, ttl_seconds=ttl_hours * 3600)
                except Exception:
                    pass
            return content
        return None


def get_cached_scrape(url: str) -> Optional[str]:
    """Retrieve compact scraped text from cache with default 24hr TTL."""
    return get_cached_scrape_with_ttl(url, ttl_hours=24)


def set_cached_scrape(url: str, compact_content: str):
    """Store or update compact scraped text in hybrid cache and legacy research_cache."""
    try:
        from cache import HybridCacheManager, normalize_url, make_cache_key
        clean_url = normalize_url(url)
        key = make_cache_key("web_scrape", clean_url)
        mgr = HybridCacheManager.get_instance()
        mgr.set(key, "web_scrape", compact_content, ttl_seconds=24 * 3600)
    except Exception:
        clean_url = url.strip()

    url_hash = hashlib.sha256(clean_url.encode("utf-8")).hexdigest()
    with get_connection() as (conn, is_tidb):
        if is_tidb:
            sql = """
                INSERT INTO research_cache (url_hash, url, compact_content)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE compact_content = VALUES(compact_content)
            """
            cursor = conn.cursor()
            cursor.execute(sql, (url_hash, clean_url, compact_content))
        else:
            sql = """
                INSERT INTO research_cache (url_hash, url, compact_content)
                VALUES (?, ?, ?)
                ON CONFLICT(url_hash) DO UPDATE SET compact_content = excluded.compact_content
            """
            conn.execute(sql, (url_hash, clean_url, compact_content))


def get_user_memories(user_id: Optional[int] = None, user_key: Optional[str] = None) -> Dict[str, str]:
    """Retrieve all persistent preferences and guidelines for a user."""
    resolved_key = str(user_id) if user_id is not None else (user_key or "default_user")
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                "SELECT memory_key, memory_value FROM user_memory WHERE user_id = ? OR user_key = ?",
                (user_id, resolved_key),
            )
        else:
            cursor = _exec(
                conn, is_tidb,
                "SELECT memory_key, memory_value FROM user_memory WHERE user_key = ?",
                (resolved_key,),
            )
        rows = cursor.fetchall()
        result = {}
        for r in rows:
            if is_tidb:
                result[r["memory_key"]] = r["memory_value"]
            else:
                result[r[0]] = r[1]
        return result


def set_user_memory(key: str, value: str, memory_type: str = "preference", user_id: Optional[int] = None, user_key: Optional[str] = None):
    """Store or update a persistent memory item."""
    resolved_key = str(user_id) if user_id is not None else (user_key or "default_user")
    with get_connection() as (conn, is_tidb):
        if is_tidb:
            sql = """
                INSERT INTO user_memory (user_key, user_id, memory_type, memory_key, memory_value)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE memory_value = VALUES(memory_value), memory_type = VALUES(memory_type), user_id = VALUES(user_id)
            """
            cursor = conn.cursor()
            cursor.execute(sql, (resolved_key, user_id, memory_type, key, value))
        else:
            sql = """
                INSERT INTO user_memory (user_key, user_id, memory_type, memory_key, memory_value)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_key, memory_key) DO UPDATE SET memory_value = excluded.memory_value, memory_type = excluded.memory_type, user_id = excluded.user_id
            """
            conn.execute(sql, (resolved_key, user_id, memory_type, key, value))


def delete_user_memory(key: str, user_id: Optional[int] = None, user_key: Optional[str] = None):
    """Remove a persistent memory item."""
    resolved_key = str(user_id) if user_id is not None else (user_key or "default_user")
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            _exec(conn, is_tidb, "DELETE FROM user_memory WHERE (user_id = ? OR user_key = ?) AND memory_key = ?", (user_id, resolved_key, key))
        else:
            _exec(conn, is_tidb, "DELETE FROM user_memory WHERE user_key = ? AND memory_key = ?", (resolved_key, key))


def get_user_api_keys(user_id: int) -> Dict[str, str]:
    """Retrieve saved API keys for a user, falling back to server environment variables."""
    memories = get_user_memories(user_id=user_id)
    return {
        "gemini_api_key": memories.get("api_key_gemini", "") or os.getenv("GEMINI_API_KEY", ""),
        "openrouter_api_key": memories.get("api_key_openrouter", "") or os.getenv("OPENROUTER_API_KEY", "") or os.getenv("OPEN_ROUTER_API_KEY", ""),
    }


def save_user_api_keys(user_id: int, gemini_key: Optional[str] = None, openrouter_key: Optional[str] = None):
    """Save persistent API keys for a user in user_memory."""
    if gemini_key is not None and gemini_key.strip():
        set_user_memory("api_key_gemini", gemini_key.strip(), memory_type="credential", user_id=user_id)
    if openrouter_key is not None and openrouter_key.strip():
        set_user_memory("api_key_openrouter", openrouter_key.strip(), memory_type="credential", user_id=user_id)


def get_chat_session(article_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Retrieve the rolling summary and message count for a chat session."""
    legacy = _legacy_sql()
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                f"SELECT article_id, user_id, running_summary, message_count FROM chat_sessions WHERE article_id = ? AND (user_id = ?{legacy})",
                (article_id, user_id),
            )
        else:
            cursor = _exec(
                conn, is_tidb,
                "SELECT article_id, user_id, running_summary, message_count FROM chat_sessions WHERE article_id = ?",
                (article_id,),
            )
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None


def save_chat_session(article_id: int, running_summary: str, message_count: int = 0, user_id: Optional[int] = None):
    """Store or update the running summary for an article chat session."""
    with get_connection() as (conn, is_tidb):
        if is_tidb:
            sql = """
                INSERT INTO chat_sessions (article_id, running_summary, message_count, user_id)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE running_summary = VALUES(running_summary), message_count = VALUES(message_count), user_id = VALUES(user_id)
            """
            cursor = conn.cursor()
            cursor.execute(sql, (article_id, running_summary, message_count, user_id))
        else:
            sql = """
                INSERT INTO chat_sessions (article_id, running_summary, message_count, user_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(article_id) DO UPDATE SET running_summary = excluded.running_summary, message_count = excluded.message_count, user_id = excluded.user_id
            """
            conn.execute(sql, (article_id, running_summary, message_count, user_id))


# ---------------------------------------------------------------------------
# Stats / Utility
# ---------------------------------------------------------------------------

def get_stats(user_id: Optional[int] = None):
    """Return aggregate stats for the dashboard, scoped to user_id if provided."""
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(conn, is_tidb, """
                SELECT
                    COUNT(*)                     AS total_articles,
                    COALESCE(SUM(word_count), 0) AS total_words,
                    COALESCE(AVG(word_count), 0) AS avg_words,
                    COALESCE(SUM(tokens_used), 0) AS total_tokens,
                    (SELECT COUNT(*) FROM chat_history WHERE user_id = ?) AS total_chats,
                    (SELECT COUNT(*) FROM telemetry_runs WHERE user_id = ?) AS total_runs,
                    (SELECT COALESCE(SUM(fallback_count), 0) FROM telemetry_runs WHERE user_id = ?) AS total_fallbacks,
                    (SELECT COUNT(*) FROM security_audit_logs WHERE user_id = ?) AS total_security_events
                FROM articles
                WHERE user_id = ?
            """, (user_id, user_id, user_id, user_id, user_id))
        else:
            cursor = _exec(conn, is_tidb, """
                SELECT
                    COUNT(*)                     AS total_articles,
                    COALESCE(SUM(word_count), 0) AS total_words,
                    COALESCE(AVG(word_count), 0) AS avg_words,
                    COALESCE(SUM(tokens_used), 0) AS total_tokens,
                    (SELECT COUNT(*) FROM chat_history) AS total_chats,
                    (SELECT COUNT(*) FROM telemetry_runs) AS total_runs,
                    (SELECT COALESCE(SUM(fallback_count), 0) FROM telemetry_runs) AS total_fallbacks,
                    (SELECT COUNT(*) FROM security_audit_logs) AS total_security_events
                FROM articles
            """)
        row = cursor.fetchone()
        return _row_to_dict(row) if row else {}


# ---------------------------------------------------------------------------
# Research Job Model & Event Ledger (SSE Resumption & Durable Executions)
# ---------------------------------------------------------------------------

def create_research_job(
    run_id: str,
    topic: str,
    user_id: Optional[int] = None,
    tone: Optional[str] = None,
    audience: Optional[str] = None,
    target_length: Optional[str] = None,
) -> None:
    """Create a new research job in 'pending' status."""
    with get_connection() as (conn, is_tidb):
        _exec(
            conn, is_tidb,
            """INSERT INTO research_jobs
               (run_id, user_id, topic, tone, audience, target_length, status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            (run_id, user_id, topic, tone, audience, target_length),
        )


_TERMINAL_JOB_STATUSES = ("cancelled", "failed", "completed")


def update_research_job(
    run_id: str,
    status: Optional[str] = None,
    result_article_id: Optional[int] = None,
    error_message: Optional[str] = None,
    trace_url: Optional[str] = None,
) -> bool:
    """Update status/metadata of an existing research job.

    Terminal jobs are frozen: a status transition is only applied while the job is
    still ``pending``/``running``. This prevents a slow background worker from
    resurrecting a job the user already cancelled (or a failed job from flipping
    itself back to ``running``). Metadata-only updates stay allowed.

    Returns True when a row was actually updated.
    """
    updates = []
    params: List[Any] = []
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if result_article_id is not None:
        updates.append("result_article_id = ?")
        params.append(result_article_id)
    if error_message is not None:
        updates.append("error_message = ?")
        params.append(error_message)
    if trace_url is not None:
        updates.append("trace_url = ?")
        params.append(trace_url)

    if not updates:
        return False

    params.append(run_id)
    with get_connection() as (conn, is_tidb):
        sql = f"UPDATE research_jobs SET {', '.join(updates)} WHERE run_id = ?"
        if status is not None:
            sql += " AND status NOT IN ('cancelled', 'failed', 'completed')"
        cursor = _exec(conn, is_tidb, sql, tuple(params))
        rowcount = getattr(cursor, "rowcount", None)
        if rowcount is None:
            return True
        return bool(rowcount > 0)


def get_research_job(run_id: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Retrieve research job details, optionally verifying user ownership."""
    legacy = _legacy_sql()
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                f"SELECT * FROM research_jobs WHERE run_id = ? AND (user_id = ?{legacy})",
                (run_id, user_id),
            )
        else:
            cursor = _exec(conn, is_tidb, "SELECT * FROM research_jobs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None


def get_active_user_job(user_id: int) -> Optional[Dict[str, Any]]:
    """Check if the user already has an active research job ('pending' or 'running')."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            "SELECT * FROM research_jobs WHERE user_id = ? AND status IN ('pending', 'running') ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        )
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None


def recover_interrupted_jobs(stale_after_seconds: int = 0) -> int:
    """Mark jobs left in ``pending``/``running`` by a dead process as failed.

    Background research workers run in in-process daemon threads and the
    cancellation events live only in memory, so a restart orphans any in-flight
    job forever. Call this from the FastAPI lifespan startup (after ``init_db``)
    to fail such jobs with a clear reason and append a terminal SSE event so
    reconnecting clients close their streams.

    ``stale_after_seconds`` limits the sweep to jobs whose ``updated_at`` is at
    least that old (default 0 = every inherited pending/running job).

    Returns the number of recovered jobs.
    """
    try:
        stale_after = max(0, int(stale_after_seconds))
    except (TypeError, ValueError):
        stale_after = 0
    now = datetime.now(timezone.utc)
    cutoff_str = (now - timedelta(seconds=stale_after)).strftime("%Y-%m-%d %H:%M:%S")
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    message = "interrupted by server restart"

    recovered_run_ids: List[str] = []
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn,
            is_tidb,
            "SELECT run_id FROM research_jobs WHERE status IN ('pending', 'running') AND updated_at <= ?",
            (cutoff_str,),
        )
        rows = cursor.fetchall()
        recovered_run_ids = [str(_get_value(r, is_tidb, "run_id", 0)) for r in rows]
        if not recovered_run_ids:
            return 0
        cursor = _exec(
            conn,
            is_tidb,
            "UPDATE research_jobs SET status = 'failed', error_message = ?, updated_at = ? "
            "WHERE status IN ('pending', 'running') AND updated_at <= ?",
            (message, now_str, cutoff_str),
        )
        rowcount = getattr(cursor, "rowcount", None)
        recovered_count = int(rowcount) if isinstance(rowcount, int) and rowcount >= 0 else len(recovered_run_ids)

    # Append terminal events *after* the status sweep committed (durable ordering).
    for run_id in recovered_run_ids:
        try:
            append_job_event(run_id, "error", {"message": message, "timestamp": time.time()})
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not append recovery event for run %s: %s", run_id, exc)
    return recovered_count


def append_job_event(run_id: str, event_type: str, payload: Any) -> int:
    """Append a sequenced event to the durable job event ledger.

    The sequence is allocated atomically (single ``INSERT ... SELECT MAX+1`` on
    SQLite, ``SELECT ... FOR UPDATE`` inside the transaction on TiDB) and the
    UNIQUE(run_id, seq_id) constraint backs that up: on a duplicate/lock error we
    retry with a freshly computed sequence instead of losing the event.
    """
    payload_str = json.dumps(payload) if not isinstance(payload, str) else payload
    last_error: Optional[BaseException] = None
    for attempt in range(_MAX_WRITE_RETRIES):
        try:
            with get_connection() as (conn, is_tidb):
                if is_tidb:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT COALESCE(MAX(seq_id), 0) + 1 AS next_seq FROM job_events WHERE run_id = %s FOR UPDATE",
                        (run_id,),
                    )
                    row = cursor.fetchone()
                    next_seq = int(_get_value(row, True, "next_seq", 0) or 1)
                    cursor.execute(
                        "INSERT INTO job_events (run_id, seq_id, event_type, payload) VALUES (%s, %s, %s, %s)",
                        (run_id, next_seq, event_type, payload_str),
                    )
                else:
                    cursor = conn.execute(
                        "INSERT INTO job_events (run_id, seq_id, event_type, payload) "
                        "SELECT ?, COALESCE(MAX(seq_id), 0) + 1, ?, ? FROM job_events WHERE run_id = ?",
                        (run_id, event_type, payload_str, run_id),
                    )
                    inserted_rowid = cursor.lastrowid
                    seq_cursor = conn.execute("SELECT seq_id FROM job_events WHERE id = ?", (inserted_rowid,))
                    seq_row = seq_cursor.fetchone()
                    next_seq = int(_get_value(seq_row, False, "seq_id", 0) or 1)
                return next_seq
        except Exception as exc:
            last_error = exc
            if attempt < _MAX_WRITE_RETRIES - 1 and _is_retryable_write_error(exc):
                time.sleep(0.01 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"Could not append job event for run {run_id}: {last_error}")


def get_job_events(run_id: str, after_seq_id: int = 0, limit: int = 2000) -> List[Dict[str, Any]]:
    """Retrieve sequenced events for a job with seq_id > after_seq_id (bounded)."""
    safe_limit = _clamp_limit(limit, default=2000, maximum=5000)
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            "SELECT seq_id, event_type, payload, created_at FROM job_events WHERE run_id = ? AND seq_id > ? ORDER BY seq_id ASC LIMIT ?",
            (run_id, after_seq_id, safe_limit),
        )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = _row_to_dict(r)
            try:
                d["payload"] = json.loads(d["payload"])
            except Exception:
                pass
            result.append(d)
        return result


# init_db() is called explicitly by:
#   - backend/main.py lifespan (production FastAPI startup)
#   - tests/conftest.py isolated_database fixture (per-test reset)
#   - crew.py / app.py entry points via their own startup paths
# It is intentionally NOT called here at module level so that:
#   1. Tests can set RESEARCH_STUDIO_DB_PATH in conftest before the first
#      connection is opened, without racing module-level execution.
#   2. Importing database.py in unit tests that don't need a DB doesn't
#      create a stale file or fail when the path isn't writable yet.
