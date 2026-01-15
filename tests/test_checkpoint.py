"""Tests for RalphX checkpoint and recovery."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from ralphx.core.checkpoint import (
    Checkpoint,
    CheckpointManager,
    ProjectLock,
    RecoveryManager,
    is_pid_running,
)
from ralphx.core.database import Database


@pytest.fixture
def db():
    """Create in-memory database."""
    database = Database(":memory:")
    database.create_project(
        id="proj-123",
        slug="test",
        name="Test Project",
        path="/tmp/test",
    )
    yield database
    database.close()


@pytest.fixture
def checkpoint_manager(db):
    """Create a checkpoint manager."""
    return CheckpointManager(db)


@pytest.fixture
def workspace():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_path = Path(tmpdir)
        yield workspace_path


class TestCheckpoint:
    """Test Checkpoint dataclass."""

    def test_default_values(self):
        """Test default values."""
        checkpoint = Checkpoint(
            project_id="proj-123",
            run_id="run-456",
            loop_name="research",
            iteration=5,
        )
        assert checkpoint.status == "in_progress"
        assert checkpoint.data == {}
        assert checkpoint.created_at is not None

    def test_to_dict(self):
        """Test converting to dictionary."""
        checkpoint = Checkpoint(
            project_id="proj-123",
            run_id="run-456",
            loop_name="research",
            iteration=5,
            status="completed",
            data={"items_generated": 10},
        )
        d = checkpoint.to_dict()
        assert d["project_id"] == "proj-123"
        assert d["run_id"] == "run-456"
        assert d["loop_name"] == "research"
        assert d["iteration"] == 5
        assert d["status"] == "completed"
        assert d["data"]["items_generated"] == 10

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "project_id": "proj-123",
            "run_id": "run-456",
            "loop_name": "research",
            "iteration": 5,
            "status": "in_progress",
            "data": {"key": "value"},
            "created_at": "2024-01-01T12:00:00",
        }
        checkpoint = Checkpoint.from_dict(data)
        assert checkpoint.project_id == "proj-123"
        assert checkpoint.iteration == 5
        assert checkpoint.data["key"] == "value"


class TestCheckpointManager:
    """Test CheckpointManager functionality."""

    def test_save_checkpoint(self, checkpoint_manager):
        """Test saving a checkpoint."""
        checkpoint = Checkpoint(
            project_id="proj-123",
            run_id="run-456",
            loop_name="research",
            iteration=5,
        )
        checkpoint_manager.save(checkpoint)

        loaded = checkpoint_manager.load("proj-123")
        assert loaded is not None
        assert loaded.run_id == "run-456"
        assert loaded.iteration == 5

    def test_save_updates_existing(self, checkpoint_manager):
        """Test saving updates existing checkpoint."""
        checkpoint1 = Checkpoint(
            project_id="proj-123",
            run_id="run-456",
            loop_name="research",
            iteration=5,
        )
        checkpoint_manager.save(checkpoint1)

        checkpoint2 = Checkpoint(
            project_id="proj-123",
            run_id="run-456",
            loop_name="research",
            iteration=10,
        )
        checkpoint_manager.save(checkpoint2)

        loaded = checkpoint_manager.load("proj-123")
        assert loaded.iteration == 10

    def test_load_nonexistent(self, checkpoint_manager):
        """Test loading nonexistent checkpoint."""
        loaded = checkpoint_manager.load("not-exists")
        assert loaded is None

    def test_clear_checkpoint(self, checkpoint_manager):
        """Test clearing checkpoint."""
        checkpoint = Checkpoint(
            project_id="proj-123",
            run_id="run-456",
            loop_name="research",
            iteration=5,
        )
        checkpoint_manager.save(checkpoint)

        result = checkpoint_manager.clear("proj-123")
        assert result is True
        assert checkpoint_manager.load("proj-123") is None

    def test_clear_nonexistent(self, checkpoint_manager):
        """Test clearing nonexistent checkpoint."""
        result = checkpoint_manager.clear("not-exists")
        assert result is False

    def test_has_active_checkpoint(self, checkpoint_manager):
        """Test checking for active checkpoint."""
        assert checkpoint_manager.has_active_checkpoint("proj-123") is False

        checkpoint = Checkpoint(
            project_id="proj-123",
            run_id="run-456",
            loop_name="research",
            iteration=5,
            status="in_progress",
        )
        checkpoint_manager.save(checkpoint)
        assert checkpoint_manager.has_active_checkpoint("proj-123") is True

        # Completed checkpoint is not active
        checkpoint.status = "completed"
        checkpoint_manager.save(checkpoint)
        assert checkpoint_manager.has_active_checkpoint("proj-123") is False

    def test_get_recovery_info(self, checkpoint_manager):
        """Test getting recovery info."""
        assert checkpoint_manager.get_recovery_info("proj-123") is None

        checkpoint = Checkpoint(
            project_id="proj-123",
            run_id="run-456",
            loop_name="research",
            iteration=5,
            data={"items": 10},
        )
        checkpoint_manager.save(checkpoint)

        info = checkpoint_manager.get_recovery_info("proj-123")
        assert info is not None
        assert info["run_id"] == "run-456"
        assert info["iteration"] == 5
        assert info["data"]["items"] == 10


class TestIsPidRunning:
    """Test PID checking."""

    def test_current_pid_is_running(self):
        """Test current process is detected as running."""
        assert is_pid_running(os.getpid()) is True

    def test_invalid_pid_not_running(self):
        """Test invalid PID is not running."""
        # Use a very high PID that's unlikely to exist
        assert is_pid_running(999999999) is False

    def test_negative_pid_not_running(self):
        """Test negative PID is not running."""
        assert is_pid_running(-1) is False


class TestProjectLock:
    """Test ProjectLock functionality."""

    def test_acquire_release(self, workspace):
        """Test acquiring and releasing lock."""
        with patch("ralphx.core.workspace.ensure_project_workspace", return_value=workspace):
            lock = ProjectLock("proj-123", "test")
            assert lock.acquire() is True
            assert lock.is_locked is True
            assert lock.lock_path.exists()

            lock.release()
            assert lock.is_locked is False
            assert not lock.lock_path.exists()

    def test_context_manager(self, workspace):
        """Test using lock as context manager."""
        with patch("ralphx.core.workspace.ensure_project_workspace", return_value=workspace):
            lock = ProjectLock("proj-123", "test")
            with lock:
                assert lock.is_locked is True
                assert lock.lock_path.exists()

            assert lock.is_locked is False

    def test_double_acquire_fails(self, workspace):
        """Test second acquire fails."""
        with patch("ralphx.core.workspace.ensure_project_workspace", return_value=workspace):
            lock1 = ProjectLock("proj-123", "test")
            lock2 = ProjectLock("proj-123", "test")

            assert lock1.acquire() is True
            assert lock2.acquire() is False

            lock1.release()

    def test_acquire_after_release(self, workspace):
        """Test can acquire after release."""
        with patch("ralphx.core.workspace.ensure_project_workspace", return_value=workspace):
            lock1 = ProjectLock("proj-123", "test")
            assert lock1.acquire() is True
            lock1.release()

            lock2 = ProjectLock("proj-123", "test")
            assert lock2.acquire() is True
            lock2.release()

    def test_stale_lock_detection(self, workspace):
        """Test detecting stale lock."""
        with patch("ralphx.core.workspace.ensure_project_workspace", return_value=workspace):
            lock = ProjectLock("proj-123", "test")
            lock_path = lock.lock_path

            # Create a fake stale lock file with non-existent PID
            lock_data = {
                "pid": 999999999,
                "project_id": "proj-123",
                "created_at": datetime.utcnow().isoformat(),
            }
            lock_path.write_text(json.dumps(lock_data))

            assert lock.check_stale() is True

            # Now with current PID (not stale)
            lock_data["pid"] = os.getpid()
            lock_path.write_text(json.dumps(lock_data))

            assert lock.check_stale() is False

    def test_acquire_stale_lock(self, workspace):
        """Test acquiring a stale lock."""
        with patch("ralphx.core.workspace.ensure_project_workspace", return_value=workspace):
            lock = ProjectLock("proj-123", "test")
            lock_path = lock.lock_path

            # Create a stale lock
            lock_data = {
                "pid": 999999999,
                "project_id": "proj-123",
            }
            lock_path.write_text(json.dumps(lock_data))

            # Should be able to acquire stale lock
            assert lock.acquire() is True
            lock.release()

    def test_get_lock_info(self, workspace):
        """Test getting lock info."""
        with patch("ralphx.core.workspace.ensure_project_workspace", return_value=workspace):
            lock = ProjectLock("proj-123", "test")

            # No lock exists
            assert lock.get_lock_info() is None

            # Create lock
            lock.acquire()
            info = lock.get_lock_info()
            assert info is not None
            assert info["pid"] == os.getpid()
            assert info["project_id"] == "proj-123"

            lock.release()


class TestRecoveryManager:
    """Test RecoveryManager functionality."""

    def test_can_recover_no_checkpoint(self, db, workspace):
        """Test can_recover when no checkpoint exists."""
        with patch("ralphx.core.workspace.ensure_project_workspace", return_value=workspace):
            recovery = RecoveryManager(db)
            assert recovery.can_recover("proj-123", "test") is False

    def test_can_recover_with_checkpoint(self, db, workspace):
        """Test can_recover with active checkpoint."""
        with patch("ralphx.core.workspace.ensure_project_workspace", return_value=workspace):
            # Create checkpoint
            checkpoint = Checkpoint(
                project_id="proj-123",
                run_id="run-456",
                loop_name="research",
                iteration=5,
            )
            CheckpointManager(db).save(checkpoint)

            recovery = RecoveryManager(db)
            assert recovery.can_recover("proj-123", "test") is True

    def test_can_recover_with_active_lock(self, db, workspace):
        """Test can_recover fails when lock is held."""
        with patch("ralphx.core.workspace.ensure_project_workspace", return_value=workspace):
            # Create checkpoint
            checkpoint = Checkpoint(
                project_id="proj-123",
                run_id="run-456",
                loop_name="research",
                iteration=5,
            )
            CheckpointManager(db).save(checkpoint)

            # Acquire lock
            lock = ProjectLock("proj-123", "test")
            lock.acquire()

            try:
                recovery = RecoveryManager(db)
                assert recovery.can_recover("proj-123", "test") is False
            finally:
                lock.release()

    def test_get_recovery_context(self, db, workspace):
        """Test getting recovery context."""
        with patch("ralphx.core.workspace.ensure_project_workspace", return_value=workspace):
            checkpoint = Checkpoint(
                project_id="proj-123",
                run_id="run-456",
                loop_name="research",
                iteration=5,
                data={"items": 10},
            )
            CheckpointManager(db).save(checkpoint)

            recovery = RecoveryManager(db)
            context = recovery.get_recovery_context("proj-123", "test")

            assert context is not None
            assert context["run_id"] == "run-456"
            assert context["iteration"] == 5
            assert context["data"]["items"] == 10

    def test_prepare_recovery(self, db, workspace):
        """Test preparing for recovery."""
        with patch("ralphx.core.workspace.ensure_project_workspace", return_value=workspace):
            checkpoint = Checkpoint(
                project_id="proj-123",
                run_id="run-456",
                loop_name="research",
                iteration=5,
            )
            CheckpointManager(db).save(checkpoint)

            recovery = RecoveryManager(db)
            success, context, lock = recovery.prepare_recovery("proj-123", "test")

            assert success is True
            assert context is not None
            assert lock is not None
            assert lock.is_locked is True

            # Cleanup
            lock.release()

    def test_complete_recovery_success(self, db, workspace):
        """Test completing successful recovery."""
        with patch("ralphx.core.workspace.ensure_project_workspace", return_value=workspace):
            checkpoint = Checkpoint(
                project_id="proj-123",
                run_id="run-456",
                loop_name="research",
                iteration=5,
            )
            CheckpointManager(db).save(checkpoint)

            recovery = RecoveryManager(db)
            recovery.complete_recovery("proj-123", success=True)

            # Checkpoint should be cleared
            assert CheckpointManager(db).load("proj-123") is None

    def test_complete_recovery_failure(self, db, workspace):
        """Test completing failed recovery."""
        with patch("ralphx.core.workspace.ensure_project_workspace", return_value=workspace):
            checkpoint = Checkpoint(
                project_id="proj-123",
                run_id="run-456",
                loop_name="research",
                iteration=5,
            )
            CheckpointManager(db).save(checkpoint)

            recovery = RecoveryManager(db)
            recovery.complete_recovery("proj-123", success=False)

            # Checkpoint should be marked as failed
            loaded = CheckpointManager(db).load("proj-123")
            assert loaded is not None
            assert loaded.status == "recovery_failed"
