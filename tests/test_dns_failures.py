"""Tests for DNS resolution failure handling (bounty #2645)."""

import unittest
from src.webhook.manager import WebhookManager, SubscriptionState, DNSResolver


class TestDNSResolver(unittest.TestCase):
    def test_resolve_valid_host(self):
        r = DNSResolver()
        self.assertIsNotNone(r.resolve("example.com"))

    def test_resolve_unresolvable_host(self):
        r = DNSResolver()
        self.assertIsNone(r.resolve("dead.example.com"))


class TestDNSFailureHandling(unittest.TestCase):
    def setUp(self):
        self.mgr = WebhookManager()

    def test_deliver_succeeds_for_valid_endpoint(self):
        sub = self.mgr.create_subscription("https://example.com/hook", ["agent.started"])
        self.assertTrue(self.mgr.deliver(sub.id))

    def test_dns_failure_flags_endpoint(self):
        sub = self.mgr.create_subscription("https://dead.example.com/hook", ["agent.started"])
        self.assertFalse(self.mgr.deliver(sub.id))
        self.assertEqual(sub.state, SubscriptionState.DNS_FAILED)
        self.assertEqual(sub.dns_failures, 1)

    def test_dns_failed_endpoints_listed(self):
        sub = self.mgr.create_subscription("https://dead.example.com/hook", ["agent.started"])
        self.mgr.deliver(sub.id)
        failed = self.mgr.get_dns_failed_endpoints()
        self.assertEqual(len(failed), 1)

    def test_delivery_to_dns_failed_rejected(self):
        sub = self.mgr.create_subscription("https://dead.example.com/hook", ["agent.started"])
        self.mgr.deliver(sub.id)
        self.assertFalse(self.mgr.deliver(sub.id))

    def test_dns_does_not_block_other_endpoints(self):
        s1 = self.mgr.create_subscription("https://dead.example.com/hook", ["agent.started"])
        s2 = self.mgr.create_subscription("https://ok.example.com/cb", ["task.completed"])
        self.mgr.deliver(s1.id)  # DNS fails but doesn't crash
        self.assertTrue(self.mgr.deliver(s2.id))
        self.assertEqual(s2.state, SubscriptionState.ACTIVE)

    def test_reactivate_after_dns_recovery(self):
        sub = self.mgr.create_subscription("https://dead.example.com/hook", ["agent.started"])
        self.mgr.deliver(sub.id)
        self.assertFalse(self.mgr.reactivate_after_dns_recovery(sub.id))

        sub2 = self.mgr.create_subscription("https://ok.example.com/hook", ["agent.started"])
        self.assertTrue(self.mgr.reactivate_after_dns_recovery(sub2.id))


if __name__ == "__main__":
    unittest.main()
