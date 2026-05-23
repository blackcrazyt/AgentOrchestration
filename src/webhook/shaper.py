"""Webhook payload shaping — prevent internal metadata leaks (bounty #2893).

Sensitive operational fields are filtered before serialization, logging,
or webhook payload shaping.  Internal-only fields never reach integrations.
"""

from typing import Dict, List, Set


class PayloadShaper:
    """Strips internal metadata from webhook payloads before delivery.

    Defines a set of internal-only fields that must never appear in
    public webhook events or log outputs.  Any field whose key matches
    a pattern in the denylist is removed during shaping.
    """

    # Internal fields that must be stripped from public payloads
    INTERNAL_FIELDS: Set[str] = {
        "internal_token", "internal_secret", "_internal_id",
        "raw_sql", "private_key", "ssh_key", "bearer_token",
        "workspace_secret", "admin_override",
    }

    # Prefixes that mark fields as internal
    INTERNAL_PREFIXES: List[str] = ["_internal_", "__", "ao_internal_"]

    def shape(self, payload: Dict) -> Dict:
        """Return a safe copy of the payload with internal fields removed."""
        clean = {}
        for key, value in payload.items():
            if self._is_internal(key):
                continue
            if isinstance(value, dict):
                clean[key] = self.shape(value)
            else:
                clean[key] = value
        return clean

    def _is_internal(self, key: str) -> bool:
        """Check if a key should be stripped from public payloads."""
        if key in self.INTERNAL_FIELDS:
            return True
        for prefix in self.INTERNAL_PREFIXES:
            if key.startswith(prefix):
                return True
        return False

    def shape_list(self, payloads: List[Dict]) -> List[Dict]:
        """Shape a list of payloads."""
        return [self.shape(p) for p in payloads]

    def audit_leak(self, original: Dict, shaped: Dict) -> List[str]:
        """Return list of field names that were stripped."""
        stripped = []
        for key in original:
            if self._is_internal(key):
                stripped.append(key)
        return stripped

    def was_shaped(self, original: Dict, shaped: Dict) -> bool:
        """Return True if any fields were stripped."""
        return len(original) != len(shaped) or any(
            self._is_internal(k) for k in original
        )
