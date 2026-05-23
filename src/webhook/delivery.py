"""Webhook delivery with 410 Gone handling."""

import logging
import time
from typing import Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


class WebhookDelivery:
    """Delivers webhook payloads with safe 410 Gone handling."""

    def __init__(self):
        self._disabled_endpoints: Dict[str, float] = {}

    def deliver(self, url: str, payload: Dict, headers: Optional[Dict] = None) -> bool:
        """Deliver webhook payload. Returns True on success."""
        if url in self._disabled_endpoints:
            disabled_at = self._disabled_endpoints[url]
            if time.time() - disabled_at < 3600:  # Re-check hourly
                logger.debug(f"Endpoint {url} is disabled (410)")
                return False
            del self._disabled_endpoints[url]

        for attempt in range(MAX_RETRIES):
            try:
                req = Request(url, data=payload, headers=headers or {}, method="POST")
                with urlopen(req, timeout=10) as resp:
                    if resp.status < 400:
                        return True
            except HTTPError as e:
                if e.code == 410:
                    return self._handle_410(url)
                if e.code >= 500 and attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                logger.error(f"Webhook to {url} failed: HTTP {e.code}")
                return False
            except URLError as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                logger.error(f"Webhook to {url} failed: {e.reason}")
                return False

        return False

    def _handle_410(self, url: str) -> bool:
        """Handle 410 Gone: disable endpoint without crashing."""
        self._disabled_endpoints[url] = time.time()
        logger.warning(f"Webhook endpoint {url} returned 410 - disabled for 1 hour")
        return False  # Don't retry

    def reenable(self, url: str) -> None:
        """Manually re-enable a disabled endpoint."""
        self._disabled_endpoints.pop(url, None)
        logger.info(f"Re-enabled webhook endpoint {url}")
