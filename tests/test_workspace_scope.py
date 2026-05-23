"""Tests for row-level workspace scope on task state (bounty #2537)."""

import unittest
from src.storage.repository import ScopedTaskStore


class TestScopedTaskStore(unittest.TestCase):

    def setUp(self):
        self.store = ScopedTaskStore()

    # -- put --
    def test_put_creates_task_with_workspace(self):
        t = self.store.put("ws-a", "pending")
        self.assertEqual(t.workspace, "ws-a")
        self.assertEqual(t.status, "pending")

    # -- get --
    def test_get_same_workspace(self):
        t = self.store.put("ws-a", "pending")
        result = self.store.get(t.task_id, "ws-a")
        self.assertIsNotNone(result)
        self.assertEqual(result["task_id"], t.task_id)

    def test_get_cross_workspace_blocked(self):
        t = self.store.put("ws-a", "pending")
        result = self.store.get(t.task_id, "ws-b")
        self.assertIsNone(result)

    # -- update --
    def test_update_same_workspace(self):
        t = self.store.put("ws-a", "pending")
        self.assertTrue(self.store.update_status(t.task_id, "ws-a", "running"))
        result = self.store.get(t.task_id, "ws-a")
        self.assertEqual(result["status"], "running")

    def test_update_cross_workspace_blocked(self):
        t = self.store.put("ws-a", "pending")
        self.assertFalse(self.store.update_status(t.task_id, "ws-b", "running"))

    # -- delete --
    def test_delete_cross_workspace_blocked(self):
        t = self.store.put("ws-a", "pending")
        self.assertFalse(self.store.delete(t.task_id, "ws-b"))

    # -- list --
    def test_list_tasks_scoped_to_workspace(self):
        self.store.put("ws-a", "pending")
        self.store.put("ws-a", "running")
        self.store.put("ws-b", "pending")
        self.assertEqual(len(self.store.list_tasks("ws-a")), 2)
        self.assertEqual(len(self.store.list_tasks("ws-b")), 1)

    def test_list_tasks_filtered_by_status(self):
        self.store.put("ws-a", "pending")
        self.store.put("ws-a", "running")
        self.assertEqual(len(self.store.list_tasks("ws-a", status="pending")), 1)

    # -- violations --
    def test_cross_workspace_access_logged(self):
        t = self.store.put("ws-a", "pending")
        self.store.get(t.task_id, "ws-b")
        self.store.update_status(t.task_id, "ws-b", "running")
        self.assertEqual(len(self.store.get_violations()), 2)

    # -- count --
    def test_count_scoped_to_workspace(self):
        self.store.put("ws-a", "p")
        self.store.put("ws-a", "r")
        self.store.put("ws-b", "p")
        self.assertEqual(self.store.count("ws-a"), 2)

    # -- delete same workspace --
    def test_delete_same_workspace(self):
        t = self.store.put("ws-a", "pending")
        self.assertTrue(self.store.delete(t.task_id, "ws-a"))


if __name__ == "__main__":
    unittest.main()
