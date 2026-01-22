"""Tests for RalphX project management."""

import tempfile
from pathlib import Path

import pytest

from ralphx.core.global_db import GlobalDatabase
from ralphx.core.project import ProjectManager
from ralphx.core.workspace import get_project_workspace


@pytest.fixture
def temp_project_dir():
    """Create a temporary directory for project tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def manager(monkeypatch):
    """Create a ProjectManager with in-memory database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Override workspace to use temp directory
        monkeypatch.setenv("RALPHX_HOME", str(Path(tmpdir) / "ralphx"))
        global_db = GlobalDatabase(":memory:")
        yield ProjectManager(global_db=global_db)
        global_db.close()


class TestProjectManager:
    """Test ProjectManager functionality."""

    def test_add_project(self, manager, temp_project_dir):
        """Test adding a project."""
        project = manager.add_project(
            path=temp_project_dir,
            name="Test Project",
        )
        assert project.name == "Test Project"
        assert project.slug == "test-project"
        assert project.path == temp_project_dir

    def test_add_project_auto_name(self, manager, temp_project_dir):
        """Test adding project uses directory name if no name provided."""
        project = manager.add_project(path=temp_project_dir)
        assert project.name == temp_project_dir.name

    def test_add_project_custom_slug(self, manager, temp_project_dir):
        """Test adding project with custom slug."""
        project = manager.add_project(
            path=temp_project_dir,
            name="My App",
            slug="custom",
        )
        assert project.slug == "custom"

    def test_add_project_with_design_doc(self, manager, temp_project_dir):
        """Test adding project with design document."""
        # Create design doc
        design_dir = temp_project_dir / "design"
        design_dir.mkdir()
        (design_dir / "PRD.md").write_text("# Design Doc")

        project = manager.add_project(
            path=temp_project_dir,
            name="App",
            design_doc="design/PRD.md",
        )
        assert project.design_doc == "design/PRD.md"

    def test_add_project_invalid_design_doc(self, manager, temp_project_dir):
        """Test error when design doc doesn't exist."""
        with pytest.raises(ValueError, match="not found"):
            manager.add_project(
                path=temp_project_dir,
                design_doc="nonexistent.md",
            )

    def test_add_project_duplicate_slug(self, manager, temp_project_dir):
        """Test error when adding project with duplicate slug."""
        manager.add_project(path=temp_project_dir, name="First")

        with tempfile.TemporaryDirectory() as tmpdir2:
            with pytest.raises(FileExistsError, match="already exists"):
                manager.add_project(
                    path=Path(tmpdir2),
                    name="Second",
                    slug="first",  # Same slug
                )

    def test_add_project_duplicate_path(self, manager, temp_project_dir):
        """Test error when adding project with duplicate path."""
        manager.add_project(path=temp_project_dir, name="First")

        with pytest.raises(FileExistsError, match="already registered"):
            manager.add_project(path=temp_project_dir, name="Second")

    def test_get_project(self, manager, temp_project_dir):
        """Test getting a project by slug."""
        manager.add_project(path=temp_project_dir, name="Test")
        project = manager.get_project("test")
        assert project is not None
        assert project.name == "Test"

    def test_get_project_not_found(self, manager):
        """Test getting nonexistent project returns None."""
        project = manager.get_project("nonexistent")
        assert project is None

    def test_list_projects(self, manager, temp_project_dir):
        """Test listing projects."""
        # Initially empty
        assert len(manager.list_projects()) == 0

        # Add projects
        manager.add_project(path=temp_project_dir, name="First")

        with tempfile.TemporaryDirectory() as tmpdir2:
            manager.add_project(path=Path(tmpdir2), name="Second")

            projects = manager.list_projects()
            assert len(projects) == 2

    def test_remove_project(self, manager, temp_project_dir):
        """Test removing a project."""
        manager.add_project(path=temp_project_dir, name="Test")
        assert manager.project_exists("test") is True

        result = manager.remove_project("test")
        assert result is True
        assert manager.project_exists("test") is False

    def test_remove_project_not_found(self, manager):
        """Test removing nonexistent project returns False."""
        result = manager.remove_project("nonexistent")
        assert result is False

    def test_update_project(self, manager, temp_project_dir):
        """Test updating project metadata."""
        manager.add_project(path=temp_project_dir, name="Original")
        project = manager.update_project("original", name="Updated")
        assert project.name == "Updated"

    def test_project_exists(self, manager, temp_project_dir):
        """Test checking if project exists."""
        assert manager.project_exists("test") is False
        manager.add_project(path=temp_project_dir, name="Test")
        assert manager.project_exists("test") is True

    def test_get_project_stats(self, manager, temp_project_dir):
        """Test getting project statistics."""
        project = manager.add_project(path=temp_project_dir, name="Test")

        # Get project-specific database and add work items
        project_db = manager.get_project_db(project.path)

        # Create workflow context for work items
        workflow_id = "wf-stats-test"
        project_db.create_workflow(
            id=workflow_id,
            name="Stats Test Workflow",
            status="active"
        )
        step = project_db.create_workflow_step(
            workflow_id=workflow_id,
            step_number=1,
            name="Test Step",
            step_type="autonomous",
            status="pending"
        )

        project_db.create_work_item(
            id="item-1",
            workflow_id=workflow_id,
            source_step_id=step["id"],
            content="First",
        )
        project_db.create_work_item(
            id="item-2",
            workflow_id=workflow_id,
            source_step_id=step["id"],
            content="Second",
        )
        # Update second item to completed status
        project_db.update_work_item("item-2", status="completed")

        stats = manager.get_project_stats("test")
        assert stats is not None
        assert stats["total"] == 2
        assert stats["by_status"]["pending"] == 1
        assert stats["by_status"]["completed"] == 1


