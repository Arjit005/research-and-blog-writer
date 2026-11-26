"""Base repository abstraction for incremental database.py modularization."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import database as db


class BaseRepository:
    """Provides shared connection/transaction context for domain repositories."""

    @contextmanager
    def connection(self) -> Iterator:
        with db.get_db_connection() as conn:
            yield conn

    @property
    def is_tidb(self) -> bool:
        return bool(getattr(db, "USE_TIDB", False))
