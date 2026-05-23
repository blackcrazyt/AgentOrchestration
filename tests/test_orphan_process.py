"""Tests for orphaned subprocess cancellation (bounty #2974)."""

import unittest
import subprocess
from src.agent.runtime import AgentRuntime, RuntimeState


class TestOrphanedProcessCancellation(unittest.TestCase):

    def setUp(self):
        self.rt = AgentRuntime()

    def test_get_orphaned_count_zero_initially(self):
        self.assertEqual(self.rt.get_orphaned_count(), 0)

    def test_cancel_orphaned_returns_empty_for_no_running(self):
        cancelled = self.rt.cancel_orphaned(timeout=60)
        self.assertEqual(cancelled, [])

    def test_orphaned_count_increases_with_running_process(self):
        self.rt._states["agent-1"] = RuntimeState.RUNNING
        # Simulate a running process
        self.rt._processes["agent-1"] = subprocess.Popen(["timeout", "300"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        cnt = self.rt.get_orphaned_count()
        self.rt._processes["agent-1"].kill()
        self.rt._processes["agent-1"].wait()
        self.assertEqual(cnt, 1)

    def test_crash_detection_marks_crashed(self):
        self.rt._states["agent-dead"] = RuntimeState.RUNNING
        # Create process then immediately kill it
        self.rt._processes["agent-dead"] = subprocess.Popen(["echo", "hello"], stdout=subprocess.PIPE)
        self.rt._processes["agent-dead"].wait()
        self.rt.cancel_orphaned()
        self.assertEqual(self.rt._states["agent-dead"], RuntimeState.CRASHED)

    def test_cancel_orphaned_sets_stopped(self):
        self.rt._states["agent-run"] = RuntimeState.RUNNING
        self.rt._processes["agent-run"] = subprocess.Popen(["timeout", "30"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        cancelled = self.rt.cancel_orphaned(timeout=0.1)
        self.rt._processes["agent-run"].wait()
        self.assertIn("agent-run", cancelled)
        self.assertEqual(self.rt._states["agent-run"], RuntimeState.STOPPED)

    def test_is_running_detects_live_process(self):
        self.rt._processes["live"] = subprocess.Popen(["timeout", "60"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertTrue(self.rt.is_running("live"))
        self.rt._processes["live"].kill()
        self.rt._processes["live"].wait()

    def test_is_running_false_for_dead_process(self):
        self.rt._processes["dead"] = subprocess.Popen(["echo", "done"], stdout=subprocess.PIPE)
        self.rt._processes["dead"].wait()
        self.assertFalse(self.rt.is_running("dead"))


if __name__ == "__main__":
    unittest.main()
