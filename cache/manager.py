"""Unified Hybrid Two-Tier Cache Manager (L1 Memory LRU + L2 TiDB/SQLite Persistence).

Provides:
- L1 In-Memory Thread-Safe LRU bounded by byte budget (~25 MB) and item count (500).
- L2 Durable DB persistence in TiDB Cloud Serverless / SQLite with fail-open safety.
- Granular Anti-Stampede Lock per cache key with timeout to prevent duplicate remote fetches.
- Real latency tracking, failure negative caching, and serve-stale-on-error failover resilience.
- Canonical URL normalization and versioned SHA-256 key generation.
"""

from __future__ import annotations

import re
import time
import json
import hashlib
import logging
import threading
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, Optional, Tuple, List

import database as db

logger = logging.getLogger(__name__)

# Max single payload allowed in cache: 1 MB
MAX_PAYLOAD_BYTES = 1024 * 1024

# Default L1 byte budget: 25 MB
DEFAULT_L1_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_L1_MAX_ITEMS = 500

# Maximum number of negative-cache entries kept in memory (bounded to prevent
# unbounded growth when remote sources fail with high-cardinality URLs/keys).
DEFAULT_MAX_FAILURE_CACHE = 512

# Known tracking parameters stripped during URL normalization. Only parameters
# that do not change server-side content are removed: generic parameters such as
# ``ref``/``source`` are preserved because they can be semantically meaningful
# (e.g. ``?ref=download``) and collapsing them caused distinct payloads to share
# one cache entry.
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "utm_reader", "utm_social", "utm_brand",
    "fbclid", "gclid", "dclid", "gclsrc", "msclkid", "mc_cid", "mc_eid",
    "igshid", "yclid", "twclid", "li_fat_id", "_hsenc", "_hsmi",
}


