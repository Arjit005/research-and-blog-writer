"""Database layer supporting TiDB Cloud (MySQL-compatible) with SQLite fallback.

If TiDB Cloud environment variables (TIDB_HOST, TIDB_USER, TIDB_PASSWORD) are set,
the application connects to TiDB Cloud with TLS/SSL encryption.
Otherwise, it falls back to local SQLite (research_studio.db) with WAL mode.
"""

from __future__ import annotations

import os
import json
import sqlite3
import hashlib
import logging
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Local SQLite database path
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "research_studio.db")


def is_tidb_configured() -> bool:
    """Check if TiDB Cloud credentials are provided."""
    return bool(os.getenv("TIDB_HOST") and os.getenv("TIDB_USER"))


def get_active_backend() -> str:
    """Return 'tidb' if TiDB Cloud is active, otherwise 'sqlite'."""
    return "tidb" if is_tidb_configured() else "sqlite"


@contextmanager
def get_connection():
    """Yield a database connection and a helper execute wrapper.

    Yields:
        (conn, execute_fn, is_tidb_bool)
    """
    if is_tidb_configured():
        try:
            import pymysql
            from pymysql.cursors import DictCursor

            host = os.getenv("TIDB_HOST")
            port = int(os.getenv("TIDB_PORT", 4000))
            user = os.getenv("TIDB_USER")
            password = os.getenv("TIDB_PASSWORD", "")
            database = os.getenv("TIDB_DATABASE", "test")

            # TiDB Cloud requires SSL/TLS
            conn = pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                cursorclass=DictCursor,
                ssl={"check_hostname": False},
                connect_timeout=10,
                autocommit=False,
            )

            try:
                yield conn, True
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            return
        except Exception as e:
            logger.warning(f"Failed to connect to TiDB Cloud ({e}). Falling back to local SQLite.")

    # SQLite fallback
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn, False
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _exec(conn: Any, is_tidb: bool, sql: str, params: Tuple = ()) -> Any:
    """Execute SQL query handling placeholder differences (? for SQLite, %s for TiDB) with auto-reconnect retry."""
    if is_tidb:
        tidb_sql = sql.replace("?", "%s")
        # Pre-ping reconnection to defeat idle serverless drops
        try:
            conn.ping(reconnect=True)
        except Exception:
            pass
        cursor = conn.cursor()
        try:
            cursor.execute(tidb_sql, params)
        except Exception:
            # Reconnect-once retry for idle serverless drops
            try:
                conn.ping(reconnect=True)
                cursor = conn.cursor()
                cursor.execute(tidb_sql, params)
            except Exception:
                raise
        return cursor
    else:
        return conn.execute(sql, params)


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
                return False, "Connection to TiDB failed. Falling back to local SQLite."
            cursor = _exec(conn, True, "SELECT 1 AS alive")
            row = cursor.fetchone()
            if row:
                return True, "TiDB Cloud Serverless connected and healthy."
            return False, "TiDB returned empty response to ping."
    except Exception as e:
        return False, f"TiDB connection error: {e}"


