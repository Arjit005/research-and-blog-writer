"""Authentication and user session repository."""

from __future__ import annotations

from typing import Any, Dict, Optional

import database as db
from core.repositories.base import BaseRepository


class AuthRepository(BaseRepository):
    """Domain repository for users, OTP codes, and auth sessions."""

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        return db.get_user_by_email(email)

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        return db.get_user_by_id(user_id)

    def cleanup_expired_auth_data(self) -> Any:
        return db.cleanup_expired_auth_data()
