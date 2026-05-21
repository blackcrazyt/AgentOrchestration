"""Webhook fanout with per-endpoint rate limiting.

Provides WebhookFanoutManager that enforces per-endpoint rate limits during
fanout delivery, preventing a single misconfigured integration from
consuming all available dispatch capacity.
"""

import time
import threading
from typing import Dict


class WebhookFanoutManager:
    """Rate-limits webhook fanout on a per-endpoint basis.

    Unlike the global RateLimitMiddleware which operates on client IP,
    this guard prevents any single endpoint URL from being flooded during
    a fanout (e.g. when a single event is dispatched to hundreds of
    subscribers).

    Thread-safe for async usage via internal lock.
    """

    def __init__(self, max_per_endpoint: int = 10, window: float = 60.0):
        """
        Args:
            max_per_endpoint: Maximum deliveries to a single endpoint URL
                              within the window.
            window: Time window in seconds.
        """
        self._max = max_per_endpoint
        self._window = window
        self._endpoint_attempts: Dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, endpoint_url: str) -> bool:
        """Check whether a delivery to *endpoint_url* is currently permitted.

        Returns True if the endpoint is under its rate limit, False if it
        should be skipped / deferred.
        """
        now = time.time()
        with self._lock:
            attempts = self._endpoint_attempts.get(endpoint_url)
            if attempts is None:
                self._endpoint_attempts[endpoint_url] = [now]
                return True

            # Prune expired timestamps
            cutoff = now - self._window
            attempts[:] = [t for t in attempts if t > cutoff]

            if len(attempts) >= self._max:
                return False

            attempts.append(now)
            return True

    def reset(self) -> None:
        """Clear all rate-limit state (useful for tests)."""
        with self._lock:
            self._endpoint_attempts.clear()
