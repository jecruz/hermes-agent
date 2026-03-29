"""Lightweight TTL-based HTTP response cache for web API calls.

Reduces redundant API calls and JSON parsing for repeated queries.
Thread-safe using a lock for concurrent access.
"""

import json
import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Global cache storage and lock
_cache: Dict[str, Tuple[Any, float]] = {}  # key -> (response_json, expiry_time)
_cache_lock = threading.RLock()

# Configurable TTL (seconds)
_DEFAULT_TTL = 300  # 5 minutes


def _make_cache_key(method: str, url: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Create a stable cache key from request components."""
    # Sort params for stable serialization
    if params:
        stable = json.dumps(params, sort_keys=True, default=str)
    else:
        stable = ""
    return f"{method.upper()}|{url}|{stable}"


def get_cached(method: str, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    """Return cached response if present and not expired. Thread-safe."""
    key = _make_cache_key(method, url, params)
    with _cache_lock:
        if key not in _cache:
            return None
        value, expiry = _cache[key]
        if time.time() < expiry:
            logger.debug("Cache HIT: %s", key)
            return value
        else:
            # Expired — remove
            del _cache[key]
            logger.debug("Cache EXPIRED: %s", key)
    return None


def set_cached(
    method: str,
    url: str,
    response: Any,
    params: Optional[Dict[str, Any]] = None,
    ttl: int = _DEFAULT_TTL,
) -> None:
    """Store response in cache with TTL. Thread-safe."""
    key = _make_cache_key(method, url, params)
    expiry = time.time() + ttl
    with _cache_lock:
        _cache[key] = (response, expiry)
    logger.debug("Cache SET: %s (ttl=%ds)", key, ttl)


def clear_cache() -> None:
    """Clear all cached entries. Thread-safe."""
    with _cache_lock:
        _cache.clear()


def cache_stats() -> Dict[str, int]:
    """Return cache statistics."""
    with _cache_lock:
        now = time.time()
        expired = sum(1 for _, (_, exp) in _cache.items() if now >= exp)
        return {"total": len(_cache), "active": len(_cache) - expired, "expired": expired}
