"""Checkpoint and recovery for RalphX.

Implements:
- CheckpointManager for saving/loading checkpoints
- ProjectLock for atomic file locking
- Stale lock detection with PID checking
- Recovery flow for resuming interrupted runs
"""

import fcntl
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ralphx.core.database import Database
from ralphx.core.workspace import ensure_project_workspace


@dataclass
class Checkpoint:
    """Checkpoint data for a run."""

    project_id: str
    run_id: str
    loop_name: str
    iteration: int
    status: str = "in_progress"
    data: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "project_id": self.project_id,
            "run_id": self.run_id,
            "loop_name": self.loop_name,
            "iteration": self.iteration,
            "status": self.status,
            "data": self.data,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Checkpoint":
        """Create from dictionary."""
        return cls(
            project_id=data["project_id"],
            run_id=data["run_id"],
            loop_name=data["loop_name"],
            iteration=data["iteration"],
            status=data.get("status", "in_progress"),
            data=data.get("data", {}),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if isinstance(data.get("created_at"), str)
                else data.get("created_at", datetime.utcnow())
            ),
        )


class CheckpointManager:
    """Manages checkpoints for run recovery.

    Features:
    - Save checkpoints before/after each iteration
    - Load last checkpoint for recovery
    - Clear checkpoints on run completion
    - Track items generated, consecutive errors, etc.
    """

    def __init__(self, db: Database):
        """Initialize the checkpoint manager.

        Args:
            db: Database instance.
        """
        self.db = db

    def save(self, checkpoint: Checkpoint) -> None:
        """Save a checkpoint.

        Args:
            checkpoint: Checkpoint to save.
        """
        self.db.save_checkpoint(
            project_id=checkpoint.project_id,
            run_id=checkpoint.run_id,
            loop_name=checkpoint.loop_name,
            iteration=checkpoint.iteration,
            status=checkpoint.status,
            data=checkpoint.data,
        )

    def load(self, project_id: str) -> Optional[Checkpoint]:
        """Load the last checkpoint for a project.

        Args:
            project_id: Project ID.

        Returns:
            Checkpoint or None.
        """
        data = self.db.get_checkpoint(project_id)
        if data:
            return Checkpoint.from_dict(data)
        return None

    def clear(self, project_id: str) -> bool:
        """Clear checkpoint for a project.

        Args:
            project_id: Project ID.

        Returns:
            True if cleared.
        """
        return self.db.clear_checkpoint(project_id)

    def has_active_checkpoint(self, project_id: str) -> bool:
        """Check if there's an in-progress checkpoint.

        Args:
            project_id: Project ID.

        Returns:
            True if active checkpoint exists.
        """
        checkpoint = self.load(project_id)
        return checkpoint is not None and checkpoint.status == "in_progress"

    def get_recovery_info(self, project_id: str) -> Optional[dict]:
        """Get information needed for recovery.

        Args:
            project_id: Project ID.

        Returns:
            Dictionary with recovery details or None.
        """
        checkpoint = self.load(project_id)
        if not checkpoint or checkpoint.status != "in_progress":
            return None

        return {
            "run_id": checkpoint.run_id,
            "loop_name": checkpoint.loop_name,
            "iteration": checkpoint.iteration,
            "data": checkpoint.data,
            "created_at": checkpoint.created_at,
        }


def is_pid_running(pid: int) -> bool:
    """Check if a process with given PID is running.

    Cross-platform implementation.

    Args:
        pid: Process ID to check.

    Returns:
        True if process is running.
    """
    # Invalid PIDs
    if pid <= 0:
        return False

    if sys.platform == "win32":
        # Windows implementation
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259

            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                try:
                    exit_code = ctypes.c_ulong()
                    if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                        return exit_code.value == STILL_ACTIVE
                finally:
                    kernel32.CloseHandle(handle)
            return False
        except Exception:
            return False
    else:
        # Unix implementation
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


