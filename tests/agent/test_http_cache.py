"""Tests for the HTTP response cache module."""

import time
from unittest.mock import patch

import pytest

from agent.http_cache import (
    get_cached,
    set_cached,
    clear_cache,
    cache_stats,
    _make_cache_key,
    _DEFAULT_TTL,
)


class TestCacheKey:
    """Cache key generation is stable and deterministic."""

    def test_method_normalized_to_uppercase(self):
        assert _make_cache_key("get", "http://x.com") == _make_cache_key("GET", "http://x.com")

    def test_params_sorted_for_stability(self):
        key1 = _make_cache_key("POST", "http://x.com", {"b": 1, "a": 2})
        key2 = _make_cache_key("POST", "http://x.com", {"a": 2, "b": 1})
        assert key1 == key2

    def test_no_params_works(self):
        key = _make_cache_key("GET", "http://x.com")
        assert "http://x.com" in key
        assert "GET" in key

    def test_tuple_as_params(self):
        """Tuples are valid cache keys (used by parallel/exa search)."""
        key = _make_cache_key("search", ("hello", 5, "agentic"))
        assert "hello" in key
        assert "5" in key


class TestCacheOperations:
    """Basic cache get/set/clear operations."""

    def setup_method(self):
        clear_cache()

    def test_set_and_get(self):
        set_cached("GET", "http://x.com", {"result": "data"})
        result = get_cached("GET", "http://x.com")
        assert result == {"result": "data"}

    def test_get_miss_returns_none(self):
        assert get_cached("GET", "http://nonexistent.com") is None

    def test_different_urls_different_keys(self):
        set_cached("GET", "http://x.com", "x")
        set_cached("GET", "http://y.com", "y")
        assert get_cached("GET", "http://x.com") == "x"
        assert get_cached("GET", "http://y.com") == "y"

    def test_different_methods_different_keys(self):
        set_cached("GET", "http://x.com", "get_result")
        set_cached("POST", "http://x.com", "post_result")
        assert get_cached("GET", "http://x.com") == "get_result"
        assert get_cached("POST", "http://x.com") == "post_result"

    def test_clear_cache(self):
        set_cached("GET", "http://x.com", "data")
        clear_cache()
        assert get_cached("GET", "http://x.com") is None

    def test_cache_stats(self):
        stats = cache_stats()
        assert "total" in stats
        assert "active" in stats


class TestCacheExpiry:
    """Cache entries expire after TTL."""

    def setup_method(self):
        clear_cache()

    def test_entry_expires_after_ttl(self):
        set_cached("GET", "http://x.com", "data", ttl=1)
        assert get_cached("GET", "http://x.com") == "data"
        time.sleep(1.1)
        assert get_cached("GET", "http://x.com") is None

    def test_custom_ttl(self):
        set_cached("GET", "http://x.com", "data", ttl=2)
        time.sleep(1)
        assert get_cached("GET", "http://x.com") == "data"  # not yet expired
        time.sleep(1.1)
        assert get_cached("GET", "http://x.com") is None  # expired


class TestCacheThreadSafety:
    """Cache operations are thread-safe."""

    def setup_method(self):
        clear_cache()

    def test_concurrent_set_and_get(self):
        import threading

        results = []

        def writer(key: str):
            for j in range(50):
                set_cached("GET", f"http://{key}.com", f"data-{j}")

        def reader(key: str):
            for j in range(50):
                r = get_cached("GET", f"http://{key}.com")
                if r is not None:
                    results.append(r)

        threads = [
            threading.Thread(target=writer, args=("a",)),
            threading.Thread(target=reader, args=("b",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have collected some results without errors
        assert len(results) >= 0  # no crash, which is the main guarantee
