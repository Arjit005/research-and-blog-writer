"""Database layer supporting TiDB Cloud (MySQL-compatible) with SQLite fallback.

If TiDB Cloud environment variables (TIDB_HOST, TIDB_USER, TIDB_PASSWORD) are set,
the application connects to TiDB Cloud with TLS/SSL encryption.
Otherwise, it falls back to local SQLite (research_studio.db) with WAL mode.
"""

from __future__ import annotations

import os
import re
import time
import uuid
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

# Exact TiDB / MySQL error codes that represent transient transaction write conflicts:
# - 1205: Lock wait timeout exceeded
# - 1213: Deadlock found when trying to get lock
# - 8002: SELECT FOR UPDATE commit conflict
# - 8005: Write conflict (txnRetryable)
# - 8022: Transaction commit failed
# - 8028: Information schema changed
# - 9007: Write conflict in TiDB
# Note: 9008 represents TiKV request overload (server overload), NOT a transaction write conflict.
_TIDB_RETRYABLE_ERROR_CODES = {1205, 1213, 8002, 8005, 8022, 8028, 9007}

# Standard SQLSTATEs for serialization failure and deadlock:
# - '40001': Serialization failure / deadlock
# - 'HY000': General error (only inspected when coupled with recognized error code or marker)
_TIDB_RETRYABLE_SQLSTATES = {"40001"}

_RETRYABLE_WRITE_MARKERS = (
    "DATABASE IS LOCKED",
    "DATABASE LOCKED",
    "SQLITE_BUSY",
    "LOCK WAIT TIMEOUT",
    "DEADLOCK",
    "WRITE CONFLICT",
    "TXNRETRYABLE",
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


_tidb_pool = TiDBConnectionPool(max_size=max(1, int(os.getenv("TIDB_POOL_SIZE", "8"))))


def _init_tidb_session(conn: Any) -> None:
    """Safely configure UTC session timezone and verify TiDB pessimistic transaction mode.

    On TiDB Cloud Serverless / Essential, `tidb_txn_mode` may be a read-only system variable.
    Therefore, we:
    1. Set the session time_zone to UTC ('+00:00').
    2. Read @@session.tidb_txn_mode.
    3. If not already 'pessimistic', attempt to set it if allowed; otherwise raise DatabaseConnectionError
       if pessimistic mode is strictly required and not enabled.
    """
    cursor = conn.cursor()
    # 1. Configure UTC session timezone
    cursor.execute("SET SESSION time_zone = '+00:00';")

    # 2. Inspect session tidb_txn_mode
    try:
        cursor.execute("SELECT @@session.tidb_txn_mode AS txn_mode;")
        row = cursor.fetchone()
        mode = (row["txn_mode"] if isinstance(row, dict) else row[0]) if row else ""
        mode_str = str(mode).lower() if mode else ""
        if mode_str != "pessimistic":
            # Attempt safe set
            try:
                cursor.execute("SET SESSION tidb_txn_mode = 'pessimistic';")
            except Exception as set_err:
                logger.warning("Could not set tidb_txn_mode to pessimistic: %s (current mode: %s)", set_err, mode_str)
                # If deployment enforces optimistic mode and denies alteration
                if os.getenv("REQUIRE_PESSIMISTIC_TIDB", "").lower() in ("true", "1"):
                    raise DatabaseConnectionError(
                        f"TiDB session transaction mode is {mode_str!r}, but pessimistic mode is required. "
                        f"Alteration failed: {set_err}"
                    )
    except Exception as e:
        logger.debug("TiDB transaction mode inspection notice: %s", e)


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
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            cursorclass=DictCursor,
            ssl=ssl_config,
            connect_timeout=10,
            autocommit=False,
            init_command="SET SESSION time_zone = '+00:00';",
        )
        _init_tidb_session(conn)
        return conn
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

            conn = pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                cursorclass=DictCursor,
                ssl=ssl_config,
                connect_timeout=10,
                autocommit=False,
                init_command="SET SESSION time_zone = '+00:00';",
            )
            _init_tidb_session(conn)
            return conn
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
    """Whether a write failed for a transient transaction conflict and may retry.

    Recognizes:
    - Structured TiDB/MySQL error codes:
        * 1205: Lock wait timeout
        * 1213: Deadlock
        * 8002: SELECT FOR UPDATE commit conflict
        * 8005: Write conflict
        * 8022: Transaction commit failed
        * 8028: Information schema changed
        * 9007: Write conflict
    - Structured SQLSTATE values (e.g. '40001' serialization failure)
    - SQLite locking errors (SQLITE_BUSY, database is locked)

    Explicitly NOT retryable:
    - 9008: TiKV request overload (server overload, not a transaction write conflict)
    - Genuine application unique constraint / integrity errors (e.g. duplicate users, foreign keys)
    """
    args = getattr(exc, "args", None)
    if args and isinstance(args, (tuple, list)) and len(args) > 0:
        err_code = args[0]
        if isinstance(err_code, int):
            if err_code == 9008:
                # TiKV request overload: do not classify as a generic transaction write conflict
                return False
            if err_code in _TIDB_RETRYABLE_ERROR_CODES:
                return True

    # Check SQLSTATE or pymysql error structure if present
    sqlstate = getattr(exc, "sqlstate", None) or getattr(exc, "errno", None)
    if isinstance(sqlstate, str) and sqlstate in _TIDB_RETRYABLE_SQLSTATES:
        return True

    message = f"{type(exc).__name__} {exc}".upper()
    # Ensure 9008 is not accidentally matched by substring
    if "9008" in message or "TIKV REQUEST OVERLOAD" in message:
        return False

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
            try:
                cursor.execute(f"ALTER TABLE `{safe_table}` ADD COLUMN `{safe_col}` {safe_type}")
                logger.info("Added column %s.%s (%s) to TiDB.", safe_table, safe_col, safe_type)
            except Exception as exc:
                logger.error("Failed to add column %s.%s to TiDB: %s", safe_table, safe_col, exc)
                raise
    else:
        cursor = conn.execute(f"PRAGMA table_info({safe_table})")
        existing_cols = [row[1] for row in cursor.fetchall()]
        if safe_col not in existing_cols:
            try:
                conn.execute(f"ALTER TABLE {safe_table} ADD COLUMN {safe_col} {safe_type}")
                logger.info("Added column %s.%s (%s) to SQLite.", safe_table, safe_col, safe_type)
            except Exception as exc:
                logger.error("Failed to add column %s.%s to SQLite: %s", safe_table, safe_col, exc)
                raise


def _ensure_job_event_unique_index(conn: Any, is_tidb: bool) -> None:
    """Idempotently enforce UNIQUE(run_id, seq_id) and UNIQUE(run_id, event_id) on job_events."""
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

            # 1. UNIQUE(run_id, seq_id)
            if not ("uk_event_run_seq" in indexes or any(e["columns"] == ["run_id", "seq_id"] for e in indexes.values())):
                try:
                    cursor.execute("ALTER TABLE job_events ADD UNIQUE KEY uk_event_run_seq (run_id, seq_id)")
                except Exception as exc:
                    if "1061" not in str(exc) and "Duplicate key name" not in str(exc):
                        logger.warning("Could not add UNIQUE(run_id, seq_id) to job_events: %s", exc)

            # 2. UNIQUE(run_id, event_id)
            if not ("uk_event_run_event_id" in indexes or any(e["columns"] == ["run_id", "event_id"] for e in indexes.values())):
                try:
                    cursor.execute("ALTER TABLE job_events ADD UNIQUE KEY uk_event_run_event_id (run_id, event_id)")
                except Exception as exc:
                    if "1061" not in str(exc) and "Duplicate key name" not in str(exc):
                        logger.warning("Could not add UNIQUE(run_id, event_id) to job_events: %s", exc)
        else:
            cursor = conn.execute("PRAGMA index_list(job_events)")
            existing_indices = {}
            for idx_row in cursor.fetchall():
                index_name = idx_row[1]
                is_unique = bool(idx_row[2])
                cols_cursor = conn.execute(f"PRAGMA index_info({index_name})")
                cols = [r[2] for r in cols_cursor.fetchall()]
                existing_indices[index_name] = {"unique": is_unique, "columns": cols}

            # 1. UNIQUE(run_id, seq_id)
            has_seq_idx = any(v["unique"] and v["columns"] == ["run_id", "seq_id"] for v in existing_indices.values())
            if not has_seq_idx:
                conn.execute("DROP INDEX IF EXISTS idx_event_run_seq")
                try:
                    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uk_event_run_seq ON job_events(run_id, seq_id)")
                except sqlite3.IntegrityError:
                    pass

            # 2. UNIQUE(run_id, event_id)
            has_ev_idx = any(v["unique"] and v["columns"] == ["run_id", "event_id"] for v in existing_indices.values())
            if not has_ev_idx:
                try:
                    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uk_event_run_event_id ON job_events(run_id, event_id) WHERE event_id IS NOT NULL")
                except sqlite3.IntegrityError:
                    pass
    except Exception as exc:  # pragma: no cover - defensive migration path
        logger.warning("Job event unique-index migration skipped: %s", exc)


