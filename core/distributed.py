"""Distributed state, rate limiting, and pub/sub abstractions.

Automatically uses Redis when ``REDIS_URL`` is configured and ``redis`` is
installed, and gracefully falls back to thread-safe in-memory structures for
single-node deployments and local/CI testing.
"""

from __future__ import annotations

import collections
import logging
import os
import threading
import time
from typing import Deque, Dict, Optional

logger = logging.getLogger(__name__)

_redis_client = None
_redis_init_attempted = False
_redis_lock = threading.Lock()


def get_redis_client():
    """Return a shared Redis client if REDIS_URL is configured and redis is installed."""
    global _redis_client, _redis_init_attempted
    if _redis_init_attempted:
        return _redis_client
    with _redis_lock:
        if _redis_init_attempted:
            return _redis_client
        _redis_init_attempted = True
        redis_url = (os.getenv("REDIS_URL") or "").strip()
        if not redis_url:
            return None
        try:
            import redis  # type: ignore

            client = redis.Redis.from_url(redis_url, decode_responses=True, socket_timeout=2.0)
            client.ping()
            _redis_client = client
            logger.info("Connected to Redis for distributed state and rate limiting.")
        except Exception as exc:
            logger.warning("Redis unavailable (%s); using in-memory fallback.", exc)
            _redis_client = None
        return _redis_client


class DistributedRateLimiter:
    """Per-IP sliding-window rate limiter with Redis + in-memory fallback."""

    def __init__(self, max_requests: int, window_seconds: int, gc_interval: int = 300) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.gc_interval = gc_interval
        self._store: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()
        self._last_gc: float = 0.0

    def allow(self, ip: str) -> bool:
        """Return True when the IP is within its request budget, False when throttled."""
        client = get_redis_client()
        if client is not None:
            try:
                key = f"rl:{ip}"
                count = client.incr(key)
                if count == 1:
                    client.expire(key, self.window_seconds)
                return int(count) <= self.max_requests
            except Exception as exc:
                logger.debug("Redis rate-limit fallback to memory: %s", exc)

        now = time.time()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._store.get(ip)
            if bucket is None:
                bucket = collections.deque()
                self._store[ip] = bucket
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                return False
            bucket.append(now)
        return True

    def maybe_gc(self, now: Optional[float] = None) -> None:
        """Periodically purge expired in-memory buckets."""
        current = now if now is not None else time.time()
        if current - self._last_gc < self.gc_interval:
            return
        cutoff = current - self.window_seconds
        with self._lock:
            stale = [ip for ip, bucket in self._store.items() if not bucket or bucket[-1] < cutoff]
            for ip in stale:
                del self._store[ip]
        self._last_gc = current


def mark_run_cancelled_distributed(run_id: str, ttl_seconds: int = 3600) -> None:
    """Propagate run cancellation across instances via Redis when available."""
    client = get_redis_client()
    if client is not None:
        try:
            client.setex(f"run_cancel:{run_id}", ttl_seconds, "1")
        except Exception as exc:
            logger.debug("Redis cancel propagation failed for %s: %s", run_id, exc)


def is_run_cancelled_distributed(run_id: str) -> bool:
    """Check if a run was cancelled on any instance via Redis."""
    client = get_redis_client()
    if client is not None:
        try:
            return bool(client.exists(f"run_cancel:{run_id}"))
        except Exception as exc:
            logger.debug("Redis cancel check failed for %s: %s", run_id, exc)
    return False


def cache_set_json(key: str, value: str, ttl_seconds: int = 86400) -> bool:
    """Store a cache entry in Redis if available. Returns True if stored in Redis."""
    client = get_redis_client()
    if client is None:
        return False
    try:
        client.setex(f"cache:{key}", max(1, ttl_seconds), value)
        return True
    except Exception as exc:
        logger.debug("Redis cache_set failed for %s: %s", key, exc)
        return False


def cache_get_json(key: str) -> Optional[str]:
    """Fetch a cache entry from Redis if available."""
    client = get_redis_client()
    if client is None:
        return None
    try:
        return client.get(f"cache:{key}")
    except Exception as exc:
        logger.debug("Redis cache_get failed for %s: %s", key, exc)
        return None
