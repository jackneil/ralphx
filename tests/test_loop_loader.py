"""Tests for RalphX loop configuration management."""

import tempfile
from pathlib import Path

import pytest

from ralphx.core.project_db import ProjectDatabase
from ralphx.core.loop import LoopLoader, LoopValidationError
from ralphx.models import Project


VALID_LOOP_YAML = """
name: research
display_name: "Research Loop"
type: generator

modes:
  turbo:
    description: "Fast extraction"
    timeout: 180
    model: sonnet
    tools: []
    prompt_template: prompts/turbo.md
  deep:
    description: "Thorough research"
    timeout: 900
    model: opus
    tools: [WebSearch, WebFetch]
    prompt_template: prompts/deep.md

mode_selection:
  strategy: weighted_random
  weights:
    turbo: 85
    deep: 15

limits:
  max_iterations: 100
  max_consecutive_errors: 5
"""

MINIMAL_LOOP_YAML = """
name: simple
display_name: "Simple Loop"
type: generator

modes:
  default:
    timeout: 300
    model: sonnet
    prompt_template: prompts/default.md

mode_selection:
  strategy: fixed
  fixed_mode: default
"""

INVALID_LOOP_YAML = """
name: INVALID  # uppercase not allowed
display_name: "Test"
type: generator

modes:
  default:
    timeout: 300
    model: sonnet
    prompt_template: prompts/default.md

mode_selection:
  strategy: fixed
  fixed_mode: default
"""


@pytest.fixture
def loader():
    """Create a LoopLoader with in-memory database and workflow context."""
    db = ProjectDatabase(":memory:")

    # Create workflow context for loop registration
    workflow_id = "wf-loader-test"
    db.create_workflow(
        id=workflow_id,
        name="Loader Test Workflow",
        status="active"
    )
    step = db.create_workflow_step(
        workflow_id=workflow_id,
        step_number=1,
        name="Test Step",
        step_type="autonomous",
        status="pending"
    )
    # Store workflow context for tests
    db._test_workflow_id = workflow_id
    db._test_step_id = step["id"]

    yield LoopLoader(db=db)
    db.close()


