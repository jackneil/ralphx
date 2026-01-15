"""Tests for RalphX MCP server."""

import json
import tempfile
from pathlib import Path

import pytest

from ralphx.mcp_server import MCPServer


@pytest.fixture
def workspace_dir(monkeypatch):
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_path = Path(tmpdir)
        monkeypatch.setenv("RALPHX_HOME", str(workspace_path))

        from ralphx.core.workspace import ensure_workspace
        ensure_workspace()

        yield workspace_path


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

    def test_get_tool_definitions(self, server):
        """Test that tool definitions are returned correctly."""
        tools = server._get_tool_definitions()
        assert len(tools) > 0

        tool_names = [t["name"] for t in tools]
        assert "ralphx_list_projects" in tool_names
        assert "ralphx_get_project" in tool_names
        assert "ralphx_list_loops" in tool_names
        assert "ralphx_start_loop" in tool_names
        assert "ralphx_stop_loop" in tool_names
        assert "ralphx_list_items" in tool_names
        assert "ralphx_add_item" in tool_names
        assert "ralphx_update_item" in tool_names

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
        result = server._list_projects()
        assert result == []

    def test_list_projects_with_project(self, server, workspace_dir, project_dir):
        """Test listing projects after adding one."""
        server.manager.add_project(project_dir, name="Test Project")

        result = server._list_projects()
        assert len(result) == 1
        assert result[0]["name"] == "Test Project"

    def test_get_project(self, server, workspace_dir, project_dir):
        """Test getting a specific project."""
        server.manager.add_project(project_dir, name="Test Project")
        projects = server.manager.list_projects()
        slug = projects[0].slug

        result = server._get_project(slug)
        assert result["name"] == "Test Project"
        assert "stats" in result

    def test_get_project_not_found(self, server, workspace_dir):
        """Test getting a non-existent project."""
        with pytest.raises(ValueError, match="not found"):
            server._get_project("nonexistent")

    def test_add_item(self, server, workspace_dir, project_dir):
        """Test adding a work item."""
        server.manager.add_project(project_dir, name="Test Project")
        projects = server.manager.list_projects()
        slug = projects[0].slug

        result = server._add_item(
            slug=slug,
            content="Test item content",
            category="bugs",
            priority=5,
        )

        assert "id" in result
        assert result["message"] == "Item created"

    def test_list_items(self, server, workspace_dir, project_dir):
        """Test listing work items."""
        server.manager.add_project(project_dir, name="Test Project")
        projects = server.manager.list_projects()
        slug = projects[0].slug

        # Add some items
        server._add_item(slug=slug, content="Item 1", category="bugs")
        server._add_item(slug=slug, content="Item 2", category="features")

        result = server._list_items(slug=slug)
        assert result["total"] == 2
        assert len(result["items"]) == 2

    def test_list_items_with_filter(self, server, workspace_dir, project_dir):
        """Test filtering work items."""
        server.manager.add_project(project_dir, name="Test Project")
        projects = server.manager.list_projects()
        slug = projects[0].slug

        server._add_item(slug=slug, content="Bug 1", category="bugs")
        server._add_item(slug=slug, content="Feature 1", category="features")

        result = server._list_items(slug=slug, category="bugs")
        assert result["total"] == 1
        assert result["items"][0]["category"] == "bugs"

    def test_update_item(self, server, workspace_dir, project_dir):
        """Test updating a work item."""
        server.manager.add_project(project_dir, name="Test Project")
        projects = server.manager.list_projects()
        slug = projects[0].slug

        add_result = server._add_item(slug=slug, content="Original")
        item_id = add_result["id"]

        update_result = server._update_item(
            slug=slug,
            item_id=item_id,
            content="Updated",
            status="completed",
        )

        assert update_result["message"] == "Item updated"

        # Verify update
        items = server._list_items(slug=slug)
        item = next(i for i in items["items"] if i["id"] == item_id)
        assert item["content"] == "Updated"
        assert item["status"] == "completed"

    def test_handle_tools_call(self, server, workspace_dir):
        """Test handling a tools/call request."""
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
        assert response["error"]["code"] == -32601


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
