"""Tests for agent template cloning with role-based access control."""

import pytest
from fastapi.testclient import TestClient

from src.api.server import create_app
from src.agent.registry import AgentRegistry, AgentStatus


@pytest.fixture
def client():
    """Create a fresh test client with a clean registry."""
    app = create_app()
    # Override the routes module's registry with a fresh one for each test
    from src.api import routes
    routes.registry = AgentRegistry()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def source_agent(client):
    """Register a source agent to clone from."""
    from src.api import routes
    agent_id = routes.registry.register(
        "source-agent",
        "worker.processor",
        {"param1": "value1", "param2": 42},
    )
    # Set some metrics on the source
    routes.registry._agents[agent_id]["metrics"] = {
        "tasks_completed": 10,
        "errors": 3,
        "uptime": 3600,
    }
    routes.registry._agents[agent_id]["config_version"] = 5
    return agent_id


def _auth_headers(role="admin", etag='"v1"'):
    return {
        "Authorization": "Bearer test-token",
        "X-Workspace-Role": role,
        "If-Match": etag,
    }


class TestAgentTemplateClone:
    """Test suite for agent template cloning with RBAC."""

    def test_clone_by_admin_succeeds(self, client, source_agent):
        """Admin role should be able to clone an agent."""
        resp = client.post(
            f"/api/v2/agents/{source_agent}/clone?name=cloned-by-admin",
            headers=_auth_headers(role="admin"),
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["name"] == "cloned-by-admin"
        assert data["type"] == "worker.processor"
        assert data["status"] == "pending"
        assert data["config"] == {"param1": "value1", "param2": 42}
        assert "ETag" in resp.headers

    def test_clone_by_writer_succeeds(self, client, source_agent):
        """Writer role should be able to clone an agent."""
        resp = client.post(
            f"/api/v2/agents/{source_agent}/clone?name=cloned-by-writer",
            headers=_auth_headers(role="writer"),
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["name"] == "cloned-by-writer"

    def test_clone_by_reader_forbidden(self, client, source_agent):
        """Reader role should get 403 Forbidden."""
        resp = client.post(
            f"/api/v2/agents/{source_agent}/clone?name=cloned-by-reader",
            headers=_auth_headers(role="reader"),
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"

    def test_clone_missing_role_header(self, client, source_agent):
        """Missing X-Workspace-Role header should get 403."""
        headers = {
            "Authorization": "Bearer test-token",
            "If-Match": '"v1"',
        }
        resp = client.post(
            f"/api/v2/agents/{source_agent}/clone?name=cloned-no-role",
            headers=headers,
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"

    def test_clone_invalid_role_value(self, client, source_agent):
        """Invalid role value should get 403."""
        resp = client.post(
            f"/api/v2/agents/{source_agent}/clone?name=cloned-bad-role",
            headers=_auth_headers(role="superuser"),
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"

    def test_clone_preserves_config_resets_metrics(self, client, source_agent):
        """Clone should preserve config but reset metrics."""
        resp = client.post(
            f"/api/v2/agents/{source_agent}/clone?name=cloned-metrics-test",
            headers=_auth_headers(role="admin"),
        )
        assert resp.status_code == 201
        data = resp.json()

        # Config should be preserved
        assert data["config"] == {"param1": "value1", "param2": 42}

        # Metrics should be reset
        assert data["metrics"]["tasks_completed"] == 0
        assert data["metrics"]["errors"] == 0
        assert data["metrics"]["uptime"] == 0

    def test_clone_has_separate_config_version(self, client, source_agent):
        """Clone should have config_version=1 regardless of source."""
        resp = client.post(
            f"/api/v2/agents/{source_agent}/clone?name=cloned-version-test",
            headers=_auth_headers(role="admin"),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["config_version"] == 1, f"Expected config_version=1, got {data['config_version']}"

        # Source should retain its original config_version
        from src.api import routes
        source = routes.registry.get(source_agent)
        assert source["config_version"] == 5

    def test_clone_nonexistent_agent(self, client):
        """Cloning a nonexistent agent should return 404."""
        resp = client.post(
            "/api/v2/agents/nonexistent-id/clone?name=ghost-clone",
            headers=_auth_headers(role="admin"),
        )
        assert resp.status_code == 404

    def test_clone_missing_if_match(self, client, source_agent):
        """Missing If-Match header should return 428."""
        headers = {
            "Authorization": "Bearer test-token",
            "X-Workspace-Role": "admin",
        }
        resp = client.post(
            f"/api/v2/agents/{source_agent}/clone?name=no-etag-clone",
            headers=headers,
        )
        assert resp.status_code == 428, f"Expected 428, got {resp.status_code}: {resp.text}"


class TestObserverRole:
    """Observer role tests for middleware behavior."""

    def test_observer_can_list_agents(self, client):
        """Observer role should still be able to read (GET requests)."""
        headers = {
            "Authorization": "Bearer test-token",
            "X-Workspace-Role": "observer",
        }
        resp = client.get("/api/v2/agents", headers=headers)
        assert resp.status_code == 200
