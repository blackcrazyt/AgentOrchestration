"""Tests for ETag/If-Match optimistic concurrency guard on agent API routes."""

import pytest
from fastapi.testclient import TestClient

from src.api.server import create_app
from src.api.routes import registry


class TestEtagGuard:
    """Test ETag/If-Match concurrency control on agent mutation endpoints."""

    AUTH = {"Authorization": "Bearer test-token"}

    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset registry before each test and create a test app client."""
        registry._agents.clear()
        registry._index.clear()
        self.app = create_app()
        self.client = TestClient(self.app)

    def _hdrs(self, **extra):
        """Merge auth headers with any additional headers."""
        return {**self.AUTH, **extra}

    # ------------------------------------------------------------------
    # GET /agents/{agent_id} — ETag header
    # ------------------------------------------------------------------
    def test_get_returns_etag_header(self):
        """GET /agents/{agent_id} should return an ETag header with config_version."""
        resp = self.client.post(
            "/api/v2/agents",
            params={"name": "get-etag-test", "agent_type": "worker.echo"},
            headers=self.AUTH,
        )
        assert resp.status_code == 200
        agent_id = resp.json()["agent_id"]

        resp = self.client.get(
            f"/api/v2/agents/{agent_id}",
            headers=self.AUTH,
        )
        assert resp.status_code == 200
        assert "etag" in resp.headers
        etag = resp.headers["etag"]
        assert etag == '"1"'  # config_version starts at 1

    # ------------------------------------------------------------------
    # POST /agents (register) — ETag header
    # ------------------------------------------------------------------
    def test_register_returns_etag_header(self):
        """POST /agents should return an ETag header with config_version=1."""
        resp = self.client.post(
            "/api/v2/agents",
            params={"name": "reg-etag-test", "agent_type": "worker.echo"},
            headers=self.AUTH,
        )
        assert resp.status_code == 200
        assert "etag" in resp.headers
        assert resp.headers["etag"] == '"1"'

    # ------------------------------------------------------------------
    # POST /agents/{agent_id}/start — successful with correct ETag
    # ------------------------------------------------------------------
    def test_start_succeeds_with_correct_etag(self):
        """start_agent succeeds when If-Match matches current config_version."""
        resp = self.client.post(
            "/api/v2/agents",
            params={"name": "start-ok", "agent_type": "worker.echo"},
            headers=self.AUTH,
        )
        agent_id = resp.json()["agent_id"]
        etag = resp.headers["etag"]  # "1"

        resp = self.client.post(
            f"/api/v2/agents/{agent_id}/start",
            headers=self._hdrs(**{"If-Match": etag}),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "started"
        assert "etag" in resp.headers
        assert resp.headers["etag"] == '"2"'

    # ------------------------------------------------------------------
    # POST /agents/{agent_id}/start — 412 on stale ETag
    # ------------------------------------------------------------------
    def test_start_412_on_stale_etag(self):
        """start_agent returns 412 when If-Match is outdated."""
        resp = self.client.post(
            "/api/v2/agents",
            params={"name": "stale-test", "agent_type": "worker.echo"},
            headers=self.AUTH,
        )
        agent_id = resp.json()["agent_id"]
        original_etag = resp.headers["etag"]  # "1"

        # First mutation: start (version becomes 2)
        resp = self.client.post(
            f"/api/v2/agents/{agent_id}/start",
            headers=self._hdrs(**{"If-Match": original_etag}),
        )
        assert resp.status_code == 200

        # Second mutation with stale ETag "1"
        resp = self.client.post(
            f"/api/v2/agents/{agent_id}/start",
            headers=self._hdrs(**{"If-Match": original_etag}),
        )
        assert resp.status_code == 412
        assert "Precondition Failed" in resp.json()["detail"]

    # ------------------------------------------------------------------
    # POST /agents/{agent_id}/start — 412 on missing If-Match
    # ------------------------------------------------------------------
    def test_start_412_on_missing_if_match(self):
        """start_agent returns 412 when If-Match header is missing."""
        resp = self.client.post(
            "/api/v2/agents",
            params={"name": "no-etag-test", "agent_type": "worker.echo"},
            headers=self.AUTH,
        )
        agent_id = resp.json()["agent_id"]

        resp = self.client.post(
            f"/api/v2/agents/{agent_id}/start",
            headers=self.AUTH,
        )
        assert resp.status_code == 412
        assert "If-Match header required" in resp.json()["detail"]

    # ------------------------------------------------------------------
    # POST /agents/{agent_id}/stop — successful with correct ETag
    # ------------------------------------------------------------------
    def test_stop_succeeds_with_correct_etag(self):
        """stop_agent succeeds when If-Match matches current config_version."""
        resp = self.client.post(
            "/api/v2/agents",
            params={"name": "stop-ok", "agent_type": "worker.echo"},
            headers=self.AUTH,
        )
        agent_id = resp.json()["agent_id"]
        etag = resp.headers["etag"]  # "1"

        resp = self.client.post(
            f"/api/v2/agents/{agent_id}/stop",
            headers=self._hdrs(**{"If-Match": etag}),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"
        assert resp.headers["etag"] == '"2"'

    # ------------------------------------------------------------------
    # POST /agents/{agent_id}/stop — 412 on stale ETag
    # ------------------------------------------------------------------
    def test_stop_412_on_stale_etag(self):
        """stop_agent returns 412 when If-Match is outdated."""
        resp = self.client.post(
            "/api/v2/agents",
            params={"name": "stop-stale", "agent_type": "worker.echo"},
            headers=self.AUTH,
        )
        agent_id = resp.json()["agent_id"]
        original_etag = resp.headers["etag"]  # "1"

        # First mutation: stop (version becomes 2)
        resp = self.client.post(
            f"/api/v2/agents/{agent_id}/stop",
            headers=self._hdrs(**{"If-Match": original_etag}),
        )
        assert resp.status_code == 200

        # Second mutation with stale ETag "1"
        resp = self.client.post(
            f"/api/v2/agents/{agent_id}/stop",
            headers=self._hdrs(**{"If-Match": original_etag}),
        )
        assert resp.status_code == 412

    # ------------------------------------------------------------------
    # Version increments correctly across multiple updates
    # ------------------------------------------------------------------
    def test_version_increments_across_multiple_updates(self):
        """config_version increments by 1 on every status mutation."""
        resp = self.client.post(
            "/api/v2/agents",
            params={"name": "chain-test", "agent_type": "worker.echo"},
            headers=self.AUTH,
        )
        agent_id = resp.json()["agent_id"]

        # Initial version from GET
        resp = self.client.get(
            f"/api/v2/agents/{agent_id}",
            headers=self.AUTH,
        )
        assert resp.headers["etag"] == '"1"'

        # Mutation 1: start (version 1 -> 2)
        resp = self.client.post(
            f"/api/v2/agents/{agent_id}/start",
            headers=self._hdrs(**{"If-Match": '"1"'}),
        )
        assert resp.status_code == 200
        etag2 = resp.headers["etag"]
        assert etag2 == '"2"'

        # Mutation 2: stop (version 2 -> 3)
        resp = self.client.post(
            f"/api/v2/agents/{agent_id}/stop",
            headers=self._hdrs(**{"If-Match": etag2}),
        )
        assert resp.status_code == 200
        etag3 = resp.headers["etag"]
        assert etag3 == '"3"'

        # Mutation 3: start (version 3 -> 4)
        resp = self.client.post(
            f"/api/v2/agents/{agent_id}/start",
            headers=self._hdrs(**{"If-Match": etag3}),
        )
        assert resp.status_code == 200
        etag4 = resp.headers["etag"]
        assert etag4 == '"4"'

        # Verify GET reflects latest version
        resp = self.client.get(
            f"/api/v2/agents/{agent_id}",
            headers=self.AUTH,
        )
        assert resp.headers["etag"] == '"4"'

    # ------------------------------------------------------------------
    # Edge case: 404 takes priority over 412
    # ------------------------------------------------------------------
    def test_404_on_nonexistent_agent_start(self):
        """start_agent on nonexistent agent returns 404, not 412."""
        resp = self.client.post(
            "/api/v2/agents/nonexistent-id/start",
            headers=self._hdrs(**{"If-Match": '"1"'}),
        )
        assert resp.status_code == 404

    def test_404_on_nonexistent_agent_stop(self):
        """stop_agent on nonexistent agent returns 404, not 412."""
        resp = self.client.post(
            "/api/v2/agents/nonexistent-id/stop",
            headers=self._hdrs(**{"If-Match": '"1"'}),
        )
        assert resp.status_code == 404

    # ------------------------------------------------------------------
    # ETag value has quotes per HTTP spec
    # ------------------------------------------------------------------
    def test_etag_format_is_quoted(self):
        """ETag header value must be a quoted string per RFC 7232."""
        resp = self.client.post(
            "/api/v2/agents",
            params={"name": "fmt-test", "agent_type": "worker.echo"},
            headers=self.AUTH,
        )
        agent_id = resp.json()["agent_id"]

        resp = self.client.get(
            f"/api/v2/agents/{agent_id}",
            headers=self.AUTH,
        )
        etag = resp.headers["etag"]
        assert etag.startswith('"')
        assert etag.endswith('"')
        inner = etag.strip('"')
        assert inner.isdigit()
        assert int(inner) >= 1

    # ------------------------------------------------------------------
    # If-Match accepts unquoted version
    # ------------------------------------------------------------------
    def test_if_match_accepts_unquoted_version(self):
        """If-Match header with unquoted integer also works (lenient)."""
        resp = self.client.post(
            "/api/v2/agents",
            params={"name": "unquoted-test", "agent_type": "worker.echo"},
            headers=self.AUTH,
        )
        agent_id = resp.json()["agent_id"]

        resp = self.client.post(
            f"/api/v2/agents/{agent_id}/start",
            headers=self._hdrs(**{"If-Match": "1"}),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "started"
