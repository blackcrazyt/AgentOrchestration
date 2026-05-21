"""Task Scheduler — Priority-based task queuing and dispatch with state reconciliation.

Bounty #81: reconcile queue and state divergence on partial dispatch failures.
Bounty #1546: retry transient queue failures with jitter.
"""

import asyncio
import heapq
import random
import time
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4


class TaskState(Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    IN_FLIGHT = "in_flight"
    COMPLETED = "completed"
    FAILED = "failed"


class PriorityQueue:
    def __init__(self):
        self._queue = []
        self._counter = 0

    def push(self, item: Any, priority: int = 0) -> None:
        heapq.heappush(self._queue, (-priority, self._counter, item))
        self._counter += 1

    def pop(self) -> Optional[Any]:
        if self._queue:
            return heapq.heappop(self._queue)[2]
        return None

    def peek(self) -> Optional[Any]:
        if self._queue:
            return self._queue[0][2]
        return None

    def __len__(self) -> int:
        return len(self._queue)


class TaskScheduler:
    def __init__(self, backoff_base: float = 0.5, max_backoff: float = 30.0):
        self._queues: Dict[str, PriorityQueue] = {}
        self._scheduled: Dict[str, float] = {}
        self._in_flight: Dict[str, Dict] = {}
        self._states: Dict[str, TaskState] = {}
        self._revisions: Dict[str, int] = {}
        self._retry_counts: Dict[str, int] = {}
        self._next_retry_at: Dict[str, float] = {}
        self._max_retries = 3
        self._backoff_base = backoff_base
        self._max_backoff = max_backoff

    # ---------- public API ----------------------------------------

    def enqueue(self, task: Dict, queue: str = "default", priority: int = 0) -> str:
        task_id = str(uuid4())
        task["id"] = task_id
        task["enqueued_at"] = time.time()
        task["retries"] = 0
        if queue not in self._queues:
            self._queues[queue] = PriorityQueue()
        self._queues[queue].push(task, priority)
        self._states[task_id] = TaskState.PENDING
        self._revisions[task_id] = 0
        return task_id

    def schedule(self, task: Dict, delay: float, queue: str = "default", priority: int = 0) -> str:
        task_id = str(uuid4())
        task["id"] = task_id
        self._scheduled[task_id] = time.time() + delay
        self._states[task_id] = TaskState.PENDING
        self._revisions[task_id] = 0
        return task_id

    async def dequeue(self, queue: str = "default", timeout: float = 1.0) -> Optional[Dict]:
        """Pop highest-priority task with reconcile guard.

        Only PENDING tasks are eligible. Previously dispatched tasks
        are skipped to prevent queue/state divergence from partial failures.
        Tasks scheduled with backoff delay are promoted when their time arrives.
        """
        now = time.time()
        expired = [tid for tid, t in self._scheduled.items() if t <= now]
        for tid in expired:
            task_data = self._scheduled.pop(tid)
            if task_data:
                self.enqueue(task_data, queue)
        if queue not in self._queues or len(self._queues[queue]) == 0:
            return None
        task = self._queues[queue].pop()
        if not task:
            return None
        tid = task["id"]
        # -- reconcile guard --
        if self._states.get(tid, TaskState.PENDING) != TaskState.PENDING:
            return await self.dequeue(queue, timeout)
        # -- backoff guard: don't dispatch before retry window --
        if tid in self._next_retry_at and now < self._next_retry_at[tid]:
            # Not ready yet, push back and try next
            self._queues[queue].push(task, priority=task.get("priority", 0))
            return None
        self._in_flight[tid] = task
        self._states[tid] = TaskState.DISPATCHED
        self._revisions[tid] = self._revisions.get(tid, 0) + 1
        return task

    def complete(self, task_id: str) -> bool:
        if self._states.get(task_id) != TaskState.DISPATCHED:
            return False
        self._in_flight.pop(task_id, None)
        self._states[task_id] = TaskState.COMPLETED
        self._revisions[task_id] = self._revisions.get(task_id, 0) + 1
        # Clean up retry tracking on successful completion
        self._retry_counts.pop(task_id, None)
        self._next_retry_at.pop(task_id, None)
        return True

    def fail(self, task_id: str, queue: str = "default") -> bool:
        if self._states.get(task_id) != TaskState.DISPATCHED:
            return False
        task = self._in_flight.pop(task_id, None)
        if not task:
            return False
        task["retries"] = task.get("retries", 0) + 1
        if task["retries"] < self._max_retries:
            # Calculate jittered backoff delay
            attempt = self._retry_counts.get(task_id, 0) + 1
            self._retry_counts[task_id] = attempt
            base_delay = self._backoff_base * (2 ** (attempt - 1))
            delay = min(base_delay, self._max_backoff)
            jitter = delay * random.uniform(0.5, 1.5)
            delay = max(0.1, jitter)
            self._next_retry_at[task_id] = time.time() + delay
            if queue not in self._queues:
                self._queues[queue] = PriorityQueue()
            self._queues[queue].push(task, priority=task.get("priority", 0))
            self._states[task_id] = TaskState.PENDING
        else:
            self._states[task_id] = TaskState.FAILED
        self._revisions[task_id] = self._revisions.get(task_id, 0) + 1
        return True

    def get_state(self, task_id: str) -> Optional[str]:
        s = self._states.get(task_id)
        return s.value if s else None

    def get_revision(self, task_id: str) -> Optional[int]:
        return self._revisions.get(task_id)

    def get_retry_count(self, task_id: str) -> int:
        """Return the current retry attempt count for a task."""
        return self._retry_counts.get(task_id, 0)

    def get_backoff_remaining(self, task_id: str) -> float:
        """Return seconds until the task is eligible for retry, or 0 if ready."""
        if task_id not in self._next_retry_at:
            return 0.0
        remaining = self._next_retry_at[task_id] - time.time()
        return max(0.0, remaining)
