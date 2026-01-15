"""Tests for RalphX workspace management."""

import os
import tempfile
from pathlib import Path

import pytest

from ralphx.core.workspace import (
    DEFAULT_WORKSPACE,
    clean_workspace,
    ensure_loop_directory,
    ensure_project_workspace,
    ensure_workspace,
    get_backups_path,
    get_database_path,
    get_global_guardrails_path,
    get_logs_path,
    get_loop_path,
    get_project_workspace,
    get_workspace_path,
    validate_loop_name,
    workspace_exists,
)


class TestWorkspacePaths:
    """Test workspace path functions."""

    def test_default_workspace_path(self, monkeypatch):
        """Test default workspace path is ~/.ralphx."""
        monkeypatch.delenv("RALPHX_HOME", raising=False)
        path = get_workspace_path()
        assert path == Path.home() / ".ralphx"

    def test_custom_workspace_path(self, monkeypatch):
        """Test RALPHX_HOME environment variable."""
        monkeypatch.setenv("RALPHX_HOME", "/custom/path")
        path = get_workspace_path()
        assert path == Path("/custom/path")

    def test_database_path(self, monkeypatch):
        """Test database path."""
        monkeypatch.setenv("RALPHX_HOME", "/custom")
        path = get_database_path()
        assert path == Path("/custom/ralphx.db")

    def test_global_guardrails_path(self, monkeypatch):
        """Test global guardrails path."""
        monkeypatch.setenv("RALPHX_HOME", "/custom")
        path = get_global_guardrails_path()
        assert path == Path("/custom/guardrails")

    def test_logs_path(self, monkeypatch):
        """Test logs path."""
        monkeypatch.setenv("RALPHX_HOME", "/custom")
        path = get_logs_path()
        assert path == Path("/custom/logs")

    def test_backups_path(self, monkeypatch):
        """Test backups path."""
        monkeypatch.setenv("RALPHX_HOME", "/custom")
        path = get_backups_path()
        assert path == Path("/custom/backups")

    def test_project_workspace_path(self, monkeypatch):
        """Test project workspace path."""
        monkeypatch.setenv("RALPHX_HOME", "/custom")
        path = get_project_workspace("my_project")
        assert path == Path("/custom/projects/my_project")


class TestWorkspaceCreation:
    """Test workspace creation functions."""

    def test_ensure_workspace_creates_structure(self, monkeypatch):
        """Test ensure_workspace creates correct directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir) / "ralphx"
            monkeypatch.setenv("RALPHX_HOME", str(workspace_path))

            result = ensure_workspace()

            assert result == workspace_path
            assert workspace_path.exists()
            assert (workspace_path / "projects").exists()
            assert (workspace_path / "guardrails").exists()
            assert (workspace_path / "guardrails/system").exists()
            assert (workspace_path / "guardrails/safety").exists()
            assert (workspace_path / "guardrails/domain").exists()
            assert (workspace_path / "guardrails/output").exists()
            assert (workspace_path / "guardrails/custom").exists()
            assert (workspace_path / "templates").exists()
            assert (workspace_path / "logs").exists()
            assert (workspace_path / "backups").exists()

    def test_ensure_workspace_idempotent(self, monkeypatch):
        """Test ensure_workspace can be called multiple times."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir) / "ralphx"
            monkeypatch.setenv("RALPHX_HOME", str(workspace_path))

            ensure_workspace()
            ensure_workspace()  # Should not raise

            assert workspace_path.exists()

    def test_ensure_project_workspace(self, monkeypatch):
        """Test ensure_project_workspace creates project structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir) / "ralphx"
            monkeypatch.setenv("RALPHX_HOME", str(workspace_path))

            result = ensure_project_workspace("test_project")

            assert result == workspace_path / "projects/test_project"
            assert (result / "guardrails").exists()
            assert (result / "prompts").exists()
            assert (result / "sessions").exists()


class TestWorkspaceExists:
    """Test workspace existence check."""

    def test_workspace_exists_false_when_missing(self, monkeypatch):
        """Test workspace_exists returns False when not initialized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir) / "nonexistent"
            monkeypatch.setenv("RALPHX_HOME", str(workspace_path))

            assert workspace_exists() is False

    def test_workspace_exists_true_when_initialized(self, monkeypatch):
        """Test workspace_exists returns True after initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir) / "ralphx"
            monkeypatch.setenv("RALPHX_HOME", str(workspace_path))

            ensure_workspace()
            assert workspace_exists() is True


class TestCleanWorkspace:
    """Test workspace cleanup."""

    def test_clean_workspace_requires_confirm(self, monkeypatch):
        """Test clean_workspace requires confirm=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir) / "ralphx"
            monkeypatch.setenv("RALPHX_HOME", str(workspace_path))

            ensure_workspace()

            with pytest.raises(ValueError, match="confirm=True"):
                clean_workspace(confirm=False)

            # Workspace should still exist
            assert workspace_path.exists()

    def test_clean_workspace_removes_all(self, monkeypatch):
        """Test clean_workspace removes entire workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir) / "ralphx"
            monkeypatch.setenv("RALPHX_HOME", str(workspace_path))

            ensure_workspace()
            ensure_project_workspace("test")
            assert workspace_path.exists()

            clean_workspace(confirm=True)

            assert not workspace_path.exists()


class TestLoopNameValidation:
    """Test loop name validation to prevent path traversal attacks."""

    def test_valid_loop_names(self):
        """Test valid loop names are accepted."""
        valid_names = ["planning", "implementation", "my_loop", "loop-1", "TestLoop123"]
        for name in valid_names:
            # Should not raise
            validate_loop_name(name)

    def test_empty_loop_name_rejected(self):
        """Test empty loop name is rejected."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_loop_name("")

    def test_path_traversal_rejected(self):
        """Test path traversal attempts are rejected."""
        invalid_names = [
            "../evil",
            "..\\evil",
            "foo/../bar",
            "foo/bar",
            "foo\\bar",
            "/absolute/path",
        ]
        for name in invalid_names:
            with pytest.raises(ValueError, match="Invalid loop name"):
                validate_loop_name(name)

    def test_special_characters_rejected(self):
        """Test special characters in loop names are rejected."""
        invalid_names = [
            "loop name",  # Space
            "loop@name",  # @
            "loop.name",  # Dot (could be used in attacks)
            "loop;name",  # Semicolon
        ]
        for name in invalid_names:
            with pytest.raises(ValueError, match="Invalid loop name"):
                validate_loop_name(name)

    def test_long_loop_name_rejected(self):
        """Test excessively long loop names are rejected."""
        long_name = "a" * 101
        with pytest.raises(ValueError, match="too long"):
            validate_loop_name(long_name)

    def test_get_loop_path_validates(self):
        """Test get_loop_path validates loop name before constructing path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Valid name should work
            path = get_loop_path(tmpdir, "valid_loop")
            assert "valid_loop" in str(path)

            # Invalid name should raise
            with pytest.raises(ValueError):
                get_loop_path(tmpdir, "../escape")

    def test_ensure_loop_directory_validates(self):
        """Test ensure_loop_directory validates loop name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Invalid name should raise before creating any directories
            with pytest.raises(ValueError):
                ensure_loop_directory(tmpdir, "../../escape")
