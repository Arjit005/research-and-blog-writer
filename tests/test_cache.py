"""Comprehensive Unit & Integration Test Suite for Hybrid Two-Tier Cache System.

Validates:
1. Canonical URL normalization & deterministic versioned cache keys.
2. L1 In-Memory LRU hit, miss, and byte/count eviction limits.
3. L2 TiDB/SQLite persistence, TTL enforcement, and fail-open resilience.
4. Promotion from L2 to L1 upon hit.
5. Anti-stampede locking under high concurrency (single fetch execution).
6. Serve-stale on remote fetch failure.
7. Deterministic LLM response memoization vs creative temperature bypass.
8. 1 MB payload capping and multi-tenant user scoping.
"""

import time
import threading
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest

import database as db
from cache import (
    HybridCacheManager,
    normalize_url,
    make_cache_key,
    MAX_PAYLOAD_BYTES,
)
from llm_fallback import FallbackLLM


@pytest.fixture(autouse=True)
def setup_clean_db():
    """Ensure database schema is ready and cache is clean before every test."""
    db.init_db()
    mgr = HybridCacheManager.get_instance()
    mgr.clear()
    yield
    mgr.clear()


# ---------------------------------------------------------------------------
# 1. URL Normalization
# ---------------------------------------------------------------------------
def test_url_normalization():
    """Verify only known tracking params are stripped while meaningful params/fragments remain."""
    raw = "HTTPS://Example.COM:443/api/v1/resource/?utm_source=twitter&valid=true#section-2"
    clean = normalize_url(raw)
    # Tracking params stripped, fragment and real query params preserved.
    assert clean == "https://example.com/api/v1/resource?valid=true#section-2"

    # Generic, potentially semantic params must NOT be collapsed anymore.
    assert normalize_url("https://example.com/page?ref=nav") == "https://example.com/page?ref=nav"
    assert normalize_url("https://example.com/page?source=feed") == "https://example.com/page?source=feed"
    assert normalize_url("https://example.com/page?utm_source=rss&b=2") == "https://example.com/page?b=2"

    # Default http port 80 stripped
    assert normalize_url("http://example.com:80/path/") == "http://example.com/path"

    # Trailing slash stripped on non-root path
    assert normalize_url("https://example.com/path/") == "https://example.com/path"


def test_cache_key_encoding_is_collision_resistant():
    """Length-prefixed component encoding must not alias distinct component tuples."""
    assert make_cache_key("ns", "a||b") != make_cache_key("ns", "a", "b")
    assert make_cache_key("ns", "a", "b") != make_cache_key("ns", "ab")
    assert make_cache_key("ns", "1", "23") != make_cache_key("ns", "12", "3")
    assert make_cache_key("ns", "x") == make_cache_key("ns", "x")


def test_failure_cache_is_bounded():
    """Negative caching must not grow without bound across high-cardinality keys."""
    mgr = HybridCacheManager(max_failures=5)

    def always_fails():
        raise RuntimeError("upstream down")

    for index in range(12):
        with pytest.raises(RuntimeError):
            mgr.fetch_or_compute(
                f"fail-key-{index}", "resilience", always_fails, ttl_seconds=60,
                allow_stale_on_error=False,
            )
    assert len(mgr._failure_cache) <= 5


def test_stampede_locks_are_released_when_fetch_raises():
    """Exception paths must not leak per-key anti-stampede lock entries."""
    mgr = HybridCacheManager()

    def boom():
        raise ValueError("compute failed")

    for index in range(5):
        with pytest.raises(ValueError):
            mgr.fetch_or_compute(
                f"raise-key-{index}", "resilience", boom, ttl_seconds=60,
                allow_stale_on_error=False,
            )
    assert mgr._key_locks == {}


def test_get_and_get_metrics_do_not_deadlock_concurrently():
    """get()/get_metrics() must use one lock order (previously ABBA-deadlocked)."""
    mgr = HybridCacheManager.get_instance()
    mgr.set(make_cache_key("lock_order", "entry"), "lock_order", "payload", ttl_seconds=60)
    key = make_cache_key("lock_order", "entry")
    errors = []

    def read_loop():
        try:
            for _ in range(200):
                mgr.get(key, namespace="lock_order")
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    def metrics_loop():
        try:
            for _ in range(200):
                mgr.get_metrics()
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    readers = [threading.Thread(target=read_loop), threading.Thread(target=read_loop)]
    metrics = [threading.Thread(target=metrics_loop), threading.Thread(target=metrics_loop)]
    for thread in readers + metrics:
        thread.start()
    for thread in readers + metrics:
        thread.join(timeout=15)
        assert not thread.is_alive(), "get()/get_metrics() deadlocked"

    assert not errors
    metrics_snapshot = mgr.get_metrics()
    assert metrics_snapshot["total_requests"] >= metrics_snapshot["total_hits"]



