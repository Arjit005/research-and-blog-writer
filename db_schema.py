"""Shared database schema definitions — single source of truth for all tables.

Both the TiDB (MySQL-compatible) and SQLite backends in ``database.py`` are
generated from these definitions, eliminating the previous duplication where
every ``CREATE TABLE`` statement existed twice and had already drifted (e.g.
``FOREIGN KEY`` constraints were only present in the SQLite branch).

Usage::

    from db_schema import build_tidb_ddl, build_sqlite_ddl, MIGRATION_COLUMNS
"""

from __future__ import annotations

from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Table definitions
# Each entry is:
#   (table_name, tidb_ddl, sqlite_ddl)
#
# Rules:
# - Column names/types/defaults are kept identical where dialects allow.
# - TiDB uses INT AUTO_INCREMENT / MEDIUMTEXT / ON UPDATE CURRENT_TIMESTAMP.
# - SQLite uses INTEGER AUTOINCREMENT / TEXT / no ON UPDATE support.
# - FOREIGN KEY constraints appear in both dialects (SQLite enforces them when
#   PRAGMA foreign_keys=ON, which database.py sets for every connection).
# ---------------------------------------------------------------------------

# (table_name, tidb_create_sql, sqlite_create_sql)
TABLE_DEFINITIONS: List[Tuple[str, str, str]] = [
    # ------------------------------------------------------------------
    # Schema version tracker
    # ------------------------------------------------------------------
    (
        "schema_version",
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version    INT PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version    INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
    ),

    # ------------------------------------------------------------------
    # Articles
    # ------------------------------------------------------------------
    (
        "articles",
        """
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
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS articles (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             INTEGER NULL,
            topic               TEXT NOT NULL,
            content             TEXT NOT NULL,
            word_count          INTEGER NOT NULL DEFAULT 0,
            tone                TEXT DEFAULT 'Professional & Authoritative',
            audience            TEXT DEFAULT 'Software Engineers & Developers',
            target_length       TEXT DEFAULT 'Standard Blog (1,500 - 2,000 words)',
            generation_time_sec REAL DEFAULT 0,
            tokens_used         INTEGER DEFAULT 0,
            created_at          TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
    ),

    # ------------------------------------------------------------------
    # Chat history
    # ------------------------------------------------------------------
    (
        "chat_history",
        """
        CREATE TABLE IF NOT EXISTS chat_history (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            user_id    INT NULL,
            article_id INT NOT NULL,
            role       VARCHAR(20) NOT NULL,
            content    MEDIUMTEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_chat_article (article_id),
            INDEX idx_chat_user (user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NULL,
            article_id INTEGER NOT NULL,
            role       TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content    TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
        )
        """,
    ),

    # ------------------------------------------------------------------
    # Telemetry runs
    # ------------------------------------------------------------------
    (
        "telemetry_runs",
        """
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
            trace_url         VARCHAR(512) NULL,
            created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_telem_user (user_id)
        )
        """,
        """
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
            trace_url         TEXT NULL,
            created_at        TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE SET NULL
        )
        """,
    ),

    # ------------------------------------------------------------------
    # Security audit logs
    # ------------------------------------------------------------------
    (
        "security_audit_logs",
        """
        CREATE TABLE IF NOT EXISTS security_audit_logs (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            user_id    INT NULL,
            event_type VARCHAR(100) NOT NULL,
            details    TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_audit_user (user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS security_audit_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NULL,
            event_type TEXT NOT NULL,
            details    TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
    ),

    # ------------------------------------------------------------------
    # System cache (L2)
    # ------------------------------------------------------------------
    (
        "system_cache",
        """
        CREATE TABLE IF NOT EXISTS system_cache (
            cache_key  VARCHAR(128) PRIMARY KEY,
            namespace  VARCHAR(32) NOT NULL,
            payload    LONGTEXT NOT NULL,
            meta_info  JSON NULL,
            user_id    INT NULL,
            created_at DATETIME NOT NULL,
            expires_at DATETIME NOT NULL,
            INDEX idx_cache_ns_exp (namespace, expires_at),
            INDEX idx_cache_user (user_id),
            INDEX idx_cache_created (created_at)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS system_cache (
            cache_key  TEXT PRIMARY KEY,
            namespace  TEXT NOT NULL,
            payload    TEXT NOT NULL,
            meta_info  TEXT NULL,
            user_id    INTEGER NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
        """,
    ),

    # ------------------------------------------------------------------
    # Research cache (URL scrape memos)
    # ------------------------------------------------------------------
    (
        "research_cache",
        """
        CREATE TABLE IF NOT EXISTS research_cache (
            url_hash        VARCHAR(64) PRIMARY KEY,
            url             TEXT NOT NULL,
            compact_content MEDIUMTEXT NOT NULL,
            created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS research_cache (
            url_hash        TEXT PRIMARY KEY,
            url             TEXT NOT NULL,
            compact_content TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
    ),

    # ------------------------------------------------------------------
    # User memory (long-term author preferences)
    # ------------------------------------------------------------------
    (
        "user_memory",
        """
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
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_memory (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NULL,
            user_key     TEXT NOT NULL DEFAULT 'default_user',
            memory_type  TEXT NOT NULL DEFAULT 'preference',
            memory_key   TEXT NOT NULL,
            memory_value TEXT NOT NULL,
            updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(user_key, memory_key)
        )
        """,
    ),

    # ------------------------------------------------------------------
    # Chat sessions (sliding-window summary)
    # ------------------------------------------------------------------
    (
        "chat_sessions",
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            article_id      INT PRIMARY KEY,
            user_id         INT NULL,
            running_summary MEDIUMTEXT,
            message_count   INT DEFAULT 0,
            updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_sess_usr (user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            article_id      INTEGER PRIMARY KEY,
            user_id         INTEGER NULL,
            running_summary TEXT,
            message_count   INTEGER DEFAULT 0,
            updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
        )
        """,
    ),

    # ------------------------------------------------------------------
    # Article revisions
    # ------------------------------------------------------------------
    (
        "article_revisions",
        """
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
        )
        """,
        """
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
        )
        """,
    ),

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    (
        "users",
        """
        CREATE TABLE IF NOT EXISTS users (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            email         VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NULL,
            google_id     VARCHAR(255) NULL UNIQUE,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_login_at DATETIME NULL,
            is_active     TINYINT(1) NOT NULL DEFAULT 1
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NULL,
            google_id     TEXT NULL UNIQUE,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            last_login_at TEXT NULL,
            is_active     INTEGER NOT NULL DEFAULT 1
        )
        """,
    ),

    # ------------------------------------------------------------------
    # OTP codes
    # ------------------------------------------------------------------
    (
        "otp_codes",
        """
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
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS otp_codes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT NOT NULL,
            code_hash  TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts   INTEGER NOT NULL DEFAULT 0,
            used       INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            request_ip TEXT NULL
        )
        """,
    ),

    # ------------------------------------------------------------------
    # Auth sessions
    # ------------------------------------------------------------------
    (
        "auth_sessions",
        """
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            user_id      INT NOT NULL,
            token_hash   CHAR(64) NOT NULL UNIQUE,
            expires_at   DATETIME NOT NULL,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen_at DATETIME NULL,
            INDEX idx_sess_user (user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            token_hash   TEXT NOT NULL UNIQUE,
            expires_at   TEXT NOT NULL,
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            last_seen_at TEXT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """,
    ),

    # ------------------------------------------------------------------
    # Research jobs
    # ------------------------------------------------------------------
    (
        "research_jobs",
        """
        CREATE TABLE IF NOT EXISTS research_jobs (
            run_id            VARCHAR(64) PRIMARY KEY,
            user_id           INT NULL,
            topic             TEXT NOT NULL,
            tone              VARCHAR(100) NULL,
            audience          VARCHAR(100) NULL,
            target_length     VARCHAR(100) NULL,
            status            VARCHAR(30) NOT NULL DEFAULT 'pending',
            result_article_id INT NULL,
            error_message     TEXT NULL,
            trace_url         VARCHAR(512) NULL,
            created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_job_user (user_id, status)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS research_jobs (
            run_id            TEXT PRIMARY KEY,
            user_id           INTEGER NULL,
            topic             TEXT NOT NULL,
            tone              TEXT NULL,
            audience          TEXT NULL,
            target_length     TEXT NULL,
            status            TEXT NOT NULL DEFAULT 'pending',
            result_article_id INTEGER NULL,
            error_message     TEXT NULL,
            trace_url         TEXT NULL,
            created_at        TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
    ),

    # ------------------------------------------------------------------
    # Job events (resumable SSE ledger with idempotent event_id)
    # ------------------------------------------------------------------
    (
        "job_events",
        """
        CREATE TABLE IF NOT EXISTS job_events (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            run_id     VARCHAR(64) NOT NULL,
            seq_id     INT NOT NULL,
            event_id   VARCHAR(64) NULL,
            event_type VARCHAR(50) NOT NULL,
            payload    MEDIUMTEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uk_event_run_seq (run_id, seq_id),
            UNIQUE KEY uk_event_run_event_id (run_id, event_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS job_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id     TEXT NOT NULL,
            seq_id     INTEGER NOT NULL,
            event_id   TEXT NULL,
            event_type TEXT NOT NULL,
            payload    TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
    ),

    # ------------------------------------------------------------------
    # Job event counters (atomic persistent SSE sequence counter per run)
    # ------------------------------------------------------------------
    (
        "job_event_counters",
        """
        CREATE TABLE IF NOT EXISTS job_event_counters (
            run_id     VARCHAR(64) PRIMARY KEY,
            last_seq   INT NOT NULL DEFAULT 0,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS job_event_counters (
            run_id     TEXT PRIMARY KEY,
            last_seq   INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
    ),

    # ------------------------------------------------------------------
    # User lease sequences (monotonic persistent fencing token counter per user)
    # ------------------------------------------------------------------
    (
        "user_lease_sequences",
        """
        CREATE TABLE IF NOT EXISTS user_lease_sequences (
            user_id         INT PRIMARY KEY,
            current_fencing BIGINT NOT NULL DEFAULT 0,
            updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_lease_sequences (
            user_id         INTEGER PRIMARY KEY,
            current_fencing INTEGER NOT NULL DEFAULT 0,
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
    ),

    # ------------------------------------------------------------------
    # Active run claims (atomic distributed single-active-run lease per user)
    # ------------------------------------------------------------------
    (
        "active_run_claims",
        """
        CREATE TABLE IF NOT EXISTS active_run_claims (
            user_id            INT PRIMARY KEY,
            run_id             VARCHAR(64) NOT NULL,
            worker_id          VARCHAR(64) NOT NULL,
            lease_token        VARCHAR(64) NOT NULL,
            fencing_token      BIGINT NOT NULL DEFAULT 1,
            claimed_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            heartbeat_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            lease_expires_at   DATETIME NOT NULL,
            INDEX idx_claim_run (run_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS active_run_claims (
            user_id            INTEGER PRIMARY KEY,
            run_id             TEXT NOT NULL,
            worker_id          TEXT NOT NULL,
            lease_token        TEXT NOT NULL,
            fencing_token      INTEGER NOT NULL DEFAULT 1,
            claimed_at         TEXT NOT NULL DEFAULT (datetime('now')),
            heartbeat_at       TEXT NOT NULL DEFAULT (datetime('now')),
            lease_expires_at   TEXT NOT NULL
        )
        """,
    ),

    # ------------------------------------------------------------------
    # Password attempt log (brute-force throttling)
    # ------------------------------------------------------------------
    (
        "password_attempts",
        """
        CREATE TABLE IF NOT EXISTS password_attempts (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            email        VARCHAR(255) NOT NULL,
            ip           VARCHAR(64) NULL,
            attempted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_pwd_attempt_email (email, attempted_at),
            INDEX idx_pwd_attempt_ip (ip, attempted_at)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS password_attempts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            email        TEXT NOT NULL,
            ip           TEXT NULL,
            attempted_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
    ),

    # ------------------------------------------------------------------
    # Visual Research System: visuals library and evidence assets
    # ------------------------------------------------------------------
    (
        "research_visuals",
        """
        CREATE TABLE IF NOT EXISTS research_visuals (
            id                    INT AUTO_INCREMENT PRIMARY KEY,
            user_id               INT NOT NULL,
            article_id            INT NULL,
            run_id                VARCHAR(64) NULL,
            visual_type           VARCHAR(32) NOT NULL,
            origin_type           VARCHAR(32) NOT NULL,
            title                 VARCHAR(255) NOT NULL,
            caption               TEXT NULL,
            description           TEXT NULL,
            source_url            VARCHAR(1024) NULL,
            source_title          VARCHAR(255) NULL,
            publisher             VARCHAR(255) NULL,
            author                VARCHAR(255) NULL,
            publication_date      VARCHAR(64) NULL,
            retrieval_timestamp   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            license_information   VARCHAR(255) NULL,
            usage_restrictions    TEXT NULL,
            alt_text              TEXT NULL,
            dimensions            VARCHAR(64) NULL,
            file_format           VARCHAR(32) NULL,
            media_content         MEDIUMTEXT NULL,
            thumbnail_url         TEXT NULL,
            metadata_json         MEDIUMTEXT NULL,
            created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_vis_user (user_id),
            INDEX idx_vis_article (article_id),
            INDEX idx_vis_run (run_id),
            INDEX idx_vis_type (visual_type),
            INDEX idx_vis_created (created_at DESC)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS research_visuals (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id               INTEGER NOT NULL,
            article_id            INTEGER NULL,
            run_id                TEXT NULL,
            visual_type           TEXT NOT NULL,
            origin_type           TEXT NOT NULL,
            title                 TEXT NOT NULL,
            caption               TEXT NULL,
            description           TEXT NULL,
            source_url            TEXT NULL,
            source_title          TEXT NULL,
            publisher             TEXT NULL,
            author                TEXT NULL,
            publication_date      TEXT NULL,
            retrieval_timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
            license_information   TEXT NULL,
            usage_restrictions    TEXT NULL,
            alt_text              TEXT NULL,
            dimensions            TEXT NULL,
            file_format           TEXT NULL,
            media_content         TEXT NULL,
            thumbnail_url         TEXT NULL,
            metadata_json         TEXT NULL,
            created_at            TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
    ),

    # ------------------------------------------------------------------
    # Visual Research System: interactive structured research charts
    # ------------------------------------------------------------------
    (
        "research_charts",
        """
        CREATE TABLE IF NOT EXISTS research_charts (
            id                INT AUTO_INCREMENT PRIMARY KEY,
            user_id           INT NOT NULL,
            article_id        INT NULL,
            title             VARCHAR(255) NOT NULL,
            description       TEXT NULL,
            chart_type        VARCHAR(32) NOT NULL,
            structured_data   MEDIUMTEXT NOT NULL,
            data_source       VARCHAR(512) NULL,
            units             VARCHAR(64) NULL,
            methodology       TEXT NULL,
            created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_chart_user (user_id),
            INDEX idx_chart_art (article_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS research_charts (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           INTEGER NOT NULL,
            article_id        INTEGER NULL,
            title             TEXT NOT NULL,
            description       TEXT NULL,
            chart_type        TEXT NOT NULL,
            structured_data   TEXT NOT NULL,
            data_source       TEXT NULL,
            units             TEXT NULL,
            methodology       TEXT NULL,
            created_at        TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
    ),

    # ------------------------------------------------------------------
    # Visual Research System: visual evidence links to claims and sections
    # ------------------------------------------------------------------
    (
        "visual_evidence_links",
        """
        CREATE TABLE IF NOT EXISTS visual_evidence_links (
            id                    INT AUTO_INCREMENT PRIMARY KEY,
            user_id               INT NOT NULL,
            visual_id             INT NOT NULL,
            claim_id              VARCHAR(64) NULL,
            article_id            INT NULL,
            report_section        VARCHAR(128) NULL,
            evidence_status       VARCHAR(32) NOT NULL DEFAULT 'unverified',
            citation_url          VARCHAR(1024) NULL,
            created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_vel_user (user_id),
            INDEX idx_vel_visual (visual_id),
            INDEX idx_vel_claim (claim_id),
            INDEX idx_vel_art (article_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS visual_evidence_links (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id               INTEGER NOT NULL,
            visual_id             INTEGER NOT NULL,
            claim_id              TEXT NULL,
            article_id            INTEGER NULL,
            report_section        TEXT NULL,
            evidence_status       TEXT NOT NULL DEFAULT 'unverified',
            citation_url          TEXT NULL,
            created_at            TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
    ),

    # ------------------------------------------------------------------
    # Document Studio Metadata
    # ------------------------------------------------------------------
    (
        "document_metadata",
        """
        CREATE TABLE IF NOT EXISTS document_metadata (
            id                    INT AUTO_INCREMENT PRIMARY KEY,
            article_id            INT NOT NULL,
            user_id               INT NOT NULL,
            title                 VARCHAR(255) NULL,
            abstract              MEDIUMTEXT NULL,
            keywords              VARCHAR(512) NULL,
            authors               VARCHAR(512) NULL,
            institution           VARCHAR(255) NULL,
            citation_style        VARCHAR(32) NOT NULL DEFAULT 'IEEE',
            version_tag           VARCHAR(64) NOT NULL DEFAULT 'v1.0',
            layout_settings       MEDIUMTEXT NULL,
            created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_doc_article (article_id),
            INDEX idx_doc_user (user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS document_metadata (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id            INTEGER NOT NULL UNIQUE,
            user_id               INTEGER NOT NULL,
            title                 TEXT NULL,
            abstract              TEXT NULL,
            keywords              TEXT NULL,
            authors               TEXT NULL,
            institution           TEXT NULL,
            citation_style        TEXT NOT NULL DEFAULT 'IEEE',
            version_tag           TEXT NOT NULL DEFAULT 'v1.0',
            layout_settings       TEXT NULL,
            created_at            TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
    ),
]

# ---------------------------------------------------------------------------
# Standalone index definitions for SQLite (TiDB defines them inline above)
# ---------------------------------------------------------------------------
SQLITE_EXTRA_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_chat_article        ON chat_history(article_id)",
    "CREATE INDEX IF NOT EXISTS idx_articles_created    ON articles(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_telemetry_created   ON telemetry_runs(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_user_mem            ON user_memory(user_key)",
    "CREATE INDEX IF NOT EXISTS idx_rev_art             ON article_revisions(article_id)",
    "CREATE INDEX IF NOT EXISTS idx_otp_email           ON otp_codes(email, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_sess_user           ON auth_sessions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_job_user            ON research_jobs(user_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_pwd_attempt_email   ON password_attempts(email, attempted_at)",
    "CREATE INDEX IF NOT EXISTS idx_pwd_attempt_ip      ON password_attempts(ip, attempted_at)",
    "CREATE INDEX IF NOT EXISTS idx_cache_ns_exp        ON system_cache(namespace, expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_cache_user          ON system_cache(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_cache_created       ON system_cache(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_art_user            ON articles(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_chat_user           ON chat_history(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_telem_user          ON telemetry_runs(user_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id) WHERE google_id IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS uk_event_run_event_id ON job_events(run_id, event_id) WHERE event_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_vis_user            ON research_visuals(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_vis_article         ON research_visuals(article_id)",
    "CREATE INDEX IF NOT EXISTS idx_vis_run             ON research_visuals(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_vis_type            ON research_visuals(visual_type)",
    "CREATE INDEX IF NOT EXISTS idx_vis_created         ON research_visuals(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_chart_user          ON research_charts(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_chart_art           ON research_charts(article_id)",
    "CREATE INDEX IF NOT EXISTS idx_vel_user            ON visual_evidence_links(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_vel_visual          ON visual_evidence_links(visual_id)",
    "CREATE INDEX IF NOT EXISTS idx_vel_claim           ON visual_evidence_links(claim_id)",
    "CREATE INDEX IF NOT EXISTS idx_vel_art             ON visual_evidence_links(article_id)",
    "CREATE INDEX IF NOT EXISTS idx_doc_meta_user       ON document_metadata(user_id)",
]

# ---------------------------------------------------------------------------
# Migration columns: columns that may be absent on pre-existing databases.
# Each entry: (table, column, tidb_type, sqlite_type)
# ---------------------------------------------------------------------------
MIGRATION_COLUMNS: List[Tuple[str, str, str, str]] = [
    ("articles",            "user_id",      "INT NULL",          "INTEGER"),
    ("chat_history",        "user_id",      "INT NULL",          "INTEGER"),
    ("telemetry_runs",      "user_id",      "INT NULL",          "INTEGER"),
    ("telemetry_runs",      "trace_url",    "VARCHAR(512) NULL", "TEXT"),
    ("security_audit_logs", "user_id",      "INT NULL",          "INTEGER"),
    ("user_memory",         "user_id",      "INT NULL",          "INTEGER"),
    ("chat_sessions",       "user_id",      "INT NULL",          "INTEGER"),
    ("article_revisions",   "user_id",      "INT NULL",          "INTEGER"),
    ("research_jobs",       "trace_url",    "VARCHAR(512) NULL", "TEXT"),
    ("users",               "password_hash","VARCHAR(255) NULL", "TEXT"),
    ("users",               "google_id",    "VARCHAR(255) NULL", "TEXT NULL"),
    ("job_events",          "event_id",     "VARCHAR(64) NULL",  "TEXT NULL"),
]


def build_tidb_ddl() -> List[str]:
    """Return the ordered list of TiDB CREATE TABLE statements."""
    return [ddl.strip() for _, ddl, _ in TABLE_DEFINITIONS]


def build_sqlite_ddl() -> List[str]:
    """Return the ordered list of SQLite CREATE TABLE statements."""
    return [ddl.strip() for _, _, ddl in TABLE_DEFINITIONS]