@pytest.fixture
def project_dir():
    """Create a temporary project directory with prompt templates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        prompts_dir = project_path / "prompts"
        prompts_dir.mkdir()

        # Create prompt templates
        (prompts_dir / "turbo.md").write_text("Turbo mode prompt")
        (prompts_dir / "deep.md").write_text("Deep mode prompt")
        (prompts_dir / "default.md").write_text("Default prompt")

        yield project_path


class TestLoopLoader:
    """Test LoopLoader functionality."""

    def test_load_from_string(self, loader):
        """Test loading from YAML string."""
        config = loader.load_from_string(VALID_LOOP_YAML)
        assert config.name == "research"
        assert len(config.modes) == 2

    def test_load_from_file(self, loader, project_dir):
        """Test loading from YAML file."""
        yaml_path = project_dir / "research.yaml"
        yaml_path.write_text(VALID_LOOP_YAML)

        config = loader.load_from_file(yaml_path, project_dir)
        assert config.name == "research"

    def test_load_file_not_found(self, loader):
        """Test error when file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            loader.load_from_file(Path("/nonexistent/file.yaml"))

    def test_validate_invalid_yaml(self, loader):
        """Test error on invalid YAML syntax."""
        with pytest.raises(LoopValidationError, match="Invalid YAML"):
            loader.load_from_string("not: valid: yaml: syntax:")

    def test_validate_invalid_name(self, loader):
        """Test error on invalid loop name."""
        with pytest.raises(LoopValidationError) as exc:
            loader.load_from_string(INVALID_LOOP_YAML)
        assert len(exc.value.errors) > 0

    def test_validate_checks_prompt_templates(self, loader, project_dir):
        """Test validation checks prompt template files exist."""
        yaml_content = """
name: test
display_name: "Test"
type: generator
modes:
  default:
    timeout: 300
    model: sonnet
    prompt_template: prompts/nonexistent.md
mode_selection:
  strategy: fixed
  fixed_mode: default
"""
        with pytest.raises(LoopValidationError) as exc:
            loader.load_from_string(yaml_content, project_path=project_dir)
        assert "File not found" in str(exc.value.errors)

    def test_validate_without_file_checks(self, loader):
        """Test validation can skip file existence checks."""
        yaml_content = """
name: test
display_name: "Test"
type: generator
modes:
  default:
    timeout: 300
    model: sonnet
    prompt_template: prompts/nonexistent.md
mode_selection:
  strategy: fixed
  fixed_mode: default
"""
        # Should not raise when project_path is None
        config = loader.load_from_string(yaml_content, project_path=None)
        assert config.name == "test"

    def test_register_loop(self, loader, project_dir):
        """Test registering a loop in the database."""
        config = loader.load_from_string(MINIMAL_LOOP_YAML)

        loop_id = loader.register_loop(
            config,
            workflow_id=loader.db._test_workflow_id,
            step_id=loader.db._test_step_id,
        )
        assert loop_id is not None

        # Should be retrievable (no project_id needed with ProjectDatabase)
        retrieved = loader.get_loop("simple")
        assert retrieved is not None
        assert retrieved.name == "simple"

    def test_register_loop_update(self, loader, project_dir):
        """Test updating an existing loop."""
        config = loader.load_from_string(MINIMAL_LOOP_YAML)

        # First registration
        first_id = loader.register_loop(
            config,
            workflow_id=loader.db._test_workflow_id,
            step_id=loader.db._test_step_id,
        )

        # Update
        second_id = loader.register_loop(
            config,
            workflow_id=loader.db._test_workflow_id,
            step_id=loader.db._test_step_id,
        )

        assert first_id == second_id  # Same ID

    def test_list_loops(self, loader, project_dir):
        """Test listing loops."""
        # Initially empty
        assert len(loader.list_loops()) == 0

        # Add loops
        config1 = loader.load_from_string(MINIMAL_LOOP_YAML)
        config2 = loader.load_from_string(VALID_LOOP_YAML)
        loader.register_loop(
            config1,
            workflow_id=loader.db._test_workflow_id,
            step_id=loader.db._test_step_id,
        )
        loader.register_loop(
            config2,
            workflow_id=loader.db._test_workflow_id,
            step_id=loader.db._test_step_id,
        )

        loops = loader.list_loops()
        assert len(loops) == 2

    def test_delete_loop(self, loader, project_dir):
        """Test deleting a loop."""
        config = loader.load_from_string(MINIMAL_LOOP_YAML)
        loader.register_loop(
            config,
            workflow_id=loader.db._test_workflow_id,
            step_id=loader.db._test_step_id,
        )

        result = loader.delete_loop("simple")
        assert result is True
        assert loader.get_loop("simple") is None

    def test_discover_loops(self, loader, project_dir):
        """Test discovering loop files in a project."""
        # Create loop directories and files
        loops_dir = project_dir / "loops"
        loops_dir.mkdir()
        (loops_dir / "research.yaml").write_text(VALID_LOOP_YAML)
        (loops_dir / "implement.yml").write_text(MINIMAL_LOOP_YAML)

        # Also create .loop.yaml file in root
        (project_dir / "custom.loop.yaml").write_text(MINIMAL_LOOP_YAML)

        discovered = loader.discover_loops(project_dir)
        assert len(discovered) == 3

    def test_sync_loops(self, loader, project_dir):
        """Test syncing loops from files to database."""
        # Create loop files
        loops_dir = project_dir / "loops"
        loops_dir.mkdir()
        (loops_dir / "research.yaml").write_text(VALID_LOOP_YAML)

        project = Project(
            id="proj-123",
            slug="test",
            name="Test",
            path=project_dir,
        )

        result = loader.sync_loops(
            project,
            workflow_id=loader.db._test_workflow_id,
            step_id=loader.db._test_step_id,
        )
        assert result["added"] == 1
        assert result["updated"] == 0
        assert result["removed"] == 0

        # Sync again should update
        result = loader.sync_loops(
            project,
            workflow_id=loader.db._test_workflow_id,
            step_id=loader.db._test_step_id,
        )
        assert result["added"] == 0
        assert result["updated"] == 1

    def test_sync_removes_deleted_loops(self, loader, project_dir):
        """Test sync removes loops when files are deleted."""
        loops_dir = project_dir / "loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "research.yaml"
        loop_file.write_text(VALID_LOOP_YAML)

        project = Project(
            id="proj-123",
            slug="test",
            name="Test",
            path=project_dir,
        )

        # First sync
        loader.sync_loops(
            project,
            workflow_id=loader.db._test_workflow_id,
            step_id=loader.db._test_step_id,
        )
        assert len(loader.list_loops()) == 1

        # Delete file and sync again
        loop_file.unlink()
        result = loader.sync_loops(
            project,
            workflow_id=loader.db._test_workflow_id,
            step_id=loader.db._test_step_id,
        )
        assert result["removed"] == 1
        assert len(loader.list_loops()) == 0