def normalize_url(url: str) -> str:
    """Normalize a URL to prevent duplicate caching from cosmetic variations.

    Normalization drops known tracking parameters (UTM/click IDs), lowercases the
    scheme/host, removes default ports and trailing slashes. Fragments and
    non-tracking query parameters are preserved so semantically distinct URLs are
    not collapsed into one shared cache payload.
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        # Lowercase scheme and hostname
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()

        # Remove default ports (80 for http, 443 for https)
        if ":" in netloc:
            host, port = netloc.split(":", 1)
            if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
                netloc = host

        # Normalize path
        path = parsed.path
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]

        # Filter out *known* tracking query parameters only, then sort the rest
        filtered_query = []
        if parsed.query:
            query_tuples = parse_qsl(parsed.query, keep_blank_values=True)
            for k, v in query_tuples:
                if k.lower() not in TRACKING_PARAMS:
                    filtered_query.append((k, v))
            filtered_query.sort()

        query_str = urlencode(filtered_query)
        return urlunparse((scheme, netloc, path, parsed.params, query_str, parsed.fragment))
    except Exception as e:
        logger.debug(f"URL normalization failed for '{url}': {e}")
        return url.strip()


def _encode_cache_component(component: Any) -> str:
    """Length-prefix/type-prefix a cache key component (collision-safe encoding).

    Naive ``"|".join(components)`` aliases ``("ns", "a||b")`` with
    ``("ns", "a", "b")``. Length prefixes make the encoding unambiguous.
    """
    if isinstance(component, str):
        encoded = "s:" + component
    else:
        try:
            encoded = "j:" + json.dumps(component, sort_keys=True, default=str)
        except Exception:
            encoded = "r:" + repr(component)
    return f"{len(encoded)}:{encoded}"


def make_cache_key(namespace: str, *components: Any, user_id: Optional[int] = None) -> str:
    """Generate a deterministic versioned SHA-256 key for a namespace and components."""
    serialized_parts = [_encode_cache_component(c) for c in components]

    if user_id is not None:
        serialized_parts.append(_encode_cache_component(f"user:{user_id}"))

    joined = "|".join(serialized_parts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return f"v1:{namespace}:{digest}"


class HybridCacheManager:
    """Two-tier thread-safe cache engine combining L1 in-memory LRU with durable L2 database persistence."""

    _instance: Optional[HybridCacheManager] = None
    _singleton_lock = threading.Lock()

    def __init__(
        self,
        max_bytes: int = DEFAULT_L1_MAX_BYTES,
        max_items: int = DEFAULT_L1_MAX_ITEMS,
        max_failures: int = DEFAULT_MAX_FAILURE_CACHE,
    ):
        self._max_bytes = max_bytes
        self._max_items = max_items
        self._current_bytes = 0

        # L1 In-Memory LRU storage
        self._l1: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        # Lock hierarchy (always acquire in this order to avoid ABBA deadlock):
        #   1. self._lock       (L1 store)
        #   2. self._metrics_lock
        #   3. self._failure_lock (never nested inside the others)
        self._lock = threading.RLock()

        # Anti-stampede granular per-key mutexes: key -> [Lock, ref_count]
        self._key_locks: Dict[str, List[Any]] = {}
        self._key_locks_mutex = threading.Lock()

        # Transient negative failure cache: key -> failure_timestamp (bounded)
        self._failure_cache: Dict[str, float] = {}
        self._failure_ttl_sec = 30.0
        self._max_failures = max(1, int(max_failures))
        self._failure_lock = threading.Lock()

        # Observability metrics
        self._metrics_lock = threading.Lock()
        self._metrics = {
            "l1_hits": 0,
            "l2_hits": 0,
            "misses": 0,
            "tokens_saved": 0,
            "latency_saved_ms": 0,
        }

    @classmethod
    def get_instance(cls) -> HybridCacheManager:
        """Get or initialize singleton instance."""
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @contextmanager
    def _acquire_stampede_lock(self, key: str, timeout: float = 10.0):
        """Acquire a granular lock for a specific key, automatically cleaning up references.

        The refcount bookkeeping is exception-safe: even if acquiring or the wrapped
        body raises (including BaseException/KeyboardInterrupt) the entry is released
        and removed, so ``_key_locks`` can never leak entries.
        """
        with self._key_locks_mutex:
            if key not in self._key_locks:
                self._key_locks[key] = [threading.Lock(), 1]
            else:
                self._key_locks[key][1] += 1
            key_lock = self._key_locks[key][0]

        acquired = False
        try:
            acquired = key_lock.acquire(timeout=timeout)
        except BaseException:
            with self._key_locks_mutex:
                self._release_key_lock_ref(key)
            raise

        try:
            yield acquired
        finally:
            if acquired:
                try:
                    key_lock.release()
                except RuntimeError:
                    pass
            with self._key_locks_mutex:
                self._release_key_lock_ref(key)

    def _release_key_lock_ref(self, key: str) -> None:
        """Decrement/remove a key-lock reference. Caller must hold ``_key_locks_mutex``."""
        entry = self._key_locks.get(key)
        if entry is None:
            return
        entry[1] -= 1
        if entry[1] <= 0:
            self._key_locks.pop(key, None)

    # -- Negative failure cache (bounded) ---------------------------------
    def _record_failure(self, key: str) -> None:
        """Record a transient failure timestamp, evicting oldest entries when full."""
        with self._failure_lock:
            self._failure_cache[key] = time.time()
            overflow = len(self._failure_cache) - self._max_failures
            if overflow > 0:
                oldest = sorted(self._failure_cache.items(), key=lambda kv: kv[1])[:overflow]
                for old_key, _ in oldest:
                    self._failure_cache.pop(old_key, None)

    def _get_failure_timestamp(self, key: str) -> Optional[float]:
        with self._failure_lock:
            return self._failure_cache.get(key)

    def _clear_failure(self, key: str) -> None:
        with self._failure_lock:
            self._failure_cache.pop(key, None)

    def _evict_l1_if_needed(self, incoming_bytes: int):
        """Evict oldest entries in L1 LRU until within item and byte limits."""
        while self._l1 and (
            (self._current_bytes + incoming_bytes > self._max_bytes) or
            (len(self._l1) >= self._max_items)
        ):
            _, evicted_item = self._l1.popitem(last=False)
            self._current_bytes = max(0, self._current_bytes - evicted_item.get("size_bytes", 0))

    def get(
        self,
        key: str,
        namespace: Optional[str] = None,
        allow_stale: bool = False,
        now: Optional[datetime] = None,
        record_miss: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve an entry checking L1 first, then falling back to L2.

        Promotes L2 hits into L1 automatically.
        """
        curr_time = now or datetime.now(timezone.utc)

        # 1. Check L1 Memory
        with self._lock:
            if key in self._l1:
                item = self._l1[key]
                expires_at = item["expires_at"]
                is_stale = expires_at < curr_time

                if is_stale and not allow_stale:
                    # Expired in L1: remove it
                    self._current_bytes = max(0, self._current_bytes - item.get("size_bytes", 0))
                    del self._l1[key]
                else:
                    self._l1.move_to_end(key)
                    with self._metrics_lock:
                        self._metrics["l1_hits"] += 1
                        meta = item.get("meta_info") or {}
                        self._metrics["latency_saved_ms"] += meta.get("latency_ms", 0)
                        self._metrics["tokens_saved"] += meta.get("tokens_saved", 0)
                    return {
                        "cache_key": key,
                        "namespace": item["namespace"],
                        "payload": item["payload"],
                        "meta_info": item.get("meta_info"),
                        "user_id": item.get("user_id"),
                        "expires_at": expires_at,
                        "is_stale": is_stale,
                        "tier": "L1",
                    }

        # 2. Check L2 Durable Storage (Fail-Open)
        l2_entry = db.get_cache_entry(key, namespace=namespace, allow_stale=allow_stale, now=curr_time)
        if l2_entry is not None:
            # Populate L1 with result
            with self._lock:
                size = len(l2_entry["payload"].encode("utf-8"))
                self._evict_l1_if_needed(size)
                self._l1[key] = {
                    "namespace": l2_entry["namespace"],
                    "payload": l2_entry["payload"],
                    "meta_info": l2_entry["meta_info"],
                    "expires_at": l2_entry["expires_at"],
                    "user_id": l2_entry.get("user_id"),
                    "size_bytes": size,
                }
                self._current_bytes += size

            with self._metrics_lock:
                self._metrics["l2_hits"] += 1
                meta = l2_entry.get("meta_info") or {}
                self._metrics["latency_saved_ms"] += meta.get("latency_ms", 0)
                self._metrics["tokens_saved"] += meta.get("tokens_saved", 0)

            l2_entry["tier"] = "L2"
            return l2_entry

        if record_miss:
            with self._metrics_lock:
                self._metrics["misses"] += 1
        return None

    def set(
        self,
        key: str,
        namespace: str,
        payload: str,
        ttl_seconds: int,
        meta_info: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> bool:
        """Store an entry into both L1 Memory and L2 Database."""
        payload_bytes = payload.encode("utf-8")
        size = len(payload_bytes)

        if size > MAX_PAYLOAD_BYTES:
            logger.warning(f"Payload for key {key} is {size} bytes (exceeds 1 MB cap). Skipping cache.")
            return False

        curr_time = now or datetime.now(timezone.utc)
        expires_at = curr_time + timedelta(seconds=ttl_seconds)

        # 1. Update L1
        with self._lock:
            # If replacing an existing key, subtract old size
            if key in self._l1:
                self._current_bytes = max(0, self._current_bytes - self._l1[key].get("size_bytes", 0))

            self._evict_l1_if_needed(size)
            self._l1[key] = {
                "namespace": namespace,
                "payload": payload,
                "meta_info": meta_info,
                "expires_at": expires_at,
                "user_id": user_id,
                "size_bytes": size,
            }
            self._l1.move_to_end(key)
            self._current_bytes += size

        # 2. Update L2 (TiDB/SQLite)
        db.set_cache_entry(
            cache_key=key,
            namespace=namespace,
            payload=payload,
            expires_at=expires_at,
            meta_info=meta_info,
            user_id=user_id,
            created_at=curr_time,
        )

        # Clear negative failure cache for this key if previously marked
        self._clear_failure(key)
        return True

    def fetch_or_compute(
        self,
        key: str,
        namespace: str,
        fetch_fn: Callable[[], str],
        ttl_seconds: int,
        meta_info: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        allow_stale_on_error: bool = True,
        bypass: bool = False,
    ) -> Tuple[str, Dict[str, Any]]:
        """Fetch or compute value using Anti-Stampede lock and Stale-on-Error failover.

        Args:
            key: Unique versioned cache key.
            namespace: Domain namespace.
            fetch_fn: Function to produce value on cache miss.
            ttl_seconds: TTL duration in seconds.
            meta_info: Additional metadata dict (e.g. models used, tokens).
            user_id: Optional user identifier.
            allow_stale_on_error: If True, returns stale entry if fetch_fn raises an exception.
            bypass: If True, skips cache and forces computation, then updates cache.

        Returns:
            (payload, metadata_dict)
        """
        # Check negative cache
        last_failure = self._get_failure_timestamp(key)
        if last_failure and (time.time() - last_failure) < self._failure_ttl_sec and not bypass:
            # If recently failed, check if we have a stale entry to serve instead of re-failing
            if allow_stale_on_error:
                stale = self.get(key, namespace=namespace, allow_stale=True)
                if stale:
                    stale_meta = stale.get("meta_info") or {}
                    stale_meta["stale_served_due_to_recent_failure"] = True
                    return stale["payload"], stale_meta
            raise RuntimeError(f"Transient failure cooldown active for key '{key}' (retry in 30s).")

        # Fast path without lock if not bypassing
        if not bypass:
            cached = self.get(key, namespace=namespace, record_miss=False)
            if cached is not None and not cached.get("is_stale"):
                return cached["payload"], (cached.get("meta_info") or {})

        # Acquire Anti-Stampede Lock to ensure only one thread computes
        with self._acquire_stampede_lock(key) as acquired:
            # Double check cache inside lock (another thread might have just finished)
            if not bypass:
                cached = self.get(key, namespace=namespace, record_miss=False)
                if cached is not None and not cached.get("is_stale"):
                    return cached["payload"], (cached.get("meta_info") or {})

            # Count miss only when we actually proceed to compute
            with self._metrics_lock:
                self._metrics["misses"] += 1

            # Execute fetch
            t0 = time.perf_counter()
            try:
                result = fetch_fn()
                latency_ms = int((time.perf_counter() - t0) * 1000)

                final_meta = dict(meta_info or {})
                final_meta["latency_ms"] = latency_ms

                self.set(
                    key=key,
                    namespace=namespace,
                    payload=result,
                    ttl_seconds=ttl_seconds,
                    meta_info=final_meta,
                    user_id=user_id,
                )
                return result, final_meta

            except Exception as err:
                logger.warning(f"Computation failed for key '{key}': {err}")
                self._record_failure(key)

                if allow_stale_on_error:
                    stale = self.get(key, namespace=namespace, allow_stale=True)
                    if stale:
                        logger.info(f"Serving stale entry for key '{key}' due to computation failure.")
                        stale_meta = stale.get("meta_info") or {}
                        stale_meta["stale"] = True
                        stale_meta["fetch_error"] = str(err)
                        return stale["payload"], stale_meta

                raise

    def invalidate(self, key: str) -> bool:
        """Remove an entry from L1 and L2."""
        with self._lock:
            if key in self._l1:
                item = self._l1.pop(key)
                self._current_bytes = max(0, self._current_bytes - item.get("size_bytes", 0))

        return db.delete_cache_entry(key)

    def clear(self, namespace: Optional[str] = None, user_id: Optional[int] = None) -> int:
        """Clear all or matching entries across L1 and L2."""
        with self._lock:
            if namespace or user_id is not None:
                keys_to_del = [
                    k for k, v in self._l1.items()
                    if (not namespace or v.get("namespace") == namespace) and
                       (user_id is None or v.get("user_id") == user_id)
                ]
                for k in keys_to_del:
                    item = self._l1.pop(k)
                    self._current_bytes = max(0, self._current_bytes - item.get("size_bytes", 0))
            else:
                self._l1.clear()
                self._current_bytes = 0

        return db.clear_cache(namespace=namespace, user_id=user_id)

    def get_metrics(self) -> Dict[str, Any]:
        """Return real-time cache performance metrics.

        Lock order is ``_lock`` -> ``_metrics_lock`` (identical to ``get()``) which
        eliminates the ABBA deadlock the previous reverse ordering could trigger
        under concurrent reads.
        """
        with self._lock:
            l1_item_count = len(self._l1)
            l1_bytes = self._current_bytes
            with self._metrics_lock:
                snapshot = dict(self._metrics)

        total_hits = snapshot["l1_hits"] + snapshot["l2_hits"]
        total_requests = total_hits + snapshot["misses"]
        hit_ratio = round((total_hits / total_requests * 100), 1) if total_requests > 0 else 0.0

        return {
            "l1_hits": snapshot["l1_hits"],
            "l2_hits": snapshot["l2_hits"],
            "total_hits": total_hits,
            "misses": snapshot["misses"],
            "total_requests": total_requests,
            "hit_ratio_percent": hit_ratio,
            "latency_saved_ms": snapshot["latency_saved_ms"],
            "tokens_saved": snapshot["tokens_saved"],
            "l1_items": l1_item_count,
            "l1_bytes": l1_bytes,
        }
