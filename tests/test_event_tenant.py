"""Tests for event tenant ownership validation (bounty #1870)."""

import unittest
from src.orchestrator.engine import OrchestrationEngine, EventTenantError


class TestEventTenantOwnership(unittest.TestCase):

    def setUp(self):
        self.engine = OrchestrationEngine()
        self.engine.register_tenant("tenant-a")
        self.engine.register_tenant("tenant-b")

    def test_tenant_registration_creates_empty_agent_set(self):
        """register_tenant initialises a tenant with no agents."""
        agents = self.engine.get_tenant_agents("tenant-a")
        self.assertEqual(agents, [])

    def test_assign_agent_to_tenant(self):
        """assign_agent_to_tenant links an agent to a tenant."""
        ok = self.engine.assign_agent_to_tenant("agent-1", "tenant-a")
        self.assertTrue(ok)
        self.assertEqual(self.engine.get_agent_tenant("agent-1"), "tenant-a")
        self.assertIn("agent-1", self.engine.get_tenant_agents("tenant-a"))

    def test_assign_agent_to_unknown_tenant_fails(self):
        """Assigning to an unregistered tenant returns False."""
        ok = self.engine.assign_agent_to_tenant("agent-1", "ghost-tenant")
        self.assertFalse(ok)

    def test_validate_event_correct_tenant(self):
        """Event targeting own tenant's agent is accepted."""
        self.engine.assign_agent_to_tenant("agent-1", "tenant-a")
        event = {"id": "evt-1", "target_agent": "agent-1"}
        self.assertTrue(self.engine.validate_event_ownership(event, "tenant-a"))

    def test_validate_event_wrong_tenant_rejected(self):
        """Event targeting another tenant's agent is rejected."""
        self.engine.assign_agent_to_tenant("agent-1", "tenant-a")
        event = {"id": "evt-2", "target_agent": "agent-1"}
        self.assertFalse(self.engine.validate_event_ownership(event, "tenant-b"))

    def test_validate_event_unassigned_agent_rejected(self):
        """Event targeting an agent with no tenant is rejected."""
        event = {"id": "evt-3", "target_agent": "orphan-agent"}
        self.assertFalse(self.engine.validate_event_ownership(event, "tenant-a"))

    def test_validate_event_missing_target_rejected(self):
        """Event without target_agent field is rejected."""
        event = {"id": "evt-4", "data": "some data"}
        self.assertFalse(self.engine.validate_event_ownership(event, "tenant-a"))

    def test_rejected_events_audit_trail(self):
        """Rejected events are recorded with reason."""
        self.engine.assign_agent_to_tenant("agent-1", "tenant-a")
        self.engine.validate_event_ownership({"id": "evt-x", "target_agent": "agent-1"}, "tenant-b")
        rejected = self.engine.get_rejected_events()
        self.assertEqual(len(rejected), 1)
        self.assertIn("reason", rejected[0])
        self.assertEqual(rejected[0]["tenant"], "tenant-b")

    def test_get_agent_tenant_unknown_agent(self):
        """Unknown agent returns None tenant."""
        self.assertIsNone(self.engine.get_agent_tenant("nope"))

    def test_cross_tenant_isolation(self):
        """Two tenants can own different agents without cross-access."""
        self.engine.assign_agent_to_tenant("agent-1", "tenant-a")
        self.engine.assign_agent_to_tenant("agent-2", "tenant-b")
        self.assertTrue(self.engine.validate_event_ownership(
            {"id": "e1", "target_agent": "agent-1"}, "tenant-a"))
        self.assertTrue(self.engine.validate_event_ownership(
            {"id": "e2", "target_agent": "agent-2"}, "tenant-b"))
        self.assertFalse(self.engine.validate_event_ownership(
            {"id": "e3", "target_agent": "agent-1"}, "tenant-b"))


if __name__ == "__main__":
    unittest.main()