def _ensure_column_exists(conn: Any, is_tidb: bool, table: str, col: str, col_type: str):
    """Safely and idempotently ensure a column exists in a table across TiDB and SQLite."""
    if is_tidb:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) AS cnt 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
            """,
            (table, col),
        )
        res = cursor.fetchone()
        cnt = res["cnt"] if isinstance(res, dict) else res[0]
        if cnt == 0:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
    else:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        existing_cols = [row[1] for row in cursor.fetchall()]
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")


def init_db():
    """Initialize database schemas and apply idempotent migrations on TiDB Cloud or SQLite."""
    with get_connection() as (conn, is_tidb):
        if is_tidb:
            cursor = conn.cursor()
            # Migration tracking table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INT PRIMARY KEY,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 1. Base Studio Tables
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id                  INT AUTO_INCREMENT PRIMARY KEY,
                    user_id             INT NULL,
                    topic               TEXT NOT NULL,
                    content             MEDIUMTEXT NOT NULL,
                    word_count          INT NOT NULL DEFAULT 0,
                    tone                VARCHAR(100) DEFAULT 'Professional & Authoritative',
                    audience            VARCHAR(100) DEFAULT 'Software Engineers & Developers',
                    target_length       VARCHAR(100) DEFAULT 'Standard Blog (1,500 - 2,000 words)',
                    generation_time_sec DOUBLE DEFAULT 0,
                    tokens_used         INT DEFAULT 0,
                    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_art_user (user_id)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id          INT AUTO_INCREMENT PRIMARY KEY,
                    user_id     INT NULL,
                    article_id  INT NOT NULL,
                    role        VARCHAR(20) NOT NULL,
                    content     MEDIUMTEXT NOT NULL,
                    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_chat_article (article_id),
                    INDEX idx_chat_user (user_id)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_runs (
                    id                INT AUTO_INCREMENT PRIMARY KEY,
                    user_id           INT NULL,
                    article_id        INT,
                    topic             TEXT NOT NULL,
                    duration_sec      DOUBLE DEFAULT 0,
                    tokens_estimated  INT DEFAULT 0,
                    models_used       TEXT,
                    fallback_count    INT DEFAULT 0,
                    fallback_events   MEDIUMTEXT,
                    readability_score DOUBLE DEFAULT 0,
                    readability_grade VARCHAR(100) DEFAULT 'N/A',
                    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_telem_user (user_id)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS security_audit_logs (
                    id          INT AUTO_INCREMENT PRIMARY KEY,
                    user_id     INT NULL,
                    event_type  VARCHAR(100) NOT NULL,
                    details     TEXT NOT NULL,
                    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_audit_user (user_id)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS research_cache (
                    url_hash        VARCHAR(64) PRIMARY KEY,
                    url             TEXT NOT NULL,
                    compact_content MEDIUMTEXT NOT NULL,
                    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_memory (
                    id           INT AUTO_INCREMENT PRIMARY KEY,
                    user_id      INT NULL,
                    user_key     VARCHAR(128) NOT NULL DEFAULT 'default_user',
                    memory_type  VARCHAR(64) NOT NULL DEFAULT 'preference',
                    memory_key   VARCHAR(128) NOT NULL,
                    memory_value TEXT NOT NULL,
                    updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_user_mem (user_key, memory_key),
                    INDEX idx_mem_user (user_id)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    article_id      INT PRIMARY KEY,
                    user_id         INT NULL,
                    running_summary MEDIUMTEXT,
                    message_count   INT DEFAULT 0,
                    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_sess_usr (user_id)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS article_revisions (
                    id           INT AUTO_INCREMENT PRIMARY KEY,
                    user_id      INT NULL,
                    article_id   INT NOT NULL,
                    revision_num INT NOT NULL,
                    content      MEDIUMTEXT NOT NULL,
                    summary      VARCHAR(255) DEFAULT 'Copilot edit',
                    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_rev_art (article_id),
                    INDEX idx_rev_usr (user_id),
                    UNIQUE KEY uk_art_rev (article_id, revision_num)
                );
            """)

            # 2. Auth Tables (Milestone 1)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id            INT AUTO_INCREMENT PRIMARY KEY,
                    email         VARCHAR(255) NOT NULL UNIQUE,
                    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_login_at DATETIME NULL,
                    is_active     TINYINT(1) NOT NULL DEFAULT 1
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS otp_codes (
                    id         INT AUTO_INCREMENT PRIMARY KEY,
                    email      VARCHAR(255) NOT NULL,
                    code_hash  CHAR(64) NOT NULL,
                    expires_at DATETIME NOT NULL,
                    attempts   INT NOT NULL DEFAULT 0,
                    used       TINYINT(1) NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    request_ip VARCHAR(64) NULL,
                    INDEX idx_otp_email (email, created_at)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    id           INT AUTO_INCREMENT PRIMARY KEY,
                    user_id      INT NOT NULL,
                    token_hash   CHAR(64) NOT NULL UNIQUE,
                    expires_at   DATETIME NOT NULL,
                    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at DATETIME NULL,
                    INDEX idx_sess_user (user_id)
                );
            """)

            # Ensure user_id column exists on pre-existing tables if created earlier
            for tbl in ["articles", "chat_history", "telemetry_runs", "security_audit_logs", "user_memory", "chat_sessions", "article_revisions"]:
                _ensure_column_exists(conn, is_tidb, tbl, "user_id", "INT NULL")

        else:
            # SQLite Backend
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS articles (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NULL,
                    topic       TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    word_count  INTEGER NOT NULL DEFAULT 0,
                    tone        TEXT DEFAULT 'Professional & Authoritative',
                    audience    TEXT DEFAULT 'Software Engineers & Developers',
                    target_length TEXT DEFAULT 'Standard Blog (1,500 - 2,000 words)',
                    generation_time_sec REAL DEFAULT 0,
                    tokens_used INTEGER DEFAULT 0,
                    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS chat_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NULL,
                    article_id  INTEGER NOT NULL,
                    role        TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content     TEXT NOT NULL,
                    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS telemetry_runs (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id           INTEGER NULL,
                    article_id        INTEGER,
                    topic             TEXT NOT NULL,
                    duration_sec      REAL DEFAULT 0,
                    tokens_estimated  INTEGER DEFAULT 0,
                    models_used       TEXT DEFAULT '[]',
                    fallback_count    INTEGER DEFAULT 0,
                    fallback_events   TEXT DEFAULT '[]',
                    readability_score REAL DEFAULT 0,
                    readability_grade TEXT DEFAULT 'N/A',
                    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS security_audit_logs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NULL,
                    event_type  TEXT NOT NULL,
                    details     TEXT NOT NULL,
                    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS research_cache (
                    url_hash        TEXT PRIMARY KEY,
                    url             TEXT NOT NULL,
                    compact_content TEXT NOT NULL,
                    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS user_memory (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      INTEGER NULL,
                    user_key     TEXT NOT NULL DEFAULT 'default_user',
                    memory_type  TEXT NOT NULL DEFAULT 'preference',
                    memory_key   TEXT NOT NULL,
                    memory_value TEXT NOT NULL,
                    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(user_key, memory_key)
                );

                CREATE TABLE IF NOT EXISTS chat_sessions (
                    article_id      INTEGER PRIMARY KEY,
                    user_id         INTEGER NULL,
                    running_summary TEXT,
                    message_count   INTEGER DEFAULT 0,
                    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS article_revisions (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      INTEGER NULL,
                    article_id   INTEGER NOT NULL,
                    revision_num INTEGER NOT NULL,
                    content      TEXT NOT NULL,
                    summary      TEXT DEFAULT 'Copilot edit',
                    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
                    UNIQUE(article_id, revision_num)
                );

                CREATE TABLE IF NOT EXISTS users (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    email         TEXT NOT NULL UNIQUE,
                    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                    last_login_at TEXT NULL,
                    is_active     INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS otp_codes (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    email      TEXT NOT NULL,
                    code_hash  TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    attempts   INTEGER NOT NULL DEFAULT 0,
                    used       INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    request_ip TEXT NULL
                );

                CREATE TABLE IF NOT EXISTS auth_sessions (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      INTEGER NOT NULL,
                    token_hash   TEXT NOT NULL UNIQUE,
                    expires_at   TEXT NOT NULL,
                    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
                    last_seen_at TEXT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_chat_article ON chat_history(article_id);
                CREATE INDEX IF NOT EXISTS idx_articles_created ON articles(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_telemetry_created ON telemetry_runs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_user_mem ON user_memory(user_key);
                CREATE INDEX IF NOT EXISTS idx_rev_art ON article_revisions(article_id);
                CREATE INDEX IF NOT EXISTS idx_otp_email ON otp_codes(email, created_at);
                CREATE INDEX IF NOT EXISTS idx_sess_user ON auth_sessions(user_id);
            """)

            # Ensure user_id column exists on pre-existing tables if created earlier
            for tbl in ["articles", "chat_history", "telemetry_runs", "security_audit_logs", "user_memory", "chat_sessions", "article_revisions"]:
                _ensure_column_exists(conn, is_tidb, tbl, "user_id", "INTEGER")

            conn.executescript("""
                CREATE INDEX IF NOT EXISTS idx_art_user ON articles(user_id);
                CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_history(user_id);
                CREATE INDEX IF NOT EXISTS idx_telem_user ON telemetry_runs(user_id);
            """)