# ---------------------------------------------------------------------------
# 2. Key Generation & Tenant Scoping
# ---------------------------------------------------------------------------
def test_cache_key_generation_and_user_scoping():
    """Verify versioned keys include namespace, components, and optional user_id."""
    k1 = make_cache_key("web_scrape", "https://example.com/page")
    k2 = make_cache_key("web_scrape", "https://example.com/page")
    assert k1 == k2
    assert k1.startswith("v1:web_scrape:")

    # User scoping creates distinct keys for privacy & multi-tenant isolation
    k_user1 = make_cache_key("llm_eval", "prompt", user_id=1)
    k_user2 = make_cache_key("llm_eval", "prompt", user_id=2)
    assert k_user1 != k_user2


# ---------------------------------------------------------------------------
# 3. L1 In-Memory LRU & Byte Limit Eviction
# ---------------------------------------------------------------------------
def test_l1_lru_and_byte_eviction():
    """Verify L1 respects item count and maximum byte limits."""
    # Create small cache manager: max 2 items, max 100 bytes
    mini_mgr = HybridCacheManager(max_bytes=100, max_items=2)

    # 1. Store item 1 (40 bytes)
    p1 = "A" * 40
    mini_mgr.set("key1", "test", p1, ttl_seconds=3600)

    # 2. Store item 2 (40 bytes)
    p2 = "B" * 40
    mini_mgr.set("key2", "test", p2, ttl_seconds=3600)

    assert mini_mgr.get("key1", "test") is not None
    assert mini_mgr.get("key2", "test") is not None

    # 3. Store item 3 (40 bytes): total 120 > 100 bytes limit -> evicts key1 (least recently used)
    # (Note: key2 was accessed more recently via get)
    p3 = "C" * 40
    mini_mgr.set("key3", "test", p3, ttl_seconds=3600)

    # In L1, key1 was evicted to free bytes
    with mini_mgr._lock:
        assert "key1" not in mini_mgr._l1
        assert "key3" in mini_mgr._l1


# ---------------------------------------------------------------------------
# 4. L2 Database Persistence & L1 Promotion
# ---------------------------------------------------------------------------
def test_l2_persistence_and_l1_promotion():
    """Verify a miss in L1 that hits L2 gets promoted back into L1."""
    mgr = HybridCacheManager.get_instance()
    key = make_cache_key("test_ns", "data_1")

    # Manually insert directly into L2 database bypassing L1
    now = datetime.now(timezone.utc)
    db.set_cache_entry(key, "test_ns", "Durable Database Payload", expires_at=now + timedelta(hours=1))

    # L1 should not have it yet
    with mgr._lock:
        assert key not in mgr._l1

    # First get checks L1 (miss), checks L2 (hit), and populates L1
    entry = mgr.get(key, namespace="test_ns")
    assert entry is not None
    assert entry["payload"] == "Durable Database Payload"
    assert entry["tier"] == "L2"

    # L1 should now contain the promoted entry
    with mgr._lock:
        assert key in mgr._l1

    # Second get hits L1 directly (tier L1)
    entry2 = mgr.get(key, namespace="test_ns")
    assert entry2 is not None
    assert entry2["tier"] == "L1"


# ---------------------------------------------------------------------------
# 5. Time-Travel TTL Expiration
# ---------------------------------------------------------------------------
def test_time_travel_ttl_and_batched_prune():
    """Verify entries expire accurately according to injected clock and get pruned."""
    t0 = datetime(2026, 11, 4, 12, 0, 0, tzinfo=timezone.utc)
    mgr = HybridCacheManager.get_instance()
    key = make_cache_key("temp", "volatile_data")

    # Set with 300 seconds TTL (expires at 12:05:00)
    mgr.set(key, "temp", "Ephemeral Secret", ttl_seconds=300, now=t0)

    # Read at 12:04:00 (still valid)
    t_valid = t0 + timedelta(seconds=240)
    assert mgr.get(key, "temp", now=t_valid) is not None

    # Read at 12:06:00 (expired)
    t_expired = t0 + timedelta(seconds=360)
    assert mgr.get(key, "temp", now=t_expired) is None

    # But allow_stale returns it flagged as is_stale=True
    stale_entry = mgr.get(key, "temp", allow_stale=True, now=t_expired)
    assert stale_entry is not None
    assert stale_entry["is_stale"] is True

    # Prune expired entries
    pruned = db.prune_expired_cache(now=t_expired)
    assert pruned >= 1


