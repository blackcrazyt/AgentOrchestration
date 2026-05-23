"""Tests for batch acknowledgement ownership (bounty #2572)."""

import unittest
from src.orchestrator.batch_ack import BatchAckManager


class TestBatchAck(unittest.TestCase):

    def setUp(self):
        self.mgr = BatchAckManager()

    def test_ack_own_task_succeeds(self):
        """Worker can ack tasks assigned to it."""
        self.mgr.assign("task-1", "worker-a")
        self.mgr.assign("task-2", "worker-a")
        accepted = self.mgr.ack_batch("worker-a", ["task-1", "task-2"])
        self.assertEqual(accepted, 2)

    def test_cross_worker_ack_rejected(self):
        """Worker cannot ack another worker's task."""
        self.mgr.assign("task-1", "worker-a")
        self.mgr.assign("task-2", "worker-b")
        accepted = self.mgr.ack_batch("worker-a", ["task-1", "task-2"])
        self.assertEqual(accepted, 1)
        self.assertEqual(len(self.mgr.get_rejected()), 1)

    def test_unassigned_task_rejected(self):
        """Acking an unassigned task is rejected."""
        accepted = self.mgr.ack_batch("worker-a", ["ghost-task"])
        self.assertEqual(accepted, 0)
        rejected = self.mgr.get_rejected()
        self.assertEqual(len(rejected), 1)
        self.assertIn("not assigned", rejected[0]["reason"])

    def test_double_ack_rejected(self):
        """Re-acking an already-acked task is rejected."""
        self.mgr.assign("task-1", "worker-a")
        self.mgr.ack_batch("worker-a", ["task-1"])
        accepted = self.mgr.ack_batch("worker-a", ["task-1"])
        self.assertEqual(accepted, 0)
        self.assertIn("already acknowledged", self.mgr.get_rejected()[0]["reason"])

    def test_is_acked(self):
        """is_acked returns True after successful ack."""
        self.mgr.assign("task-1", "worker-a")
        self.mgr.ack_batch("worker-a", ["task-1"])
        self.assertTrue(self.mgr.is_acked("task-1"))

    def test_partial_batch_mixed_ownership(self):
        """Mixed batch: own tasks accepted, others rejected."""
        self.mgr.assign("t1", "w1")
        self.mgr.assign("t2", "w2")
        self.mgr.assign("t3", "w1")
        accepted = self.mgr.ack_batch("w1", ["t1", "t2", "t3"])
        self.assertEqual(accepted, 2)
        self.assertEqual(len(self.mgr.get_rejected()), 1)

    def test_get_worker_tasks(self):
        """get_worker_tasks returns only this worker's tasks."""
        self.mgr.assign("t1", "w1")
        self.mgr.assign("t2", "w2")
        self.mgr.assign("t3", "w1")
        tasks = self.mgr.get_worker_tasks("w1")
        self.assertEqual(set(tasks), {"t1", "t3"})


if __name__ == "__main__":
    unittest.main()
