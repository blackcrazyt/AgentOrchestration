"""Tests for webhook event type allowlist validation (bounty #2318)."""

import unittest
from src.webhook.manager import WebhookManager, SubscriptionState


class TestWebhookAllowlist(unittest.TestCase):

    def setUp(self):
        self.mgr = WebhookManager()

    # -- allowlist --
    def test_default_allowlist_populated(self):
        """Default allowlist contains built-in event types."""
        allowed = self.mgr.get_allowlist()
        self.assertIn("agent.started", allowed)
        self.assertIn("workflow.completed", allowed)

    def test_update_allowlist_replaces(self):
        """update_allowlist replaces the entire set."""
        self.mgr.update_allowlist({"custom.event"})
        self.assertEqual(self.mgr.get_allowlist(), ["custom.event"])

    # -- valid subscriptions --
    def test_create_subscription_with_valid_types(self):
        """Subscriptions with valid event types are created."""
        sub = self.mgr.create_subscription(
            "https://hook.example.com/cb",
            ["agent.started", "task.completed"],
        )
        self.assertIsNotNone(sub)
        self.assertEqual(sub.state, SubscriptionState.ACTIVE)
        self.assertEqual(sub.endpoint, "https://hook.example.com/cb")
        self.assertIn("agent.started", sub.event_types)

    # -- invalid subscriptions --
    def test_create_subscription_rejects_unknown_type(self):
        """Subscriptions with unknown event types return None."""
        sub = self.mgr.create_subscription(
            "https://hook.example.com/evil",
            ["agent.started", "xss.injection"],
        )
        self.assertIsNone(sub)

    def test_create_subscription_all_unknown_rejected(self):
        """Subscriptions where every type is unknown are rejected."""
        sub = self.mgr.create_subscription(
            "https://hook.example.com/bad",
            ["unknown.1", "unknown.2"],
        )
        self.assertIsNone(sub)

    # -- rejection audit --
    def test_rejected_recorded(self):
        """Invalid subscription attempts are recorded for audit."""
        self.mgr.create_subscription("https://bad.hook", ["custom.bad"])
        rejected = self.mgr.get_rejected()
        self.assertEqual(len(rejected), 1)
        self.assertIn("invalid_types", rejected[0])
        self.assertEqual(rejected[0]["endpoint"], "https://bad.hook")

    # -- listing --
    def test_list_subscriptions(self):
        """list_subscriptions returns created subscriptions."""
        self.mgr.create_subscription("https://a.example.com", ["agent.started"])
        self.mgr.create_subscription("https://b.example.com", ["task.completed"])
        self.assertEqual(len(self.mgr.list_subscriptions()), 2)

    def test_list_subscriptions_filtered_by_workspace(self):
        """list_subscriptions filters by workspace."""
        self.mgr.create_subscription("https://a.example.com", ["agent.started"], workspace="ws-a")
        self.mgr.create_subscription("https://b.example.com", ["task.completed"], workspace="ws-b")
        self.assertEqual(len(self.mgr.list_subscriptions(workspace="ws-a")), 1)

    # -- disable --
    def test_disable_subscription(self):
        """Disabling a subscription changes state."""
        sub = self.mgr.create_subscription("https://h.example.com", ["agent.started"])
        self.assertTrue(self.mgr.disable_subscription(sub.id))
        self.assertEqual(sub.state, SubscriptionState.DISABLED)

    def test_disable_unknown_subscription(self):
        """Disabling a non-existent subscription returns False."""
        self.assertFalse(self.mgr.disable_subscription("nope"))

    # -- count --
    def test_subscription_count(self):
        self.mgr.create_subscription("https://a.example.com", ["agent.started"])
        self.assertEqual(self.mgr.subscription_count(), 1)


if __name__ == "__main__":
    unittest.main()
