"""Telemetry, LLMOps, and Cache governance endpoints."""

from __future__ import annotations

from typing import Dict, Any, List
from fastapi import APIRouter, Depends

import database as db
from cache import HybridCacheManager
from backend.deps import get_current_user

router = APIRouter(prefix="/api/v1/telemetry", tags=["Telemetry"])


@router.get("/stats")
def get_telemetry_stats(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Retrieve studio statistics, recent telemetry runs, and cache metrics."""
    studio_stats = db.get_stats(user_id=user["id"])
    cache_mgr = HybridCacheManager.get_instance()
    cache_metrics = cache_mgr.get_metrics()
    db_cache_stats = db.get_cache_stats()
    recent_runs = db.get_telemetry_history(limit=10, user_id=user["id"])
    is_live, tidb_msg = db.check_tidb_live_status()

    return {
        "studio": studio_stats,
        "cache": {
            "metrics": cache_metrics,
            "db_stats": db_cache_stats,
        },
        "database": {
            "backend": db.get_active_backend(),
            "is_live": is_live,
            "status_message": tidb_msg,
        },
        "recent_runs": recent_runs,
    }


@router.get("/cache")
def get_cache_info(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Retrieve detailed hybrid cache metrics."""
    cache_mgr = HybridCacheManager.get_instance()
    metrics = cache_mgr.get_metrics()
    db_stats = db.get_cache_stats()
    return {**metrics, "db_stats": db_stats}


@router.post("/cache/prune")
def prune_cache(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Prune expired cache entries across all namespaces."""
    pruned_count = db.prune_expired_cache()
    return {"success": True, "pruned_count": pruned_count}
