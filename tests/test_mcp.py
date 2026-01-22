"""Tests for RalphX MCP server."""

import json
import tempfile
from pathlib import Path

import pytest

from ralphx.mcp import MCPServer
from ralphx.mcp.base import MCPError, PaginatedResult, validate_pagination


@pytest.fixture
def workspace_dir(monkeypatch):
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_path = Path(tmpdir)
        monkeypatch.setenv("RALPHX_HOME", str(workspace_path))

        from ralphx.core.workspace import ensure_workspace
        ensure_workspace()

        # Reset the project manager to use the new workspace
        from ralphx.mcp.tools.projects import reset_manager
        reset_manager()

        yield workspace_path

        # Reset after test too
        reset_manager()


@pytest.fixture
def project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        (project_path / ".ralphx" / "loops").mkdir(parents=True)
        yield project_path


@pytest.fixture
def server(workspace_dir):
    """Create an MCP server instance."""
    return MCPServer()


class TestMCPServer:
    """Test MCP server functionality."""

    def test_tool_count(self, server):
        """Test that all expected tools are registered."""
        tools = server.registry.get_definitions()
        # We have 66 tools across all categories
        assert len(tools) >= 50  # Allow some flexibility

    def test_get_tool_definitions(self, server):
        """Test that tool definitions are returned correctly."""
        tools = server.registry.get_definitions()
        assert len(tools) > 0

        tool_names = [t["name"] for t in tools]
        # Original tools
        assert "ralphx_list_projects" in tool_names
        assert "ralphx_get_project" in tool_names
        assert "ralphx_list_loops" in tool_names
        assert "ralphx_start_loop" in tool_names
        assert "ralphx_stop_loop" in tool_names
        assert "ralphx_list_items" in tool_names
        assert "ralphx_add_item" in tool_names
        assert "ralphx_update_item" in tool_names

        # New tools
        assert "ralphx_add_project" in tool_names
        assert "ralphx_remove_project" in tool_names
        assert "ralphx_check_system_health" in tool_names
        assert "ralphx_diagnose_project" in tool_names
        assert "ralphx_list_runs" in tool_names
        assert "ralphx_get_logs" in tool_names
        assert "ralphx_list_guardrails" in tool_names
        assert "ralphx_check_permissions" in tool_names
        assert "ralphx_import_paste" in tool_names

    def test_handle_initialize(self, server):
        """Test initialize method handling."""
        message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
        }

        response = server._handle_message(message)
        assert response["id"] == 1
        assert "result" in response
        assert response["result"]["serverInfo"]["name"] == "ralphx"

    def test_handle_tools_list(self, server):
        """Test tools/list method handling."""
        # Must initialize first per MCP protocol
        server._handle_message({"jsonrpc": "2.0", "id": 0, "method": "initialize"})

        message = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
        }

        response = server._handle_message(message)
        assert response["id"] == 2
        assert "result" in response
        assert "tools" in response["result"]
        assert len(response["result"]["tools"]) > 0

    def test_list_projects_empty(self, server, workspace_dir):
        """Test listing projects when none exist."""
        result = server.registry.call("ralphx_list_projects")
        assert result["items"] == []
        assert result["total"] == 0
        assert result["has_more"] is False

    def test_list_projects_with_project(self, server, workspace_dir, project_dir):
        """Test listing projects after adding one."""
        from ralphx.mcp.tools.projects import get_manager
        manager = get_manager()
        manager.add_project(project_dir, name="Test Project")

        result = server.registry.call("ralphx_list_projects")
        assert len(result["items"]) == 1
        assert result["items"][0]["name"] == "Test Project"

    def test_get_project(self, server, workspace_dir, project_dir):
        """Test getting a specific project."""
        from ralphx.mcp.tools.projects import get_manager
        manager = get_manager()
        manager.add_project(project_dir, name="Test Project")
        projects = manager.list_projects()
        slug = projects[0].slug

        result = server.registry.call("ralphx_get_project", slug=slug)
        assert result["name"] == "Test Project"
        assert "stats" in result

    def test_get_project_not_found(self, server, workspace_dir):
        """Test getting a non-existent project."""
        with pytest.raises(MCPError) as exc_info:
            server.registry.call("ralphx_get_project", slug="nonexistent")
        assert exc_info.value.error_code == "PROJECT_NOT_FOUND"

    def test_add_and_get_item(self, server, workspace_dir, project_dir):
        """Test adding and getting a work item."""
        from ralphx.mcp.tools.projects import get_manager
        manager = get_manager()
        manager.add_project(project_dir, name="Test Project")
        projects = manager.list_projects()
        slug = projects[0].slug

        # Create a workflow first
        project_db = manager.get_project_db(str(project_dir))
        workflow_id = "wf-test123"
        project_db.create_workflow(
            id=workflow_id,
            name="Test Workflow",
            status="draft",
        )

        # Create a step
        step = project_db.create_workflow_step(
            workflow_id=workflow_id,
            step_number=1,
            name="Step 1",
            step_type="planning",
            status="pending",
        )
        step_id = step["id"]

        # Add item
        result = server.registry.call(
            "ralphx_add_item",
            slug=slug,
            content="Test item content",
            workflow_id=workflow_id,
            source_step_id=step_id,
            category="bugs",
            priority=5,
        )

        assert "id" in result
        assert result["message"] == "Work item created"

        # Get item
        item_result = server.registry.call(
            "ralphx_get_item",
            slug=slug,
            item_id=result["id"],
        )
        assert item_result["content"] == "Test item content"
        assert item_result["category"] == "bugs"
        assert item_result["priority"] == 5

    def test_list_items(self, server, workspace_dir, project_dir):
        """Test listing work items."""
        from ralphx.mcp.tools.projects import get_manager
        manager = get_manager()
        manager.add_project(project_dir, name="Test Project")
        projects = manager.list_projects()
        slug = projects[0].slug

        # Create a workflow and step
        project_db = manager.get_project_db(str(project_dir))
        workflow_id = "wf-test456"
        project_db.create_workflow(
            id=workflow_id,
            name="Test Workflow",
            status="draft",
        )
        step = project_db.create_workflow_step(
            workflow_id=workflow_id,
            step_number=1,
            name="Step 1",
            step_type="planning",
            status="pending",
        )
        step_id = step["id"]

        # Add some items
        server.registry.call(
            "ralphx_add_item",
            slug=slug,
            content="Item 1",
            workflow_id=workflow_id,
            source_step_id=step_id,
            category="bugs",
        )
        server.registry.call(
            "ralphx_add_item",
            slug=slug,
            content="Item 2",
            workflow_id=workflow_id,
            source_step_id=step_id,
            category="features",
        )

        result = server.registry.call("ralphx_list_items", slug=slug)
        assert result["total"] == 2
        assert len(result["items"]) == 2

    def test_list_items_with_filter(self, server, workspace_dir, project_dir):
        """Test filtering work items."""
        from ralphx.mcp.tools.projects import get_manager
        manager = get_manager()
        manager.add_project(project_dir, name="Test Project")
        projects = manager.list_projects()
        slug = projects[0].slug

        # Create a workflow and step
        project_db = manager.get_project_db(str(project_dir))
        workflow_id = "wf-test789"
        project_db.create_workflow(
            id=workflow_id,
            name="Test Workflow",
            status="draft",
        )
        step = project_db.create_workflow_step(
            workflow_id=workflow_id,
            step_number=1,
            name="Step 1",
            step_type="planning",
            status="pending",
        )
        step_id = step["id"]

        server.registry.call(
            "ralphx_add_item",
            slug=slug,
            content="Bug 1",
            workflow_id=workflow_id,
            source_step_id=step_id,
            category="bugs",
        )
        server.registry.call(
            "ralphx_add_item",
            slug=slug,
            content="Feature 1",
            workflow_id=workflow_id,
            source_step_id=step_id,
            category="features",
        )

        result = server.registry.call("ralphx_list_items", slug=slug, category="bugs")
        assert result["total"] == 1
        assert result["items"][0]["category"] == "bugs"

    def test_update_item(self, server, workspace_dir, project_dir):
        """Test updating a work item."""
        from ralphx.mcp.tools.projects import get_manager
        manager = get_manager()
        manager.add_project(project_dir, name="Test Project")
        projects = manager.list_projects()
        slug = projects[0].slug

        # Create a workflow and step
        project_db = manager.get_project_db(str(project_dir))
        workflow_id = "wf-test-update"
        project_db.create_workflow(
            id=workflow_id,
            name="Test Workflow",
            status="draft",
        )
        step = project_db.create_workflow_step(
            workflow_id=workflow_id,
            step_number=1,
            name="Step 1",
            step_type="planning",
            status="pending",
        )
        step_id = step["id"]

        add_result = server.registry.call(
            "ralphx_add_item",
            slug=slug,
            content="Original",
            workflow_id=workflow_id,
            source_step_id=step_id,
        )
        item_id = add_result["id"]

        update_result = server.registry.call(
            "ralphx_update_item",
            slug=slug,
            item_id=item_id,
            content="Updated",
            status="completed",
        )

        assert update_result["message"] == "Work item updated"

        # Verify update
        item = server.registry.call("ralphx_get_item", slug=slug, item_id=item_id)
        assert item["content"] == "Updated"
        assert item["status"] == "completed"

    def test_handle_tools_call(self, server, workspace_dir):
        """Test handling a tools/call request."""
        # Must initialize first per MCP protocol
        server._handle_message({"jsonrpc": "2.0", "id": 0, "method": "initialize"})

        message = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "ralphx_list_projects",
                "arguments": {},
            },
        }

        response = server._handle_message(message)
        assert response["id"] == 3
        assert "result" in response
        assert "content" in response["result"]

    def test_handle_unknown_tool(self, server):
        """Test handling an unknown tool call."""
        # Must initialize first per MCP protocol
        server._handle_message({"jsonrpc": "2.0", "id": 0, "method": "initialize"})

        message = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "unknown_tool",
                "arguments": {},
            },
        }

        response = server._handle_message(message)
        assert "error" in response
        # Per MCP spec: unknown tool is -32602 (Invalid params), not -32601 (Method not found)
        # because tools/call method exists, the tool name is a parameter
        assert response["error"]["code"] == -32602


