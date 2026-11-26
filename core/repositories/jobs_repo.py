"""Research jobs and event stream repository."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import database as db
from core.repositories.base import BaseRepository


class JobsRepository(BaseRepository):
    """Domain repository for research_jobs and job_events."""

    def get_job(self, run_id: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        return db.get_research_job(run_id, user_id=user_id)

    def update_job(self, run_id: str, **kwargs: Any) -> Any:
        return db.update_research_job(run_id, **kwargs)

    def append_event(self, run_id: str, event_type: str, payload: Dict[str, Any]) -> Any:
        return db.append_job_event(run_id, event_type, payload)

    def get_events(self, run_id: str, after_seq: int = 0) -> List[Dict[str, Any]]:
        return db.get_job_events(run_id, after_seq)
