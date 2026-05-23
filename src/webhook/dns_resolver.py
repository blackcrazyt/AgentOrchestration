"""Webhook DNS resolution with failure handling."""

import logging
import socket
import time
from functools import lru_cache
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

DNS_CACHE_TTL = 300  # 5 minutes
DNS_TIMEOUT = 5  # seconds
MAX_DNS_FAILURES = 5
DNS_FAILURE_WINDOW = 60  # 1 minute


class DNSResolver:
    """Resolves webhook hostnames with DNS failure tolerance."""

    def __init__(self):
        self._failure_counts: dict = {}
        self._backoff_until: dict = {}

    def resolve(self, url: str) -> Optional[Tuple[str, int]]:
        """Resolve host from URL. Returns (ip, port) or None if DNS failed."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        if not host:
            logger.error(f"Invalid URL for webhook: {url}")
            return None

        # Check if this host is in backoff
        if host in self._backoff_until and time.time() < self._backoff_until[host]:
            logger.debug(f"DNS resolution for {host} is in backoff")
            return None

        try:
            # Resolve with timeout
            socket.setdefaulttimeout(DNS_TIMEOUT)
            addr_info = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
            if addr_info:
                ip = addr_info[0][4][0]
                self._record_success(host)
                return (ip, port)
            else:
                self._record_failure(host)
                return None
        except socket.gaierror as e:
            logger.warning(f"DNS resolution failed for {host}: {e}")
            self._record_failure(host)
            return None
        except socket.timeout:
            logger.warning(f"DNS resolution timed out for {host}")
            self._record_failure(host)
            return None

    def _record_success(self, host: str) -> None:
        """Reset failure count on successful resolution."""
        self._failure_counts.pop(host, None)
        self._backoff_until.pop(host, None)

    def _record_failure(self, host: str) -> None:
        """Track failure count and apply backoff if needed."""
        now = time.time()
        # Expire old failures
        self._failure_counts[host] = self._failure_counts.get(host, 0) + 1
        if self._failure_counts[host] >= MAX_DNS_FAILURES:
            backoff = min(60 * (2 ** (self._failure_counts[host] - MAX_DNS_FAILURES)), 3600)
            self._backoff_until[host] = now + backoff
            logger.error(
                f"DNS for {host} failed {self._failure_counts[host]} times - "
                f"backing off for {backoff}s"
            )