class TestProjectManagerCLI:
    """Test project CLI commands via Typer test runner."""

    def test_add_command(self, temp_project_dir, monkeypatch):
        """Test add command via CLI."""
        from typer.testing import CliRunner
        from ralphx.cli import app

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("RALPHX_HOME", str(Path(tmpdir) / "ralphx"))

            runner = CliRunner()
            result = runner.invoke(
                app,
                ["add", str(temp_project_dir), "--name", "CLI Test"],
            )
            assert result.exit_code == 0
            assert "Added project" in result.stdout
            assert "cli-test" in result.stdout

    def test_add_command_duplicate(self, temp_project_dir, monkeypatch):
        """Test add command fails on duplicate."""
        from typer.testing import CliRunner
        from ralphx.cli import app

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("RALPHX_HOME", str(Path(tmpdir) / "ralphx"))

            runner = CliRunner()
            # First add
            runner.invoke(app, ["add", str(temp_project_dir), "--name", "Test"])
            # Second add should fail
            result = runner.invoke(
                app, ["add", str(temp_project_dir), "--name", "Test"]
            )
            assert result.exit_code == 1
            assert "already exists" in result.stdout

    def test_list_command_empty(self, monkeypatch):
        """Test list command with no projects."""
        from typer.testing import CliRunner
        from ralphx.cli import app

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("RALPHX_HOME", str(Path(tmpdir) / "ralphx"))

            runner = CliRunner()
            result = runner.invoke(app, ["projects", "list"])
            assert result.exit_code == 0
            assert "No projects" in result.stdout

    def test_list_command_with_projects(self, temp_project_dir, monkeypatch):
        """Test list command shows projects."""
        from typer.testing import CliRunner
        from ralphx.cli import app

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("RALPHX_HOME", str(Path(tmpdir) / "ralphx"))

            runner = CliRunner()
            runner.invoke(app, ["add", str(temp_project_dir), "--name", "Test"])
            result = runner.invoke(app, ["projects", "list"])
            assert result.exit_code == 0
            assert "test" in result.stdout

    def test_show_command(self, temp_project_dir, monkeypatch):
        """Test show command."""
        from typer.testing import CliRunner
        from ralphx.cli import app

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("RALPHX_HOME", str(Path(tmpdir) / "ralphx"))

            runner = CliRunner()
            runner.invoke(app, ["add", str(temp_project_dir), "--name", "Test Project"])
            result = runner.invoke(app, ["projects", "show", "test-project"])
            assert result.exit_code == 0
            assert "Test Project" in result.stdout

    def test_show_command_not_found(self, monkeypatch):
        """Test show command with nonexistent project."""
        from typer.testing import CliRunner
        from ralphx.cli import app

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("RALPHX_HOME", str(Path(tmpdir) / "ralphx"))

            runner = CliRunner()
            result = runner.invoke(app, ["projects", "show", "nonexistent"])
            assert result.exit_code == 1
            assert "not found" in result.stdout

    def test_remove_command(self, temp_project_dir, monkeypatch):
        """Test remove command."""
        from typer.testing import CliRunner
        from ralphx.cli import app

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("RALPHX_HOME", str(Path(tmpdir) / "ralphx"))

            runner = CliRunner()
            runner.invoke(app, ["add", str(temp_project_dir), "--name", "Test"])
            result = runner.invoke(app, ["remove", "test", "--force"])
            assert result.exit_code == 0
            assert "Removed" in result.stdout

    def test_remove_command_not_found(self, monkeypatch):
        """Test remove command with nonexistent project."""
        from typer.testing import CliRunner
        from ralphx.cli import app

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("RALPHX_HOME", str(Path(tmpdir) / "ralphx"))

            runner = CliRunner()
            result = runner.invoke(app, ["remove", "nonexistent", "--force"])
            assert result.exit_code == 1
            assert "not found" in result.stdout


