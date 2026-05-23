"""SSE cursor ownership validation using HMAC-signed tokens."""

import hashlib
import hmac
import json
import logging
import time
from base64 import urlsafe_b64encode, urlsafe_b64decode
from typing import Optional

logger = logging.getLogger(__name__)

# Rotate secrets via environment
SECRET = __import__("os").getenv("AO_CURSOR_SECRET", "ao-cursor-secret-change-me")
CURSOR_MAX_AGE = 3600  # 1 hour


class CursorManager:
    """Creates and validates SSE cursors with ownership verification."""

    @staticmethod
    def create(user_id: str, position: str, tenant_id: str = "") -> str:
        """Create an HMAC-signed cursor for a specific user."""
        payload = {
            "u": user_id,           # ownership claim
            "p": position,          # stream position
            "t": tenant_id,         # tenant isolation
            "iat": int(time.time()),  # issued at
        }
        data = urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
        sig = hmac.new(
            SECRET.encode(), data.encode(), hashlib.sha256
        ).hexdigest()[:32]
        return f"{data}.{sig}"

    @staticmethod
    def validate(cursor: str, current_user_id: str, current_tenant_id: str = "") -> Optional[str]:
        """Validate cursor ownership. Returns position string or None."""
        try:
            parts = cursor.split(".", 1)
            if len(parts) != 2:
                return None

            data_b64, provided_sig = parts
            expected_sig = hmac.new(
                SECRET.encode(), data_b64.encode(), hashlib.sha256
            ).hexdigest()[:32]

            if not hmac.compare_digest(provided_sig, expected_sig):
                logger.warning("SSE cursor HMAC validation failed")
                return None

            payload = json.loads(urlsafe_b64decode(data_b64 + "=="))

            # Validate ownership
            if payload.get("u") != current_user_id:
                logger.warning(
                    f"SSE cursor ownership mismatch: "
                    f"claimed={payload.get('u')}, actual={current_user_id}"
                )
                return None

            # Validate tenant isolation
            if current_tenant_id and payload.get("t") != current_tenant_id:
                logger.warning("SSE cursor tenant mismatch")
                return None

            # Validate age
            age = int(time.time()) - payload.get("iat", 0)
            if age > CURSOR_MAX_AGE:
                logger.warning(f"SSE cursor expired (age: {age}s)")
                return None

            return payload.get("p")

        except Exception as e:
            logger.error(f"SSE cursor validation error: {e}")
            return None
