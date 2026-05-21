"""Workflow Manager — Defines and executes multi-step agent workflows.

Bounty #68: block downstream execution after partial rollback.
"""

from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


class WorkflowStep:
    def __init__(self, name: str, handler: Callable, retries: int = 0,
                 timeout: int = 300, compensate: Optional[Callable] = None):
        self.id = str(uuid4())
        self.name = name
        self.handler = handler
        self.retries = retries
        self.timeout = timeout
        self.compensate = compensate
        self.status = StepStatus.PENDING
        self.result: Any = None
        self.error: Optional[str] = None


class Workflow:
    def __init__(self, name: str, description: str = ""):
        self.id = str(uuid4())
        self.name = name
        self.description = description
        self.steps: List[WorkflowStep] = []
        self._step_map: Dict[str, WorkflowStep] = {}
        self.status = StepStatus.PENDING
        self._compensating = False

    @property
    def compensating(self) -> bool:
        return self._compensating

    def add_step(self, step: WorkflowStep) -> "Workflow":
        self.steps.append(step)
        self._step_map[step.id] = step
        return self

    def get_step(self, step_id: str) -> Optional[WorkflowStep]:
        return self._step_map.get(step_id)


class WorkflowManager:
    def __init__(self):
        self._workflows: Dict[str, Workflow] = {}

    def create_workflow(self, name: str, description: str = "") -> Workflow:
        workflow = Workflow(name, description)
        self._workflows[workflow.id] = workflow
        return workflow

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> List[Workflow]:
        return list(self._workflows.values())

    def delete_workflow(self, workflow_id: str) -> bool:
        return self._workflows.pop(workflow_id, None) is not None

    def execute_workflow(self, workflow_id: str) -> bool:
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return False

        # Block execution if workflow is in a terminal or compensating state.
        if workflow.status in (StepStatus.FAILED, StepStatus.ROLLED_BACK):
            return False
        if workflow.compensating:
            return False

        workflow.status = StepStatus.RUNNING
        for step in workflow.steps:
            step.status = StepStatus.RUNNING
            try:
                result = step.handler()
                step.result = result
                step.status = StepStatus.COMPLETED
            except Exception as e:
                step.error = str(e)
                step.status = StepStatus.FAILED
                workflow.status = StepStatus.FAILED
                workflow._compensating = True
                return False

        workflow.status = StepStatus.COMPLETED
        return True

    def rollback(self, workflow_id: str) -> bool:
        """Roll back a failed workflow by calling compensate on completed steps in reverse."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return False
        if workflow.status != StepStatus.FAILED:
            return False

        workflow.status = StepStatus.RUNNING
        # Iterate completed steps in reverse, calling compensate if available.
        for step in reversed(workflow.steps):
            if step.status == StepStatus.COMPLETED and step.compensate is not None:
                try:
                    step.compensate()
                except Exception:
                    pass
            step.status = StepStatus.ROLLED_BACK

        workflow.status = StepStatus.ROLLED_BACK
        workflow._compensating = False
        return True