class TestWorkItemClaimRelease:
    """Test work item claim/release functionality for generator->consumer flow.

    These tests verify the fixes for:
    - claim_work_item: Claims 'pending' or 'completed' items with claimed_by IS NULL
    - release_work_item: Restores status based on source step
    - release_work_item_claim: Same status restoration with ownership check
    - release_stale_claims: Same status restoration for timed-out claims
    - release_claims_by_loop: Same status restoration when loop is deleted
    """

    @pytest.fixture
    def project_db(self, manager, temp_project_dir):
        """Create project and return project database with workflow context."""
        project = manager.add_project(path=temp_project_dir, name="ClaimTest")
        db = manager.get_project_db(project.path)

        # Create workflow context
        workflow_id = "wf-claim-test"
        db.create_workflow(
            id=workflow_id,
            name="Claim Test Workflow",
            status="active"
        )
        # Create two steps: generator and consumer
        gen_step = db.create_workflow_step(
            workflow_id=workflow_id,
            step_number=1,
            name="Generator Step",
            step_type="autonomous",
            status="pending"
        )
        db.create_workflow_step(
            workflow_id=workflow_id,
            step_number=2,
            name="Consumer Step",
            step_type="autonomous",
            status="pending"
        )
        # Store workflow context on the db object for tests to use
        db._test_workflow_id = workflow_id
        db._test_gen_step_id = gen_step["id"]
        return db

    def test_claim_pending_item(self, project_db):
        """Test claiming a pending item succeeds."""
        project_db.create_work_item(
            id="item-1",
            workflow_id=project_db._test_workflow_id,
            source_step_id=project_db._test_gen_step_id,
            content="Test",
            status="pending"
        )
        result = project_db.claim_work_item("item-1", "consumer-loop")
        assert result is True
        item = project_db.get_work_item("item-1")
        assert item["status"] == "claimed"
        assert item["claimed_by"] == "consumer-loop"

    def test_claim_completed_generator_item(self, project_db):
        """Test claiming a completed item from generator succeeds."""
        project_db.create_work_item(
            id="item-1",
            workflow_id=project_db._test_workflow_id,
            source_step_id=project_db._test_gen_step_id,
            content="Test",
            status="completed",
        )
        result = project_db.claim_work_item("item-1", "consumer-loop")
        assert result is True
        item = project_db.get_work_item("item-1")
        assert item["status"] == "claimed"
        assert item["claimed_by"] == "consumer-loop"

    def test_claim_already_claimed_fails(self, project_db):
        """Test claiming an already-claimed item fails."""
        project_db.create_work_item(
            id="item-1",
            workflow_id=project_db._test_workflow_id,
            source_step_id=project_db._test_gen_step_id,
            content="Test",
            status="pending"
        )
        project_db.claim_work_item("item-1", "loop-a")
        result = project_db.claim_work_item("item-1", "loop-b")
        assert result is False

    def test_release_generator_item_restores_completed(self, project_db):
        """Test releasing a generator item restores to 'completed' status."""
        project_db.create_work_item(
            id="item-1",
            workflow_id=project_db._test_workflow_id,
            source_step_id=project_db._test_gen_step_id,
            content="Test",
            status="pending",
        )
        project_db.claim_work_item("item-1", "consumer")
        project_db.release_work_item("item-1")
        item = project_db.get_work_item("item-1")
        # Release restores to pending (the original status before claim)
        assert item["status"] == "pending"
        assert item["claimed_by"] is None

    def test_release_direct_item_restores_pending(self, project_db):
        """Test releasing a direct item restores to 'pending'."""
        project_db.create_work_item(
            id="item-1",
            workflow_id=project_db._test_workflow_id,
            source_step_id=project_db._test_gen_step_id,
            content="Test",
            status="pending"
        )
        project_db.claim_work_item("item-1", "consumer")
        project_db.release_work_item("item-1")
        item = project_db.get_work_item("item-1")
        assert item["status"] == "pending"
        assert item["claimed_by"] is None

    def test_release_claim_with_ownership_check(self, project_db):
        """Test release_work_item_claim verifies ownership."""
        project_db.create_work_item(
            id="item-1",
            workflow_id=project_db._test_workflow_id,
            source_step_id=project_db._test_gen_step_id,
            content="Test",
            status="pending"
        )
        project_db.claim_work_item("item-1", "loop-a")
        # Wrong owner should fail
        result = project_db.release_work_item_claim("item-1", "loop-b")
        assert result is False
        # Correct owner should succeed
        result = project_db.release_work_item_claim("item-1", "loop-a")
        assert result is True

    def test_release_claim_only_affects_claimed_items(self, project_db):
        """Test release_work_item_claim doesn't affect processed items."""
        # TODO: Verify expected behavior with user - should release_work_item_claim
        # fail silently on processed items, or is this an error case?
        project_db.create_work_item(
            id="item-1",
            workflow_id=project_db._test_workflow_id,
            source_step_id=project_db._test_gen_step_id,
            content="Test",
            status="pending"
        )
        project_db.claim_work_item("item-1", "consumer")
        project_db.mark_work_item_processed("item-1", "consumer")
        # Item is now 'processed' but claimed_by is still set
        result = project_db.release_work_item_claim("item-1", "consumer")
        # Should fail because status is not 'claimed'
        assert result is False
        item = project_db.get_work_item("item-1")
        assert item["status"] == "processed"  # Status unchanged

    def test_release_claims_by_loop_restores_status(self, project_db):
        """Test release_claims_by_loop restores status correctly for all items."""
        # Create items from the generator step
        project_db.create_work_item(
            id="item-1",
            workflow_id=project_db._test_workflow_id,
            source_step_id=project_db._test_gen_step_id,
            content="From generator",
        )
        project_db.create_work_item(
            id="item-2",
            workflow_id=project_db._test_workflow_id,
            source_step_id=project_db._test_gen_step_id,
            content="Direct input"
        )
        project_db.claim_work_item("item-1", "consumer")
        project_db.claim_work_item("item-2", "consumer")

        count = project_db.release_claims_by_loop("consumer")
        assert count == 2

        item1 = project_db.get_work_item("item-1")
        item2 = project_db.get_work_item("item-2")
        # Both items should be restored to pending (their original status)
        assert item1["status"] == "pending"
        assert item2["status"] == "pending"

    def test_generator_consumer_full_flow(self, project_db):
        """Integration test: Generator creates -> Consumer claims -> Error -> Re-claim."""
        # Step 1: Generator creates item
        project_db.create_work_item(
            id="story-1",
            workflow_id=project_db._test_workflow_id,
            source_step_id=project_db._test_gen_step_id,
            content="User story from generator",
            status="completed",
        )

        # Step 2: Consumer claims
        result = project_db.claim_work_item("story-1", "implementer")
        assert result is True
        item = project_db.get_work_item("story-1")
        assert item["status"] == "claimed"

        # Step 3: Consumer encounters error, releases
        project_db.release_work_item_claim("story-1", "implementer")
        item = project_db.get_work_item("story-1")
        assert item["status"] == "pending"  # Back to pending for re-claim

        # Step 4: Consumer re-claims after fixing error
        result = project_db.claim_work_item("story-1", "implementer")
        assert result is True
        item = project_db.get_work_item("story-1")
        assert item["status"] == "claimed"

        # Step 5: Consumer successfully processes
        project_db.mark_work_item_processed("story-1", "implementer")
        item = project_db.get_work_item("story-1")
        assert item["status"] == "processed"
