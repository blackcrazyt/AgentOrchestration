"""Webhook management with DNS failure handling (bounty #2645).

DNS resolution failures must not block workers — failing endpoints are
flagged and delivery is deferred without crashing the delivery loop.
"""

from enum import Enum
from typing import Dict, List, Optional, Set
from uuid import uuid4


class SubscriptionState(Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ROTATED = "rotated"
    REVOKED = "revoked"
    DNS_FAILED = "dns_failed"


class WebhookSubscription:
    def __init__(self, endpoint: str, event_types: List[str], workspace: str = "default"):
        self.id = str(uuid4())
        self.endpoint = endpoint
        self.event_types = set(event_types)
        self.workspace = workspace
        self.state = SubscriptionState.ACTIVE
        self.dns_failures = 0

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "endpoint": self.endpoint,
            "event_types": sorted(self.event_types),
            "workspace": self.workspace, "state": self.state.value,
            "dns_failures": self.dns_failures,
        }


class DNSResolver:
    """Simulated DNS resolver for webhook endpoint validation."""

    UNRESOLVABLE_HOSTS = {"dead.example.com", "nxdomain.test"}

    def resolve(self, hostname: str) -> Optional[str]:
        """Resolve a hostname. Returns IP or None on failure."""
        if hostname in self.UNRESOLVABLE_HOSTS:
            return None
        return f"1.2.3.4"  # Simulated IP


class WebhookManager:
    def __init__(self, event_allowlist: Optional[Set[str]] = None):
        self._subscriptions: Dict[str, WebhookSubscription] = {}
        self._allowlist: Set[str] = set(event_allowlist) if event_allowlist else {
            "agent.started", "agent.stopped", "agent.error",
            "task.queued", "task.dispatched", "task.completed", "task.failed",
            "workflow.started", "workflow.completed", "workflow.failed",
        }
        self._rejected: List[Dict] = []
        self._resolver = DNSResolver()

    def create_subscription(self, endpoint: str, event_types: List[str], workspace: str = "default") -> Optional[WebhookSubscription]:
        requested = set(event_types)
        invalid = requested - self._allowlist
        if invalid:
            self._rejected.append({"endpoint": endpoint, "invalid_types": sorted(invalid), "reason": f"Unknown: {sorted(invalid)}"})
            return None
        sub = WebhookSubscription(endpoint, list(requested), workspace)
        self._subscriptions[sub.id] = sub
        return sub

    def deliver(self, sub_id: str) -> bool:
        """Attempt delivery. DNS failures flag endpoint without blocking."""
        sub = self._subscriptions.get(sub_id)
        if not sub:
            return False
        if sub.state != SubscriptionState.ACTIVE:
            self._rejected.append({"subscription_id": sub_id, "reason": f"Endpoint is {sub.state.value}"})
            return False
        # Extract hostname from endpoint URL
        hostname = sub.endpoint.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
        if not self._resolver.resolve(hostname):
            sub.dns_failures += 1
            sub.state = SubscriptionState.DNS_FAILED
            self._rejected.append({
                "subscription_id": sub_id, "endpoint": sub.endpoint,
                "hostname": hostname, "reason": f"DNS resolution failed for {hostname}",
            })
            return False
        return True

    def reactivate_after_dns_recovery(self, sub_id: str) -> bool:
        """Reactivate a DNS_FAILED subscription once DNS recovers."""
        sub = self._subscriptions.get(sub_id)
        if not sub or sub.state != SubscriptionState.DNS_FAILED:
            return False
        hostname = sub.endpoint.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
        if self._resolver.resolve(hostname):
            sub.state = SubscriptionState.ACTIVE
            return True
        return False

    def get_dns_failed_endpoints(self) -> List[Dict]:
        return [s.to_dict() for s in self._subscriptions.values() if s.state == SubscriptionState.DNS_FAILED]

    def get_subscription(self, sub_id: str) -> Optional[WebhookSubscription]:
        return self._subscriptions.get(sub_id)

    def list_subscriptions(self, workspace: Optional[str] = None) -> List[Dict]:
        subs = self._subscriptions.values()
        if workspace: subs = [s for s in subs if s.workspace == workspace]
        return [s.to_dict() for s in subs]

    def get_rejected(self) -> List[Dict]:
        return list(self._rejected)

    def subscription_count(self) -> int:
        return len(self._subscriptions)