class TestMCPBasePatterns:
    """Test MCP base patterns and utilities."""

    def test_paginated_result(self):
        """Test PaginatedResult helper."""
        items = [{"id": i} for i in range(10)]
        result = PaginatedResult(items=items, total=100, limit=10, offset=0)

        assert result.has_more is True
        d = result.to_dict()
        assert d["items"] == items
        assert d["total"] == 100
        assert d["has_more"] is True

    def test_paginated_result_no_more(self):
        """Test PaginatedResult when no more items."""
        items = [{"id": i} for i in range(5)]
        result = PaginatedResult(items=items, total=5, limit=10, offset=0)

        assert result.has_more is False

    def test_validate_pagination(self):
        """Test pagination validation."""
        # Normal case
        limit, offset = validate_pagination(50, 10)
        assert limit == 50
        assert offset == 10

        # Defaults
        limit, offset = validate_pagination(None, None)
        assert limit == 100
        assert offset == 0

        # Cap at max
        limit, offset = validate_pagination(1000, 0)
        assert limit == 500

        # Min values
        limit, offset = validate_pagination(0, -5)
        assert limit == 1
        assert offset == 0

    def test_mcp_error(self):
        """Test MCPError class."""
        error = MCPError(
            error_code="TEST_ERROR",
            message="Test error message",
            details={"key": "value"},
        )

        d = error.to_dict()
        assert d["error_code"] == "TEST_ERROR"
        assert d["message"] == "Test error message"
        assert d["details"]["key"] == "value"


