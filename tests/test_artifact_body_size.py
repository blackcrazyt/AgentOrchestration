"""Tests for artifact upload body size enforcement (bounty #1542)."""

import unittest
from fastapi.testclient import TestClient
from src.api.server import create_app
from src.api.routes import registry


class TestArtifactBodySize(unittest.TestCase):
    """Verify body size enforcement on artifact upload endpoints."""

    def setUp(self):
        """Fresh registry and client for each test."""
        registry._agents.clear()
        registry._index.clear()
        self.app = create_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)
        # Register a test agent
        agent_id = registry.register("test-agent", "worker.processor", {"version": "1.0"})
        self.agent_id = agent_id

    def _auth_headers(self, **extra):
        return {"Authorization": "Bearer test-token", **extra}

    def test_upload_within_limit_succeeds(self):
        """Small payload gets accepted."""
        resp = self.client.post(
            f"/api/v2/agents/{self.agent_id}/artifacts?name=small.log",
            headers=self._auth_headers(**{"Content-Length": "1024"}),
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["artifact_name"], "small.log")
        self.assertEqual(data["size_bytes"], 1024)
        self.assertEqual(data["status"], "accepted")

    def test_upload_over_limit_413(self):
        """Payload exceeding max body size returns 413."""
        resp = self.client.post(
            f"/api/v2/agents/{self.agent_id}/artifacts?name=huge.zip",
            headers=self._auth_headers(**{"Content-Length": str(11 * 1024 * 1024)}),
        )
        self.assertEqual(resp.status_code, 413)

    def test_upload_exactly_at_limit_succeeds(self):
        """Payload exactly at limit is accepted."""
        resp = self.client.post(
            f"/api/v2/agents/{self.agent_id}/artifacts?name=exact.bin",
            headers=self._auth_headers(**{"Content-Length": str(10 * 1024 * 1024)}),
        )
        self.assertEqual(resp.status_code, 200)

    def test_upload_missing_content_length_accepted(self):
        """When Content-Length is missing, forward to route handler."""
        resp = self.client.post(
            f"/api/v2/agents/{self.agent_id}/artifacts?name=no-size.data",
            headers=self._auth_headers(),
        )
        self.assertIn(resp.status_code, (200, 400))

    def test_upload_invalid_content_length_400(self):
        """Non-numeric Content-Length returns 400."""
        resp = self.client.post(
            f"/api/v2/agents/{self.agent_id}/artifacts?name=bad.data",
            headers=self._auth_headers(**{"Content-Length": "abc"}),
        )
        self.assertEqual(resp.status_code, 400)

    def test_upload_nonexistent_agent_404(self):
        """404 for non-existent agent, not 413."""
        resp = self.client.post(
            "/api/v2/agents/nonexistent/artifacts?name=ghost.file",
            headers=self._auth_headers(**{"Content-Length": "100"}),
        )
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
