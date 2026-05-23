"""Agent context variable propagation for nested agent calls."""

import contextvars
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Context variables that should be propagated to nested agents
_trace_id = contextvars.ContextVar("trace_id", default="")
_tenant_id = contextvars.ContextVar("tenant_id", default="")
_parent_agent_id = contextvars.ContextVar("parent_agent_id", default="")
_execution_depth = contextvars.ContextVar("execution_depth", default=0)


class AgentContext:
    """Manages context variable propagation across nested agent calls."""

    @staticmethod
    def set_trace(trace_id: str) -> None:
        _trace_id.set(trace_id)

    @staticmethod
    def get_trace() -> str:
        return _trace_id.get()

    @staticmethod
    def set_tenant(tenant_id: str) -> None:
        _tenant_id.set(tenant_id)

    @staticmethod
    def get_tenant() -> str:
        return _tenant_id.get()

    @staticmethod
    def set_parent(agent_id: str) -> None:
        _parent_agent_id.set(agent_id)

    @staticmethod
    def get_parent() -> str:
        return _parent_agent_id.get()

    @staticmethod
    def increment_depth() -> int:
        depth = _execution_depth.get() + 1
        _execution_depth.set(depth)
        return depth

    @staticmethod
    def get_depth() -> int:
        return _execution_depth.get()

    @staticmethod
    def snapshot() -> Dict[str, Any]:
        """Capture current context for propagation to nested calls."""
        return {
            "trace_id": _trace_id.get(),
            "tenant_id": _tenant_id.get(),
            "parent_agent_id": _parent_agent_id.get(),
            "execution_depth": _execution_depth.get(),
        }

    @staticmethod
    def restore(snapshot: Dict[str, Any]) -> None:
        """Restore context from a parent agent snapshot."""
        _trace_id.set(snapshot.get("trace_id", ""))
        _tenant_id.set(snapshot.get("tenant_id", ""))
        _parent_agent_id.set(snapshot.get("parent_agent_id", ""))
        _execution_depth.set(snapshot.get("execution_depth", 0))

    @staticmethod
    def fork_for_child(parent_agent_id: str) -> Dict[str, Any]:
        """Create a child context forked from the current context."""
        ctx = contextvars.copy_context()
        snapshot = AgentContext.snapshot()
        # Update for child
        snapshot["parent_agent_id"] = parent_agent_id
        snapshot["execution_depth"] = snapshot.get("execution_depth", 0) + 1
        return snapshot
