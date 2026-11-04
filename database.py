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
from datetime import datetime
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
    """Execute SQL query handling placeholder differences (? for SQLite, %s for TiDB)."""
    if is_tidb:
        tidb_sql = sql.replace("?", "%s")
        cursor = conn.cursor()
        cursor.execute(tidb_sql, params)
        return cursor
    else:
        return conn.execute(sql, params)


def init_db():
    """Initialize database schemas on TiDB Cloud or SQLite."""
    with get_connection() as (conn, is_tidb):
        if is_tidb:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id                  INT AUTO_INCREMENT PRIMARY KEY,
                    topic               TEXT NOT NULL,
                    content             MEDIUMTEXT NOT NULL,
                    word_count          INT NOT NULL DEFAULT 0,
                    tone                VARCHAR(100) DEFAULT 'Professional & Authoritative',
                    audience            VARCHAR(100) DEFAULT 'Software Engineers & Developers',
                    target_length       VARCHAR(100) DEFAULT 'Standard Blog (1,500 - 2,000 words)',
                    generation_time_sec DOUBLE DEFAULT 0,
                    tokens_used         INT DEFAULT 0,
                    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id          INT AUTO_INCREMENT PRIMARY KEY,
                    article_id  INT NOT NULL,
                    role        VARCHAR(20) NOT NULL,
                    content     MEDIUMTEXT NOT NULL,
                    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_chat_article (article_id)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_runs (
                    id                INT AUTO_INCREMENT PRIMARY KEY,
                    article_id        INT,
                    topic             TEXT NOT NULL,
                    duration_sec      DOUBLE DEFAULT 0,
                    tokens_estimated  INT DEFAULT 0,
                    models_used       TEXT,
                    fallback_count    INT DEFAULT 0,
                    fallback_events   MEDIUMTEXT,
                    readability_score DOUBLE DEFAULT 0,
                    readability_grade VARCHAR(100) DEFAULT 'N/A',
                    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS security_audit_logs (
                    id          INT AUTO_INCREMENT PRIMARY KEY,
                    event_type  VARCHAR(100) NOT NULL,
                    details     TEXT NOT NULL,
                    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
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
                    user_key     VARCHAR(128) NOT NULL DEFAULT 'default_user',
                    memory_type  VARCHAR(64) NOT NULL DEFAULT 'preference',
                    memory_key   VARCHAR(128) NOT NULL,
                    memory_value TEXT NOT NULL,
                    updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_user_mem (user_key, memory_key)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    article_id      INT PRIMARY KEY,
                    running_summary MEDIUMTEXT,
                    message_count   INT DEFAULT 0,
                    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS article_revisions (
                    id           INT AUTO_INCREMENT PRIMARY KEY,
                    article_id   INT NOT NULL,
                    revision_num INT NOT NULL,
                    content      MEDIUMTEXT NOT NULL,
                    summary      VARCHAR(255) DEFAULT 'Copilot edit',
                    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_rev_art (article_id),
                    UNIQUE KEY uk_art_rev (article_id, revision_num)
                );
            """)
        else:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS articles (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic       TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    word_count  INTEGER NOT NULL DEFAULT 0,
                    tone        TEXT DEFAULT 'Professional & Authoritative',
                    audience    TEXT DEFAULT 'Software Engineers & Developers',
                    target_length TEXT DEFAULT 'Standard Blog (1,500 - 2,000 words)',
                    generation_time_sec REAL DEFAULT 0,
                    tokens_used INTEGER DEFAULT 0,
                    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                );

                CREATE TABLE IF NOT EXISTS chat_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id  INTEGER NOT NULL,
                    role        TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content     TEXT NOT NULL,
                    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS telemetry_runs (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id        INTEGER,
                    topic             TEXT NOT NULL,
                    duration_sec      REAL DEFAULT 0,
                    tokens_estimated  INTEGER DEFAULT 0,
                    models_used       TEXT DEFAULT '[]',
                    fallback_count    INTEGER DEFAULT 0,
                    fallback_events   TEXT DEFAULT '[]',
                    readability_score REAL DEFAULT 0,
                    readability_grade TEXT DEFAULT 'N/A',
                    created_at        TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS security_audit_logs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type  TEXT NOT NULL,
                    details     TEXT NOT NULL,
                    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                );

                CREATE TABLE IF NOT EXISTS research_cache (
                    url_hash        TEXT PRIMARY KEY,
                    url             TEXT NOT NULL,
                    compact_content TEXT NOT NULL,
                    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                );

                CREATE TABLE IF NOT EXISTS user_memory (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_key     TEXT NOT NULL DEFAULT 'default_user',
                    memory_type  TEXT NOT NULL DEFAULT 'preference',
                    memory_key   TEXT NOT NULL,
                    memory_value TEXT NOT NULL,
                    updated_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                    UNIQUE(user_key, memory_key)
                );

                CREATE TABLE IF NOT EXISTS chat_sessions (
                    article_id      INTEGER PRIMARY KEY,
                    running_summary TEXT,
                    message_count   INTEGER DEFAULT 0,
                    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS article_revisions (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id   INTEGER NOT NULL,
                    revision_num INTEGER NOT NULL,
                    content      TEXT NOT NULL,
                    summary      TEXT DEFAULT 'Copilot edit',
                    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
                    UNIQUE(article_id, revision_num)
                );

                CREATE INDEX IF NOT EXISTS idx_chat_article ON chat_history(article_id);
                CREATE INDEX IF NOT EXISTS idx_articles_created ON articles(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_telemetry_created ON telemetry_runs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_user_mem ON user_memory(user_key);
                CREATE INDEX IF NOT EXISTS idx_rev_art ON article_revisions(article_id);
            """)


# ---------------------------------------------------------------------------
# Article CRUD
# ---------------------------------------------------------------------------

def save_article(topic, content, tone=None, audience=None, target_length=None, generation_time=0, tokens_used=0):
    """Insert a new article and return its generated ID."""
    word_count = len(content.split())
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            """INSERT INTO articles
               (topic, content, word_count, tone, audience, target_length, generation_time_sec, tokens_used)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (topic, content, word_count, tone, audience, target_length, generation_time, tokens_used),
        )
        return cursor.lastrowid


def get_articles(limit=50):
    """Fetch recent articles ordered by creation date."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            """SELECT id, topic, content, word_count, tone, audience, target_length,
                      generation_time_sec, tokens_used, created_at, updated_at
               FROM articles ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


# Alias for backward compatibility
get_all_articles = get_articles


def get_article(article_id):
    """Fetch a single article by ID, or None if not found."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            """SELECT id, topic, content, word_count, tone, audience, target_length,
                      generation_time_sec, tokens_used, created_at, updated_at
               FROM articles WHERE id = ?""",
            (article_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def update_article_content(article_id, new_content):
    """Update article content after an AI Copilot revision."""
    word_count = len(new_content.split())
    with get_connection() as (conn, is_tidb):
        if is_tidb:
            sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = NOW() WHERE id = ?"
        else:
            sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = datetime('now', 'localtime') WHERE id = ?"
        _exec(conn, is_tidb, sql, (new_content, word_count, article_id))


# ---------------------------------------------------------------------------
# Revisions CRUD & Atomic Transactions
# ---------------------------------------------------------------------------

def get_article_revisions(article_id: int) -> List[Dict[str, Any]]:
    """Fetch all stored revisions for an article ordered from latest to oldest."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            """SELECT id, article_id, revision_num, content, summary, created_at
               FROM article_revisions WHERE article_id = ? ORDER BY revision_num DESC""",
            (article_id,),
        )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def get_single_revision(revision_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a specific revision by ID."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            """SELECT id, article_id, revision_num, content, summary, created_at
               FROM article_revisions WHERE id = ?""",
            (revision_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def apply_article_edit_transaction(article_id: int, new_content: str, summary: str = "Copilot revision") -> int:
    """Atomic transaction: snapshots current article content into article_revisions, then updates articles.content.

    Returns the new revision number.
    If either operation fails, the transaction rolls back cleanly.
    """
    with get_connection() as (conn, is_tidb):
        # 1. Fetch current article content
        cursor = _exec(conn, is_tidb, "SELECT content FROM articles WHERE id = ?", (article_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Article {article_id} not found.")

        current_content = row["content"] if is_tidb else row[0]

        # 2. Get next revision number
        cursor = _exec(conn, is_tidb, "SELECT COALESCE(MAX(revision_num), 0) + 1 AS next_rev FROM article_revisions WHERE article_id = ?", (article_id,))
        rev_row = cursor.fetchone()
        next_rev = (rev_row["next_rev"] if is_tidb else rev_row[0]) or 1

        # 3. Snapshot current content as revision N
        _exec(
            conn, is_tidb,
            "INSERT INTO article_revisions (article_id, revision_num, content, summary) VALUES (?, ?, ?, ?)",
            (article_id, next_rev, current_content, summary),
        )

        # 4. Update articles with new content
        word_count = len(new_content.split())
        if is_tidb:
            sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = NOW() WHERE id = ?"
        else:
            sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = datetime('now', 'localtime') WHERE id = ?"
        _exec(conn, is_tidb, sql, (new_content, word_count, article_id))

        return next_rev


def rollback_article_revision_transaction(article_id: int, target_revision_id: int) -> bool:
    """Atomic rollback: snapshots current content as 'Before rollback to N', then restores target revision content."""
    with get_connection() as (conn, is_tidb):
        # 1. Fetch target revision
        cursor = _exec(conn, is_tidb, "SELECT revision_num, content FROM article_revisions WHERE id = ? AND article_id = ?", (target_revision_id, article_id))
        target_row = cursor.fetchone()
        if not target_row:
            return False

        target_rev_num = target_row["revision_num"] if is_tidb else target_row[0]
        target_content = target_row["content"] if is_tidb else target_row[1]

        # 2. Fetch current article content
        cursor = _exec(conn, is_tidb, "SELECT content FROM articles WHERE id = ?", (article_id,))
        curr_row = cursor.fetchone()
        current_content = curr_row["content"] if is_tidb else curr_row[0]

        # 3. Get next revision number for current content snapshot
        cursor = _exec(conn, is_tidb, "SELECT COALESCE(MAX(revision_num), 0) + 1 AS next_rev FROM article_revisions WHERE article_id = ?", (article_id,))
        rev_row = cursor.fetchone()
        next_rev = (rev_row["next_rev"] if is_tidb else rev_row[0]) or 1

        # 4. Snapshot current content before rollback
        _exec(
            conn, is_tidb,
            "INSERT INTO article_revisions (article_id, revision_num, content, summary) VALUES (?, ?, ?, ?)",
            (article_id, next_rev, current_content, f"Before rollback to revision {target_rev_num}"),
        )

        # 5. Restore target content to article
        word_count = len(target_content.split())
        if is_tidb:
            sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = NOW() WHERE id = ?"
        else:
            sql = "UPDATE articles SET content = ?, word_count = ?, updated_at = datetime('now', 'localtime') WHERE id = ?"
        _exec(conn, is_tidb, sql, (target_content, word_count, article_id))

        return True


def delete_article(article_id):
    """Delete an article and its associated chat history."""
    with get_connection() as (conn, is_tidb):
        _exec(conn, is_tidb, "DELETE FROM articles WHERE id = ?", (article_id,))
        if is_tidb:
            _exec(conn, is_tidb, "DELETE FROM chat_history WHERE article_id = ?", (article_id,))


# ---------------------------------------------------------------------------
# Chat History CRUD
# ---------------------------------------------------------------------------

def save_chat_message(article_id, role, content):
    """Insert a single chat message for an article."""
    with get_connection() as (conn, is_tidb):
        _exec(
            conn, is_tidb,
            "INSERT INTO chat_history (article_id, role, content) VALUES (?, ?, ?)",
            (article_id, role, content),
        )


def get_chat_history(article_id):
    """Fetch all chat messages for an article in order."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            "SELECT role, content, created_at FROM chat_history WHERE article_id = ? ORDER BY id ASC",
            (article_id,),
        )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def clear_chat_history(article_id):
    """Delete all chat messages for an article."""
    with get_connection() as (conn, is_tidb):
        _exec(conn, is_tidb, "DELETE FROM chat_history WHERE article_id = ?", (article_id,))