def _ensure_users_google_id_unique_index(conn: Any, is_tidb: bool) -> None:
    """Idempotently ensure a unique index exists on users(google_id) across TiDB and SQLite.

    TiDB rejects inline UNIQUE constraints during ALTER TABLE ADD COLUMN on existing tables.
    Instead, google_id is added as a nullable column, and this helper checks information_schema.STATISTICS
    for an existing index on google_id. If missing, it adds `uk_users_google_id`.
    For SQLite, it ensures `idx_users_google_id` partial index is created.
    """
    if is_tidb:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users'
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

        # Check if any unique index covers (google_id,) exclusively
        has_unique_gid = any(
            (entry["non_unique"] == 0 or entry["non_unique"] is False) and entry["columns"] == ["google_id"]
            for entry in indexes.values()
        )
        if has_unique_gid:
            return

        try:
            cursor.execute("ALTER TABLE `users` ADD UNIQUE KEY `uk_users_google_id` (`google_id`)")
            logger.info("Created unique index uk_users_google_id on users(google_id) in TiDB.")
        except Exception as exc:
            err_str = str(exc)
            if "1061" in err_str or "Duplicate key name" in err_str:
                return
            logger.error("Failed to create unique index uk_users_google_id on users(google_id): %s", exc)
            raise
    else:
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id) WHERE google_id IS NOT NULL"
            )
        except Exception as exc:
            logger.error("Failed to create unique index idx_users_google_id on users(google_id) in SQLite: %s", exc)
            raise


def _ensure_system_cache_key_length(conn: Any, is_tidb: bool) -> None:
    """Idempotently ensure system_cache.cache_key is VARCHAR(128) in TiDB to accommodate SHA-256 keys."""
    if is_tidb:
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT CHARACTER_MAXIMUM_LENGTH
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'system_cache' AND COLUMN_NAME = 'cache_key'
                """
            )
            row = cursor.fetchone()
            max_len = row["CHARACTER_MAXIMUM_LENGTH"] if isinstance(row, dict) else (row[0] if row else None)
            if max_len is not None and max_len < 128:
                cursor.execute("ALTER TABLE `system_cache` MODIFY COLUMN `cache_key` VARCHAR(128)")
                logger.info("Migrated system_cache.cache_key to VARCHAR(128) in TiDB.")
        except Exception as exc:
            logger.warning("Could not modify system_cache.cache_key column length in TiDB: %s", exc)


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

            _ensure_users_google_id_unique_index(conn, is_tidb)
            _ensure_system_cache_key_length(conn, is_tidb)

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

            _ensure_users_google_id_unique_index(conn, is_tidb)
            _ensure_system_cache_key_length(conn, is_tidb)

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
            "SELECT id, email, password_hash, google_id, created_at, last_login_at, is_active FROM users WHERE email = ?",
            (norm_email,),
        )
        row = cursor.fetchone()
        return _row_to_dict(row)


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve user record by user_id."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(conn, is_tidb, "SELECT id, email, password_hash, google_id, created_at, last_login_at, is_active FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Retrieve user record by email, or None if non-existent."""
    norm_email = email.strip().lower()
    with get_connection() as (conn, is_tidb):
        cursor = _exec(conn, is_tidb, "SELECT id, email, password_hash, google_id, created_at, last_login_at, is_active FROM users WHERE email = ?", (norm_email,))
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None




def get_user_by_google_id(google_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve user record by Google unique subject identifier."""
    if not google_id or not str(google_id).strip():
        return None
    clean_gid = str(google_id).strip()
    try:
        with get_connection() as (conn, is_tidb):
            cursor = _exec(
                conn,
                is_tidb,
                "SELECT id, email, password_hash, google_id, created_at, last_login_at, is_active FROM users WHERE google_id = ?",
                (clean_gid,),
            )
            row = cursor.fetchone()
            return _row_to_dict(row) if row else None
    except Exception as exc:
        err_str = str(exc).lower()
        if "1054" in err_str or "unknown column" in err_str or "no such column" in err_str:
            logger.warning("google_id column not present in users table; attempting automatic self-healing migration: %s", exc)
            try:
                init_db()
                with get_connection() as (conn, is_tidb):
                    cursor = _exec(
                        conn,
                        is_tidb,
                        "SELECT id, email, password_hash, google_id, created_at, last_login_at, is_active FROM users WHERE google_id = ?",
                        (clean_gid,),
                    )
                    row = cursor.fetchone()
                    return _row_to_dict(row) if row else None
            except Exception as retry_exc:
                logger.error("Failed to recover from missing google_id column: %s", retry_exc)
                return None
        logger.exception("Unexpected error in get_user_by_google_id")
        raise


def link_user_google_id(user_id: int, google_id: str) -> Tuple[bool, str]:
    """Atomically link a Google ID to an existing user.

    Guarantees:
    - Verifies user exists and is active.
    - Prevents overwriting if user is already linked to a different Google ID.
    - Prevents duplicate linking if Google ID is already linked to another user.
    - Handles concurrent race conditions and database IntegrityError safely.
    """
    clean_gid = str(google_id).strip()
    if not clean_gid or not user_id:
        return False, "INVALID_ARGUMENTS"

    try:
        with get_connection() as (conn, is_tidb):
            cursor = _exec(
                conn, is_tidb,
                "SELECT id, google_id, is_active FROM users WHERE id = ?",
                (user_id,),
            )
            user_row = cursor.fetchone()
            if not user_row:
                return False, "USER_NOT_FOUND"

            existing_gid = _get_value(user_row, is_tidb, "google_id", None)
            if existing_gid and existing_gid != clean_gid:
                return False, "USER_LINKED_TO_DIFFERENT_GOOGLE_ACCOUNT"
            if existing_gid == clean_gid:
                return True, "ALREADY_LINKED"

            # Check if google_id is already claimed by another user
            cursor = _exec(
                conn, is_tidb,
                "SELECT id FROM users WHERE google_id = ? AND id != ?",
                (clean_gid, user_id),
            )
            if cursor.fetchone():
                return False, "GOOGLE_ACCOUNT_ALREADY_LINKED"

            if is_tidb:
                sql = "UPDATE users SET google_id = ?, last_login_at = NOW() WHERE id = ?"
            else:
                sql = "UPDATE users SET google_id = ?, last_login_at = datetime('now') WHERE id = ?"

            try:
                _exec(conn, is_tidb, sql, (clean_gid, user_id))
                return True, "LINKED_SUCCESSFULLY"
            except Exception as exc:
                err_text = str(exc).lower()
                if "unique" in err_text or "duplicate" in err_text or "1062" in err_text or isinstance(exc, sqlite3.IntegrityError):
                    logger.warning("Integrity violation during link_user_google_id: %s", exc)
                    return False, "GOOGLE_ACCOUNT_ALREADY_LINKED"
                raise
    except Exception as exc:
        err_text = str(exc).lower()
        if "unique" in err_text or "duplicate" in err_text or "1062" in err_text or isinstance(exc, sqlite3.IntegrityError):
            logger.warning("Integrity violation during link_user_google_id: %s", exc)
            return False, "GOOGLE_ACCOUNT_ALREADY_LINKED"
        logger.exception("Unexpected error in link_user_google_id")
        return False, f"DATABASE_ERROR: {exc}"


def create_google_user(email: str, google_id: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Atomically create a new user authenticated via Google.

    Guarantees:
    - Normalizes email to lowercase.
    - Handles concurrent race conditions and database IntegrityError safely.
    - Preserves existing user accounts if collision occurs.
    """
    clean_email = str(email).strip().lower()
    clean_gid = str(google_id).strip()
    if not clean_email or not clean_gid:
        return None, "INVALID_ARGUMENTS"

    try:
        with get_connection() as (conn, is_tidb):
            cursor = _exec(
                conn, is_tidb,
                "SELECT id, email, password_hash, google_id, created_at, last_login_at, is_active FROM users WHERE email = ? OR google_id = ?",
                (clean_email, clean_gid),
            )
            row = cursor.fetchone()
            if row:
                user_dict = _row_to_dict(row)
                if user_dict.get("email") == clean_email and not user_dict.get("google_id"):
                    success, reason = link_user_google_id(user_dict["id"], clean_gid)
                    if success:
                        user_dict["google_id"] = clean_gid
                        return user_dict, "LINKED"
                    return None, reason
                elif user_dict.get("google_id") == clean_gid:
                    if user_dict.get("email") == clean_email:
                        return user_dict, "EXISTS"
                    return None, "GOOGLE_ACCOUNT_ALREADY_LINKED"
                return None, "EMAIL_ALREADY_EXISTS"

            if is_tidb:
                sql = "INSERT INTO users (email, google_id, is_active, created_at, last_login_at) VALUES (?, ?, 1, NOW(), NOW())"
            else:
                sql = "INSERT INTO users (email, google_id, is_active, created_at, last_login_at) VALUES (?, ?, 1, datetime('now'), datetime('now'))"

            try:
                cursor = _exec(conn, is_tidb, sql, (clean_email, clean_gid))
                new_id = cursor.lastrowid
                return {
                    "id": new_id,
                    "email": clean_email,
                    "password_hash": None,
                    "google_id": clean_gid,
                    "is_active": 1,
                }, "CREATED"
            except Exception as exc:
                err_text = str(exc).lower()
                if "unique" in err_text or "duplicate" in err_text or "1062" in err_text or isinstance(exc, sqlite3.IntegrityError):
                    logger.warning("Integrity error on concurrent create_google_user: %s", exc)
                    cursor = _exec(
                        conn, is_tidb,
                        "SELECT id, email, password_hash, google_id, created_at, last_login_at, is_active FROM users WHERE email = ? OR google_id = ?",
                        (clean_email, clean_gid),
                    )
                    race_row = cursor.fetchone()
                    if race_row:
                        winner = _row_to_dict(race_row)
                        if winner.get("email") == clean_email and winner.get("google_id") == clean_gid:
                            return winner, "EXISTS"
                    return None, "CONCURRENT_COLLISION"
                raise
    except Exception as exc:
        err_text = str(exc).lower()
        if "unique" in err_text or "duplicate" in err_text or "1062" in err_text or isinstance(exc, sqlite3.IntegrityError):
            return None, "CONCURRENT_COLLISION"
        logger.exception("Unexpected error in create_google_user")
        return None, f"DATABASE_ERROR: {exc}"

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
    run_id: Optional[str] = None,
    worker_id: Optional[str] = None,
    lease_token: Optional[str] = None,
    fencing_token: Optional[int] = None,
) -> Tuple[int, int]:
    """Atomically insert an article and its revision #1 with mandatory lease and cancellation validation.

    Guarantees:
    1. If `run_id` is provided, verifies within the SAME transaction that:
       - The job in `research_jobs` is still active and has NOT been cancelled or completed.
       - If lease/fencing tokens are supplied, verifies the active lease in `active_run_claims` has NOT
         expired (`lease_expires_at >= UTC_NOW`) and matches `worker_id`, `lease_token`, and `fencing_token`.
    2. If cancelled or lease expired, raises `PermissionError` or returns `(0, 0)` without writing any rows.
    3. Keeps the article row and its first snapshot in one atomic transaction.
    """
    word_count = len(content.split())
    with get_connection() as (conn, is_tidb):
        # 1. Atomic lease and cancellation validation
        if run_id:
            # Check research_jobs status inside transaction using pessimistic row lock
            if is_tidb:
                cur_job = _exec(conn, is_tidb, "SELECT status FROM research_jobs WHERE run_id = %s FOR UPDATE", (run_id,))
            else:
                cur_job = _exec(conn, is_tidb, "SELECT status FROM research_jobs WHERE run_id = ?", (run_id,))
            job_row = cur_job.fetchone()
            if job_row:
                current_status = job_row["status"] if is_tidb else job_row[0]
                if current_status in ("cancelled", "failed", "completed"):
                    raise PermissionError(f"Cannot save article: run {run_id} is already in terminal state '{current_status}'.")

            # Worker-generated content MUST provide full fencing credentials
            if worker_id is None or lease_token is None or fencing_token is None:
                raise PermissionError("Worker article persistence rejected: missing mandatory fencing parameters (worker_id, lease_token, fencing_token).")

            # Check active_run_claims lease validity under row lock
            if is_tidb:
                cur_claim = _exec(conn, is_tidb, "SELECT worker_id, lease_token, fencing_token, lease_expires_at FROM active_run_claims WHERE run_id = %s FOR UPDATE", (run_id,))
            else:
                cur_claim = _exec(conn, is_tidb, "SELECT worker_id, lease_token, fencing_token, lease_expires_at FROM active_run_claims WHERE run_id = ?", (run_id,))
            claim_row = cur_claim.fetchone()
            if claim_row:
                c_worker = claim_row["worker_id"] if is_tidb else claim_row[0]
                c_lease = claim_row["lease_token"] if is_tidb else claim_row[1]
                c_fencing = claim_row["fencing_token"] if is_tidb else claim_row[2]
                c_expires = claim_row["lease_expires_at"] if is_tidb else claim_row[3]

                # Validate worker, lease, and fencing token
                if worker_id and c_worker != worker_id:
                    raise PermissionError(f"Stale worker {worker_id} rejected; current owner is {c_worker}.")
                if lease_token and c_lease != lease_token:
                    raise PermissionError("Stale lease token rejected.")
                if fencing_token is not None and c_fencing != fencing_token:
                    raise PermissionError(f"Stale fencing token {fencing_token} rejected; current generation is {c_fencing}.")

                # Validate lease expiry timestamp against UTC
                now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                if str(c_expires) < now_str:
                    raise PermissionError(f"Lease expired at {c_expires} (current: {now_str}).")

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
            # For revision numbers allocated via SELECT MAX+1, duplicate revision_num is a sequence race that should be retried with fresh MAX
            err_str = str(exc).upper()
            is_rev_conflict = "UNIQUE" in err_str or "DUPLICATE" in err_str or "1062" in err_str
            if attempt < max_attempts - 1 and (_is_retryable_write_error(exc) or is_rev_conflict):
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
        "beatapi_key": memories.get("api_key_beatapi", "") or os.getenv("BEATAPI_KEY", "") or os.getenv("BEAT_API_KEY", ""),
        "openrouter_api_key": memories.get("api_key_openrouter", "") or os.getenv("OPENROUTER_API_KEY", "") or os.getenv("OPEN_ROUTER_API_KEY", ""),
    }


