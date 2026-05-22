"""Orchestration Engine — Core execution and coordination with tenant isolation.

Bounty #1870: validate event tenant ownership on shared event bus.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from src.agent import AgentRegistry, AgentStatus
from src.orchestrator.scheduler import TaskScheduler

logger = logging.getLogger(__name__)


class EventTenantError(Exception):
    """Raised when an event references a tenant that does not own the target agent."""
    pass


class OrchestrationEngine:
    def __init__(self, max_workers: int = 10, agent_timeout: int = 300):
        self.registry = AgentRegistry()
        self.scheduler = TaskScheduler()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.agent_timeout = agent_timeout
        self._running = False
        self._tenant_agents: Dict[str, set] = {}  # tenant_id -> set of agent_ids
        self._agent_tenants: Dict[str, str] = {}  # agent_id -> tenant_id
        self._hooks: Dict[str, List[Callable]] = {
            "pre_execute": [],
            "post_execute": [],
            "on_error": [],
            "on_complete": [],
        }
        self._rejected_events: List[Dict] = []

    # ── tenant management ──

    def register_tenant(self, tenant_id: str) -> None:
        """Register a tenant for event isolation."""
        if tenant_id not in self._tenant_agents:
            self._tenant_agents[tenant_id] = set()

    def assign_agent_to_tenant(self, agent_id: str, tenant_id: str) -> bool:
        """Associate an agent with a tenant for ownership checks."""
        if tenant_id not in self._tenant_agents:
            return False
        self._tenant_agents[tenant_id].add(agent_id)
        self._agent_tenants[agent_id] = tenant_id
        return True

    def validate_event_ownership(self, event: Dict, tenant_id: str) -> bool:
        """Check that the event's target agent belongs to the claimed tenant.

        Returns True if the event is valid for this tenant, False otherwise.
        """
        target_agent = event.get("target_agent", event.get("agent_id"))
        if not target_agent:
            self._rejected_events.append({
                "event": event.get("id", "unknown"),
                "tenant": tenant_id,
                "reason": "Missing target_agent in event",
            })
            return False

        owner = self._agent_tenants.get(target_agent)
        if owner is None:
            self._rejected_events.append({
                "event": event.get("id", "unknown"),
                "tenant": tenant_id,
                "target_agent": target_agent,
                "reason": f"Agent {target_agent} not assigned to any tenant",
            })
            return False

        if owner != tenant_id:
            self._rejected_events.append({
                "event": event.get("id", "unknown"),
                "tenant": tenant_id,
                "target_agent": target_agent,
                "reason": f"Agent {target_agent} belongs to tenant '{owner}', not '{tenant_id}'",
            })
            return False

        return True

    def get_tenant_agents(self, tenant_id: str) -> List[str]:
        """Return all agent IDs owned by a tenant."""
        return list(self._tenant_agents.get(tenant_id, set()))

    def get_agent_tenant(self, agent_id: str) -> Optional[str]:
        """Return the tenant that owns an agent."""
        return self._agent_tenants.get(agent_id)

    def get_rejected_events(self) -> List[Dict]:
        """Return audit trail of rejected events."""
        return list(self._rejected_events)

    # ── hooks ──

    def register_hook(self, event: str, callback: Callable) -> None:
        if event in self._hooks:
            self._hooks[event].append(callback)

    # ── lifecycle ──

    async def start(self) -> None:
        self._running = True
        logger.info("Orchestration engine started")
        while self._running:
            task = await self.scheduler.dequeue()
            if task:
                asyncio.create_task(self._execute_task(task))
            await asyncio.sleep(0.1)

    def stop(self) -> None:
        self._running = False
        logger.info("Orchestration engine stopped")

    # ── task execution ──

    async def _execute_task(self, task: Dict[str, Any]) -> None:
        task_id = task["id"]
        agent_id = task.get("target_agent")
        if not agent_id:
            logger.error(f"Task {task_id} missing target_agent")
            return

        logger.info(f"Executing task {task_id} on agent {agent_id}")

        for hook in self._hooks["pre_execute"]:
            await hook(task)

        try:
            agent = self.registry.get(agent_id)
            if not agent:
                raise ValueError(f"Agent {agent_id} not found")

            self.registry.update_status(agent_id, AgentStatus.RUNNING)
            result = await asyncio.wait_for(
                self._run_agent_task(agent, task),
                timeout=self.agent_timeout,
            )
            self.registry.update_status(agent_id, AgentStatus.PAUSED)

            for hook in self._hooks["post_execute"]:
                await hook(task, result)

            logger.info(f"Task {task_id} completed successfully")

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            for hook in self._hooks["on_error"]:
                await hook(task, e)

    async def _run_agent_task(self, agent: Dict, task: Dict) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self._execute_in_thread,
            agent,
            task,
        )

    def _execute_in_thread(self, agent: Dict, task: Dict) -> Any:
        return {
            "status": "completed",
            "output": f"Task {task['id']} processed by {agent['name']}",
        }