# ---------------------------------------------------------------------------
# LLMOps & Security Telemetry CRUD
# ---------------------------------------------------------------------------

def save_telemetry_run(article_id, telemetry_data):
    """Save pipeline run telemetry for LLMOps observability."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            """INSERT INTO telemetry_runs
               (article_id, topic, duration_sec, tokens_estimated, models_used,
                fallback_count, fallback_events, readability_score, readability_grade)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            ),
        )
        return cursor.lastrowid


def save_security_event(event_type, details):
    """Record a security audit log event."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            "INSERT INTO security_audit_logs (event_type, details) VALUES (?, ?)",
            (event_type, str(details)),
        )
        return cursor.lastrowid


def get_telemetry_history(limit=10):
    """Fetch recent telemetry runs."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            """SELECT id, article_id, topic, duration_sec, tokens_estimated,
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


def get_security_audit_logs(limit=20):
    """Fetch recent security audit events."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            "SELECT id, event_type, details, created_at FROM security_audit_logs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Context & Memory Layer CRUD (Research Cache, User Preferences, Chat Sessions)
# ---------------------------------------------------------------------------

def get_cached_scrape(url: str) -> Optional[str]:
    """Retrieve compact scraped text from cache if available."""
    url_hash = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            "SELECT compact_content FROM research_cache WHERE url_hash = ?",
            (url_hash,),
        )
        row = cursor.fetchone()
        if row:
            return row["compact_content"] if is_tidb else row[0]
        return None


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


def get_user_memories(user_key: str = "default_user") -> Dict[str, str]:
    """Retrieve all persistent preferences and guidelines for a user."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            "SELECT memory_key, memory_value FROM user_memory WHERE user_key = ?",
            (user_key,),
        )
        rows = cursor.fetchall()
        result = {}
        for r in rows:
            if is_tidb:
                result[r["memory_key"]] = r["memory_value"]
            else:
                result[r[0]] = r[1]
        return result


