"""Webhook subscription management with event type allowlist and 410 handling.

Bounty #2318: validate event type allowlist at subscription create.
Bounty #2832: handle 410 Gone by disabling endpoint safely.
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
    def __init__(self, endpoint: str, event_types: List[str], workspace: str = "default"):
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
    def __init__(self, event_allowlist: Optional[Set[str]] = None):
        self._subscriptions: Dict[str, WebhookSubscription] = {}
        self._allowlist: Set[str] = set(event_allowlist) if event_allowlist else {
            "agent.started", "agent.stopped", "agent.error",
            "task.queued", "task.dispatched", "task.completed", "task.failed",
            "workflow.started", "workflow.completed", "workflow.failed",
        }
        self._rejected: List[Dict] = []

    def update_allowlist(self, event_types: Set[str]) -> None:
        self._allowlist = set(event_types)

    def get_allowlist(self) -> List[str]:
        return sorted(self._allowlist)

    def create_subscription(self, endpoint: str, event_types: List[str], workspace: str = "default") -> Optional[WebhookSubscription]:
        requested = set(event_types)
        invalid = requested - self._allowlist
        if invalid:
            self._rejected.append({
                "endpoint": endpoint, "workspace": workspace,
                "invalid_types": sorted(invalid),
                "reason": f"Unknown event types: {sorted(invalid)}",
            })
            return None
        sub = WebhookSubscription(endpoint, list(requested), workspace)
        self._subscriptions[sub.id] = sub
        return sub

    def handle_410_gone(self, sub_id: str) -> bool:
        """Disable endpoint safely when receiving HTTP 410 Gone."""
        sub = self._subscriptions.get(sub_id)
        if not sub:
            return False
        sub.state = SubscriptionState.REVOKED
        self._rejected.append({
            "subscription_id": sub_id, "endpoint": sub.endpoint,
            "reason": "410 Gone — endpoint permanently disabled",
        })
        return True

    def get_disabled_endpoints(self) -> List[Dict]:
        return [s.to_dict() for s in self._subscriptions.values() if s.state != SubscriptionState.ACTIVE]

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
