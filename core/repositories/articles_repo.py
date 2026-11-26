"""Articles, revisions, and operational cleanup repository."""

from __future__ import annotations

from typing import Any, Dict, Optional

import database as db
from core.repositories.base import BaseRepository


class ArticlesRepository(BaseRepository):
    """Domain repository for articles and operational retention."""

    def get_article(self, article_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        return db.get_article(article_id, user_id=user_id)

    def cleanup_stale_data(self, retention_days: int = 30) -> Dict[str, int]:
        return db.cleanup_stale_operational_data(retention_days=retention_days)
