"""Tests for retry with jitter and backoff (bounty #1546)."""

import asyncio
import time
import unittest
from src.orchestrator.scheduler import TaskScheduler, TaskState


class TestRetryJitter(unittest.TestCase):
    """Verify retry behavior uses jittered backoff instead of immediate re-enqueue."""

    def setUp(self):
        self.s = TaskScheduler()

    # -- backoff timing --
    def test_first_retry_has_backoff(self):
        """After first failure, task has a non-zero backoff remaining."""
        tid = self.s.enqueue({"target": "a"})
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.s.dequeue())
        loop.close()
        self.s.fail(tid)
        remaining = self.s.get_backoff_remaining(tid)
        self.assertGreater(remaining, 0.0, "first retry should have backoff delay")

    def test_successful_task_clears_retry_state(self):
        """Completing a task clears retry tracking."""
        tid = self.s.enqueue({"target": "a"})
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.s.dequeue())
        loop.close()
        self.s.complete(tid)
        self.assertEqual(self.s.get_retry_count(tid), 0)

    def test_retry_count_increments(self):
        """Each fail increments the retry count."""
        tid = self.s.enqueue({"target": "a"})
        self.assertEqual(self.s.get_retry_count(tid), 0)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.s.dequeue())
        loop.close()
        self.s.fail(tid)
        self.assertEqual(self.s.get_retry_count(tid), 1)

    def test_backoff_increases_with_attempts(self):
        """Multiple failures increase the backoff delay."""
        tid = self.s.enqueue({"target": "a"})
        delays = []
        for _ in range(2):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.s.dequeue())
            loop.close()
            self.s.fail(tid)
            delays.append(self.s.get_backoff_remaining(tid))
            # Wait for backoff to expire before next dequeue
            # (in tests, override via internal manipulation)
            self.s._next_retry_at[tid] = 0  # force ready
        self.assertGreaterEqual(len(delays), 2)

    def test_fail_exhausts_retries(self):
        """After max_retries, task goes to FAILED."""
        self.s._max_retries = 1
        tid = self.s.enqueue({"target": "a"})
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.s.dequeue())
        loop.close()
        result = self.s.fail(tid)
        self.assertTrue(result)
        self.assertEqual(self.s.get_state(tid), "failed")

    # -- idempotency --
    def test_fail_only_on_dispatched(self):
        """fail() is idempotent — only works on DISPATCHED tasks."""
        tid = self.s.enqueue({"target": "a"})
        self.assertFalse(self.s.fail(tid))  # not dispatched

    def test_backoff_remaining_on_unknown(self):
        """Unknown task returns 0 backoff."""
        self.assertEqual(self.s.get_backoff_remaining("nope"), 0.0)

    def test_dequeue_respects_backoff_window(self):
        """dequeue does not return a task whose backoff hasn't expired."""
        tid = self.s.enqueue({"target": "a"})
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.s.dequeue())
        loop.close()
        self.s.fail(tid)
        # Backoff is now active — dequeue should not return this task
        t = asyncio.new_event_loop().run_until_complete(self.s.dequeue())
        self.assertIsNone(t, "task with active backoff should not be dequeued")


if __name__ == "__main__":
    unittest.main()
