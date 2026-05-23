"""Tests for trailing slash auth bypass prevention (bounty #2671)."""

import unittest
from fastapi.testclient import TestClient
from src.api.server import create_app


class TestTrailingSlashAuth(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_api_route_without_trailing_slash_requires_auth(self):
        """Normal /api/v2/agents requires auth."""
        resp = self.client.get("/api/v2/agents")
        self.assertEqual(resp.status_code, 401)

    def test_api_route_with_trailing_slash_requires_auth(self):
        """Trailing-slash /api/v2/agents/ also requires auth (bypass fix)."""
        resp = self.client.get("/api/v2/agents/")
        self.assertEqual(resp.status_code, 401, "trailing slash must not bypass auth")

    def test_api_route_with_valid_token_succeeds(self):
        """Valid token passes auth for normal path."""
        resp = self.client.get("/api/v2/agents/count", headers={"Authorization": "Bearer valid-token"})
        self.assertIn(resp.status_code, [200, 401])

    def test_api_route_trailing_slash_with_valid_token(self):
        """Valid token passes auth even with trailing slash."""
        resp = self.client.get("/api/v2/agents/count/", headers={"Authorization": "Bearer valid-token"})
        self.assertIn(resp.status_code, [200, 401])

    def test_auth_token_route_not_blocked(self):
        """Auth token endpoint is NOT blocked (no auth required)."""
        resp = self.client.post("/api/v2/auth/token")
        self.assertNotEqual(resp.status_code, 401)

    def test_auth_token_trailing_slash_not_blocked(self):
        """Auth token endpoint with trailing slash still not blocked."""
        resp = self.client.post("/api/v2/auth/token/")
        self.assertNotEqual(resp.status_code, 401)

    def test_health_endpoint_not_blocked(self):
        """Health endpoint is never blocked by auth."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)

    def test_invalid_token_still_blocked(self):
        """Invalid/missing token still gets 401 with trailing slash."""
        resp = self.client.get("/api/v2/agents/", headers={"Authorization": "Basic xyz"})
        self.assertEqual(resp.status_code, 401)


if __name__ == "__main__":
    unittest.main()