class TestLoopLoaderCLI:
    """Test loop CLI commands."""

    def test_validate_command_valid(self, project_dir):
        """Test validate command with valid file."""
        from typer.testing import CliRunner
        from ralphx.cli import app

        yaml_path = project_dir / "research.yaml"
        yaml_path.write_text(VALID_LOOP_YAML)

        runner = CliRunner()
        result = runner.invoke(app, ["validate", str(yaml_path)])
        assert result.exit_code == 0
        assert "Valid" in result.stdout

    def test_validate_command_invalid(self, project_dir):
        """Test validate command with invalid file."""
        from typer.testing import CliRunner
        from ralphx.cli import app

        yaml_path = project_dir / "invalid.yaml"
        yaml_path.write_text(INVALID_LOOP_YAML)

        runner = CliRunner()
        result = runner.invoke(app, ["validate", str(yaml_path), "--no-check-files"])
        assert result.exit_code == 1
        assert "Invalid" in result.stdout

    def test_loops_list_empty(self, project_dir, monkeypatch):
        """Test loops list with no loops."""
        from typer.testing import CliRunner
        from ralphx.cli import app

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("RALPHX_HOME", str(Path(tmpdir) / "ralphx"))

            runner = CliRunner()
            # Add a project first
            runner.invoke(app, ["add", str(project_dir), "--name", "Test"])
            result = runner.invoke(app, ["loops", "list", "--project", "test"])
            assert result.exit_code == 0
            assert "No loops" in result.stdout

    @pytest.mark.skip(reason="CLI loops sync requires workflow context - needs workflow-first CLI update")
    def test_loops_sync_and_list(self, project_dir, monkeypatch):
        """Test syncing and listing loops."""
        from typer.testing import CliRunner
        from ralphx.cli import app

        # Create loop file
        loops_dir = project_dir / "loops"
        loops_dir.mkdir()
        (loops_dir / "research.yaml").write_text(VALID_LOOP_YAML)

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("RALPHX_HOME", str(Path(tmpdir) / "ralphx"))

            runner = CliRunner()
            runner.invoke(app, ["add", str(project_dir), "--name", "Test"])

            # Sync
            result = runner.invoke(app, ["loops", "sync", "--project", "test"])
            assert result.exit_code == 0
            assert "Added: 1" in result.stdout

            # List
            result = runner.invoke(app, ["loops", "list", "--project", "test"])
            assert result.exit_code == 0
            assert "research" in result.stdout

    @pytest.mark.skip(reason="CLI loops sync requires workflow context - needs workflow-first CLI update")
    def test_loops_show(self, project_dir, monkeypatch):
        """Test showing loop details."""
        from typer.testing import CliRunner
        from ralphx.cli import app

        # Create loop file
        loops_dir = project_dir / "loops"
        loops_dir.mkdir()
        (loops_dir / "research.yaml").write_text(VALID_LOOP_YAML)

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("RALPHX_HOME", str(Path(tmpdir) / "ralphx"))

            runner = CliRunner()
            runner.invoke(app, ["add", str(project_dir), "--name", "Test"])
            runner.invoke(app, ["loops", "sync", "--project", "test"])

            result = runner.invoke(app, ["loops", "show", "research", "--project", "test"])
            assert result.exit_code == 0
            assert "Research Loop" in result.stdout
            assert "turbo" in result.stdout
            assert "deep" in result.stdout