def set_user_memory(key: str, value: str, memory_type: str = "preference", user_key: str = "default_user"):
    """Store or update a persistent memory item."""
    with get_connection() as (conn, is_tidb):
        if is_tidb:
            sql = """
                INSERT INTO user_memory (user_key, memory_type, memory_key, memory_value)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE memory_value = VALUES(memory_value), memory_type = VALUES(memory_type)
            """
            cursor = conn.cursor()
            cursor.execute(sql, (user_key, memory_type, key, value))
        else:
            sql = """
                INSERT INTO user_memory (user_key, memory_type, memory_key, memory_value)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_key, memory_key) DO UPDATE SET memory_value = excluded.memory_value, memory_type = excluded.memory_type
            """
            conn.execute(sql, (user_key, memory_type, key, value))


def delete_user_memory(key: str, user_key: str = "default_user"):
    """Remove a persistent memory item."""
    with get_connection() as (conn, is_tidb):
        _exec(conn, is_tidb, "DELETE FROM user_memory WHERE user_key = ? AND memory_key = ?", (user_key, key))


def get_chat_session(article_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve the rolling summary and message count for a chat session."""
    with get_connection() as (conn, is_tidb):
        cursor = _exec(
            conn, is_tidb,
            "SELECT article_id, running_summary, message_count FROM chat_sessions WHERE article_id = ?",
            (article_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def save_chat_session(article_id: int, running_summary: str, message_count: int = 0):
    """Store or update the running summary for an article chat session."""
    with get_connection() as (conn, is_tidb):
        if is_tidb:
            sql = """
                INSERT INTO chat_sessions (article_id, running_summary, message_count)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE running_summary = VALUES(running_summary), message_count = VALUES(message_count)
            """
            cursor = conn.cursor()
            cursor.execute(sql, (article_id, running_summary, message_count))
        else:
            sql = """
                INSERT INTO chat_sessions (article_id, running_summary, message_count)
                VALUES (?, ?, ?)
                ON CONFLICT(article_id) DO UPDATE SET running_summary = excluded.running_summary, message_count = excluded.message_count
            """
            conn.execute(sql, (article_id, running_summary, message_count))


# ---------------------------------------------------------------------------
# Stats / Utility
# ---------------------------------------------------------------------------

def get_stats():
    """Return aggregate stats for the dashboard."""
    with get_connection() as (conn, is_tidb):
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
