"""Tests for RalphX API endpoints."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ralphx.api.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        # Create .ralphx/loops directory for loop configs
        (project_path / ".ralphx" / "loops").mkdir(parents=True)
        yield project_path


@pytest.fixture
def workspace_dir(monkeypatch):
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_path = Path(tmpdir)

        # Use environment variable to set workspace path
        monkeypatch.setenv("RALPHX_HOME", str(workspace_path))

        # Initialize workspace
        from ralphx.core.workspace import ensure_workspace
        ensure_workspace()

        yield workspace_path


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self, client):
        """Test health endpoint returns healthy status."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data


class TestRootEndpoint:
    """Test root API endpoint."""

    def test_root(self, client):
        """Test root endpoint returns API info."""
        response = client.get("/api")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "RalphX API"
        assert "version" in data


class TestProjectEndpoints:
    """Test project CRUD endpoints."""

    def test_list_projects_empty(self, client, workspace_dir):
        """Test listing projects when none exist."""
        response = client.get("/api/projects")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_project(self, client, workspace_dir, project_dir):
        """Test creating a project."""
        response = client.post(
            "/api/projects",
            json={
                "path": str(project_dir),
                "name": "Test Project",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Project"
        assert data["path"] == str(project_dir)
        assert "slug" in data
        assert "id" in data

    def test_create_project_auto_name(self, client, workspace_dir, project_dir):
        """Test creating project with auto-generated name."""
        response = client.post(
            "/api/projects",
            json={"path": str(project_dir)},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == project_dir.name

    def test_create_project_duplicate(self, client, workspace_dir, project_dir):
        """Test creating duplicate project fails."""
        # Create first
        client.post("/api/projects", json={"path": str(project_dir)})

        # Try duplicate
        response = client.post("/api/projects", json={"path": str(project_dir)})
        assert response.status_code == 409

    def test_create_project_invalid_path(self, client, workspace_dir):
        """Test creating project with non-existent path."""
        response = client.post(
            "/api/projects",
            json={"path": "/nonexistent/path"},
        )
        assert response.status_code == 400

    def test_get_project(self, client, workspace_dir, project_dir):
        """Test getting a specific project."""
        # Create project
        create_resp = client.post(
            "/api/projects",
            json={"path": str(project_dir), "name": "Test"},
        )
        slug = create_resp.json()["slug"]

        # Get project
        response = client.get(f"/api/projects/{slug}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test"
        assert "stats" in data

    def test_get_project_not_found(self, client, workspace_dir):
        """Test getting non-existent project."""
        response = client.get("/api/projects/nonexistent")
        assert response.status_code == 404

    def test_delete_project(self, client, workspace_dir, project_dir):
        """Test deleting a project."""
        # Create project
        create_resp = client.post(
            "/api/projects",
            json={"path": str(project_dir)},
        )
        slug = create_resp.json()["slug"]

        # Delete project
        response = client.delete(f"/api/projects/{slug}")
        assert response.status_code == 204

        # Verify deleted
        get_resp = client.get(f"/api/projects/{slug}")
        assert get_resp.status_code == 404

    def test_delete_project_not_found(self, client, workspace_dir):
        """Test deleting non-existent project."""
        response = client.delete("/api/projects/nonexistent")
        assert response.status_code == 404


@pytest.mark.skip(
    reason="TODO(workflow-migration): Legacy loop tests need workflow context. "
    "After workflow-first migration, loops require workflow_id and step_id. "
    "These tests need to be updated to create a workflow first."
)
class TestLoopEndpoints:
    """Test loop management endpoints.

    DEPRECATED: These tests use the legacy standalone loop creation path.
    In the workflow-first architecture, loops must belong to a workflow step.
    Tests need to be updated to create a workflow and step first.
    """

    @pytest.fixture
    def project_with_loop(self, client, workspace_dir, project_dir):
        """Create a project with a loop config."""
        # Create .ralphx/loops directory
        (project_dir / ".ralphx" / "loops").mkdir(parents=True, exist_ok=True)

        # Create prompts directory and template file
        (project_dir / "prompts").mkdir(parents=True, exist_ok=True)
        (project_dir / "prompts" / "test.md").write_text("Test prompt template")

        # Create loop config file
        loop_file = project_dir / ".ralphx" / "loops" / "test.yaml"
        loop_file.write_text("""name: test
display_name: Test Loop
type: generator
modes:
  default:
    model: sonnet
    timeout: 300
    tools: [Read, Glob]
    prompt_template: prompts/test.md
mode_selection:
  strategy: fixed
  fixed_mode: default
limits:
  max_iterations: 10
  max_runtime_seconds: 3600
  max_consecutive_errors: 3
""")

        # Create project
        create_resp = client.post(
            "/api/projects",
            json={"path": str(project_dir), "name": "Test Project"},
        )
        slug = create_resp.json()["slug"]

        # Sync loops
        client.post(f"/api/projects/{slug}/loops/sync")

        return slug, "test"

    def test_list_loops_empty(self, client, workspace_dir, project_dir):
        """Test listing loops when none exist."""
        # Create project without loops
        create_resp = client.post(
            "/api/projects",
            json={"path": str(project_dir)},
        )
        slug = create_resp.json()["slug"]

        response = client.get(f"/api/projects/{slug}/loops")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_loops(self, client, project_with_loop):
        """Test listing loops."""
        slug, _ = project_with_loop

        response = client.get(f"/api/projects/{slug}/loops")
        assert response.status_code == 200
        loops = response.json()
        assert len(loops) == 1
        assert loops[0]["name"] == "test"

    def test_get_loop(self, client, project_with_loop):
        """Test getting a specific loop."""
        slug, loop_name = project_with_loop

        response = client.get(f"/api/projects/{slug}/loops/{loop_name}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test"
        assert data["display_name"] == "Test Loop"
        assert len(data["modes"]) == 1

    def test_get_loop_not_found(self, client, workspace_dir, project_dir):
        """Test getting non-existent loop."""
        # Create project
        create_resp = client.post(
            "/api/projects",
            json={"path": str(project_dir)},
        )
        slug = create_resp.json()["slug"]

        response = client.get(f"/api/projects/{slug}/loops/nonexistent")
        assert response.status_code == 404

    def test_get_loop_status(self, client, project_with_loop):
        """Test getting loop status."""
        slug, loop_name = project_with_loop

        response = client.get(f"/api/projects/{slug}/loops/{loop_name}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["loop_name"] == loop_name
        assert data["is_running"] is False

    def test_sync_loops(self, client, workspace_dir, project_dir):
        """Test syncing loops from files."""
        # Create .ralphx/loops directory
        (project_dir / ".ralphx" / "loops").mkdir(parents=True, exist_ok=True)

        # Create prompts directory and template file
        (project_dir / "prompts").mkdir(parents=True, exist_ok=True)
        (project_dir / "prompts" / "test.md").write_text("Test prompt")

        # Create loop config
        loop_file = project_dir / ".ralphx" / "loops" / "sync_test.yaml"
        loop_file.write_text("""name: sync_test
display_name: Sync Test
type: generator
modes:
  default:
    model: sonnet
    timeout: 300
    prompt_template: prompts/test.md
mode_selection:
  strategy: fixed
  fixed_mode: default
limits:
  max_iterations: 10
  max_runtime_seconds: 3600
  max_consecutive_errors: 3
""")

        # Create project
        create_resp = client.post(
            "/api/projects",
            json={"path": str(project_dir)},
        )
        slug = create_resp.json()["slug"]

        # Sync
        response = client.post(f"/api/projects/{slug}/loops/sync")
        assert response.status_code == 200
        data = response.json()
        assert data["added"] >= 1

    def test_stop_loop_not_running(self, client, project_with_loop):
        """Test stopping a loop that isn't running."""
        slug, loop_name = project_with_loop

        response = client.post(f"/api/projects/{slug}/loops/{loop_name}/stop")
        assert response.status_code == 404

    def test_pause_loop_not_running(self, client, project_with_loop):
        """Test pausing a loop that isn't running."""
        slug, loop_name = project_with_loop

        response = client.post(f"/api/projects/{slug}/loops/{loop_name}/pause")
        assert response.status_code == 404


@pytest.mark.skip(
    reason="TODO(test-infrastructure): Database migration caching issue. "
    "Tests fail due to module-level caching of workspace path across test runs. "
    "The global Database() sees stale schema versions. Requires test isolation fix."
)
class TestItemEndpoints:
    """Test work item CRUD endpoints.

    After workflow-first migration, work items require workflow_id and source_step_id.
    Tests create a workflow and step first to provide this context.

    NOTE: Currently skipped due to test infrastructure issue with database module caching.
    """

    @pytest.fixture
    def project_with_workflow(self, client, workspace_dir, project_dir):
        """Create a project with a workflow and step for item creation."""
        # Create project
        response = client.post(
            "/api/projects",
            json={"path": str(project_dir), "name": "Test Project"},
        )
        slug = response.json()["slug"]

        # Create a workflow
        workflow_resp = client.post(
            f"/api/projects/{slug}/workflows",
            json={"name": "Test Workflow"},
        )
        workflow = workflow_resp.json()
        workflow_id = workflow["id"]

        # Get the first step (workflows should have at least one step)
        steps = workflow.get("steps", [])
        step_id = steps[0]["id"] if steps else None

        # If no step was created, create one
        if step_id is None:
            step_resp = client.post(
                f"/api/projects/{slug}/workflows/{workflow_id}/steps",
                json={"name": "Planning", "step_type": "interactive", "step_number": 1},
            )
            step_id = step_resp.json().get("id")

        return slug, workflow_id, step_id

    def test_list_items_empty(self, client, project_with_workflow):
        """Test listing items when none exist."""
        slug, _, _ = project_with_workflow
        response = client.get(f"/api/projects/{slug}/items")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_create_item(self, client, project_with_workflow):
        """Test creating a work item."""
        slug, workflow_id, step_id = project_with_workflow

        # Skip if we couldn't get a step
        if step_id is None:
            pytest.skip("Could not create workflow step for test")

        response = client.post(
            f"/api/projects/{slug}/items",
            json={
                "content": "Test item",
                "priority": 5,
                "workflow_id": workflow_id,
                "source_step_id": step_id,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["content"] == "Test item"
        assert data["priority"] == 5
        assert data["status"] == "pending"
        assert "id" in data
        assert data["workflow_id"] == workflow_id

    def test_get_item(self, client, project_with_workflow):
        """Test getting a specific item."""
        slug, workflow_id, step_id = project_with_workflow

        if step_id is None:
            pytest.skip("Could not create workflow step for test")

        # Create item
        create_resp = client.post(
            f"/api/projects/{slug}/items",
            json={
                "content": "Get me",
                "workflow_id": workflow_id,
                "source_step_id": step_id,
            },
        )
        item_id = create_resp.json()["id"]

        # Get item
        response = client.get(f"/api/projects/{slug}/items/{item_id}")
        assert response.status_code == 200
        assert response.json()["content"] == "Get me"

    def test_get_item_not_found(self, client, project_with_workflow):
        """Test getting non-existent item."""
        slug, _, _ = project_with_workflow
        response = client.get(f"/api/projects/{slug}/items/nonexistent")
        assert response.status_code == 404

    def test_update_item(self, client, project_slug):
        """Test updating an item."""
        # Create item
        create_resp = client.post(
            f"/api/projects/{project_slug}/items",
            json={"content": "Original"},
        )
        item_id = create_resp.json()["id"]

        # Update item
        response = client.patch(
            f"/api/projects/{project_slug}/items/{item_id}",
            json={"content": "Updated", "status": "completed"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Updated"
        assert data["status"] == "completed"

    def test_update_item_invalid_status(self, client, project_slug):
        """Test updating with invalid status."""
        # Create item
        create_resp = client.post(
            f"/api/projects/{project_slug}/items",
            json={"content": "Test"},
        )
        item_id = create_resp.json()["id"]

        # Try invalid status
        response = client.patch(
            f"/api/projects/{project_slug}/items/{item_id}",
            json={"status": "invalid_status"},
        )
        assert response.status_code == 400

    def test_delete_item(self, client, project_slug):
        """Test deleting an item."""
        # Create item
        create_resp = client.post(
            f"/api/projects/{project_slug}/items",
            json={"content": "Delete me"},
        )
        item_id = create_resp.json()["id"]

        # Delete item
        response = client.delete(f"/api/projects/{project_slug}/items/{item_id}")
        assert response.status_code == 204

        # Verify deleted
        get_resp = client.get(f"/api/projects/{project_slug}/items/{item_id}")
        assert get_resp.status_code == 404

    def test_duplicate_item(self, client, project_slug):
        """Test duplicating an item."""
        # Create item
        create_resp = client.post(
            f"/api/projects/{project_slug}/items",
            json={"content": "Original", "priority": 3, "category": "test"},
        )
        item_id = create_resp.json()["id"]

        # Duplicate
        response = client.post(f"/api/projects/{project_slug}/items/{item_id}/duplicate")
        assert response.status_code == 201
        data = response.json()
        assert data["content"] == "Original"
        assert data["priority"] == 3
        assert data["id"] != item_id

    def test_get_items_stats(self, client, project_slug):
        """Test getting item statistics."""
        # Create some items
        client.post(
            f"/api/projects/{project_slug}/items",
            json={"content": "Item 1", "category": "bugs"},
        )
        client.post(
            f"/api/projects/{project_slug}/items",
            json={"content": "Item 2", "category": "bugs"},
        )
        client.post(
            f"/api/projects/{project_slug}/items",
            json={"content": "Item 3", "category": "features"},
        )

        # Get stats
        response = client.get(f"/api/projects/{project_slug}/items/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["by_category"]["bugs"] == 2
        assert data["by_category"]["features"] == 1

    def test_list_items_with_filter(self, client, project_slug):
        """Test filtering items."""
        # Create items with different categories
        client.post(
            f"/api/projects/{project_slug}/items",
            json={"content": "Bug 1", "category": "bugs"},
        )
        client.post(
            f"/api/projects/{project_slug}/items",
            json={"content": "Feature 1", "category": "features"},
        )

        # Filter by category
        response = client.get(
            f"/api/projects/{project_slug}/items",
            params={"category": "bugs"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["category"] == "bugs"

    def test_list_items_pagination(self, client, project_slug):
        """Test pagination."""
        # Create 5 items
        for i in range(5):
            client.post(
                f"/api/projects/{project_slug}/items",
                json={"content": f"Item {i}"},
            )

        # Get first page
        response = client.get(
            f"/api/projects/{project_slug}/items",
            params={"limit": 2, "offset": 0},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["limit"] == 2
        assert data["offset"] == 0


class TestSessionEndpoints:
    """Test session management endpoints (non-streaming)."""

    @pytest.fixture
    def project_slug(self, client, workspace_dir, project_dir):
        """Create a project and return its slug."""
        response = client.post(
            "/api/projects",
            json={"path": str(project_dir), "name": "Session Test"},
        )
        return response.json()["slug"]

    def test_list_sessions_empty(self, client, project_slug):
        """Test listing sessions when none exist."""
        response = client.get(f"/api/projects/{project_slug}/sessions")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_session_not_found(self, client, project_slug):
        """Test getting non-existent session."""
        response = client.get(
            f"/api/projects/{project_slug}/sessions/00000000-0000-0000-0000-000000000000"
        )
        assert response.status_code == 404

    def test_list_sessions_project_not_found(self, client, workspace_dir):
        """Test listing sessions from non-existent project."""
        response = client.get("/api/projects/nonexistent/sessions")
        assert response.status_code == 404

    def test_stream_loop_project_not_found(self, client, workspace_dir):
        """Test streaming from non-existent project returns 404."""
        response = client.get("/api/projects/nonexistent/loops/test/stream")
        assert response.status_code == 404


class TestTemplateEndpoints:
    """Test template API endpoints."""

    def test_list_templates(self, client):
        """Test listing all templates."""
        response = client.get("/api/templates")
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        templates = data["templates"]
        assert len(templates) >= 1  # At least one template should exist
        # Verify template structure
        for template in templates:
            assert "name" in template
            assert "display_name" in template
            assert "description" in template
            assert "type" in template
            assert "category" in template

    def test_get_template_by_name(self, client):
        """Test getting a specific template."""
        response = client.get("/api/templates/research")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "research"
        assert data["display_name"] == "Research Loop"
        assert "config" in data
        assert "config_yaml" in data
        # Verify config has expected structure
        config = data["config"]
        assert "modes" in config
        assert "limits" in config

    def test_get_template_not_found(self, client):
        """Test getting non-existent template returns 404."""
        response = client.get("/api/templates/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "nonexistent" in data["detail"]

    def test_get_template_yaml(self, client):
        """Test getting template YAML config."""
        response = client.get("/api/templates/research/yaml")
        assert response.status_code == 200
        data = response.json()
        assert "yaml" in data
        yaml_content = data["yaml"]
        assert isinstance(yaml_content, str)
        assert "name:" in yaml_content
        assert "modes:" in yaml_content

    def test_get_template_yaml_not_found(self, client):
        """Test getting YAML for non-existent template returns 404."""
        response = client.get("/api/templates/nonexistent/yaml")
        assert response.status_code == 404

    def test_all_templates_have_valid_config(self, client):
        """Test that all listed templates have retrievable configs."""
        # Get list of templates
        list_response = client.get("/api/templates")
        assert list_response.status_code == 200
        templates = list_response.json()["templates"]

        # Verify each template is retrievable
        for template in templates:
            name = template["name"]
            detail_response = client.get(f"/api/templates/{name}")
            assert detail_response.status_code == 200, f"Failed to get template: {name}"
            yaml_response = client.get(f"/api/templates/{name}/yaml")
            assert yaml_response.status_code == 200, f"Failed to get YAML for: {name}"


class TestErrorHandling:
    """Test API error handling."""

    def test_404_for_unknown_route(self, client):
        """Test 404 for unknown routes."""
        response = client.get("/api/unknown")
        assert response.status_code == 404

    def test_method_not_allowed(self, client):
        """Test method not allowed."""
        response = client.patch("/api/health")
        assert response.status_code == 405