# ---------------------------------------------------------------------------
# 6. Anti-Stampede Lock (High Concurrency)
# ---------------------------------------------------------------------------
def test_anti_stampede_concurrency():
    """Verify concurrent requests for the same uncached key execute compute function only once."""
    mgr = HybridCacheManager.get_instance()
    key = make_cache_key("concurrency", "shared_resource")

    compute_count = 0
    compute_lock = threading.Lock()

    def slow_compute():
        nonlocal compute_count
        with compute_lock:
            compute_count += 1
        time.sleep(0.15)  # Simulate expensive HTTP scrape or LLM call
        return "Single Computed Value"

    threads = []
    results = [None] * 5

    def worker(idx):
        val, _ = mgr.fetch_or_compute(key, "concurrency", slow_compute, ttl_seconds=3600)
        results[idx] = val

    for i in range(5):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # All 5 workers received the correct result
    for r in results:
        assert r == "Single Computed Value"

    # Crucial assertion: compute was called exactly ONCE across all 5 threads
    assert compute_count == 1


# ---------------------------------------------------------------------------
# 7. Serve-Stale on Remote Fetch Failure
# ---------------------------------------------------------------------------
def test_serve_stale_on_remote_failure():
    """Verify expired cache entry is served gracefully if fresh fetch fails."""
    mgr = HybridCacheManager.get_instance()
    key = make_cache_key("resilience", "fragile_api")

    # 1. Populate initial entry
    mgr.set(key, "resilience", "Old Good Data", ttl_seconds=1)
    time.sleep(1.1)  # Allow entry to expire

    # 2. Attempt fresh fetch that fails
    def broken_fetch():
        raise ConnectionError("Upstream 503 Outage")

    val, meta = mgr.fetch_or_compute(
        key, "resilience", broken_fetch, ttl_seconds=3600, allow_stale_on_error=True
    )

    assert val == "Old Good Data"
    assert meta.get("stale") is True
    assert "Upstream 503 Outage" in meta.get("fetch_error", "")


# ---------------------------------------------------------------------------
# 8. Deterministic LLM Memoization vs Creative Bypass
# ---------------------------------------------------------------------------
def test_deterministic_llm_memoization():
    """Verify temperature <= 0.2 calls are memoized while creative calls bypass cache."""
    mgr = HybridCacheManager.get_instance()
    llm = FallbackLLM(models=["openrouter/mock-model"])

    mock_inst = MagicMock()
    mock_inst.call.return_value = "Deterministic Analysis Output"
    llm._llm_instances["openrouter/mock-model"] = mock_inst

    # 1. Deterministic call (temp 0.1) -> computed & cached
    res1 = llm.call(messages=[{"role": "user", "content": "analyze logic"}], temperature=0.1)
    assert res1 == "Deterministic Analysis Output"
    assert mock_inst.call.call_count == 1

    # 2. Identical deterministic call -> hits cache (no network call)
    res2 = llm.call(messages=[{"role": "user", "content": "analyze logic"}], temperature=0.1)
    assert res2 == "Deterministic Analysis Output"
    assert mock_inst.call.call_count == 1  # Still 1! Hit cache!

    # 3. Creative call (temp 0.7) -> bypasses cache every time
    mock_inst.call.return_value = "Creative Story Output"
    res3 = llm.call(messages=[{"role": "user", "content": "write story"}], temperature=0.7)
    assert res3 == "Creative Story Output"
    assert mock_inst.call.call_count == 2


# ---------------------------------------------------------------------------
# 9. 1 MB Payload Capping
# ---------------------------------------------------------------------------
def test_oversized_payload_capping():
    """Verify payloads exceeding 1 MB are safely rejected from cache storage without crashing."""
    mgr = HybridCacheManager.get_instance()
    huge_payload = "X" * (MAX_PAYLOAD_BYTES + 500)  # > 1 MB

    saved = mgr.set("huge_key", "test", huge_payload, ttl_seconds=3600)
    assert saved is False
    assert mgr.get("huge_key", "test") is None
