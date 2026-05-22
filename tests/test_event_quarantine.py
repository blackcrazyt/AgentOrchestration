"""Tests for event type quarantine on rolling upgrades (bounty #1924)."""

import unittest
from src.orchestrator.engine import OrchestrationEngine


class TestEventQuarantine(unittest.TestCase):

    def setUp(self):
        self.engine = OrchestrationEngine()

    # -- known event types --
    def test_default_known_types_populated(self):
        """Default known event types include agent, task, workflow events."""
        known = self.engine.get_known_event_types()
        self.assertIn("agent.start", known)
        self.assertIn("task.complete", known)
        self.assertIn("workflow.start", known)

    def test_register_known_event_type(self):
        """Registering an event type adds it to the known set."""
        self.engine.register_known_event_type("custom.v2.event")
        self.assertTrue(self.engine.is_known_event_type("custom.v2.event"))

    # -- validate_event_type --
    def test_known_event_type_accepted(self):
        """A known event type passes validation."""
        event = {"id": "evt-1", "type": "agent.start", "data": {}}
        self.assertTrue(self.engine.validate_event_type(event))

    def test_unknown_event_type_quarantined(self):
        """An unknown event type is rejected and quarantined."""
        event = {"id": "evt-2", "type": "custom.unknown.v3", "data": {}}
        self.assertFalse(self.engine.validate_event_type(event))
        quarantined = self.engine.get_quarantined()
        self.assertEqual(len(quarantined), 1)
        self.assertIn("custom.unknown.v3", quarantined[0]["event_type"])

    def test_missing_event_type_rejected(self):
        """An event with no type field is rejected."""
        event = {"id": "evt-3", "data": {}}
        self.assertFalse(self.engine.validate_event_type(event))

    # -- quarantine audit --
    def test_quarantine_audit_trail(self):
        """Multiple unknown events accumulate in quarantine."""
        self.engine.validate_event_type({"id": "e1", "type": "bad.type.1"})
        self.engine.validate_event_type({"id": "e2", "type": "bad.type.2"})
        self.assertEqual(len(self.engine.get_quarantined()), 2)

    # -- rolling upgrade scenario --
    def test_new_version_event_type_registered(self):
        """During rolling upgrade, register new event type and validate."""
        self.engine.register_known_event_type("task.complete.v2")
        event = {"id": "evt-upgrade", "type": "task.complete.v2"}
        self.assertTrue(self.engine.validate_event_type(event))

    def test_old_version_event_after_upgrade_quarantined(self):
        """Old version event type that was removed gets quarantined."""
        event = {"id": "evt-old", "type": "agent.start.deprecated"}
        self.assertFalse(self.engine.validate_event_type(event))
        self.assertEqual(len(self.engine.get_quarantined()), 1)

    # -- is_known_event_type --
    def test_is_known_event_type_false_for_unknown(self):
        self.assertFalse(self.engine.is_known_event_type("nonexistent"))


if __name__ == "__main__":
    unittest.main()
