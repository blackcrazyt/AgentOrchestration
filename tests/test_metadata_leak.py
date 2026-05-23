"""Tests for webhook metadata leak prevention (bounty #2893)."""

import unittest
from src.webhook.shaper import PayloadShaper


class TestPayloadShaper(unittest.TestCase):

    def setUp(self):
        self.shaper = PayloadShaper()

    def test_public_fields_preserved(self):
        """Public fields are kept in payload."""
        payload = {"event": "task.completed", "data": {"count": 5}}
        clean = self.shaper.shape(payload)
        self.assertEqual(clean["event"], "task.completed")
        self.assertEqual(clean["data"]["count"], 5)

    def test_internal_token_stripped(self):
        """internal_token is removed from payload."""
        payload = {"event": "task.completed", "internal_token": "secret123"}
        clean = self.shaper.shape(payload)
        self.assertNotIn("internal_token", clean)

    def test_internal_prefix_stripped(self):
        """Fields with _internal_ prefix are removed."""
        payload = {"event": "ok", "_internal_trace_id": "trace-xyz"}
        clean = self.shaper.shape(payload)
        self.assertNotIn("_internal_trace_id", clean)

    def test_double_underscore_prefix_stripped(self):
        """Fields with __ prefix are removed."""
        payload = {"event": "ok", "__private_key": "abc123"}
        clean = self.shaper.shape(payload)
        self.assertNotIn("__private_key", clean)

    def test_ao_internal_prefix_stripped(self):
        """Fields with ao_internal_ prefix are removed."""
        payload = {"event": "ok", "ao_internal_secret": "x"}
        clean = self.shaper.shape(payload)
        self.assertNotIn("ao_internal_secret", clean)

    def test_nested_internal_stripped(self):
        """Internal fields in nested dicts are also stripped."""
        payload = {"event": "ok", "meta": {"public": 1, "internal_token": "secret"}}
        clean = self.shaper.shape(payload)
        self.assertIn("meta", clean)
        self.assertNotIn("internal_token", clean["meta"])

    def test_shape_list(self):
        """shape_list processes multiple payloads."""
        payloads = [{"event": "a"}, {"event": "b", "internal_token": "x"}]
        clean = self.shaper.shape_list(payloads)
        self.assertEqual(len(clean), 2)
        self.assertNotIn("internal_token", clean[1])

    def test_was_shaped(self):
        """was_shaped returns True when fields were stripped."""
        orig = {"event": "ok", "internal_token": "secret"}
        clean = self.shaper.shape(orig)
        self.assertTrue(self.shaper.was_shaped(orig, clean))

    def test_was_shaped_false_for_clean_payload(self):
        """was_shaped returns False when nothing was stripped."""
        orig = {"event": "ok", "data": {"count": 1}}
        clean = self.shaper.shape(orig)
        self.assertFalse(self.shaper.was_shaped(orig, clean))

    def test_audit_leak(self):
        """audit_leak returns list of stripped field names."""
        orig = {"event": "ok", "internal_token": "x", "public": 1}
        clean = self.shaper.shape(orig)
        leaks = self.shaper.audit_leak(orig, clean)
        self.assertIn("internal_token", leaks)


if __name__ == "__main__":
    unittest.main()
