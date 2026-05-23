"""Tests for SSE cursor ownership validation (bounty #2658)."""

import unittest
from src.stream.manager import SSEManager


class TestSSECursorOwnership(unittest.TestCase):

    def setUp(self):
        self.mgr = SSEManager()

    def test_create_cursor_in_workspace(self):
        """Cursor is created within a workspace."""
        cursor = self.mgr.create_cursor("events", "ws-alpha", "reader")
        self.assertIsNotNone(cursor)
        self.assertEqual(cursor.owner.workspace, "ws-alpha")

    def test_validate_ownership_same_workspace(self):
        """Cursor owner matches requesting workspace — accepted."""
        cursor = self.mgr.create_cursor("events", "ws-alpha")
        self.assertTrue(self.mgr.validate_ownership(cursor.id, "ws-alpha"))

    def test_validate_ownership_cross_workspace_rejected(self):
        """Cursor from ws-alpha rejected when ws-beta requests it."""
        cursor = self.mgr.create_cursor("events", "ws-alpha")
        self.assertFalse(self.mgr.validate_ownership(cursor.id, "ws-beta"))

    def test_validate_ownership_unknown_cursor(self):
        """Non-existent cursor returns False."""
        self.assertFalse(self.mgr.validate_ownership("nope", "ws-alpha"))

    def test_update_cursor_position(self):
        """Update cursor position if ownership matches."""
        cursor = self.mgr.create_cursor("events", "ws-alpha")
        self.assertTrue(self.mgr.update_cursor(cursor.id, "ws-alpha", "evt-42"))
        self.assertEqual(self.mgr.get_cursor(cursor.id)["last_event_id"], "evt-42")

    def test_update_cursor_cross_workspace_rejected(self):
        """Update rejected if workspace doesn't match."""
        cursor = self.mgr.create_cursor("events", "ws-alpha")
        self.assertFalse(self.mgr.update_cursor(cursor.id, "ws-beta", "evt-99"))

    def test_rejected_audit_trail(self):
        """Cross-workspace access attempts are recorded."""
        cursor = self.mgr.create_cursor("events", "ws-alpha")
        self.mgr.validate_ownership(cursor.id, "ws-beta")
        rejected = self.mgr.get_rejected()
        self.assertEqual(len(rejected), 1)
        self.assertIn("owner_workspace", rejected[0])

    def test_revoked_cursor_rejected(self):
        """Revoked cursor fails ownership validation."""
        cursor = self.mgr.create_cursor("events", "ws-alpha")
        self.mgr.revoke_cursor(cursor.id)
        self.assertFalse(self.mgr.validate_ownership(cursor.id, "ws-alpha"))

    def test_list_cursors_filtered_by_workspace(self):
        """list_cursors scopes to workspace."""
        self.mgr.create_cursor("events", "ws-a")
        self.mgr.create_cursor("alerts", "ws-b")
        self.assertEqual(len(self.mgr.list_cursors(workspace="ws-a")), 1)


if __name__ == "__main__":
    unittest.main()