class TestNewMCPTools:
    """Test new MCP tools added in the enhancement."""

    def test_check_system_health(self, server, workspace_dir):
        """Test system health check tool."""
        result = server.registry.call("ralphx_check_system_health")

        # Should return a result without errors
        assert isinstance(result, dict)
        # healthy can be True, False, or None (if DoctorCheck not available)
        assert "checks" in result or "message" in result

    def test_diagnose_project(self, server, workspace_dir, project_dir):
        """Test project diagnostics tool."""
        from ralphx.mcp.tools.projects import get_manager
        manager = get_manager()
        manager.add_project(project_dir, name="Test Project")
        projects = manager.list_projects()
        slug = projects[0].slug

        result = server.registry.call("ralphx_diagnose_project", slug=slug)

        assert result["project"]["slug"] == slug
        assert "checks" in result
        assert "summary" in result

    def test_list_stale_runs(self, server, workspace_dir, project_dir):
        """Test listing stale runs."""
        from ralphx.mcp.tools.projects import get_manager
        manager = get_manager()
        manager.add_project(project_dir, name="Test Project")
        projects = manager.list_projects()
        slug = projects[0].slug

        result = server.registry.call("ralphx_list_stale_runs", slug=slug)

        assert "items" in result
        assert "total" in result

    def test_detect_guardrails(self, server, workspace_dir, project_dir):
        """Test guardrail detection."""
        from ralphx.mcp.tools.projects import get_manager
        manager = get_manager()
        manager.add_project(project_dir, name="Test Project")
        projects = manager.list_projects()
        slug = projects[0].slug

        result = server.registry.call("ralphx_detect_guardrails", slug=slug)

        assert "detected" in result
        assert "total" in result

    def test_check_permissions(self, server, workspace_dir, project_dir):
        """Test permission checking."""
        from ralphx.mcp.tools.projects import get_manager
        manager = get_manager()
        manager.add_project(project_dir, name="Test Project")
        projects = manager.list_projects()
        slug = projects[0].slug

        result = server.registry.call("ralphx_check_permissions", slug=slug)

        assert "configured" in result
        assert "available" in result

    def test_list_workflow_templates(self, server, workspace_dir, project_dir):
        """Test listing workflow templates."""
        from ralphx.mcp.tools.projects import get_manager
        manager = get_manager()
        manager.add_project(project_dir, name="Test Project")
        projects = manager.list_projects()
        slug = projects[0].slug

        result = server.registry.call("ralphx_list_workflow_templates", slug=slug)

        assert "templates" in result
        assert isinstance(result["templates"], list)


