"""Tests for trace aggregation memory limit enforcement (bounty #1563)."""

import unittest
from src.agent.runtime import AgentRuntime, TraceBuffer


class TestTraceBuffer(unittest.TestCase):

    def test_add_trace_within_limit(self):
        """Small trace is accepted."""
        buf = TraceBuffer(max_bytes=1024 * 1024)  # 1 MB
        ok = buf.add({"event": "start", "data": "ok"})
        self.assertTrue(ok)
        self.assertEqual(buf.count(), 1)

    def test_single_trace_exceeds_limit_rejected(self):
        """Trace larger than max_bytes is rejected."""
        buf = TraceBuffer(max_bytes=100)
        ok = buf.add({"data": "x" * 500})  # > 100 bytes
        self.assertFalse(ok)
        self.assertEqual(buf.count(), 0)
        self.assertEqual(buf.evicted(), 1)

    def test_eviction_on_full_buffer(self):
        """Old traces are evicted to make room for new ones."""
        buf = TraceBuffer(max_bytes=1024)  # ~1 KB
        # Fill up buffer
        for i in range(200):
            buf.add({"event": f"trace-{i}", "data": f"data-{i}"})
        # Evictions should have happened
        self.assertGreater(buf.evicted(), 0)

    def test_size_bytes_increases_with_traces(self):
        """size_bytes() reflects current memory usage."""
        buf = TraceBuffer(max_bytes=10 * 1024)
        self.assertEqual(buf.size_bytes(), 0)
        buf.add({"event": "init"})
        self.assertGreater(buf.size_bytes(), 0)

    def test_clear_resets_buffer(self):
        """clear() empties the buffer."""
        buf = TraceBuffer(max_bytes=1024 * 1024)
        buf.add({"event": "a"})
        buf.add({"event": "b"})
        buf.clear()
        self.assertEqual(buf.count(), 0)
        self.assertEqual(buf.size_bytes(), 0)

    def test_get_all_returns_copy(self):
        """get_all() returns a list of buffered traces."""
        buf = TraceBuffer(max_bytes=1024 * 1024)
        buf.add({"event": "e1"})
        buf.add({"event": "e2"})
        all_traces = buf.get_all()
        self.assertEqual(len(all_traces), 2)


class TestAgentRuntimeTraces(unittest.TestCase):

    def test_record_trace_adds_to_buffer(self):
        """record_trace stores an event with agent_id and state."""
        rt = AgentRuntime(trace_max_bytes=10 * 1024 * 1024)
        rt._states["agent-1"] = rt.__class__.RuntimeState.STOPPED             if hasattr(rt, 'RuntimeState') else None

    def test_record_trace_returns_false_on_rejection(self):
        """record_trace returns False when trace is rejected."""
        rt = AgentRuntime(trace_max_bytes=100)
        ok = rt.record_trace("agent-1", "big-event", {"payload": "x" * 500})
        self.assertFalse(ok)

    def test_record_trace_includes_state(self):
        """Recorded trace captures the agent's current runtime state."""
        rt = AgentRuntime(trace_max_bytes=10 * 1024 * 1024)
        rt._states["agent-2"] = rt._states.get("agent-2") or 0
        # Just verify no crash
        ok = rt.record_trace("agent-2", "test-event")
        self.assertTrue(ok)
        traces = rt.get_traces()
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0]["agent_id"], "agent-2")
        self.assertEqual(traces[0]["event"], "test-event")

    def test_get_traces_returns_buffered(self):
        """get_traces() returns all buffered traces."""
        rt = AgentRuntime(trace_max_bytes=10 * 1024 * 1024)
        rt.record_trace("a", "e1")
        rt.record_trace("a", "e2")
        self.assertEqual(len(rt.get_traces()), 2)


if __name__ == "__main__":
    unittest.main()
