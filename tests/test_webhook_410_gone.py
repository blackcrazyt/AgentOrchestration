"""Tests for webhook 410 Gone handling (bounty #2832)."""

import unittest
from src.webhook.manager import WebhookManager, SubscriptionState


class TestWebhook410Gone(unittest.TestCase):
    def setUp(self):
        self.mgr = WebhookManager()

    def test_handle_410_disables_endpoint(self):
        sub = self.mgr.create_subscription("https://hook.example.com", ["agent.started"])
        self.assertTrue(self.mgr.handle_410_gone(sub.id))
        self.assertEqual(sub.state, SubscriptionState.REVOKED)

    def test_410_unknown_returns_false(self):
        self.assertFalse(self.mgr.handle_410_gone("nope"))

    def test_410_recorded_in_audit(self):
        sub = self.mgr.create_subscription("https://dead.com", ["agent.started"])
        self.mgr.handle_410_gone(sub.id)
        gone = [r for r in self.mgr.get_rejected() if "410" in r.get("reason","")]
        self.assertEqual(len(gone), 1)

    def test_disabled_endpoints_list(self):
        sub = self.mgr.create_subscription("https://gone.com", ["task.completed"])
        self.mgr.handle_410_gone(sub.id)
        d = self.mgr.get_disabled_endpoints()
        self.assertEqual(len(d), 1)
        self.assertEqual(d[0]["state"], "revoked")

    def test_410_not_active(self):
        sub = self.mgr.create_subscription("https://perm-gone.com", ["agent.started"])
        self.mgr.handle_410_gone(sub.id)
        self.assertNotEqual(sub.state, SubscriptionState.ACTIVE)

    def test_multi_410(self):
        s1 = self.mgr.create_subscription("https://a.com", ["agent.started"])
        s2 = self.mgr.create_subscription("https://b.com", ["task.completed"])
        self.mgr.handle_410_gone(s1.id)
        self.mgr.handle_410_gone(s2.id)
        self.assertEqual(len(self.mgr.get_disabled_endpoints()), 2)

    def test_disable_then_410(self):
        sub = self.mgr.create_subscription("https://multi.com", ["agent.started"])
        self.mgr.disable_subscription(sub.id)
        self.assertTrue(self.mgr.handle_410_gone(sub.id))
        self.assertEqual(sub.state, SubscriptionState.REVOKED)


if __name__ == "__main__":
    unittest.main()
