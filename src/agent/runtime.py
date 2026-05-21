"""Agent Runtime — Manages agent process lifecycle with trace memory limits.

Bounty #1563: enforce memory limit on trace aggregation.
"""

import os
import signal
import subprocess
import logging
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class RuntimeState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    CRASHED = "crashed"


class TraceBuffer:
    """Bounded trace aggregation with configurable memory limit.

    Traces are stored as dictionaries. When the buffer is full,
    older traces are evicted to stay within the memory limit.
    """

    # Rough per-trace overhead estimate in bytes (key names + dict overhead)
    TRACE_OVERHEAD_BYTES = 256

    def __init__(self, max_bytes: int = 10 * 1024 * 1024):  # 10 MB default
        self.max_bytes = max_bytes
        self._traces: List[Dict] = []
        self._current_bytes = 0
        self._evicted_count = 0

    def add(self, trace: Dict) -> bool:
        """Add a trace entry. Returns False if rejected due to memory limit."""
        # Estimate trace size: length of string representation as rough proxy
        trace_size = len(repr(trace)) + self.TRACE_OVERHEAD_BYTES

        if trace_size > self.max_bytes:
            logger.warning(f"Single trace ({trace_size} bytes) exceeds max ({self.max_bytes} bytes), rejected")
            self._evicted_count += 1
            return False

        # Evict oldest traces until we have room
        while self._current_bytes + trace_size > self.max_bytes and self._traces:
            old = self._traces.pop(0)
            old_size = len(repr(old)) + self.TRACE_OVERHEAD_BYTES
            self._current_bytes -= old_size
            self._evicted_count += 1

        self._traces.append(trace)
        self._current_bytes += trace_size
        return True

    def get_all(self) -> List[Dict]:
        """Return all buffered traces."""
        return list(self._traces)

    def size_bytes(self) -> int:
        """Current estimated memory usage in bytes."""
        return self._current_bytes

    def count(self) -> int:
        """Number of traces currently buffered."""
        return len(self._traces)

    def evicted(self) -> int:
        """Total number of traces evicted since creation."""
        return self._evicted_count

    def clear(self):
        """Reset the buffer."""
        self._traces.clear()
        self._current_bytes = 0


class AgentRuntime:
    def __init__(self, trace_max_bytes: int = 10 * 1024 * 1024):
        self._processes: Dict[str, subprocess.Popen] = {}
        self._states: Dict[str, RuntimeState] = {}
        self.traces = TraceBuffer(max_bytes=trace_max_bytes)

    def start(self, agent_id: str, command: list, env: Optional[Dict] = None) -> bool:
        if agent_id in self._processes and self._processes[agent_id].poll() is None:
            logger.warning(f"Agent {agent_id} is already running")
            return False

        self._states[agent_id] = RuntimeState.STARTING
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        process_env["AO_AGENT_ID"] = agent_id

        try:
            proc = subprocess.Popen(
                command,
                env=process_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._processes[agent_id] = proc
            self._states[agent_id] = RuntimeState.RUNNING
            logger.info(f"Agent {agent_id} started (PID: {proc.pid})")
            return True
        except Exception as e:
            self._states[agent_id] = RuntimeState.CRASHED
            logger.error(f"Failed to start agent {agent_id}: {e}")
            return False

    def stop(self, agent_id: str, timeout: int = 10) -> bool:
        proc = self._processes.get(agent_id)
        if not proc or proc.poll() is not None:
            return False

        self._states[agent_id] = RuntimeState.STOPPING
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

        self._states[agent_id] = RuntimeState.STOPPED
        logger.info(f"Agent {agent_id} stopped")
        return True

    def get_state(self, agent_id: str) -> RuntimeState:
        proc = self._processes.get(agent_id)
        if proc and proc.poll() is not None:
            self._states[agent_id] = RuntimeState.CRASHED
        return self._states.get(agent_id, RuntimeState.STOPPED)

    def is_running(self, agent_id: str) -> bool:
        proc = self._processes.get(agent_id)
        return proc is not None and proc.poll() is None

    def record_trace(self, agent_id: str, event: str, data: Dict = None) -> bool:
        """Record a trace event for an agent. Returns False if memory limit rejects it."""
        state = self.get_state(agent_id)
        state_str = state.value if hasattr(state, "value") else str(state)
        trace = {
            "agent_id": agent_id,
            "event": event,
            "data": data or {},
            "state": state_str,
        }
        return self.traces.add(trace)

    def get_traces(self) -> List[Dict]:
        """Return all buffered traces."""
        return self.traces.get_all()
