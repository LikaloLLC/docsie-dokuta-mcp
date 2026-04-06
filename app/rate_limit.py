"""
In-memory sliding window rate limiter.

Tracks request counts per key (IP or user_id) within a rolling time window.
For production with multiple replicas, swap to Redis-backed implementation.
"""
from __future__ import annotations

import time
import threading
from collections import defaultdict
from typing import Optional

from app.config import settings


class SlidingWindowCounter:
    """Thread-safe sliding window rate limiter."""

    def __init__(self):
        self._lock = threading.Lock()
        # key -> list of timestamps
        self._windows: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int = 3600) -> bool:
        """
        Check if a request is allowed under the rate limit.

        Args:
            key: Identifier (e.g. IP address or user_id)
            max_requests: Maximum requests allowed in the window
            window_seconds: Window duration in seconds (default: 1 hour)

        Returns:
            True if the request is allowed, False if rate limited.
        """
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            # Prune expired entries
            self._windows[key] = [
                ts for ts in self._windows[key] if ts > cutoff
            ]

            if len(self._windows[key]) >= max_requests:
                return False

            self._windows[key].append(now)
            return True

    def remaining(self, key: str, max_requests: int, window_seconds: int = 3600) -> int:
        """Return how many requests remain in the current window."""
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            self._windows[key] = [
                ts for ts in self._windows[key] if ts > cutoff
            ]
            return max(0, max_requests - len(self._windows[key]))

    def cleanup(self, max_age_seconds: int = 7200) -> None:
        """Remove stale keys to prevent unbounded memory growth."""
        now = time.time()
        cutoff = now - max_age_seconds

        with self._lock:
            stale_keys = [
                k for k, timestamps in self._windows.items()
                if not timestamps or max(timestamps) < cutoff
            ]
            for k in stale_keys:
                del self._windows[k]


# Singleton instance
_limiter = SlidingWindowCounter()


def check_rate_limit(
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Check rate limit for a video analysis request.

    Returns:
        (allowed: bool, message: str)
        If not allowed, message contains a user-friendly explanation.
    """
    if user_id:
        key = f"user:{user_id}"
        limit = settings.authenticated_hourly_limit
    elif ip_address:
        key = f"ip:{ip_address}"
        limit = settings.free_tier_hourly_limit
    else:
        # No identifier — be conservative
        key = "unknown"
        limit = settings.free_tier_hourly_limit

    if _limiter.is_allowed(key, limit):
        remaining = _limiter.remaining(key, limit)
        return True, f"{remaining} requests remaining this hour"

    return False, (
        f"Rate limit exceeded. Maximum {limit} video analyses per hour. "
        f"Please try again later."
    )


def periodic_cleanup() -> None:
    """Call periodically (e.g. every 30 min) to free memory from stale keys."""
    _limiter.cleanup()
