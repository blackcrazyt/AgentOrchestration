"""Batch acknowledgement ownership validation (bounty #2572).

Workers must prove ownership of tasks before acknowledging them in batch.
Cross-worker acknowledgements are rejected and logged.
"""

from typing import Dict, List, Optional, Set


class BatchAckManager:
    """Validates that workers own the tasks they acknowledge in batch."""

    def __init__(self):
        self._assignments: Dict[str, str] = {}  # task_id -> worker_id
        self._acked: Set[str] = set()
        self._rejected: List[Dict] = []

    def assign(self, task_id: str, worker_id: str) -> None:
        """Assign a task to a worker."""
        self._assignments[task_id] = worker_id

    def ack_batch(self, worker_id: str, task_ids: List[str]) -> int:
        """Acknowledge a batch of tasks. Returns count of accepted acks.

        Tasks not owned by this worker are silently rejected and logged.
        Re-acking already-acked tasks is also rejected.
        """
        accepted = 0
        for tid in task_ids:
            owner = self._assignments.get(tid)
            if owner is None:
                self._rejected.append({
                    "task_id": tid, "worker_id": worker_id,
                    "reason": "Task not assigned to any worker",
                })
                continue
            if owner != worker_id:
                self._rejected.append({
                    "task_id": tid, "worker_id": worker_id,
                    "owner": owner,
                    "reason": f"Task belongs to worker '{owner}', not '{worker_id}'",
                })
                continue
            if tid in self._acked:
                self._rejected.append({
                    "task_id": tid, "worker_id": worker_id,
                    "reason": "Task already acknowledged",
                })
                continue
            self._acked.add(tid)
            accepted += 1
        return accepted

    def is_acked(self, task_id: str) -> bool:
        return task_id in self._acked

    def get_rejected(self) -> List[Dict]:
        return list(self._rejected)

    def get_worker_tasks(self, worker_id: str) -> List[str]:
        return [tid for tid, wid in self._assignments.items() if wid == worker_id]
