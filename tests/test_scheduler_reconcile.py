"""Regression tests for scheduler state/revision reconcile guard (bounty #81)."""

import asyncio
import unittest
from src.orchestrator.scheduler import TaskScheduler, TaskState


class TestSchedulerReconcile(unittest.TestCase):
    """Verify queue/state divergence is prevented on partial dispatch failures."""

    def setUp(self):
        self.scheduler = TaskScheduler()

    # -- enqueue / state tracking -------------------------------------------------
    def test_enqueue_sets_pending_state(self):
        """Enqueued tasks start in PENDING with revision 0."""
        tid = self.scheduler.enqueue({"target": "agent-1"})
        self.assertEqual(self.scheduler.get_state(tid), "pending")
        self.assertEqual(self.scheduler.get_revision(tid), 0)

    def test_schedule_sets_pending_state(self):
        """Scheduled tasks start in PENDING with revision 0."""
        tid = self.scheduler.schedule({"target": "agent-1"}, delay=0)
        self.assertEqual(self.scheduler.get_state(tid), "pending")
        self.assertEqual(self.scheduler.get_revision(tid), 0)

    # -- dequeue flow -------------------------------------------------------------
    def test_dequeue_transitions_to_dispatched(self):
        """Normal dequeue moves task from PENDING to DISPATCHED."""
        tid = self.scheduler.enqueue({"target": "agent-1"})
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        task = loop.run_until_complete(self.scheduler.dequeue())
        loop.close()
        self.assertIsNotNone(task)
        self.assertEqual(task["id"], tid)
        self.assertEqual(self.scheduler.get_state(tid), "dispatched")
        self.assertEqual(self.scheduler.get_revision(tid), 1)

    # -- reconcile guard: prevent double dispatch ---------------------------------
    def test_double_dequeue_skips_dispatched_task(self):
        """Second dequeue must not dispatch a task that is already DISPATCHED."""
        self.scheduler.enqueue({"target": "agent-1"})
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        first = loop.run_until_complete(self.scheduler.dequeue())
        second = loop.run_until_complete(self.scheduler.dequeue())
        loop.close()
        self.assertIsNotNone(first)
        self.assertIsNone(second, "already-dispatched task must not be re-dispatched")

    def test_double_dequeue_after_complete_allows_next(self):
        """After completing the first task, dequeue picks the next one."""
        self.scheduler.enqueue({"target": "agent-1"})
        self.scheduler.enqueue({"target": "agent-2"})
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        t1 = loop.run_until_complete(self.scheduler.dequeue())
        tid1 = t1["id"]
        self.scheduler.complete(tid1)
        t2 = loop.run_until_complete(self.scheduler.dequeue())
        loop.close()
        self.assertIsNotNone(t2)
        self.assertNotEqual(t2["id"], tid1)

    # -- complete flow ------------------------------------------------------------
    def test_complete_only_dispatched(self):
        """complete() returns True only for DISPATCHED tasks."""
        tid = self.scheduler.enqueue({"target": "agent-1"})
        # Not dispatched yet — should reject
        self.assertFalse(self.scheduler.complete(tid))
        # Dispatch
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.scheduler.dequeue())
        loop.close()
        self.assertTrue(self.scheduler.complete(tid))
        self.assertEqual(self.scheduler.get_state(tid), "completed")

    def test_double_complete_rejected(self):
        """Completing a task twice returns False on the second call."""
        tid = self.scheduler.enqueue({"target": "agent-1"})
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.scheduler.dequeue())
        loop.close()
        self.assertTrue(self.scheduler.complete(tid))
        self.assertFalse(self.scheduler.complete(tid), "double complete must be rejected")

    # -- fail flow ----------------------------------------------------------------
    def test_fail_only_dispatched(self):
        """fail() returns True only for DISPATCHED tasks."""
        tid = self.scheduler.enqueue({"target": "agent-1"})
        self.assertFalse(self.scheduler.fail(tid))  # not dispatched yet

    def test_fail_retries_re_enqueue(self):
        """Task with retries left is re-enqueued as PENDING."""
        tid = self.scheduler.enqueue({"target": "agent-1"})
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.scheduler.dequeue())
        loop.close()
        self.assertTrue(self.scheduler.fail(tid))
        self.assertEqual(self.scheduler.get_state(tid), "pending")
        self.assertEqual(self.scheduler.get_revision(tid), 2)

    def test_fail_exhausted_retries_marks_failed(self):
        """Exhausting retries transitions task to FAILED permanently."""
        tid = self.scheduler.enqueue({"target": "agent-1"})
        self.scheduler._max_retries = 1  # only 1 attempt
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.scheduler.dequeue())
        loop.close()
        self.assertTrue(self.scheduler.fail(tid))
        self.assertEqual(self.scheduler.get_state(tid), "failed")
        # No more transitions possible
        self.assertFalse(self.scheduler.complete(tid))
        self.assertFalse(self.scheduler.fail(tid))

    # -- revision counter ---------------------------------------------------------
    def test_revision_increments_on_transitions(self):
        """Revision increments on each lifecycle transition."""
        tid = self.scheduler.enqueue({"target": "agent-1"})
        self.assertEqual(self.scheduler.get_revision(tid), 0)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.scheduler.dequeue())
        loop.close()
        self.assertEqual(self.scheduler.get_revision(tid), 1)
        self.scheduler.complete(tid)
        self.assertEqual(self.scheduler.get_revision(tid), 2)

    # -- get_state / get_revision on unknown task ---------------------------------
    def test_get_state_unknown_task(self):
        self.assertIsNone(self.scheduler.get_state("nonexistent"))

    def test_get_revision_unknown_task(self):
        self.assertIsNone(self.scheduler.get_revision("nonexistent"))


if __name__ == "__main__":
    unittest.main()
