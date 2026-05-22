"""Webhook subscription management with event type allowlist (bounty #2318).

Every subscription must declare which event types it accepts. At creation time,
the declared event types are validated against a configurable allowlist.
Invalid or unknown event types are rejected immediately.
"""

from enum import Enum
from typing import Dict, List, Optional, Set
from uuid import uuid4


class SubscriptionState(Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ROTATED = "rotated"
    REVOKED = "revoked"


class WebhookSubscription:
    def __init__(
        self,
        endpoint: str,
        event_types: List[str],
        workspace: str = "default",
    ):
        self.id = str(uuid4())
        self.endpoint = endpoint
        self.event_types = set(event_types)
        self.workspace = workspace
        self.state = SubscriptionState.ACTIVE

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "endpoint": self.endpoint,
            "event_types": sorted(self.event_types),
            "workspace": self.workspace,
            "state": self.state.value,
        }


class WebhookManager:
    """Manages webhook subscriptions with event type validation.

    Event type allowlisting: new subscriptions can only declare event types
    that appear in the global allowlist. Unknown types are rejected at creation
    time, preventing misconfigured integrations from polluting the event bus.
    """

    def __init__(self, event_allowlist: Optional[Set[str]] = None):
        self._subscriptions: Dict[str, WebhookSubscription] = {}
        self._allowlist: Set[str] = set(event_allowlist) if event_allowlist else {
            "agent.started",
            "agent.stopped",
            "agent.error",
            "task.queued",
            "task.dispatched",
            "task.completed",
            "task.failed",
            "workflow.started",
            "workflow.completed",
            "workflow.failed",
        }
        self._rejected: List[Dict] = []

    def update_allowlist(self, event_types: Set[str]) -> None:
        """Replace the global event type allowlist."""
        self._allowlist = set(event_types)

    def get_allowlist(self) -> List[str]:
        """Return the current global event type allowlist."""
        return sorted(self._allowlist)

    def create_subscription(
        self, endpoint: str, event_types: List[str], workspace: str = "default"
    ) -> Optional[WebhookSubscription]:
        """Create a subscription, validating event types against the allowlist.

        Returns None if any event type is not in the allowlist.
        The rejected event types are recorded for audit.
        """
        requested = set(event_types)
        invalid = requested - self._allowlist

        if invalid:
            self._rejected.append({
                "endpoint": endpoint,
                "workspace": workspace,
                "invalid_types": sorted(invalid),
                "reason": f"Unknown event types: {sorted(invalid)}",
            })
            return None

        sub = WebhookSubscription(endpoint, list(requested), workspace)
        self._subscriptions[sub.id] = sub
        return sub

    def get_subscription(self, sub_id: str) -> Optional[WebhookSubscription]:
        return self._subscriptions.get(sub_id)

    def list_subscriptions(self, workspace: Optional[str] = None) -> List[Dict]:
        subs = self._subscriptions.values()
        if workspace:
            subs = [s for s in subs if s.workspace == workspace]
        return [s.to_dict() for s in subs]

    def disable_subscription(self, sub_id: str) -> bool:
        sub = self._subscriptions.get(sub_id)
        if not sub:
            return False
        sub.state = SubscriptionState.DISABLED
        return True

    def get_rejected(self) -> List[Dict]:
        return list(self._rejected)

    def subscription_count(self) -> int:
        return len(self._subscriptions)
