"""Database layer for storing generated articles, chat history, and metadata.

Uses SQLite — zero config, no extra dependencies, file-based.
The database file (research_studio.db) is created automatically on first use.
"""

import sqlite3
import json
import os
from datetime import datetime
from contextlib import contextmanager

# Database file lives next to app.py
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "research_studio.db")


@contextmanager
def get_connection():
    """Context manager that yields a database connection with WAL mode enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Access columns by name
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables if they don't exist. Safe to call multiple times."""
    with get_connection() as conn:
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

            CREATE INDEX IF NOT EXISTS idx_chat_article ON chat_history(article_id);
            CREATE INDEX IF NOT EXISTS idx_articles_created ON articles(created_at DESC);
        """)


# ---------------------------------------------------------------------------
# Articles CRUD
# ---------------------------------------------------------------------------

def save_article(topic, content, tone="", audience="", target_length="", generation_time_sec=0):
    """Save a newly generated article. Returns the new article ID."""
    word_count = len(content.split())
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO articles (topic, content, word_count, tone, audience, target_length, generation_time_sec)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (topic, content, word_count, tone, audience, target_length, generation_time_sec),
        )
        return cursor.lastrowid


def get_article(article_id):
    """Fetch a single article by ID. Returns a dict or None."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        return dict(row) if row else None


def get_all_articles():
    """Fetch all articles, newest first. Returns a list of dicts."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM articles ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def update_article_content(article_id, new_content):
    """Update an article's content (e.g. after editing via copilot)."""
    word_count = len(new_content.split())
    with get_connection() as conn:
        conn.execute(
            """UPDATE articles SET content = ?, word_count = ?, updated_at = datetime('now', 'localtime')
               WHERE id = ?""",
            (new_content, word_count, article_id),
        )


def delete_article(article_id):
    """Delete an article and its chat history (CASCADE)."""
    with get_connection() as conn:
        conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))


# ---------------------------------------------------------------------------
# Chat History CRUD
# ---------------------------------------------------------------------------

def save_chat_message(article_id, role, content):
    """Save a single chat message linked to an article."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO chat_history (article_id, role, content) VALUES (?, ?, ?)",
            (article_id, role, content),
        )


def get_chat_history(article_id):
    """Fetch all chat messages for an article, in order. Returns list of dicts."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT role, content, created_at FROM chat_history WHERE article_id = ? ORDER BY id ASC",
            (article_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def clear_chat_history(article_id):
    """Delete all chat messages for an article."""
    with get_connection() as conn:
        conn.execute("DELETE FROM chat_history WHERE article_id = ?", (article_id,))


# ---------------------------------------------------------------------------
# Stats / Utility
# ---------------------------------------------------------------------------

def get_stats():
    """Return aggregate stats for the dashboard."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*)                     AS total_articles,
                COALESCE(SUM(word_count), 0) AS total_words,
                COALESCE(AVG(word_count), 0) AS avg_words,
                (SELECT COUNT(*) FROM chat_history) AS total_chats
            FROM articles
        """).fetchone()
        return dict(row)


# Auto-initialize on import
init_db()