class ProjectLock:
    """Atomic file lock for a project.

    Features:
    - Uses O_CREAT | O_EXCL for atomic creation
    - Stores PID for stale lock detection
    - Cross-platform stale lock detection
    - Automatic cleanup on release
    """

    def __init__(self, project_id: str, project_slug: str):
        """Initialize the project lock.

        Args:
            project_id: Project ID.
            project_slug: Project slug for workspace path.
        """
        self.project_id = project_id
        self.project_slug = project_slug
        self._lock_file: Optional[Path] = None
        self._fd: Optional[int] = None
        self._locked = False

    @property
    def lock_path(self) -> Path:
        """Get the path to the lock file."""
        workspace = ensure_project_workspace(self.project_slug)
        return workspace / ".lock"

    @property
    def is_locked(self) -> bool:
        """Check if lock is held by this instance."""
        return self._locked

    def acquire(self, force: bool = False) -> bool:
        """Acquire the lock.

        Args:
            force: Force acquisition even if lock exists (after stale check).

        Returns:
            True if lock acquired.
        """
        lock_path = self.lock_path

        # Check for existing lock
        if lock_path.exists():
            try:
                with open(lock_path, 'r') as f:
                    lock_data = json.load(f)
                    existing_pid = lock_data.get("pid")

                    if existing_pid and is_pid_running(existing_pid):
                        # Lock is held by running process
                        if not force:
                            return False
                    # Lock is stale, we can take it
            except (json.JSONDecodeError, IOError):
                # Lock file is corrupted, try to acquire
                pass

            # Remove stale lock
            try:
                lock_path.unlink()
            except OSError:
                return False

        # Try to create lock atomically
        try:
            if sys.platform == "win32":
                # Windows doesn't have O_EXCL, use file locking
                self._fd = os.open(
                    str(lock_path),
                    os.O_CREAT | os.O_WRONLY,
                )
                try:
                    import msvcrt
                    msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
                except Exception:
                    os.close(self._fd)
                    self._fd = None
                    return False
            else:
                # Unix: O_CREAT | O_EXCL for atomic creation
                self._fd = os.open(
                    str(lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o644,
                )
                # Also use flock for robustness
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        except (OSError, IOError):
            return False

        # Write lock data
        lock_data = {
            "pid": os.getpid(),
            "project_id": self.project_id,
            "created_at": datetime.utcnow().isoformat(),
        }

        try:
            os.write(self._fd, json.dumps(lock_data).encode())
        except OSError:
            self.release()
            return False

        self._lock_file = lock_path
        self._locked = True
        return True

    def release(self) -> None:
        """Release the lock."""
        if self._fd is not None:
            try:
                if sys.platform != "win32":
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

        if self._lock_file and self._lock_file.exists():
            try:
                self._lock_file.unlink()
            except OSError:
                pass

        self._locked = False

    def check_stale(self) -> bool:
        """Check if existing lock is stale.

        Returns:
            True if lock exists but is stale.
        """
        lock_path = self.lock_path

        if not lock_path.exists():
            return False

        try:
            with open(lock_path, 'r') as f:
                lock_data = json.load(f)
                existing_pid = lock_data.get("pid")

                if existing_pid:
                    return not is_pid_running(existing_pid)
        except (json.JSONDecodeError, IOError):
            # Corrupted lock file is considered stale
            return True

        return False

    def get_lock_info(self) -> Optional[dict]:
        """Get information about the current lock.

        Returns:
            Lock data or None if no lock.
        """
        lock_path = self.lock_path

        if not lock_path.exists():
            return None

        try:
            with open(lock_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def __enter__(self) -> "ProjectLock":
        """Context manager entry."""
        if not self.acquire():
            raise RuntimeError(f"Failed to acquire lock for project {self.project_slug}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.release()


class RecoveryManager:
    """Manages recovery of interrupted runs.

    Features:
    - Detect interrupted runs from checkpoints
    - Validate and acquire locks
    - Prepare recovery context
    """

    def __init__(self, db: Database):
        """Initialize the recovery manager.

        Args:
            db: Database instance.
        """
        self.db = db
        self.checkpoint_manager = CheckpointManager(db)

    def can_recover(self, project_id: str, project_slug: str) -> bool:
        """Check if recovery is possible.

        Args:
            project_id: Project ID.
            project_slug: Project slug.

        Returns:
            True if recovery is possible.
        """
        # Must have an active checkpoint
        if not self.checkpoint_manager.has_active_checkpoint(project_id):
            return False

        # Lock must be stale or not exist
        lock = ProjectLock(project_id, project_slug)
        lock_info = lock.get_lock_info()

        if lock_info:
            existing_pid = lock_info.get("pid")
            if existing_pid and is_pid_running(existing_pid):
                return False

        return True

    def get_recovery_context(
        self,
        project_id: str,
        project_slug: str,
    ) -> Optional[dict]:
        """Get context needed for recovery.

        Args:
            project_id: Project ID.
            project_slug: Project slug.

        Returns:
            Recovery context or None.
        """
        if not self.can_recover(project_id, project_slug):
            return None

        checkpoint = self.checkpoint_manager.load(project_id)
        if not checkpoint:
            return None

        return {
            "run_id": checkpoint.run_id,
            "loop_name": checkpoint.loop_name,
            "iteration": checkpoint.iteration,
            "status": checkpoint.status,
            "data": checkpoint.data,
            "checkpoint_created_at": checkpoint.created_at,
        }

    def prepare_recovery(
        self,
        project_id: str,
        project_slug: str,
    ) -> tuple[bool, Optional[dict], Optional[ProjectLock]]:
        """Prepare for recovery.

        Validates recovery is possible, acquires lock, returns context.

        Args:
            project_id: Project ID.
            project_slug: Project slug.

        Returns:
            Tuple of (success, context, lock). Lock must be released when done.
        """
        context = self.get_recovery_context(project_id, project_slug)
        if not context:
            return False, None, None

        # Acquire lock (force since we validated stale)
        lock = ProjectLock(project_id, project_slug)
        if not lock.acquire(force=True):
            return False, None, None

        return True, context, lock

    def complete_recovery(
        self,
        project_id: str,
        success: bool,
    ) -> None:
        """Complete recovery process.

        Args:
            project_id: Project ID.
            success: Whether recovery was successful.
        """
        if success:
            # Clear the checkpoint on successful recovery
            self.checkpoint_manager.clear(project_id)
        else:
            # Update checkpoint status
            checkpoint = self.checkpoint_manager.load(project_id)
            if checkpoint:
                checkpoint.status = "recovery_failed"
                self.checkpoint_manager.save(checkpoint)