def save_user_api_keys(
    user_id: int,
    gemini_key: Optional[str] = None,
    openrouter_key: Optional[str] = None,
    beatapi_key: Optional[str] = None,
):
    """Save persistent API keys for a user in user_memory."""
    if gemini_key is not None and gemini_key.strip():
        set_user_memory("api_key_gemini", gemini_key.strip(), memory_type="credential", user_id=user_id)
    if beatapi_key is not None and beatapi_key.strip():
        set_user_memory("api_key_beatapi", beatapi_key.strip(), memory_type="credential", user_id=user_id)
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

def create_research_job_atomic(
    run_id: str,
    topic: str,
    user_id: Optional[int] = None,
    tone: Optional[str] = None,
    audience: Optional[str] = None,
    target_length: Optional[str] = None,
    worker_id: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """Atomically create a new research job with guaranteed cross-process single-run invariant.

    Architecture & TiDB Semantics:
    TiDB does not support gap locking on range queries like `SELECT ... WHERE user_id = ? FOR UPDATE`.
    Therefore, locking on non-existent rows is susceptible to concurrent phantom inserts.
    To enforce bulletproof multi-process concurrency across TiDB and SQLite:
    1. A dedicated `active_run_claims` table with a PRIMARY KEY on `user_id` is used.
    2. Before or during job creation, `INSERT INTO active_run_claims (user_id, run_id, worker_id)` is attempted.
    3. If another worker or process is already running a job for this user, the PRIMARY KEY / UNIQUE constraint
       immediately trips with a duplicate key conflict, rejecting the concurrent submission atomically.
    4. If claim insertion succeeds, the `research_jobs` row is created within the same atomic transaction.
    5. When the job completes, cancels, or fails, the claim is released cleanly.

    Returns:
        (created: bool, active_run_id: Optional[str])
    """
    resolved_worker = worker_id or f"worker_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    lease_token = f"lease_{uuid.uuid4().hex}"
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            # Check if there is an existing claim
            cursor = _exec(conn, is_tidb, "SELECT run_id FROM active_run_claims WHERE user_id = ?", (user_id,))
            claim_row = cursor.fetchone()
            if claim_row:
                active_id = claim_row["run_id"] if is_tidb else claim_row[0]
                return False, active_id

            # Also check existing active jobs table as defense-in-depth
            cursor = _exec(
                conn, is_tidb,
                "SELECT run_id FROM research_jobs WHERE user_id = ? AND status IN ('pending', 'running') LIMIT 1",
                (user_id,),
            )
            job_row = cursor.fetchone()
            if job_row:
                active_id = job_row["run_id"] if is_tidb else job_row[0]
                # Sync claim
                try:
                    _exec(
                        conn, is_tidb,
                        "INSERT OR IGNORE INTO active_run_claims (user_id, run_id, worker_id, lease_token, fencing_token) VALUES (?, ?, ?, ?, 1)"
                        if not is_tidb else
                        "INSERT IGNORE INTO active_run_claims (user_id, run_id, worker_id, lease_token, fencing_token) VALUES (?, ?, ?, ?, 1)",
                        (user_id, active_id, resolved_worker, lease_token),
                    )
                except Exception:
                    pass
                return False, active_id

            # Atomically allocate monotonically increasing fencing token for this user
            if is_tidb:
                _exec(
                    conn, is_tidb,
                    """
                    INSERT INTO user_lease_sequences (user_id, current_fencing)
                    VALUES (%s, 1)
                    ON DUPLICATE KEY UPDATE current_fencing = current_fencing + 1
                    """,
                    (user_id,),
                )
                cur_f = _exec(conn, is_tidb, "SELECT current_fencing FROM user_lease_sequences WHERE user_id = %s", (user_id,))
                fencing_token = int(_get_value(cur_f.fetchone(), True, "current_fencing", 0) or 1)
            else:
                _exec(
                    conn, is_tidb,
                    """
                    INSERT INTO user_lease_sequences (user_id, current_fencing)
                    VALUES (?, 1)
                    ON CONFLICT(user_id) DO UPDATE SET current_fencing = current_fencing + 1
                    """,
                    (user_id,),
                )
                cur_f = _exec(conn, is_tidb, "SELECT current_fencing FROM user_lease_sequences WHERE user_id = ?", (user_id,))
                fencing_token = int(_get_value(cur_f.fetchone(), False, "current_fencing", 0) or 1)

            # Attempt atomic claim insertion with monotonic fencing token and lease expiration
            now_dt = datetime.now(timezone.utc)
            expires_dt = now_dt + timedelta(seconds=120)
            now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
            expires_str = expires_dt.strftime("%Y-%m-%d %H:%M:%S")

            try:
                _exec(
                    conn, is_tidb,
                    "INSERT INTO active_run_claims (user_id, run_id, worker_id, lease_token, fencing_token, claimed_at, heartbeat_at, lease_expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, run_id, resolved_worker, lease_token, fencing_token, now_str, now_str, expires_str),
                )
            except Exception as exc:
                msg = str(exc).lower()
                if "unique" in msg or "duplicate" in msg or "primary key" in msg or "1062" in msg:
                    # Conflict: another concurrent worker claimed this user_id first!
                    cur = _exec(conn, is_tidb, "SELECT run_id FROM active_run_claims WHERE user_id = ?", (user_id,))
                    row = cur.fetchone()
                    active_id = (row["run_id"] if is_tidb else row[0]) if row else "unknown"
                    return False, active_id
                raise

        # Insert the research job row
        _exec(
            conn, is_tidb,
            """INSERT INTO research_jobs
               (run_id, user_id, topic, tone, audience, target_length, status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            (run_id, user_id, topic, tone, audience, target_length),
        )

        # Initialize dedicated SSE job event counter atomically
        if is_tidb:
            _exec(
                conn, is_tidb,
                "INSERT INTO job_event_counters (run_id, last_seq) VALUES (%s, 0) ON DUPLICATE KEY UPDATE last_seq = last_seq",
                (run_id,),
            )
        else:
            _exec(
                conn, is_tidb,
                "INSERT OR IGNORE INTO job_event_counters (run_id, last_seq) VALUES (?, 0)",
                (run_id,),
            )
        return True, None


def heartbeat_active_run_claim(
    run_id: str,
    worker_id: Optional[str] = None,
    lease_token: Optional[str] = None,
    fencing_token: Optional[int] = None,
    extend_seconds: int = 120,
) -> bool:
    """Update heartbeat timestamp and extend lease_expires_at, strictly validating expiry.

    Fencing & Lease Protection:
    Ensures that a stale or expired worker whose lease lapsed cannot renew
    or overwrite an active worker's lease, even if the row has not yet been deleted
    by a recovery sweep.
    Requires:
    - Matching run_id
    - Matching worker_id
    - Matching lease_token
    - Matching fencing_token
    - Current database time <= lease_expires_at (not yet expired)
    """
    now_dt = datetime.now(timezone.utc)
    new_expires_dt = now_dt + timedelta(seconds=max(30, extend_seconds))
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    new_expires_str = new_expires_dt.strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as (conn, is_tidb):
        conditions = [
            "run_id = ?",
            "lease_expires_at >= ?",  # Enforce lease has NOT expired
        ]
        params: List[Any] = [now_str, new_expires_str, run_id, now_str]
        if worker_id:
            conditions.append("worker_id = ?")
            params.append(worker_id)
        if lease_token:
            conditions.append("lease_token = ?")
            params.append(lease_token)
        if fencing_token is not None:
            conditions.append("fencing_token = ?")
            params.append(fencing_token)

        sql = f"UPDATE active_run_claims SET heartbeat_at = ?, lease_expires_at = ? WHERE {' AND '.join(conditions)}"
        cursor = _exec(conn, is_tidb, sql, tuple(params))
        rowcount = getattr(cursor, "rowcount", None)
        return bool(rowcount and rowcount > 0)


def release_active_run_claim(
    run_id: str,
    user_id: Optional[int] = None,
    lease_token: Optional[str] = None,
    fencing_token: Optional[int] = None,
) -> bool:
    """Release active run claim verifying lease ownership."""
    with get_connection() as (conn, is_tidb):
        conditions = ["run_id = ?"]
        params: List[Any] = [run_id]
        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)
        if lease_token:
            conditions.append("lease_token = ?")
            params.append(lease_token)
        if fencing_token is not None:
            conditions.append("fencing_token = ?")
            params.append(fencing_token)

        sql = f"DELETE FROM active_run_claims WHERE {' AND '.join(conditions)}"
        cursor = _exec(conn, is_tidb, sql, tuple(params))
        rowcount = getattr(cursor, "rowcount", None)
        return bool(rowcount and rowcount > 0)


def create_research_job(
    run_id: str,
    topic: str,
    user_id: Optional[int] = None,
    tone: Optional[str] = None,
    audience: Optional[str] = None,
    target_length: Optional[str] = None,
) -> None:
    """Create a new research job in 'pending' status."""
    created, _ = create_research_job_atomic(
        run_id=run_id,
        topic=topic,
        user_id=user_id,
        tone=tone,
        audience=audience,
        target_length=target_length,
    )
    if not created:
        raise ValueError(f"User {user_id} already has an active research job in progress.")


def complete_research_job_atomic(
    run_id: str,
    status: str,
    event_type: str,
    event_payload: Any,
    event_id: Optional[str] = None,
    result_article_id: Optional[int] = None,
    error_message: Optional[str] = None,
    trace_url: Optional[str] = None,
    worker_id: Optional[str] = None,
    lease_token: Optional[str] = None,
    fencing_token: Optional[int] = None,
) -> Tuple[bool, Optional[int]]:
    """Atomically commit terminal job status, terminal SSE event, and claim release in a SINGLE transaction with retry.

    Guarantee:
    1. Locks and validates `research_jobs` row (`SELECT ... FOR UPDATE` on TiDB).
    2. If already in a terminal state ('completed', 'failed', 'cancelled'), aborts transition (returns False, existing_seq_id).
    3. If worker credentials are provided, validates `active_run_claims`.
    4. Increments `job_event_counters` and inserts the terminal event into `job_events` (with event_id idempotency).
    5. Updates `research_jobs` status to terminal state.
    6. Releases `active_run_claims`.
    7. Retries transient transaction conflicts with exponential backoff and jitter.
    8. All operations commit atomically together. If anything fails, everything rolls back.

    Returns:
        (updated: bool, terminal_seq_id: Optional[int])
    """
    import random
    payload_str = json.dumps(event_payload) if not isinstance(event_payload, str) else event_payload
    last_error: Optional[BaseException] = None

    for attempt in range(_MAX_WRITE_RETRIES):
        try:
            with get_connection() as (conn, is_tidb):
                if is_tidb:
                    cursor = conn.cursor()
                    # 1. Lock job row and check status
                    cursor.execute("SELECT status FROM research_jobs WHERE run_id = %s FOR UPDATE", (run_id,))
                    job_row = cursor.fetchone()
                    if not job_row:
                        return False, None
                    curr_status = job_row["status"] if isinstance(job_row, dict) else job_row[0]
                    if curr_status in _TERMINAL_JOB_STATUSES:
                        existing_seq = None
                        if event_id:
                            cursor.execute("SELECT seq_id FROM job_events WHERE run_id = %s AND event_id = %s", (run_id, event_id))
                            erow = cursor.fetchone()
                            if erow:
                                existing_seq = int(erow["seq_id"] if isinstance(erow, dict) else erow[0])
                        return False, existing_seq

                    # 2. Worker fencing validation
                    if lease_token or fencing_token is not None:
                        cursor.execute("SELECT lease_token, fencing_token FROM active_run_claims WHERE run_id = %s FOR UPDATE", (run_id,))
                        claim = cursor.fetchone()
                        if not claim:
                            return False, None
                        cur_lease = claim["lease_token"] if isinstance(claim, dict) else claim[0]
                        cur_fencing = claim["fencing_token"] if isinstance(claim, dict) else claim[1]
                        if lease_token and cur_lease != lease_token:
                            return False, None
                        if fencing_token is not None and cur_fencing != fencing_token:
                            return False, None

                    # 3. Monotonic sequence allocation & event insert
                    cursor.execute(
                        "INSERT INTO job_event_counters (run_id, last_seq) VALUES (%s, 0) ON DUPLICATE KEY UPDATE last_seq = last_seq",
                        (run_id,),
                    )
                    cursor.execute("SELECT last_seq FROM job_event_counters WHERE run_id = %s FOR UPDATE", (run_id,))
                    crow = cursor.fetchone()
                    curr_seq = int((crow["last_seq"] if isinstance(crow, dict) else crow[0]) or 0)
                    next_seq = curr_seq + 1
                    cursor.execute("UPDATE job_event_counters SET last_seq = %s WHERE run_id = %s", (next_seq, run_id))
                    cursor.execute(
                        "INSERT INTO job_events (run_id, seq_id, event_id, event_type, payload) VALUES (%s, %s, %s, %s, %s)",
                        (run_id, next_seq, event_id, event_type, payload_str),
                    )

                    # 4. Status update
                    cursor.execute(
                        """
                        UPDATE research_jobs
                        SET status = %s,
                            result_article_id = COALESCE(%s, result_article_id),
                            error_message = COALESCE(%s, error_message),
                            trace_url = COALESCE(%s, trace_url),
                            updated_at = UTC_TIMESTAMP()
                        WHERE run_id = %s AND status NOT IN ('cancelled', 'failed', 'completed')
                        """,
                        (status, result_article_id, error_message, trace_url, run_id),
                    )

                    # 5. Claim release
                    _exec(conn, is_tidb, "DELETE FROM active_run_claims WHERE run_id = ?", (run_id,))
                    return True, next_seq
                else:
                    # SQLite atomic single-transaction block
                    cur = _exec(conn, is_tidb, "SELECT status FROM research_jobs WHERE run_id = ?", (run_id,))
                    job_row = cur.fetchone()
                    if not job_row:
                        return False, None
                    curr_status = job_row[0]
                    if curr_status in _TERMINAL_JOB_STATUSES:
                        existing_seq = None
                        if event_id:
                            ecur = _exec(conn, is_tidb, "SELECT seq_id FROM job_events WHERE run_id = ? AND event_id = ?", (run_id, event_id))
                            erow = ecur.fetchone()
                            if erow:
                                existing_seq = int(erow[0])
                        return False, existing_seq

                    if lease_token or fencing_token is not None:
                        ccur = _exec(conn, is_tidb, "SELECT lease_token, fencing_token FROM active_run_claims WHERE run_id = ?", (run_id,))
                        claim = ccur.fetchone()
                        if not claim:
                            return False, None
                        if lease_token and claim[0] != lease_token:
                            return False, None
                        if fencing_token is not None and claim[1] != fencing_token:
                            return False, None

                    _exec(conn, is_tidb, "INSERT OR IGNORE INTO job_event_counters (run_id, last_seq) VALUES (?, 0)", (run_id,))
                    _exec(conn, is_tidb, "UPDATE job_event_counters SET last_seq = last_seq + 1 WHERE run_id = ?", (run_id,))
                    scur = _exec(conn, is_tidb, "SELECT last_seq FROM job_event_counters WHERE run_id = ?", (run_id,))
                    next_seq = int(scur.fetchone()[0])

                    _exec(
                        conn, is_tidb,
                        "INSERT INTO job_events (run_id, seq_id, event_id, event_type, payload) VALUES (?, ?, ?, ?, ?)",
                        (run_id, next_seq, event_id, event_type, payload_str),
                    )

                    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    _exec(
                        conn, is_tidb,
                        """
                        UPDATE research_jobs
                        SET status = ?,
                            result_article_id = COALESCE(?, result_article_id),
                            error_message = COALESCE(?, error_message),
                            trace_url = COALESCE(?, trace_url),
                            updated_at = ?
                        WHERE run_id = ? AND status NOT IN ('cancelled', 'failed', 'completed')
                        """,
                        (status, result_article_id, error_message, trace_url, now_str, run_id),
                    )

                    _exec(conn, is_tidb, "DELETE FROM active_run_claims WHERE run_id = ?", (run_id,))
                    return True, next_seq
        except Exception as exc:
            last_error = exc
            if attempt < _MAX_WRITE_RETRIES - 1 and _is_retryable_write_error(exc):
                backoff = (0.02 * (2 ** attempt)) + random.uniform(0.005, 0.025)
                time.sleep(backoff)
                continue
            raise
    raise RuntimeError(f"Could not complete research job atomically for run {run_id}: {last_error}")


_TERMINAL_JOB_STATUSES = ("cancelled", "failed", "completed")


def update_research_job(
    run_id: str,
    status: Optional[str] = None,
    result_article_id: Optional[int] = None,
    error_message: Optional[str] = None,
    trace_url: Optional[str] = None,
    lease_token: Optional[str] = None,
    fencing_token: Optional[int] = None,
) -> bool:
    """Update status/metadata of an existing research job with optional fencing validation.

    Terminal jobs are frozen: a status transition is only applied while the job is
    still ``pending``/``running``. This prevents a slow background worker from
    resurrecting a job the user already cancelled (or a failed job from flipping
    itself back to ``running``). Metadata-only updates stay allowed.

    When lease_token / fencing_token is provided, validates that the caller still holds
    the active lease; if the lease was lost or overtaken by a newer worker, the update
    is rejected immediately.

    When transitioning to a terminal status ('completed', 'failed', 'cancelled'),
    the corresponding active_run_claims lease is automatically freed.

    Returns True when a row was actually updated.
    """
    with get_connection() as (conn, is_tidb):
        # Validate fencing / lease ownership if provided
        if lease_token or fencing_token is not None:
            cur = _exec(conn, is_tidb, "SELECT lease_token, fencing_token FROM active_run_claims WHERE run_id = ?", (run_id,))
            claim = cur.fetchone()
            if not claim:
                # Claim expired or stolen
                return False
            cur_lease = claim["lease_token"] if is_tidb else claim[0]
            cur_fencing = claim["fencing_token"] if is_tidb else claim[1]
            if lease_token and cur_lease != lease_token:
                return False
            if fencing_token is not None and cur_fencing != fencing_token:
                return False

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
        sql = f"UPDATE research_jobs SET {', '.join(updates)} WHERE run_id = ?"
        if status is not None:
            sql += " AND status NOT IN ('cancelled', 'failed', 'completed')"
        cursor = _exec(conn, is_tidb, sql, tuple(params))
        rowcount = getattr(cursor, "rowcount", None)

        if status in _TERMINAL_JOB_STATUSES:
            _exec(conn, is_tidb, "DELETE FROM active_run_claims WHERE run_id = ?", (run_id,))

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


def get_active_run_claim(run_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve the active run claim metadata (worker_id, lease_token, fencing_token, lease_expires_at) for a run."""
    with get_connection() as (conn, is_tidb):
        cur = _exec(
            conn, is_tidb,
            "SELECT user_id, run_id, worker_id, lease_token, fencing_token, lease_expires_at, claimed_at, heartbeat_at FROM active_run_claims WHERE run_id = ?",
            (run_id,),
        )
        row = cur.fetchone()
        return _row_to_dict(row) if row else None


def recover_interrupted_jobs(stale_after_seconds: int = 0) -> int:
    """Mark jobs left in ``pending``/``running`` by a dead worker process as failed.

    Multi-Worker Safety & Lease Architecture:
    In a multi-worker cluster (e.g. 4 Gunicorn/Uvicorn workers), worker restarts must
    NEVER indiscriminately abort running jobs belonging to other live, healthy workers.
    Each active run maintains a lease in `active_run_claims` with periodic heartbeats.

    A job is considered abandoned if:
    1. Its heartbeat in `active_run_claims` or its `updated_at` in `research_jobs` is
       older than `stale_after_seconds` (default: 0 = immediate sweep of orphaned/expired jobs).
    2. Jobs with recent heartbeats are recognized as actively managed by other healthy
       workers and are left untouched.

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
        # Identify stale jobs whose updated_at and claim heartbeat have both lapsed
        cursor = _exec(
            conn,
            is_tidb,
            """
            SELECT j.run_id 
            FROM research_jobs j
            LEFT JOIN active_run_claims c ON j.run_id = c.run_id
            WHERE j.status IN ('pending', 'running')
              AND j.updated_at <= ?
              AND (c.heartbeat_at IS NULL OR c.heartbeat_at <= ?)
            """,
            (cutoff_str, cutoff_str),
        )
        rows = cursor.fetchall()
        recovered_run_ids = [str(_get_value(r, is_tidb, "run_id", 0)) for r in rows]
        if not recovered_run_ids:
            return 0

        # Mark recovered jobs as failed
        cursor = _exec(
            conn,
            is_tidb,
            "UPDATE research_jobs SET status = 'failed', error_message = ?, updated_at = ? "
            "WHERE run_id IN (" + ",".join("?" for _ in recovered_run_ids) + ")",
            (message, now_str, *recovered_run_ids),
        )
        # Release orphaned claims
        _exec(
            conn,
            is_tidb,
            "DELETE FROM active_run_claims WHERE run_id IN (" + ",".join("?" for _ in recovered_run_ids) + ")",
            tuple(recovered_run_ids),
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


def append_job_event(run_id: str, event_type: str, payload: Any, event_id: Optional[str] = None) -> int:
    """Append a sequenced event to the durable job event ledger using job_event_counters with event idempotency.

    Idempotency & Sequence Allocation:
    1. If `event_id` is supplied: check if `(run_id, event_id)` was already committed.
       If found, return the existing `seq_id` immediately without incrementing the sequence counter.
    2. Atomically lock and increment the persistent counter row in `job_event_counters` for this run_id.
    3. Insert the event with `(run_id, seq_id, event_id, event_type, payload)` in the SAME transaction.
    4. If another concurrent process inserts the identical `(run_id, event_id)`, catch the duplicate key
       conflict, rollback, and return the already committed event's `seq_id`.
    5. On any unexpected failure or rollback, the counter increment rolls back cleanly with zero sequence gaps.
    """
    payload_str = json.dumps(payload) if not isinstance(payload, str) else payload
    last_error: Optional[BaseException] = None
    for attempt in range(_MAX_WRITE_RETRIES):
        try:
            with get_connection() as (conn, is_tidb):
                if is_tidb:
                    cursor = conn.cursor()
                    # 1. Pre-check idempotency if event_id provided
                    if event_id:
                        cursor.execute(
                            "SELECT seq_id FROM job_events WHERE run_id = %s AND event_id = %s",
                            (run_id, event_id),
                        )
                        row = cursor.fetchone()
                        if row:
                            return int(_get_value(row, True, "seq_id", 0))

                    # 2. Ensure counter row exists
                    cursor.execute(
                        "INSERT INTO job_event_counters (run_id, last_seq) VALUES (%s, 0) ON DUPLICATE KEY UPDATE last_seq = last_seq",
                        (run_id,),
                    )
                    # 3. Lock counter row and increment
                    cursor.execute(
                        "SELECT last_seq FROM job_event_counters WHERE run_id = %s FOR UPDATE",
                        (run_id,),
                    )
                    row = cursor.fetchone()
                    curr_seq = int(_get_value(row, True, "last_seq", 0) or 0)
                    next_seq = curr_seq + 1
                    cursor.execute(
                        "UPDATE job_event_counters SET last_seq = %s WHERE run_id = %s",
                        (next_seq, run_id),
                    )
                    # 4. Insert event using assigned sequence and optional event_id
                    cursor.execute(
                        "INSERT INTO job_events (run_id, seq_id, event_id, event_type, payload) VALUES (%s, %s, %s, %s, %s)",
                        (run_id, next_seq, event_id, event_type, payload_str),
                    )
                else:
                    # SQLite atomic counter increment & event insertion within transaction
                    if event_id:
                        cur_exist = conn.execute(
                            "SELECT seq_id FROM job_events WHERE run_id = ? AND event_id = ?",
                            (run_id, event_id),
                        )
                        exist_row = cur_exist.fetchone()
                        if exist_row:
                            return int(exist_row[0])

                    conn.execute(
                        "INSERT OR IGNORE INTO job_event_counters (run_id, last_seq) VALUES (?, 0)",
                        (run_id,),
                    )
                    conn.execute(
                        "UPDATE job_event_counters SET last_seq = last_seq + 1 WHERE run_id = ?",
                        (run_id,),
                    )
                    cur_seq = conn.execute(
                        "SELECT last_seq FROM job_event_counters WHERE run_id = ?",
                        (run_id,),
                    )
                    row = cur_seq.fetchone()
                    next_seq = int(row[0] if row else 1)
                    conn.execute(
                        "INSERT INTO job_events (run_id, seq_id, event_id, event_type, payload) VALUES (?, ?, ?, ?, ?)",
                        (run_id, next_seq, event_id, event_type, payload_str),
                    )
                return next_seq
        except Exception as exc:
            last_error = exc
            # Handle duplicate key on (run_id, event_id) if racing another insert
            err_msg = str(exc).lower()
            if event_id and ("uk_event_run_event_id" in err_msg or "unique" in err_msg or "1062" in err_msg):
                try:
                    with get_connection() as (conn, is_tidb):
                        cur = _exec(
                            conn, is_tidb,
                            "SELECT seq_id FROM job_events WHERE run_id = ? AND event_id = ?",
                            (run_id, event_id),
                        )
                        row = cur.fetchone()
                        if row:
                            return int(_get_value(row, is_tidb, "seq_id", 0))
                except Exception:
                    pass

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
            "SELECT seq_id, event_id, event_type, payload, created_at FROM job_events WHERE run_id = ? AND seq_id > ? ORDER BY seq_id ASC LIMIT ?",
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




# ---------------------------------------------------------------------------
# Visual Research System: Visuals, Charts, and Evidence Links
# ---------------------------------------------------------------------------

def save_research_visual(
    user_id: int,
    visual_type: str,
    origin_type: str,
    title: str,
    article_id: Optional[int] = None,
    run_id: Optional[str] = None,
    caption: Optional[str] = None,
    description: Optional[str] = None,
    source_url: Optional[str] = None,
    source_title: Optional[str] = None,
    publisher: Optional[str] = None,
    author: Optional[str] = None,
    publication_date: Optional[str] = None,
    license_information: Optional[str] = None,
    usage_restrictions: Optional[str] = None,
    alt_text: Optional[str] = None,
    dimensions: Optional[str] = None,
    file_format: Optional[str] = None,
    media_content: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    metadata_json: Optional[Dict[str, Any]] = None,
) -> int:
    """Insert a new visual asset into research_visuals and return its primary key."""
    meta_str = json.dumps(metadata_json) if metadata_json else None
    with get_connection() as (conn, is_tidb):
        cur = _exec(
            conn, is_tidb,
            """
            INSERT INTO research_visuals (
                user_id, article_id, run_id, visual_type, origin_type,
                title, caption, description, source_url, source_title,
                publisher, author, publication_date, license_information,
                usage_restrictions, alt_text, dimensions, file_format,
                media_content, thumbnail_url, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, article_id, run_id, visual_type, origin_type,
                title, caption, description, source_url, source_title,
                publisher, author, publication_date, license_information,
                usage_restrictions, alt_text, dimensions, file_format,
                media_content, thumbnail_url, meta_str,
            ),
        )
        return int(cur.lastrowid)


def get_research_visual(visual_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve single visual record owned by user."""
    with get_connection() as (conn, is_tidb):
        cur = _exec(
            conn, is_tidb,
            "SELECT * FROM research_visuals WHERE id = ? AND user_id = ?",
            (visual_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        res = _row_to_dict(row)
        if res.get("metadata_json") and isinstance(res["metadata_json"], str):
            try:
                res["metadata_json"] = json.loads(res["metadata_json"])
            except Exception:
                pass
        return res


def list_research_visuals(
    user_id: int,
    article_id: Optional[int] = None,
    visual_type: Optional[str] = None,
    origin_type: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "recent",
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """List visual assets owned by user with filters and pagination."""
    safe_limit = _clamp_limit(limit, default=50, maximum=100)
    safe_offset = _clamp_offset(offset)
    where_clauses = ["user_id = ?"]
    params: List[Any] = [user_id]

    if article_id is not None:
        where_clauses.append("article_id = ?")
        params.append(article_id)
    if visual_type:
        where_clauses.append("visual_type = ?")
        params.append(visual_type)
    if origin_type:
        where_clauses.append("origin_type = ?")
        params.append(origin_type)
    if search:
        where_clauses.append("(title LIKE ? OR caption LIKE ? OR description LIKE ?)")
        s = f"%{search}%"
        params.extend([s, s, s])

    where_sql = " AND ".join(where_clauses)
    with get_connection() as (conn, is_tidb):
        count_cur = _exec(conn, is_tidb, f"SELECT COUNT(*) FROM research_visuals WHERE {where_sql}", tuple(params))
        crow = count_cur.fetchone()
        total = int(crow[0] if not isinstance(crow, dict) else list(crow.values())[0])
        order_sql = "title ASC" if sort_by == "title" else "created_at DESC, id DESC"
        query_params = list(params) + [safe_limit, safe_offset]
        cur = _exec(conn, is_tidb, f"SELECT * FROM research_visuals WHERE {where_sql} ORDER BY {order_sql} LIMIT ? OFFSET ?", tuple(query_params))
        rows = cur.fetchall()
        items = []
        for r in rows:
            d = _row_to_dict(r)
            if d.get("metadata_json") and isinstance(d["metadata_json"], str):
                try:
                    d["metadata_json"] = json.loads(d["metadata_json"])
                except Exception:
                    pass
            items.append(d)
        return items, total


def delete_research_visual(visual_id: int, user_id: int) -> bool:
    with get_connection() as (conn, is_tidb):
        cur = _exec(conn, is_tidb, "DELETE FROM research_visuals WHERE id = ? AND user_id = ?", (visual_id, user_id))
        rowcount = getattr(cur, "rowcount", None)
        return bool(rowcount and rowcount > 0)


def save_research_chart(
    user_id: int,
    title: str,
    chart_type: str,
    structured_data: Dict[str, Any],
    article_id: Optional[int] = None,
    description: Optional[str] = None,
    data_source: Optional[str] = None,
    units: Optional[str] = None,
    methodology: Optional[str] = None,
) -> int:
    struct_str = json.dumps(structured_data)
    with get_connection() as (conn, is_tidb):
        cur = _exec(
            conn, is_tidb,
            """
            INSERT INTO research_charts (
                user_id, article_id, title, description,
                chart_type, structured_data, data_source, units, methodology
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, article_id, title, description, chart_type, struct_str, data_source, units, methodology),
        )
        return int(cur.lastrowid)


def list_research_charts(user_id: int, article_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with get_connection() as (conn, is_tidb):
        if article_id is not None:
            cur = _exec(conn, is_tidb, "SELECT * FROM research_charts WHERE user_id = ? AND article_id = ? ORDER BY id ASC", (user_id, article_id))
        else:
            cur = _exec(conn, is_tidb, "SELECT * FROM research_charts WHERE user_id = ? ORDER BY id DESC", (user_id,))
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = _row_to_dict(r)
            if d.get("structured_data") and isinstance(d["structured_data"], str):
                try:
                    d["structured_data"] = json.loads(d["structured_data"])
                except Exception:
                    pass
            result.append(d)
        return result


def link_visual_evidence(
    user_id: int,
    visual_id: int,
    claim_id: Optional[str] = None,
    article_id: Optional[int] = None,
    report_section: Optional[str] = None,
    evidence_status: str = "verified",
    citation_url: Optional[str] = None,
) -> int:
    with get_connection() as (conn, is_tidb):
        cur = _exec(
            conn, is_tidb,
            """
            INSERT INTO visual_evidence_links (
                user_id, visual_id, claim_id, article_id,
                report_section, evidence_status, citation_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, visual_id, claim_id, article_id, report_section, evidence_status, citation_url),
        )
        return int(cur.lastrowid)


def get_visual_evidence_links(
    user_id: int,
    visual_id: Optional[int] = None,
    claim_id: Optional[str] = None,
    article_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Retrieve visual evidence links with flexible filtering by user, visual, claim, or article."""
    clauses = ["user_id = ?"]
    params: List[Any] = [user_id]
    if visual_id is not None:
        clauses.append("visual_id = ?")
        params.append(visual_id)
    if claim_id:
        clauses.append("claim_id = ?")
        params.append(claim_id)
    if article_id is not None:
        clauses.append("article_id = ?")
        params.append(article_id)
    where_sql = " AND ".join(clauses)

    with get_connection() as (conn, is_tidb):
        cur = _exec(
            conn, is_tidb,
            f"SELECT * FROM visual_evidence_links WHERE {where_sql} ORDER BY id ASC",
            tuple(params),
        )
        rows = cur.fetchall()
        return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Document Studio Metadata
# ---------------------------------------------------------------------------


def get_document_metadata(article_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve structured academic metadata for a given article."""
    with get_connection() as (conn, is_tidb):
        cur = _exec(
            conn, is_tidb,
            """
            SELECT article_id, user_id, title, abstract, keywords, authors,
                   institution, citation_style, version_tag, layout_settings, updated_at
            FROM document_metadata
            WHERE article_id = ? AND user_id = ?
            """,
            (article_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        d = _row_to_dict(row)
        if d.get("layout_settings") and isinstance(d["layout_settings"], str):
            try:
                d["layout_settings"] = json.loads(d["layout_settings"])
            except Exception:
                pass
        return d


def save_document_metadata(
    article_id: int,
    user_id: int,
    title: Optional[str] = None,
    abstract: Optional[str] = None,
    keywords: Optional[Union[str, List[str]]] = None,
    authors: Optional[Union[str, List[str]]] = None,
    institution: Optional[str] = None,
    citation_style: str = "IEEE",
    version_tag: str = "v1.0",
    layout_settings: Optional[Dict[str, Any]] = None,
) -> bool:
    """Upsert structured academic metadata for an article (SQLite / TiDB compatible)."""
    if isinstance(keywords, list):
        keywords = ", ".join(str(k) for k in keywords)
    if isinstance(authors, list):
        authors = ", ".join(str(a) for a in authors)
    layout_str = json.dumps(layout_settings) if layout_settings is not None else None
    with get_connection() as (conn, is_tidb):
        if is_tidb:
            sql = """
            INSERT INTO document_metadata (
                article_id, user_id, title, abstract, keywords, authors,
                institution, citation_style, version_tag, layout_settings
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                title = VALUES(title),
                abstract = VALUES(abstract),
                keywords = VALUES(keywords),
                authors = VALUES(authors),
                institution = VALUES(institution),
                citation_style = VALUES(citation_style),
                version_tag = VALUES(version_tag),
                layout_settings = VALUES(layout_settings),
                updated_at = NOW()
            """
        else:
            sql = """
            INSERT INTO document_metadata (
                article_id, user_id, title, abstract, keywords, authors,
                institution, citation_style, version_tag, layout_settings, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(article_id) DO UPDATE SET
                title = excluded.title,
                abstract = excluded.abstract,
                keywords = excluded.keywords,
                authors = excluded.authors,
                institution = excluded.institution,
                citation_style = excluded.citation_style,
                version_tag = excluded.version_tag,
                layout_settings = excluded.layout_settings,
                updated_at = datetime('now')
            """
        _exec(
            conn, is_tidb, sql,
            (article_id, user_id, title, abstract, keywords, authors, institution, citation_style, version_tag, layout_str),
        )
        return True


def update_article_content(article_id: int, new_content: str, user_id: Optional[int] = None) -> bool:
    """In-place update of article content and word count without creating a new revision."""
    word_count = len(new_content.split())
    with get_connection() as (conn, is_tidb):
        if is_tidb:
            sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = NOW() WHERE id = ?"
        else:
            sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = datetime('now') WHERE id = ?"
        params: List[Any] = [new_content, word_count, article_id]
        if user_id is not None:
            sql += " AND user_id = ?"
            params.append(user_id)
        cur = _exec(conn, is_tidb, sql, tuple(params))
        rowcount = getattr(cur, "rowcount", -1)
        return rowcount > 0 or rowcount == -1


# ---------------------------------------------------------------------------
# Report & Document Studio: Document Metadata & Settings
# ---------------------------------------------------------------------------

def save_document_metadata(
    article_id: int,
    user_id: int,
    title: Optional[str] = None,
    abstract: Optional[str] = None,
    keywords: Optional[str] = None,
    authors: Optional[str] = None,
    institution: Optional[str] = None,
    citation_style: str = "IEEE",
    version_tag: str = "v1.0",
    layout_settings: Optional[Dict[str, Any]] = None,
) -> bool:
    """Upsert structured academic document metadata for an article."""
    layout_str = json.dumps(layout_settings) if layout_settings is not None else None
    legacy = _legacy_sql()
    with get_connection() as (conn, is_tidb):
        art_cur = _exec(
            conn, is_tidb,
            f"SELECT id FROM articles WHERE id = ? AND (user_id = ?{legacy})",
            (article_id, user_id),
        )
        if not art_cur.fetchone():
            return False

        if is_tidb:
            sql = """
                INSERT INTO document_metadata (
                    article_id, user_id, title, abstract, keywords,
                    authors, institution, citation_style, version_tag, layout_settings
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title),
                    abstract = VALUES(abstract),
                    keywords = VALUES(keywords),
                    authors = VALUES(authors),
                    institution = VALUES(institution),
                    citation_style = VALUES(citation_style),
                    version_tag = VALUES(version_tag),
                    layout_settings = VALUES(layout_settings),
                    updated_at = NOW()
            """
        else:
            sql = """
                INSERT INTO document_metadata (
                    article_id, user_id, title, abstract, keywords,
                    authors, institution, citation_style, version_tag, layout_settings
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(article_id) DO UPDATE SET
                    title = excluded.title,
                    abstract = excluded.abstract,
                    keywords = excluded.keywords,
                    authors = excluded.authors,
                    institution = excluded.institution,
                    citation_style = excluded.citation_style,
                    version_tag = excluded.version_tag,
                    layout_settings = excluded.layout_settings,
                    updated_at = datetime('now')
            """
        _exec(
            conn, is_tidb, sql,
            (
                article_id, user_id, title, abstract, keywords,
                authors, institution, citation_style, version_tag, layout_str
            ),
        )
        return True


def get_document_metadata(article_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve structured academic document metadata for an article."""
    legacy = _legacy_sql()
    with get_connection() as (conn, is_tidb):
        cur = _exec(
            conn, is_tidb,
            f"SELECT * FROM document_metadata WHERE article_id = ? AND (user_id = ?{legacy})",
            (article_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        res = _row_to_dict(row)
        if res.get("layout_settings"):
            try:
                res["layout_settings"] = json.loads(res["layout_settings"])
            except Exception:
                pass
        return res


# init_db() is called explicitly by:
#   - backend/main.py lifespan (production FastAPI startup)
#   - tests/conftest.py isolated_database fixture (per-test reset)
#   - crew.py / app.py entry points via their own startup paths
# It is intentionally NOT called here at module level so that:
#   1. Tests can set RESEARCH_STUDIO_DB_PATH in conftest before the first
#      connection is opened, without racing module-level execution.
#   2. Importing database.py in unit tests that don't need a DB doesn't
#      create a stale file or fail when the path isn't writable yet.


# ---------------------------------------------------------------------------
# Visual Research System: Visuals, Charts, and Evidence Links
# ---------------------------------------------------------------------------

def save_research_visual(
    user_id: int,
    visual_type: str,
    origin_type: str,
    title: str,
    article_id: Optional[int] = None,
    run_id: Optional[str] = None,
    caption: Optional[str] = None,
    description: Optional[str] = None,
    source_url: Optional[str] = None,
    source_title: Optional[str] = None,
    publisher: Optional[str] = None,
    author: Optional[str] = None,
    publication_date: Optional[str] = None,
    license_information: Optional[str] = None,
    usage_restrictions: Optional[str] = None,
    alt_text: Optional[str] = None,
    dimensions: Optional[str] = None,
    file_format: Optional[str] = None,
    media_content: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    metadata_json: Optional[Dict[str, Any]] = None,
) -> int:
    meta_str = json.dumps(metadata_json) if metadata_json else None
    with get_connection() as (conn, is_tidb):
        cur = _exec(
            conn, is_tidb,
            """
            INSERT INTO research_visuals (
                user_id, article_id, run_id, visual_type, origin_type,
                title, caption, description, source_url, source_title,
                publisher, author, publication_date, license_information,
                usage_restrictions, alt_text, dimensions, file_format,
                media_content, thumbnail_url, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, article_id, run_id, visual_type, origin_type,
                title, caption, description, source_url, source_title,
                publisher, author, publication_date, license_information,
                usage_restrictions, alt_text, dimensions, file_format,
                media_content, thumbnail_url, meta_str,
            ),
        )
        return int(cur.lastrowid)


def get_research_visual(visual_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cur = _exec(conn, is_tidb, "SELECT * FROM research_visuals WHERE id = ? AND user_id = ?", (visual_id, user_id))
        else:
            cur = _exec(conn, is_tidb, "SELECT * FROM research_visuals WHERE id = ?", (visual_id,))
        row = cur.fetchone()
        if not row:
            return None
        d = _row_to_dict(row)
        if d.get("metadata_json") and isinstance(d["metadata_json"], str):
            try:
                d["metadata_json"] = json.loads(d["metadata_json"])
            except Exception:
                pass
        return d


def list_research_visuals(
    user_id: int,
    article_id: Optional[int] = None,
    visual_type: Optional[str] = None,
    origin_type: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "recent",
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    safe_limit = _clamp_limit(limit, default=50, maximum=100)
    safe_offset = max(0, offset)
    clauses = ["user_id = ?"]
    params: List[Any] = [user_id]
    if article_id is not None:
        clauses.append("article_id = ?")
        params.append(article_id)
    if visual_type:
        clauses.append("visual_type = ?")
        params.append(visual_type)
    if origin_type:
        clauses.append("origin_type = ?")
        params.append(origin_type)
    if search:
        clauses.append("(title LIKE ? OR caption LIKE ? OR alt_text LIKE ?)")
        wildcard = f"%{search}%"
        params.extend([wildcard, wildcard, wildcard])
    where_sql = " AND ".join(clauses)
    with get_connection() as (conn, is_tidb):
        count_cur = _exec(conn, is_tidb, f"SELECT COUNT(*) FROM research_visuals WHERE {where_sql}", tuple(params))
        crow = count_cur.fetchone()
        total = int(crow[0] if not isinstance(crow, dict) else list(crow.values())[0])
        order_sql = "title ASC" if sort_by == "title" else "created_at DESC, id DESC"
        query_params = list(params) + [safe_limit, safe_offset]
        cur = _exec(conn, is_tidb, f"SELECT * FROM research_visuals WHERE {where_sql} ORDER BY {order_sql} LIMIT ? OFFSET ?", tuple(query_params))
        rows = cur.fetchall()
        items = []
        for r in rows:
            d = _row_to_dict(r)
            if d.get("metadata_json") and isinstance(d["metadata_json"], str):
                try:
                    d["metadata_json"] = json.loads(d["metadata_json"])
                except Exception:
                    pass
            items.append(d)
        return items, total


def delete_research_visual(visual_id: int, user_id: int) -> bool:
    with get_connection() as (conn, is_tidb):
        cur = _exec(conn, is_tidb, "DELETE FROM research_visuals WHERE id = ? AND user_id = ?", (visual_id, user_id))
        rowcount = getattr(cur, "rowcount", None)
        return bool(rowcount and rowcount > 0)


def save_research_chart(
    user_id: int,
    title: str,
    chart_type: str,
    structured_data: Dict[str, Any],
    article_id: Optional[int] = None,
    description: Optional[str] = None,
    data_source: Optional[str] = None,
    units: Optional[str] = None,
    methodology: Optional[str] = None,
) -> int:
    struct_str = json.dumps(structured_data)
    with get_connection() as (conn, is_tidb):
        cur = _exec(
            conn, is_tidb,
            """
            INSERT INTO research_charts (
                user_id, article_id, title, description,
                chart_type, structured_data, data_source, units, methodology
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, article_id, title, description, chart_type, struct_str, data_source, units, methodology),
        )
        return int(cur.lastrowid)


def list_research_charts(user_id: int, article_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with get_connection() as (conn, is_tidb):
        if article_id is not None:
            cur = _exec(conn, is_tidb, "SELECT * FROM research_charts WHERE user_id = ? AND article_id = ? ORDER BY id ASC", (user_id, article_id))
        else:
            cur = _exec(conn, is_tidb, "SELECT * FROM research_charts WHERE user_id = ? ORDER BY id DESC", (user_id,))
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = _row_to_dict(r)
            if d.get("structured_data") and isinstance(d["structured_data"], str):
                try:
                    d["structured_data"] = json.loads(d["structured_data"])
                except Exception:
                    pass
            result.append(d)
        return result


def link_visual_evidence(
    user_id: int,
    visual_id: int,
    claim_id: Optional[str] = None,
    article_id: Optional[int] = None,
    report_section: Optional[str] = None,
    evidence_status: str = "verified",
    citation_url: Optional[str] = None,
) -> int:
    with get_connection() as (conn, is_tidb):
        cur = _exec(
            conn, is_tidb,
            """
            INSERT INTO visual_evidence_links (
                user_id, visual_id, claim_id, article_id,
                report_section, evidence_status, citation_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, visual_id, claim_id, article_id, report_section, evidence_status, citation_url),
        )
        return int(cur.lastrowid)


def get_visual_evidence_links(
    user_id: int,
    visual_id: Optional[int] = None,
    claim_id: Optional[str] = None,
    article_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Retrieve visual evidence links with flexible filtering by user, visual, claim, or article."""
    clauses = ["user_id = ?"]
    params: List[Any] = [user_id]
    if visual_id is not None:
        clauses.append("visual_id = ?")
        params.append(visual_id)
    if claim_id:
        clauses.append("claim_id = ?")
        params.append(claim_id)
    if article_id is not None:
        clauses.append("article_id = ?")
        params.append(article_id)
    where_sql = " AND ".join(clauses)

    with get_connection() as (conn, is_tidb):
        cur = _exec(
            conn, is_tidb,
            f"SELECT * FROM visual_evidence_links WHERE {where_sql} ORDER BY id ASC",
            tuple(params),
        )
        rows = cur.fetchall()
        return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Document Studio Metadata
# ---------------------------------------------------------------------------


def get_document_metadata(article_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve structured academic metadata for a given article."""
    with get_connection() as (conn, is_tidb):
        cur = _exec(
            conn, is_tidb,
            """
            SELECT article_id, user_id, title, abstract, keywords, authors,
                   institution, citation_style, version_tag, layout_settings, updated_at
            FROM document_metadata
            WHERE article_id = ? AND user_id = ?
            """,
            (article_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        d = _row_to_dict(row)
        if d.get("layout_settings") and isinstance(d["layout_settings"], str):
            try:
                d["layout_settings"] = json.loads(d["layout_settings"])
            except Exception:
                pass
        return d


def save_document_metadata(
    article_id: int,
    user_id: int,
    title: Optional[str] = None,
    abstract: Optional[str] = None,
    keywords: Optional[Union[str, List[str]]] = None,
    authors: Optional[Union[str, List[str]]] = None,
    institution: Optional[str] = None,
    citation_style: str = "IEEE",
    version_tag: str = "v1.0",
    layout_settings: Optional[Dict[str, Any]] = None,
) -> bool:
    """Upsert structured academic metadata for an article (SQLite / TiDB compatible)."""
    if isinstance(keywords, list):
        keywords = ", ".join(str(k) for k in keywords)
    if isinstance(authors, list):
        authors = ", ".join(str(a) for a in authors)
    layout_str = json.dumps(layout_settings) if layout_settings is not None else None
    with get_connection() as (conn, is_tidb):
        if is_tidb:
            sql = """
            INSERT INTO document_metadata (
                article_id, user_id, title, abstract, keywords, authors,
                institution, citation_style, version_tag, layout_settings
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                title = VALUES(title),
                abstract = VALUES(abstract),
                keywords = VALUES(keywords),
                authors = VALUES(authors),
                institution = VALUES(institution),
                citation_style = VALUES(citation_style),
                version_tag = VALUES(version_tag),
                layout_settings = VALUES(layout_settings),
                updated_at = NOW()
            """
        else:
            sql = """
            INSERT INTO document_metadata (
                article_id, user_id, title, abstract, keywords, authors,
                institution, citation_style, version_tag, layout_settings, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(article_id) DO UPDATE SET
                title = excluded.title,
                abstract = excluded.abstract,
                keywords = excluded.keywords,
                authors = excluded.authors,
                institution = excluded.institution,
                citation_style = excluded.citation_style,
                version_tag = excluded.version_tag,
                layout_settings = excluded.layout_settings,
                updated_at = datetime('now')
            """
        _exec(
            conn, is_tidb, sql,
            (article_id, user_id, title, abstract, keywords, authors, institution, citation_style, version_tag, layout_str),
        )
        return True


def update_article_content(article_id: int, new_content: str, user_id: Optional[int] = None) -> bool:
    """In-place update of article content and word count without creating a new revision."""
    word_count = len(new_content.split())
    with get_connection() as (conn, is_tidb):
        if is_tidb:
            sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = NOW() WHERE id = ?"
        else:
            sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = datetime('now') WHERE id = ?"
        params: List[Any] = [new_content, word_count, article_id]
        if user_id is not None:
            sql += " AND user_id = ?"
            params.append(user_id)
        cur = _exec(conn, is_tidb, sql, tuple(params))
        rowcount = getattr(cur, "rowcount", -1)
        return rowcount > 0 or rowcount == -1


def cleanup_stale_operational_data(retention_days: int = 30) -> Dict[str, int]:
    """Purge old append-only job_events and security_audit_logs beyond retention_days."""
    cutoff_ts = time.time() - (max(1, retention_days) * 86400)
    deleted: Dict[str, int] = {"job_events": 0, "security_audit_logs": 0}
    with get_db_connection() as conn:
        cur = conn.cursor()
        for table in ("job_events", "security_audit_logs"):
            try:
                cur.execute(f"DELETE FROM {table} WHERE created_at < %s" if USE_TIDB else f"DELETE FROM {table} WHERE created_at < ?", (cutoff_ts,))
                deleted[table] = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            except Exception as exc:
                logger.debug("Retention cleanup skipped for %s: %s", table, exc)
        conn.commit()
    return deleted
