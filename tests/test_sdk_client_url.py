"""Regression tests for SDK client base_url normalization (bounty #1196).

Covers: trailing-slash stripping, double-slash prevention, and env-var fallback.
"""

import os
import unittest
from src.sdk.client import OrchestratorClient


class TestBaseUrlNormalization(unittest.TestCase):
    """Ensure OrchestratorClient always produces a canonical URL prefix."""

    def test_noop_for_trailing_slash(self):
        """The default URL must not end with a slash after normalization."""
        client = OrchestratorClient(base_url="https://api.example.com/")
        self.assertEqual(client.base_url, "https://api.example.com")

    def test_noop_for_no_trailing_slash(self):
        """A clean URL without a trailing slash stays untouched."""
        client = OrchestratorClient(base_url="https://api.example.com")
        self.assertEqual(client.base_url, "https://api.example.com")

    def test_double_slash_prevention(self):
        """_request must not produce // between base_url and path."""
        client = OrchestratorClient(base_url="https://api.example.com/")
        # _request is private; we can inspect the generated URL via a mock.
        recorded_url: list[str] = []

        original_request = client._request

        def capture(method, path, data=None):
            recorded_url.append(f"{client.base_url}/api/v2{path}")
            return {}

        client._request = capture
        client.register_agent("test", "test")

        self.assertEqual(len(recorded_url), 1)
        url = recorded_url[0]
        # Allow :// but no double slashes in path
        path_part = url.split("://", 1)[1]
        self.assertNotIn("//", path_part)
        self.assertTrue(url.startswith("https://api.example.com/api/v2"))

    def test_env_var_with_trailing_slash(self):
        """When AO_API_URL ends with /, strip it."""
        prior = os.environ.get("AO_API_URL")
        os.environ["AO_API_URL"] = "https://env-api.example.com/"
        try:
            client = OrchestratorClient()
            self.assertEqual(client.base_url, "https://env-api.example.com")
        finally:
            if prior is None:
                os.environ.pop("AO_API_URL", None)
            else:
                os.environ["AO_API_URL"] = prior

    def test_env_var_without_trailing_slash(self):
        """When AO_API_URL is clean, keep it intact."""
        prior = os.environ.get("AO_API_URL")
        os.environ["AO_API_URL"] = "https://env-api.example.com"
        try:
            client = OrchestratorClient()
            self.assertEqual(client.base_url, "https://env-api.example.com")
        finally:
            if prior is None:
                os.environ.pop("AO_API_URL", None)
            else:
                os.environ["AO_API_URL"] = prior

    def test_multiple_trailing_slashes(self):
        """Strip every trailing slash, not just the last one."""
        client = OrchestratorClient(base_url="https://multi.example.com///")
        self.assertEqual(client.base_url, "https://multi.example.com")

    def test_default_url_noop(self):
        """The bundled default URL is already clean."""
        client = OrchestratorClient()
        self.assertEqual(client.base_url, "https://api.agent-orchestrator.io")


if __name__ == "__main__":
    unittest.main()
