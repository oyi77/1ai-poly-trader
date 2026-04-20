"""
Tests for Redis cache with circuit-breaker fallback.

RQ-014: Redis cache with circuit-breaker fallback to SQLite
"""
import os
import tempfile
import time

import pytest

from backend.cache.redis_cache import CircuitBreaker, RedisCache
from backend.job_queue.sqlite_cache import SQLiteCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sqlite_cache(tmp_path=None) -> SQLiteCache:
    """Create a SQLiteCache backed by a temp file."""
    if tmp_path is None:
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
    else:
        path = str(tmp_path / "test_cache.db")
    return SQLiteCache(db_path=path)


def _redis_available() -> bool:
    """Return True if a local Redis server is reachable on 127.0.0.1:6379."""
    import socket
    try:
        s = socket.create_connection(("127.0.0.1", 6379), timeout=0.3)
        s.close()
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# CircuitBreaker tests (no Redis needed)
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(threshold=3, timeout=60)
        assert cb.state == CircuitBreaker.STATE_CLOSED
        assert not cb.is_open()
        assert cb.can_attempt()

    def test_circuit_breaker_opens_after_threshold(self):
        """Record 3 failures → is_open() must return True."""
        cb = CircuitBreaker(threshold=3, timeout=60)
        cb.record_failure()
        cb.record_failure()
        assert not cb.is_open()  # not yet
        cb.record_failure()
        assert cb.is_open()

    def test_circuit_breaker_recovers_after_timeout(self):
        """Open circuit then wait > timeout → can_attempt() returns True."""
        cb = CircuitBreaker(threshold=1, timeout=0.1)  # 100ms timeout
        cb.record_failure()
        assert cb.is_open()
        assert not cb.can_attempt()

        time.sleep(0.15)
        assert cb.can_attempt()

    def test_success_resets_circuit(self):
        cb = CircuitBreaker(threshold=2, timeout=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open()
        # Simulate timeout so half-open trial is allowed
        cb._opened_at -= 70
        assert cb.can_attempt()
        cb.record_success()
        assert cb.state == CircuitBreaker.STATE_CLOSED
        assert not cb.is_open()


# ---------------------------------------------------------------------------
# SQLiteCache tests
# ---------------------------------------------------------------------------

class TestSQLiteCache:
    def test_set_and_get(self, tmp_path):
        cache = _make_sqlite_cache(tmp_path)
        cache.set("foo", {"bar": 1})
        assert cache.get("foo") == {"bar": 1}

    def test_missing_key_returns_none(self, tmp_path):
        cache = _make_sqlite_cache(tmp_path)
        assert cache.get("nonexistent") is None

    def test_ttl_expiry(self, tmp_path):
        cache = _make_sqlite_cache(tmp_path)
        cache.set("ttl_key", "value", ttl_seconds=0)  # already expired
        # Give a tiny sleep so expires_at < now
        time.sleep(0.05)
        assert cache.get("ttl_key") is None

    def test_delete(self, tmp_path):
        cache = _make_sqlite_cache(tmp_path)
        cache.set("k", "v")
        cache.delete("k")
        assert cache.get("k") is None

    def test_exists(self, tmp_path):
        cache = _make_sqlite_cache(tmp_path)
        cache.set("e", 42)
        assert cache.exists("e")
        cache.delete("e")
        assert not cache.exists("e")

    def test_flush(self, tmp_path):
        cache = _make_sqlite_cache(tmp_path)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.flush()
        assert cache.get("a") is None
        assert cache.get("b") is None


# ---------------------------------------------------------------------------
# RedisCache fallback test (no live Redis required)
# ---------------------------------------------------------------------------

class TestRedisCacheFallback:
    def test_redis_cache_falls_back_on_failure(self, tmp_path):
        """
        RedisCache with unreachable URL must transparently fall back to SQLiteCache.
        set("k", "v") and get("k") should return "v" via the fallback.
        """
        fallback = _make_sqlite_cache(tmp_path)
        cache = RedisCache(
            redis_url="redis://127.0.0.1:1",  # unreachable port
            fallback=fallback,
            breaker_threshold=3,
            breaker_timeout=60,
        )

        # set should fall back to SQLiteCache after Redis fails
        cache.set("k", "v")
        # get should fall back to SQLiteCache and return "v"
        assert cache.get("k") == "v"

    def test_redis_cache_fallback_exists(self, tmp_path):
        """exists() falls back correctly."""
        fallback = _make_sqlite_cache(tmp_path)
        cache = RedisCache(
            redis_url="redis://127.0.0.1:1",
            fallback=fallback,
            breaker_threshold=3,
            breaker_timeout=60,
        )
        cache.set("exists_key", True)
        assert cache.exists("exists_key")

    def test_redis_cache_fallback_delete(self, tmp_path):
        """delete() falls back correctly."""
        fallback = _make_sqlite_cache(tmp_path)
        cache = RedisCache(
            redis_url="redis://127.0.0.1:1",
            fallback=fallback,
            breaker_threshold=3,
            breaker_timeout=60,
        )
        cache.set("del_key", "hello")
        cache.delete("del_key")
        assert cache.get("del_key") is None

    def test_redis_cache_fallback_flush(self, tmp_path):
        """flush() falls back correctly."""
        fallback = _make_sqlite_cache(tmp_path)
        cache = RedisCache(
            redis_url="redis://127.0.0.1:1",
            fallback=fallback,
            breaker_threshold=3,
            breaker_timeout=60,
        )
        cache.set("f1", 1)
        cache.set("f2", 2)
        cache.flush()
        assert cache.get("f1") is None
        assert cache.get("f2") is None


# ---------------------------------------------------------------------------
# Live Redis tests (skipped if no server available)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _redis_available(), reason="No live Redis server on 127.0.0.1:6379")
class TestRedisCacheLive:
    def test_live_set_and_get(self, tmp_path):
        fallback = _make_sqlite_cache(tmp_path)
        cache = RedisCache(
            redis_url="redis://127.0.0.1:6379",
            fallback=fallback,
        )
        cache.flush()
        cache.set("live_key", {"x": 1})
        assert cache.get("live_key") == {"x": 1}
        cache.flush()

    def test_live_ttl(self, tmp_path):
        fallback = _make_sqlite_cache(tmp_path)
        cache = RedisCache(
            redis_url="redis://127.0.0.1:6379",
            fallback=fallback,
        )
        cache.set("ttl_live", "val", ttl_seconds=1)
        assert cache.get("ttl_live") == "val"
        time.sleep(1.1)
        assert cache.get("ttl_live") is None
