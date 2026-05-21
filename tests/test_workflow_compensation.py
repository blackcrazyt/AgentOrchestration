"""Tests for workflow rollback and compensation (bounty #68)."""

import unittest
from src.orchestrator.workflow import (
    StepStatus, WorkflowStep, Workflow, WorkflowManager,
)


class TestWorkflowCompensation(unittest.TestCase):

    def setUp(self):
        self.mgr = WorkflowManager()

    def _make_workflow(self, fail_at_step=2):
        """Create a workflow where step N raises."""
        wf = self.mgr.create_workflow("test-wf", "testing rollback")
        for i in range(1, 4):
            if i == fail_at_step:
                handler = lambda: (_ for _ in ()).throw(Exception(f"step-{i}-failed"))
            else:
                handler = lambda i=i: f"result-{i}"
            wf.add_step(WorkflowStep(f"step-{i}", handler))
        return wf

    # ---- execution blocking ----

    def test_execute_fails_midway_re_execute_blocked(self):
        """After partial failure, re-execute must return False."""
        wf = self._make_workflow(fail_at_step=2)
        first = self.mgr.execute_workflow(wf.id)
        self.assertFalse(first)
        self.assertEqual(wf.status, StepStatus.FAILED)

        second = self.mgr.execute_workflow(wf.id)
        self.assertFalse(second, "re-execute must be blocked after failure")

    def test_successful_workflow_can_be_re_executed(self):
        """A successfully completed workflow can be re-executed (no failures)."""
        wf = self._make_workflow(fail_at_step=99)  # all succeed
        ok = self.mgr.execute_workflow(wf.id)
        self.assertTrue(ok)
        # Can re-execute because status is COMPLETED, not FAILED
        ok2 = self.mgr.execute_workflow(wf.id)
        self.assertTrue(ok2)

    # ---- rollback ----

    def test_rollback_after_failure_calls_compensate(self):
        """rollback runs compensate callbacks on completed steps in reverse."""
        called = []

        wf = self.mgr.create_workflow("comp-wf")
        wf.add_step(WorkflowStep("s1", lambda: "ok1", compensate=lambda: called.append("comp-1")))
        wf.add_step(WorkflowStep("s2", lambda: (_ for _ in ()).throw(Exception("boom")),
                                 compensate=lambda: called.append("comp-2")))
        wf.add_step(WorkflowStep("s3", lambda: "never", compensate=lambda: called.append("comp-3")))

        self.assertFalse(self.mgr.execute_workflow(wf.id))
        # Only s1 completed, s2 failed, s3 never ran
        self.mgr.rollback(wf.id)

        self.assertEqual(called, ["comp-1"], "only completed step gets compensate")
        self.assertEqual(wf.status, StepStatus.ROLLED_BACK)

    def test_rollback_sets_rolled_back_status(self):
        """After rollback, all steps are ROLLED_BACK and workflow is ROLLED_BACK."""
        wf = self._make_workflow(fail_at_step=3)
        self.assertFalse(self.mgr.execute_workflow(wf.id))
        self.mgr.rollback(wf.id)

        self.assertEqual(wf.status, StepStatus.ROLLED_BACK)
        for step in wf.steps:
            self.assertEqual(step.status, StepStatus.ROLLED_BACK)

    def test_rollback_on_non_failed_workflow_rejected(self):
        """rollback on RUNNING or COMPLETED workflow returns False."""
        wf = self._make_workflow(fail_at_step=99)
        self.mgr.execute_workflow(wf.id)  # completed
        self.assertFalse(self.mgr.rollback(wf.id))

    def test_compensate_errors_do_not_block_rollback(self):
        """If compensate() raises, rollback continues with remaining steps."""
        called = []

        wf = self.mgr.create_workflow("err-comp-wf")
        wf.add_step(WorkflowStep("s1", lambda: "ok", compensate=lambda: called.append("c1")))
        wf.add_step(WorkflowStep("s2", lambda: "ok",
                                 compensate=lambda: (_ for _ in ()).throw(Exception("comp fail"))))
        wf.add_step(WorkflowStep("s3", lambda: (_ for _ in ()).throw(Exception("boom")),
                                 compensate=lambda: called.append("c3")))

        self.assertFalse(self.mgr.execute_workflow(wf.id))
        result = self.mgr.rollback(wf.id)

        self.assertTrue(result)
        self.assertIn("c1", called, "first compensate should run")
        self.assertEqual(wf.status, StepStatus.ROLLED_BACK)


if __name__ == "__main__":
    unittest.main()
