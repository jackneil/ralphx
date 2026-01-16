"""Tests for RalphX SQLite database layer."""

import tempfile
import threading
import uuid
from pathlib import Path

import pytest

from ralphx.core.database import Database, SCHEMA_VERSION


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture
def file_db():
    """Create a file-based database for testing file operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        database = Database(str(db_path))
        yield database, db_path
        database.close()


class TestDatabaseInit:
    """Test database initialization."""

    def test_creates_schema(self, db):
        """Test schema is created on init."""
        with db._reader() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in cursor.fetchall()}

        expected = {
            "projects",
            "loops",
            "runs",
            "sessions",
            "work_items",
            "checkpoints",
            "guardrails",
            "logs",
            "schema_version",
        }
        assert expected.issubset(tables)

    def test_wal_mode_enabled(self, file_db):
        """Test WAL mode is enabled for file-based databases."""
        db, _ = file_db
        with db._reader() as conn:
            cursor = conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
        assert mode == "wal"

    def test_foreign_keys_enabled(self, db):
        """Test foreign keys are enabled."""
        with db._reader() as conn:
            cursor = conn.execute("PRAGMA foreign_keys")
            enabled = cursor.fetchone()[0]
        assert enabled == 1

    def test_schema_version_set(self, db):
        """Test schema version is recorded."""
        assert db.get_schema_version() == SCHEMA_VERSION

    def test_file_permissions(self, file_db):
        """Test database file has 0600 permissions."""
        db, db_path = file_db
        mode = db_path.stat().st_mode & 0o777
        assert mode == 0o600


class TestProjectOperations:
    """Test project CRUD operations."""

    def test_create_project(self, db):
        """Test creating a project."""
        project_id = db.create_project(
            id="proj-123",
            slug="my-app",
            name="My App",
            path="/home/user/my-app",
            design_doc="design/PRD.md",
        )
        assert project_id == "proj-123"

    def test_get_project(self, db):
        """Test getting a project by slug."""
        db.create_project(
            id="proj-123",
            slug="my-app",
            name="My App",
            path="/home/user/my-app",
        )
        project = db.get_project("my-app")
        assert project is not None
        assert project["slug"] == "my-app"
        assert project["name"] == "My App"

    def test_get_project_by_id(self, db):
        """Test getting a project by ID."""
        db.create_project(
            id="proj-123",
            slug="my-app",
            name="My App",
            path="/home/user/my-app",
        )
        project = db.get_project_by_id("proj-123")
        assert project is not None
        assert project["id"] == "proj-123"

    def test_list_projects(self, db):
        """Test listing all projects."""
        db.create_project(id="p1", slug="app1", name="App 1", path="/path1")
        db.create_project(id="p2", slug="app2", name="App 2", path="/path2")
        projects = db.list_projects()
        assert len(projects) == 2

    def test_update_project(self, db):
        """Test updating a project."""
        db.create_project(id="p1", slug="app1", name="App 1", path="/path1")
        result = db.update_project("app1", name="Updated App")
        assert result is True
        project = db.get_project("app1")
        assert project["name"] == "Updated App"

    def test_delete_project(self, db):
        """Test deleting a project."""
        db.create_project(id="p1", slug="app1", name="App 1", path="/path1")
        result = db.delete_project("app1")
        assert result is True
        assert db.get_project("app1") is None

    def test_delete_cascades(self, db):
        """Test that deleting a project cascades to related data."""
        db.create_project(id="p1", slug="app1", name="App 1", path="/path1")
        db.create_work_item(id="item-1", project_id="p1", content="Test item")
        db.delete_project("app1")
        # Work item should be deleted
        assert db.get_work_item("p1", "item-1") is None


class TestLoopOperations:
    """Test loop CRUD operations."""

    @pytest.fixture
    def project(self, db):
        """Create a project for loop tests."""
        db.create_project(id="p1", slug="app1", name="App 1", path="/path1")
        return "p1"

    def test_create_loop(self, db, project):
        """Test creating a loop."""
        loop_id = db.create_loop(
            id="loop-1",
            project_id=project,
            name="research",
            config_yaml="name: research\ntype: generator",
        )
        assert loop_id == "loop-1"

    def test_get_loop(self, db, project):
        """Test getting a loop."""
        db.create_loop(
            id="loop-1",
            project_id=project,
            name="research",
            config_yaml="name: research",
        )
        loop = db.get_loop(project, "research")
        assert loop is not None
        assert loop["name"] == "research"

    def test_list_loops(self, db, project):
        """Test listing loops for a project."""
        db.create_loop(id="l1", project_id=project, name="research", config_yaml="")
        db.create_loop(id="l2", project_id=project, name="implement", config_yaml="")
        loops = db.list_loops(project)
        assert len(loops) == 2


class TestRunOperations:
    """Test run CRUD operations."""

    @pytest.fixture
    def project(self, db):
        """Create a project for run tests."""
        db.create_project(id="p1", slug="app1", name="App 1", path="/path1")
        return "p1"

    def test_create_run(self, db, project):
        """Test creating a run."""
        run_id = db.create_run(
            id="run-123",
            project_id=project,
            loop_name="research",
        )
        assert run_id == "run-123"

    def test_get_run(self, db, project):
        """Test getting a run."""
        db.create_run(id="run-123", project_id=project, loop_name="research")
        run = db.get_run("run-123")
        assert run is not None
        assert run["status"] == "active"

    def test_update_run(self, db, project):
        """Test updating a run."""
        db.create_run(id="run-123", project_id=project, loop_name="research")
        db.update_run("run-123", status="paused")
        run = db.get_run("run-123")
        assert run["status"] == "paused"

    def test_complete_run(self, db, project):
        """Test completing a run."""
        db.create_run(id="run-123", project_id=project, loop_name="research")
        db.complete_run("run-123", status="completed")
        run = db.get_run("run-123")
        assert run["status"] == "completed"
        assert run["completed_at"] is not None

    def test_increment_counters(self, db, project):
        """Test incrementing run counters."""
        db.create_run(id="run-123", project_id=project, loop_name="research")
        db.increment_run_counters("run-123", iterations=1, items=5)
        db.increment_run_counters("run-123", iterations=1, items=3)
        run = db.get_run("run-123")
        assert run["iterations_completed"] == 2
        assert run["items_generated"] == 8

    def test_list_runs(self, db, project):
        """Test listing runs."""
        db.create_run(id="r1", project_id=project, loop_name="research")
        db.create_run(id="r2", project_id=project, loop_name="implement")
        runs = db.list_runs(project)
        assert len(runs) == 2


class TestSessionOperations:
    """Test session CRUD operations."""

    @pytest.fixture
    def run(self, db):
        """Create a project and run for session tests."""
        db.create_project(id="p1", slug="app1", name="App 1", path="/path1")
        db.create_run(id="run-1", project_id="p1", loop_name="research")
        return "run-1"

    def test_create_session(self, db, run):
        """Test creating a session."""
        session_id = db.create_session(
            session_id="sess-abc",
            project_id="p1",
            iteration=1,
            run_id=run,
            mode="turbo",
        )
        assert session_id == "sess-abc"

    def test_get_session(self, db, run):
        """Test getting a session."""
        db.create_session(
            session_id="sess-abc",
            project_id="p1",
            iteration=1,
            run_id=run,
        )
        session = db.get_session("sess-abc")
        assert session is not None
        assert session["iteration"] == 1

    def test_update_session(self, db, run):
        """Test updating a session."""
        db.create_session(
            session_id="sess-abc",
            project_id="p1",
            iteration=1,
            run_id=run,
        )
        db.update_session(
            "sess-abc",
            status="completed",
            duration_seconds=45.5,
            items_added=["item-1", "item-2"],
        )
        session = db.get_session("sess-abc")
        assert session["status"] == "completed"
        assert session["duration_seconds"] == 45.5


class TestWorkItemOperations:
    """Test work item CRUD operations."""

    @pytest.fixture
    def project(self, db):
        """Create a project for work item tests."""
        db.create_project(id="p1", slug="app1", name="App 1", path="/path1")
        return "p1"

    def test_create_work_item(self, db, project):
        """Test creating a work item."""
        item_id = db.create_work_item(
            id="ANS-001",
            project_id=project,
            content="Implement billing logic",
            priority=1,
            category="ANS",
            tags=["billing", "core"],
            metadata={"source": "research"},
        )
        assert item_id == "ANS-001"

    def test_get_work_item(self, db, project):
        """Test getting a work item."""
        db.create_work_item(
            id="ANS-001",
            project_id=project,
            content="Test item",
            tags=["test"],
            metadata={"key": "value"},
        )
        item = db.get_work_item(project, "ANS-001")
        assert item is not None
        assert item["tags"] == ["test"]
        assert item["metadata"] == {"key": "value"}

    def test_list_work_items(self, db, project):
        """Test listing work items."""
        for i in range(5):
            db.create_work_item(
                id=f"item-{i}",
                project_id=project,
                content=f"Item {i}",
                priority=i,
            )
        items = db.list_work_items(project)
        assert len(items) == 5

    def test_list_work_items_filtered(self, db, project):
        """Test listing work items with filters."""
        db.create_work_item(id="i1", project_id=project, content="1", status="pending")
        db.create_work_item(id="i2", project_id=project, content="2", status="completed")
        db.create_work_item(id="i3", project_id=project, content="3", status="pending")

        pending = db.list_work_items(project, status="pending")
        assert len(pending) == 2

    def test_count_work_items(self, db, project):
        """Test counting work items."""
        db.create_work_item(id="i1", project_id=project, content="1", status="pending")
        db.create_work_item(id="i2", project_id=project, content="2", status="completed")
        assert db.count_work_items(project) == 2
        assert db.count_work_items(project, status="pending") == 1

    def test_update_work_item(self, db, project):
        """Test updating a work item."""
        db.create_work_item(id="i1", project_id=project, content="Original")
        db.update_work_item(project, "i1", content="Updated", status="completed")
        item = db.get_work_item(project, "i1")
        assert item["content"] == "Updated"
        assert item["status"] == "completed"

    def test_get_work_item_stats(self, db, project):
        """Test getting work item statistics."""
        db.create_work_item(id="i1", project_id=project, content="1", status="pending", category="ANS")
        db.create_work_item(id="i2", project_id=project, content="2", status="completed", category="ANS")
        db.create_work_item(id="i3", project_id=project, content="3", status="pending", category="FND")

        stats = db.get_work_item_stats(project)
        assert stats["total"] == 3
        assert stats["by_status"]["pending"] == 2
        assert stats["by_status"]["completed"] == 1
        assert stats["by_category"]["ANS"] == 2


class TestCheckpointOperations:
    """Test checkpoint operations."""

    @pytest.fixture
    def project(self, db):
        """Create a project for checkpoint tests."""
        db.create_project(id="p1", slug="app1", name="App 1", path="/path1")
        return "p1"

    def test_save_checkpoint(self, db, project):
        """Test saving a checkpoint."""
        db.save_checkpoint(
            project_id=project,
            run_id="run-1",
            loop_name="research",
            iteration=5,
            status="in_progress",
            data={"last_category": "ANS"},
        )
        checkpoint = db.get_checkpoint(project)
        assert checkpoint is not None
        assert checkpoint["iteration"] == 5
        assert checkpoint["data"] == {"last_category": "ANS"}

    def test_checkpoint_upsert(self, db, project):
        """Test that checkpoint updates in place."""
        db.save_checkpoint(project, "run-1", "research", 5, "in_progress")
        db.save_checkpoint(project, "run-1", "research", 6, "in_progress")
        checkpoint = db.get_checkpoint(project)
        assert checkpoint["iteration"] == 6

    def test_clear_checkpoint(self, db, project):
        """Test clearing a checkpoint."""
        db.save_checkpoint(project, "run-1", "research", 5, "in_progress")
        db.clear_checkpoint(project)
        assert db.get_checkpoint(project) is None


class TestGuardrailOperations:
    """Test guardrail operations."""

    @pytest.fixture
    def project(self, db):
        """Create a project for guardrail tests."""
        db.create_project(id="p1", slug="app1", name="App 1", path="/path1")
        return "p1"

    def test_create_guardrail(self, db, project):
        """Test creating a guardrail."""
        guardrail_id = db.create_guardrail(
            project_id=project,
            category="safety",
            filename="never-do.md",
            source="global",
            file_path="/home/user/.ralphx/guardrails/safety/never-do.md",
            file_size=1024,
            loops=["research"],
            modes=["turbo"],
        )
        assert guardrail_id > 0

    def test_create_global_guardrail(self, db):
        """Test creating a global guardrail (no project)."""
        guardrail_id = db.create_guardrail(
            category="safety",
            filename="global-rule.md",
            source="global",
            file_path="/home/user/.ralphx/guardrails/safety/global-rule.md",
        )
        assert guardrail_id > 0

    def test_list_guardrails(self, db, project):
        """Test listing guardrails."""
        db.create_guardrail(
            project_id=project,
            category="safety",
            filename="rule1.md",
            source="workspace",
            file_path="/path/rule1.md",
        )
        db.create_guardrail(
            category="safety",
            filename="global.md",
            source="global",
            file_path="/path/global.md",
        )
        # Should include both project and global guardrails
        guardrails = db.list_guardrails(project_id=project)
        assert len(guardrails) == 2

    def test_list_guardrails_by_source(self, db):
        """Test filtering guardrails by source."""
        db.create_guardrail(
            category="safety",
            filename="g1.md",
            source="global",
            file_path="/p1",
        )
        db.create_guardrail(
            category="safety",
            filename="g2.md",
            source="repo",
            file_path="/p2",
        )
        global_only = db.list_guardrails(source="global")
        assert len(global_only) == 1
        assert global_only[0]["source"] == "global"


class TestLogOperations:
    """Test log operations."""

    @pytest.fixture
    def project(self, db):
        """Create a project for log tests."""
        db.create_project(id="p1", slug="app1", name="App 1", path="/path1")
        return "p1"

    def test_log_entry(self, db, project):
        """Test writing a log entry."""
        log_id = db.log(
            level="INFO",
            category="system",
            event="test",
            message="Test message",
            project_id=project,
            metadata={"key": "value"},
        )
        assert log_id > 0

    def test_get_logs(self, db, project):
        """Test getting logs."""
        db.log("INFO", "system", "test", "Message 1", project_id=project)
        db.log("ERROR", "system", "test", "Message 2", project_id=project)
        db.log("INFO", "system", "test", "Message 3", project_id=project)

        all_logs = db.get_logs(project_id=project)
        assert len(all_logs) == 3

        error_logs = db.get_logs(project_id=project, level="ERROR")
        assert len(error_logs) == 1


class TestBackupOperations:
    """Test backup operations."""

    def test_backup_creates_file(self, file_db):
        """Test backup creates a database file."""
        db, db_path = file_db
        # Add some data
        db.create_project(id="p1", slug="app1", name="App 1", path="/path1")

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_path = Path(tmpdir) / "backup.db"
            result = db.backup(str(backup_path))
            assert result.exists()
            assert result.stat().st_size > 0

    def test_backup_permissions(self, file_db):
        """Test backup file has 0600 permissions."""
        db, _ = file_db
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_path = Path(tmpdir) / "backup.db"
            result = db.backup(str(backup_path))
            mode = result.stat().st_mode & 0o777
            assert mode == 0o600

    def test_backup_is_valid_db(self, file_db):
        """Test backup is a valid SQLite database."""
        db, _ = file_db
        db.create_project(id="p1", slug="app1", name="App 1", path="/path1")

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_path = Path(tmpdir) / "backup.db"
            db.backup(str(backup_path))

            # Open backup and verify data
            backup_db = Database(str(backup_path))
            project = backup_db.get_project("app1")
            assert project is not None
            assert project["name"] == "App 1"
            backup_db.close()


class TestConcurrency:
    """Test concurrent access."""

    def test_concurrent_reads(self, file_db):
        """Test multiple threads can read concurrently."""
        db, _ = file_db
        db.create_project(id="p1", slug="app1", name="App 1", path="/path1")

        results = []
        errors = []

        def reader():
            try:
                for _ in range(10):
                    project = db.get_project("app1")
                    results.append(project is not None)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert all(results)

    def test_concurrent_writes(self, file_db):
        """Test writes are serialized correctly."""
        db, _ = file_db
        db.create_project(id="p1", slug="app1", name="App 1", path="/path1")
        db.create_run(id="run-1", project_id="p1", loop_name="test")

        errors = []

        def writer(thread_id):
            try:
                for i in range(10):
                    db.increment_run_counters("run-1", iterations=1)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        run = db.get_run("run-1")
        assert run["iterations_completed"] == 50  # 5 threads * 10 iterations
