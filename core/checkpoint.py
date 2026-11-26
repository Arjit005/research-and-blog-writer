"""Stage-level checkpointing for multi-agent research runs.

Stores intermediate stage outputs keyed by ``(run_id, stage)`` in Redis when
available, with a thread-safe in-memory fallback for single-node/test runs.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Dict, Optional

from core.distributed import get_redis_client

logger = logging.getLogger(__name__)

_LOCAL_CHECKPOINTS: Dict[str, Dict[str, Any]] = {}
_LOCAL_LOCK = threading.Lock()


def save_stage_checkpoint(run_id: str, stage: str, payload: Any, ttl_seconds: int = 86400) -> None:
    """Persist intermediate output for a completed pipeline stage."""
    serialized = json.dumps(payload, default=str)
    client = get_redis_client()
    if client is not None:
        try:
            client.setex(f"ckpt:{run_id}:{stage}", max(60, ttl_seconds), serialized)
            return
        except Exception as exc:
            logger.debug("Redis checkpoint save failed for %s/%s: %s", run_id, stage, exc)

    with _LOCAL_LOCK:
        _LOCAL_CHECKPOINTS.setdefault(run_id, {})[stage] = json.loads(serialized)


def load_stage_checkpoint(run_id: str, stage: str) -> Optional[Any]:
    """Load previously saved stage output if available."""
    client = get_redis_client()
    if client is not None:
        try:
            raw = client.get(f"ckpt:{run_id}:{stage}")
            if raw:
                return json.loads(raw)
        except Exception as exc:
            logger.debug("Redis checkpoint load failed for %s/%s: %s", run_id, stage, exc)

    with _LOCAL_LOCK:
        return _LOCAL_CHECKPOINTS.get(run_id, {}).get(stage)


def clear_run_checkpoints(run_id: str) -> None:
    """Remove all checkpoints for a completed or cancelled run."""
    client = get_redis_client()
    if client is not None:
        try:
            keys = list(client.scan_iter(match=f"ckpt:{run_id}:*"))
            if keys:
                client.delete(*keys)
        except Exception as exc:
            logger.debug("Redis checkpoint clear failed for %s: %s", run_id, exc)

    with _LOCAL_LOCK:
        _LOCAL_CHECKPOINTS.pop(run_id, None)
