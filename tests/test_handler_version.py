"""Tests for handler version compatibility validation (bounty #2494)."""

import unittest
from src.agent.registry import HandlerVersion, VersionRegistry


class TestHandlerVersion(unittest.TestCase):

    def test_parse_semver(self):
        v = HandlerVersion("2.1.3")
        self.assertEqual(v.major, 2)
        self.assertEqual(v.minor, 1)
        self.assertEqual(v.patch, 3)

    def test_same_major_compatible(self):
        v1 = HandlerVersion("2.0.0")
        v2 = HandlerVersion("2.9.5")
        self.assertTrue(v1.is_compatible_with(v2))

    def test_different_major_incompatible(self):
        v1 = HandlerVersion("1.0.0")
        v2 = HandlerVersion("2.0.0")
        self.assertFalse(v1.is_compatible_with(v2))

    def test_v_prefix_parsed(self):
        v = HandlerVersion("v3.0.0")
        self.assertEqual(v.major, 3)


class TestVersionRegistry(unittest.TestCase):

    def setUp(self):
        self.vr = VersionRegistry()

    def test_register_valid_version(self):
        self.assertTrue(self.vr.register("worker", "2.0.0"))

    def test_register_below_minimum_rejected(self):
        self.assertFalse(self.vr.register("worker", "0.5.0"))

    def test_is_compatible_same_major(self):
        self.vr.register("worker", "2.0.0")
        self.assertTrue(self.vr.is_compatible("worker", "2.5.0"))

    def test_is_compatible_different_major_rejected(self):
        self.vr.register("worker", "2.0.0")
        self.assertFalse(self.vr.is_compatible("worker", "3.0.0"))

    def test_is_compatible_new_handler_accepted(self):
        """No existing handler — always compatible."""
        self.assertTrue(self.vr.is_compatible("new_handler", "1.0.0"))

    def test_rejected_recorded(self):
        self.vr.register("worker", "0.1.0")
        rejected = self.vr.get_rejected()
        self.assertEqual(len(rejected), 1)
        self.assertIn("below minimum", rejected[0]["reason"])

    def test_get_version(self):
        self.vr.register("worker", "2.3.1")
        self.assertEqual(self.vr.get_version("worker"), "2.3.1")


if __name__ == "__main__":
    unittest.main()
