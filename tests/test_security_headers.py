"""Tests for security headers on all responses including errors (bounty #1728)."""

import unittest
from fastapi.testclient import TestClient
from src.api.server import create_app


class TestSecurityHeaders(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)

    # -- normal responses --
    def test_health_endpoint_has_security_headers(self):
        """Normal 200 response gets security headers."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(resp.headers.get("X-Frame-Options"), "DENY")

    def test_api_endpoint_has_security_headers(self):
        """API 200 response gets security headers."""
        resp = self.client.get("/api/v2/agents/count")
        self.assertIn(resp.status_code, [200, 401])
        self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")

    # -- 401 responses --
    def test_unauthorized_response_has_security_headers(self):
        """401 error response still gets security headers."""
        resp = self.client.get("/api/v2/agents")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(resp.headers.get("X-Frame-Options"), "DENY")

    # -- 404 responses --
    def test_not_found_has_security_headers(self):
        """404 error response still gets security headers."""
        resp = self.client.get("/api/v2/agents/nonexistent-id")
        self.assertIn(resp.status_code, [401, 404])
        self.assertIsNotNone(resp.headers.get("X-Content-Type-Options"))

    # -- 405 responses --
    def test_method_not_allowed_has_security_headers(self):
        """405 error response gets security headers."""
        resp = self.client.patch("/health")
        self.assertEqual(resp.status_code, 405)
        self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")

    # -- all expected headers present --
    def test_all_security_headers_present_on_error(self):
        """All configured security headers are present on error responses."""
        resp = self.client.get("/api/v2/agents", headers={
            "Authorization": "Bearer invalid-token",
        })
        headers = resp.headers
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(headers.get("X-XSS-Protection"), "1; mode=block")
        self.assertEqual(headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")

    # -- XSS header specifically --
    def test_xss_protection_header(self):
        """X-XSS-Protection header is present."""
        resp = self.client.get("/health")
        self.assertEqual(resp.headers.get("X-XSS-Protection"), "1; mode=block")

    # -- Permissions-Policy --
    def test_permissions_policy_header(self):
        """Permissions-Policy header restricts sensitive features."""
        resp = self.client.get("/health")
        policy = resp.headers.get("Permissions-Policy", "")
        self.assertIn("camera=()", policy)


if __name__ == "__main__":
    unittest.main()