class TestMCPEdgeCases:
    """Test MCP edge cases and error handling."""

    def test_empty_workflow_no_steps(self, server, workspace_dir, project_dir):
        """Test getting a workflow with no steps."""
        from ralphx.mcp.tools.projects import get_manager
        manager = get_manager()
        manager.add_project(project_dir, name="Test Project")
        projects = manager.list_projects()
        slug = projects[0].slug

        # Create a workflow without steps
        project_db = manager.get_project_db(str(project_dir))
        workflow_id = "wf-empty123"
        project_db.create_workflow(
            id=workflow_id,
            name="Empty Workflow",
            status="draft",
        )

        result = server.registry.call(
            "ralphx_get_workflow",
            slug=slug,
            workflow_id=workflow_id,
        )

        assert result["id"] == workflow_id
        assert result["steps"] == []
        assert result["name"] == "Empty Workflow"

    def test_list_items_with_max_pagination(self, server, workspace_dir, project_dir):
        """Test pagination limits are enforced."""
        from ralphx.mcp.tools.projects import get_manager
        manager = get_manager()
        manager.add_project(project_dir, name="Test Project")
        projects = manager.list_projects()
        slug = projects[0].slug

        # Request with limit above max
        result = server.registry.call(
            "ralphx_list_items",
            slug=slug,
            limit=1000,  # Above max of 500
        )

        # Should be capped at 500
        assert result["limit"] == 500

    def test_diagnose_project_path_serialization(self, server, workspace_dir, project_dir):
        """Test that project path is properly serialized to string."""
        from ralphx.mcp.tools.projects import get_manager
        manager = get_manager()
        manager.add_project(project_dir, name="Test Project")
        projects = manager.list_projects()
        slug = projects[0].slug

        result = server.registry.call("ralphx_diagnose_project", slug=slug)

        # Path should be a string, not a Path object
        assert isinstance(result["project"]["path"], str)

    def test_update_item_no_changes(self, server, workspace_dir, project_dir):
        """Test updating an item with no actual changes."""
        from ralphx.mcp.tools.projects import get_manager
        manager = get_manager()
        manager.add_project(project_dir, name="Test Project")
        projects = manager.list_projects()
        slug = projects[0].slug

        # Create workflow, step, and item
        project_db = manager.get_project_db(str(project_dir))
        workflow_id = "wf-nochange"
        project_db.create_workflow(
            id=workflow_id,
            name="Test Workflow",
            status="draft",
        )
        step = project_db.create_workflow_step(
            workflow_id=workflow_id,
            step_number=1,
            name="Step 1",
            step_type="planning",
            status="pending",
        )

        add_result = server.registry.call(
            "ralphx_add_item",
            slug=slug,
            content="Test content",
            workflow_id=workflow_id,
            source_step_id=step["id"],
        )
        item_id = add_result["id"]

        # Update with no changes
        update_result = server.registry.call(
            "ralphx_update_item",
            slug=slug,
            item_id=item_id,
        )

        assert update_result["message"] == "No changes specified"

    def test_restore_nonexistent_step_raises_error(self, server, workspace_dir, project_dir):
        """Test that restoring a non-existent step raises proper error."""
        from ralphx.mcp.tools.projects import get_manager
        manager = get_manager()
        manager.add_project(project_dir, name="Test Project")
        projects = manager.list_projects()
        slug = projects[0].slug

        with pytest.raises(MCPError) as exc_info:
            server.registry.call(
                "ralphx_restore_workflow_step",
                slug=slug,
                step_id=99999,  # Non-existent
            )
        assert exc_info.value.error_code == "STEP_NOT_FOUND"


class TestMCPCLIIntegration:
    """Test MCP CLI command."""

    def test_mcp_help(self):
        """Test mcp command help."""
        from typer.testing import CliRunner
        from ralphx.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["mcp", "--help"])
        assert result.exit_code == 0
        assert "MCP" in result.stdout or "mcp" in result.stdout