# ---------------------------------------------------------------------------
# Auth CRUD (Users, OTP Codes, Auth Sessions, Legacy Claiming)
# ---------------------------------------------------------------------------

def get_or_create_user(email: str) -> Dict[str, Any]:
    """Retrieve existing user by normalized email, or create a new user on first verified login."""
    norm_email = email.strip().lower()
    with get_connection() as (conn, is_tidb):
        cursor = _exec(conn, is_tidb, "SELECT id, email, created_at, last_login_at, is_active FROM users WHERE email = ?", (norm_email,))
        row = cursor.fetchone()
        if row:
            return dict(row)

        cursor = _exec(conn, is_tidb, "INSERT INTO users (email, is_active) VALUES (?, 1)", (norm_email,))
        user_id = cursor.lastrowid
        cursor = _exec(conn, is_tidb, "SELECT id, email, created_at, last_login_at, is_active FROM users WHERE id = ?", (user_id,))
        new_row = cursor.fetchone()
        return dict(new_row)


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve user record by user_id."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(conn, is_tidb, "SELECT id, email, created_at, last_login_at, is_active FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Retrieve user record by email, or None if non-existent."""
    norm_email = email.strip().lower()
    with get_connection() as (conn, is_tidb):
        cursor = _exec(conn, is_tidb, "SELECT id, email, created_at, last_login_at, is_active FROM users WHERE email = ?", (norm_email,))
        row = cursor.fetchone()
        return dict(row) if row else None


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
        return dict(row) if row else None


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
        return dict(row) if row else None


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


def get_articles(limit=50, user_id: Optional[int] = None):
    """Fetch recent articles ordered by creation date, scoped to user_id if provided."""
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                """SELECT id, user_id, topic, content, word_count, tone, audience, target_length,
                          generation_time_sec, tokens_used, created_at, updated_at
                   FROM articles WHERE user_id = ? ORDER BY created_at DESC LIMIT ?""",
                (user_id, limit),
            )
        else:
            cursor = _exec(
                conn, is_tidb,
                """SELECT id, user_id, topic, content, word_count, tone, audience, target_length,
                          generation_time_sec, tokens_used, created_at, updated_at
                   FROM articles ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


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
        return dict(row) if row else None


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

