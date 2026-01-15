"""Tests for RalphX CLI."""

import subprocess
import sys

import pytest
from typer.testing import CliRunner

from ralphx import __version__
from ralphx.cli import app

runner = CliRunner()


class TestCLIBasics:
    """Test basic CLI functionality."""

    def test_version(self):
        """Test --version flag."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.stdout

    def test_help(self):
        """Test --help flag."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "RalphX" in result.stdout or "ralphx" in result.stdout

    def test_no_args_shows_help(self):
        """Test that no args shows help (exit code 2 with no_args_is_help=True)."""
        result = runner.invoke(app, [])
        # Typer returns exit code 2 when no_args_is_help=True and no args provided
        assert result.exit_code == 2
        assert "Usage" in result.stdout


class TestProjectCommands:
    """Test project-related commands."""

    def test_add_project_missing_path(self):
        """Test add command with missing path."""
        result = runner.invoke(app, ["add"])
        assert result.exit_code != 0

    def test_projects_list(self):
        """Test projects list command."""
        result = runner.invoke(app, ["projects", "list"])
        assert result.exit_code == 0
        # Output is a table with Slug column header
        assert "Slug" in result.stdout or "No projects" in result.stdout

    def test_remove_project_no_force(self):
        """Test remove without force flag aborts."""
        result = runner.invoke(app, ["remove", "test-project"], input="n\n")
        assert result.exit_code == 1  # Aborted


class TestLoopCommands:
    """Test loop-related commands."""

    def test_loops_list_requires_project(self):
        """Test loops list requires --project flag."""
        result = runner.invoke(app, ["loops", "list"])
        assert result.exit_code != 0


class TestRunCommand:
    """Test run command."""

    def test_run_requires_project(self):
        """Test run command requires --project flag."""
        result = runner.invoke(app, ["run", "test-loop"])
        assert result.exit_code != 0


class TestServeCommand:
    """Test serve command."""

    def test_serve_help(self):
        """Test serve command help."""
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0
        assert "8765" in result.stdout  # Default port in help


class TestDoctorCommand:
    """Test doctor command."""

    def test_doctor_shows_checks(self):
        """Test doctor command shows check list."""
        result = runner.invoke(app, ["doctor"])
        # Exit code 1 if Claude CLI not installed (expected in CI)
        assert result.exit_code in (0, 1)
        assert "Python" in result.stdout
        # Should show summary
        assert "passed" in result.stdout


class TestGuardrailsCommands:
    """Test guardrails-related commands."""

    def test_guardrails_validate_requires_project(self):
        """Test guardrails validate requires --project flag."""
        result = runner.invoke(app, ["guardrails", "validate"])
        assert result.exit_code != 0

    def test_guardrails_list_requires_project(self):
        """Test guardrails list requires --project flag."""
        result = runner.invoke(app, ["guardrails", "list"])
        assert result.exit_code != 0


class TestMCPCommand:
    """Test MCP command."""

    def test_mcp_server_initializes(self):
        """Test MCP command starts and outputs JSON-RPC init message."""
        result = runner.invoke(app, ["mcp"])
        assert result.exit_code == 0
        # MCP server outputs JSON-RPC initialization
        assert "jsonrpc" in result.stdout
        assert "initialized" in result.stdout
