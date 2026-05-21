"""Regression tests for SDK client base_url normalization (bounty #1196).

Covers: trailing-slash stripping, double-slash prevention, and env-var fallback.
"""

import os
import unittest
from unittest.mock import patch, MagicMock
from urllib.request import Request

from src.sdk.client import OrchestratorClient


class TestBaseUrlNormalization(unittest.TestCase):
    """Ensure OrchestratorClient always produces a canonical URL prefix."""

    def test_noop_for_trailing_slash(self):
        client = OrchestratorClient(base_url="https://api.example.com/")
        self.assertEqual(client.base_url, "https://api.example.com")

    def test_noop_for_no_trailing_slash(self):
        client = OrchestratorClient(base_url="https://api.example.com")
        self.assertEqual(client.base_url, "https://api.example.com")

    def test_double_slash_prevention(self):
        """Monkeypatch urlopen to inspect real Request.full_url.

        This exercises the actual _request URL construction instead of
        mocking it away, so regressions that reintroduce double-slashes
        will be caught (see vultuk's review feedback on #1200).
        """
        client = OrchestratorClient(base_url="https://api.example.com/")
        captured_req: list[Request] = []

        def fake_urlopen(req, *args, **kwargs):
            captured_req.append(req)
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"ok": true}'
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.__exit__.return_value = False
            return mock_resp

        with patch("src.sdk.client.urlopen", fake_urlopen):
            client.register_agent("test", "test")

        self.assertEqual(len(captured_req), 1)
        req = captured_req[0]
        self.assertIsInstance(req, Request)

        full_url = req.full_url
        path_part = full_url.split("://", 1)[1]
        self.assertNotIn("//", path_part,
                         f"Double-slash in URL path: {full_url}")
        self.assertTrue(
            full_url.startswith("https://api.example.com/api/v2"),
            f"Unexpected URL: {full_url}",
        )

    def test_env_var_with_trailing_slash(self):
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
        client = OrchestratorClient(base_url="https://multi.example.com///")
        self.assertEqual(client.base_url, "https://multi.example.com")

    def test_default_url_noop(self):
        client = OrchestratorClient()
        self.assertEqual(client.base_url, "https://api.agent-orchestrator.io")


if __name__ == "__main__":
    unittest.main()