def get_article_revisions(article_id: int, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch all stored revisions for an article ordered from latest to oldest."""
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                """SELECT id, user_id, article_id, revision_num, content, summary, created_at
                   FROM article_revisions WHERE article_id = ? AND (user_id = ? OR user_id IS NULL)
                   ORDER BY revision_num DESC""",
                (article_id, user_id),
            )
        else:
            cursor = _exec(
                conn, is_tidb,
                """SELECT id, user_id, article_id, revision_num, content, summary, created_at
                   FROM article_revisions WHERE article_id = ? ORDER BY revision_num DESC""",
                (article_id,),
            )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def get_single_revision(revision_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Fetch a specific revision by ID."""
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                """SELECT id, user_id, article_id, revision_num, content, summary, created_at
                   FROM article_revisions WHERE id = ? AND (user_id = ? OR user_id IS NULL)""",
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
        return dict(row) if row else None


def apply_article_edit_transaction(article_id: int, new_content: str, summary: str = "Copilot revision", user_id: Optional[int] = None) -> int:
    """Atomic transaction: snapshots current article content into article_revisions, then updates articles.content.

    Returns the new revision number. Scoped to user_id if provided.
    """
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(conn, is_tidb, "SELECT content FROM articles WHERE id = ? AND user_id = ?", (article_id, user_id))
        else:
            cursor = _exec(conn, is_tidb, "SELECT content FROM articles WHERE id = ?", (article_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Article {article_id} not found or access denied.")

        current_content = row["content"] if is_tidb else row[0]

        cursor = _exec(conn, is_tidb, "SELECT COALESCE(MAX(revision_num), 0) + 1 AS next_rev FROM article_revisions WHERE article_id = ?", (article_id,))
        rev_row = cursor.fetchone()
        next_rev = (rev_row["next_rev"] if is_tidb else rev_row[0]) or 1

        _exec(
            conn, is_tidb,
            "INSERT INTO article_revisions (article_id, revision_num, content, summary, user_id) VALUES (?, ?, ?, ?, ?)",
            (article_id, next_rev, current_content, summary, user_id),
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
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                "SELECT revision_num, content FROM article_revisions WHERE id = ? AND article_id = ? AND (user_id = ? OR user_id IS NULL)",
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

        target_rev_num = target_row["revision_num"] if is_tidb else target_row[0]
        target_content = target_row["content"] if is_tidb else target_row[1]

        if user_id is not None:
            cursor = _exec(conn, is_tidb, "SELECT content FROM articles WHERE id = ? AND user_id = ?", (article_id, user_id))
        else:
            cursor = _exec(conn, is_tidb, "SELECT content FROM articles WHERE id = ?", (article_id,))
        curr_row = cursor.fetchone()
        if not curr_row:
            return False
        current_content = curr_row["content"] if is_tidb else curr_row[0]

        cursor = _exec(conn, is_tidb, "SELECT COALESCE(MAX(revision_num), 0) + 1 AS next_rev FROM article_revisions WHERE article_id = ?", (article_id,))
        rev_row = cursor.fetchone()
        next_rev = (rev_row["next_rev"] if is_tidb else rev_row[0]) or 1

        _exec(
            conn, is_tidb,
            "INSERT INTO article_revisions (article_id, revision_num, content, summary, user_id) VALUES (?, ?, ?, ?, ?)",
            (article_id, next_rev, current_content, f"Before rollback to revision {target_rev_num}", user_id),
        )

        word_count = len(target_content.split())
        if is_tidb:
            sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = NOW() WHERE id = ?"
        else:
            sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = datetime('now') WHERE id = ?"
        _exec(conn, is_tidb, sql, (target_content, word_count, article_id))

        return True


def delete_article(article_id: int, user_id: Optional[int] = None):
    """Delete an article and its associated chat history, respecting user ownership."""
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            _exec(conn, is_tidb, "DELETE FROM articles WHERE id = ? AND user_id = ?", (article_id, user_id))
            _exec(conn, is_tidb, "DELETE FROM chat_history WHERE article_id = ? AND (user_id = ? OR user_id IS NULL)", (article_id, user_id))
            _exec(conn, is_tidb, "DELETE FROM article_revisions WHERE article_id = ? AND (user_id = ? OR user_id IS NULL)", (article_id, user_id))
        else:
            _exec(conn, is_tidb, "DELETE FROM articles WHERE id = ?", (article_id,))
            if is_tidb:
                _exec(conn, is_tidb, "DELETE FROM chat_history WHERE article_id = ?", (article_id,))
                _exec(conn, is_tidb, "DELETE FROM article_revisions WHERE article_id = ?", (article_id,))


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
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                "SELECT role, content, created_at FROM chat_history WHERE article_id = ? AND (user_id = ? OR user_id IS NULL) ORDER BY id ASC",
                (article_id, user_id),
            )
        else:
            cursor = _exec(
                conn, is_tidb,
                "SELECT role, content, created_at FROM chat_history WHERE article_id = ? ORDER BY id ASC",
                (article_id,),
            )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def clear_chat_history(article_id: int, user_id: Optional[int] = None):
    """Delete all chat messages for an article."""
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            _exec(conn, is_tidb, "DELETE FROM chat_history WHERE article_id = ? AND (user_id = ? OR user_id IS NULL)", (article_id, user_id))
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
                fallback_count, fallback_events, readability_score, readability_grade, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                """SELECT id, user_id, article_id, topic, duration_sec, tokens_estimated,
                          models_used, fallback_count, fallback_events,
                          readability_score, readability_grade, created_at
                   FROM telemetry_runs WHERE user_id = ? OR user_id IS NULL ORDER BY created_at DESC LIMIT ?""",
                (user_id, limit),
            )
        else:
            cursor = _exec(
                conn, is_tidb,
                """SELECT id, user_id, article_id, topic, duration_sec, tokens_estimated,
                          models_used, fallback_count, fallback_events,
                          readability_score, readability_grade, created_at
                   FROM telemetry_runs ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
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
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                "SELECT id, user_id, event_type, details, created_at FROM security_audit_logs WHERE user_id = ? OR user_id IS NULL ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            )
        else:
            cursor = _exec(
                conn, is_tidb,
                "SELECT id, user_id, event_type, details, created_at FROM security_audit_logs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Context & Memory Layer CRUD (Global Research Cache, Per-User Preferences)
# ---------------------------------------------------------------------------

def get_cached_scrape_with_ttl(url: str, ttl_hours: int = 24) -> Optional[str]:
    """Retrieve compact scraped text from cache if created within ttl_hours.

    Global cache: holds scrubbed public summaries without user PII.
    """
    url_hash = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()
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
            return row["compact_content"] if is_tidb else row[0]
        return None


def get_cached_scrape(url: str) -> Optional[str]:
    """Retrieve compact scraped text from cache with default 24hr TTL."""
    return get_cached_scrape_with_ttl(url, ttl_hours=24)


def set_cached_scrape(url: str, compact_content: str):
    """Store or update compact scraped text in cache."""
    url_hash = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()
    with get_connection() as (conn, is_tidb):
        if is_tidb:
            sql = """
                INSERT INTO research_cache (url_hash, url, compact_content)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE compact_content = VALUES(compact_content)
            """
            cursor = conn.cursor()
            cursor.execute(sql, (url_hash, url, compact_content))
        else:
            sql = """
                INSERT INTO research_cache (url_hash, url, compact_content)
                VALUES (?, ?, ?)
                ON CONFLICT(url_hash) DO UPDATE SET compact_content = excluded.compact_content
            """
            conn.execute(sql, (url_hash, url, compact_content))


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


def get_chat_session(article_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Retrieve the rolling summary and message count for a chat session."""
    with get_connection() as (conn, is_tidb):
        if user_id is not None:
            cursor = _exec(
                conn, is_tidb,
                "SELECT article_id, user_id, running_summary, message_count FROM chat_sessions WHERE article_id = ? AND (user_id = ? OR user_id IS NULL)",
                (article_id, user_id),
            )
        else:
            cursor = _exec(
                conn, is_tidb,
                "SELECT article_id, user_id, running_summary, message_count FROM chat_sessions WHERE article_id = ?",
                (article_id,),
            )
        row = cursor.fetchone()
        return dict(row) if row else None


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
        return dict(row) if row else {}


# Auto-initialize database on import
init_db()
