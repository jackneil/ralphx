"""Doctor and diagnostics for RalphX.

Implements:
- DoctorCheck for prerequisite validation
- Project-specific diagnostics
- Run history and stop reason analysis
"""

import asyncio
import os
import platform
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from ralphx.core.database import Database
from ralphx.core.workspace import get_workspace_path, workspace_exists
from ralphx.models.project import Project
from ralphx.models.run import Run, RunStatus


class CheckStatus(str, Enum):
    """Status of a diagnostic check."""

    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class CheckResult:
    """Result of a diagnostic check."""

    name: str
    status: CheckStatus
    message: str
    details: Optional[str] = None
    fix_hint: Optional[str] = None


@dataclass
class DiagnosticReport:
    """Complete diagnostic report."""

    checks: list[CheckResult] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def has_errors(self) -> bool:
        """Check if any errors exist."""
        return any(c.status == CheckStatus.ERROR for c in self.checks)

    @property
    def has_warnings(self) -> bool:
        """Check if any warnings exist."""
        return any(c.status == CheckStatus.WARNING for c in self.checks)

    @property
    def all_ok(self) -> bool:
        """Check if all checks passed."""
        return all(c.status == CheckStatus.OK for c in self.checks)

    def summary(self) -> str:
        """Get a summary of the report."""
        ok = sum(1 for c in self.checks if c.status == CheckStatus.OK)
        warn = sum(1 for c in self.checks if c.status == CheckStatus.WARNING)
        err = sum(1 for c in self.checks if c.status == CheckStatus.ERROR)
        return f"{ok} passed, {warn} warnings, {err} errors"


class DoctorCheck:
    """Performs diagnostic checks for RalphX.

    Checks:
    - Python version (3.10+)
    - Node.js installed
    - Claude CLI installed and version
    - Claude CLI authenticated
    - Workspace directory writable
    - Network connectivity
    - Platform-specific issues
    """

    MIN_PYTHON_VERSION = (3, 10)
    ANTHROPIC_API_HOST = "api.anthropic.com"

    def __init__(self):
        """Initialize the doctor."""
        self._results: list[CheckResult] = []

    def run_all(self) -> DiagnosticReport:
        """Run all diagnostic checks.

        Returns:
            DiagnosticReport with all results.
        """
        self._results = []

        self._check_python_version()
        self._check_nodejs()
        self._check_claude_cli()
        self._check_claude_auth()
        self._check_workspace()
        self._check_network()
        self._check_platform()

        return DiagnosticReport(checks=self._results)

    def _add_result(
        self,
        name: str,
        status: CheckStatus,
        message: str,
        details: Optional[str] = None,
        fix_hint: Optional[str] = None,
    ) -> None:
        """Add a check result."""
        self._results.append(CheckResult(
            name=name,
            status=status,
            message=message,
            details=details,
            fix_hint=fix_hint,
        ))

    def _check_python_version(self) -> None:
        """Check Python version."""
        version = sys.version_info
        version_str = f"{version.major}.{version.minor}.{version.micro}"

        if (version.major, version.minor) >= self.MIN_PYTHON_VERSION:
            self._add_result(
                "Python version",
                CheckStatus.OK,
                f"Python {version_str}",
            )
        else:
            min_ver = ".".join(str(v) for v in self.MIN_PYTHON_VERSION)
            self._add_result(
                "Python version",
                CheckStatus.ERROR,
                f"Python {version_str} (requires {min_ver}+)",
                fix_hint=f"Upgrade to Python {min_ver} or later",
            )

    def _check_nodejs(self) -> None:
        """Check Node.js installation."""
        node_path = shutil.which("node")

        if node_path:
            try:
                result = subprocess.run(
                    ["node", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                version = result.stdout.strip()
                self._add_result(
                    "Node.js",
                    CheckStatus.OK,
                    f"Node.js {version}",
                )
            except (subprocess.TimeoutExpired, OSError):
                self._add_result(
                    "Node.js",
                    CheckStatus.WARNING,
                    "Node.js found but version check failed",
                )
        else:
            self._add_result(
                "Node.js",
                CheckStatus.WARNING,
                "Node.js not found",
                details="Some features may not work without Node.js",
                fix_hint="Install Node.js from https://nodejs.org/",
            )

    def _check_claude_cli(self) -> None:
        """Check Claude CLI installation."""
        claude_path = shutil.which("claude")

        if claude_path:
            try:
                result = subprocess.run(
                    ["claude", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    version = result.stdout.strip().split('\n')[0]
                    self._add_result(
                        "Claude CLI",
                        CheckStatus.OK,
                        f"Claude CLI: {version}",
                    )
                else:
                    self._add_result(
                        "Claude CLI",
                        CheckStatus.WARNING,
                        "Claude CLI found but version check failed",
                        details=result.stderr.strip() if result.stderr else None,
                    )
            except subprocess.TimeoutExpired:
                self._add_result(
                    "Claude CLI",
                    CheckStatus.WARNING,
                    "Claude CLI version check timed out",
                )
            except OSError as e:
                self._add_result(
                    "Claude CLI",
                    CheckStatus.ERROR,
                    f"Claude CLI error: {e}",
                )
        else:
            self._add_result(
                "Claude CLI",
                CheckStatus.ERROR,
                "Claude CLI not found",
                fix_hint="Install with: npm install -g @anthropic-ai/claude-code",
            )

    def _check_claude_auth(self) -> None:
        """Check Claude CLI authentication."""
        claude_path = shutil.which("claude")

        if not claude_path:
            self._add_result(
                "Claude CLI auth",
                CheckStatus.SKIPPED,
                "Skipped (Claude CLI not installed)",
            )
            return

        try:
            # Check if config exists
            config_path = Path.home() / ".claude" / "config.json"
            if not config_path.exists():
                self._add_result(
                    "Claude CLI auth",
                    CheckStatus.ERROR,
                    "Not authenticated",
                    fix_hint="Run: claude login",
                )
                return

            # Try to verify authentication
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                self._add_result(
                    "Claude CLI auth",
                    CheckStatus.OK,
                    "Authenticated",
                )
            else:
                self._add_result(
                    "Claude CLI auth",
                    CheckStatus.WARNING,
                    "Authentication status unclear",
                    fix_hint="Try: claude login",
                )

        except subprocess.TimeoutExpired:
            self._add_result(
                "Claude CLI auth",
                CheckStatus.WARNING,
                "Authentication check timed out",
            )
        except OSError as e:
            self._add_result(
                "Claude CLI auth",
                CheckStatus.ERROR,
                f"Error checking authentication: {e}",
            )

    def _check_workspace(self) -> None:
        """Check workspace directory."""
        workspace = get_workspace_path()

        if workspace_exists():
            # Check if writable
            try:
                test_file = workspace / ".write_test"
                test_file.touch()
                test_file.unlink()
                self._add_result(
                    "Workspace",
                    CheckStatus.OK,
                    f"Writable: {workspace}",
                )
            except (OSError, PermissionError):
                self._add_result(
                    "Workspace",
                    CheckStatus.ERROR,
                    f"Not writable: {workspace}",
                    fix_hint=f"Check permissions on {workspace}",
                )
        else:
            self._add_result(
                "Workspace",
                CheckStatus.OK,
                "Not initialized (will be created on first use)",
                details=f"Location: {workspace}",
            )

    def _check_network(self) -> None:
        """Check network connectivity."""
        try:
            socket.create_connection((self.ANTHROPIC_API_HOST, 443), timeout=5)
            self._add_result(
                "Network",
                CheckStatus.OK,
                f"Connected to {self.ANTHROPIC_API_HOST}",
            )
        except (socket.timeout, socket.error, OSError) as e:
            self._add_result(
                "Network",
                CheckStatus.WARNING,
                f"Cannot reach {self.ANTHROPIC_API_HOST}",
                details=str(e),
                fix_hint="Check your internet connection and firewall settings",
            )

    def _check_platform(self) -> None:
        """Check for platform-specific issues."""
        system = platform.system()
        release = platform.release()

        # Check for problematic Linux kernel
        if system == "Linux" and "5.15.0" in release:
            self._add_result(
                "Platform",
                CheckStatus.WARNING,
                f"Linux kernel {release}",
                details="Kernel 5.15.0 may have subprocess issues",
                fix_hint="Consider upgrading kernel if you experience hangs",
            )
            return

        # Check for WSL paths
        if system == "Linux" and Path("/mnt/c").exists():
            cwd = Path.cwd()
            if str(cwd).startswith("/mnt/"):
                self._add_result(
                    "Platform",
                    CheckStatus.WARNING,
                    "Running from WSL /mnt/ path",
                    details="Performance may be degraded on Windows filesystem",
                    fix_hint="Consider running from native WSL filesystem (/home/...)",
                )
                return

        self._add_result(
            "Platform",
            CheckStatus.OK,
            f"{system} {release}",
        )


class ProjectDiagnostics:
    """Project-specific diagnostics."""

    def __init__(self, db: Database):
        """Initialize project diagnostics.

        Args:
            db: Database instance.
        """
        self.db = db

    def diagnose(self, project: Project) -> DiagnosticReport:
        """Run diagnostics for a project.

        Args:
            project: Project to diagnose.

        Returns:
            DiagnosticReport with results.
        """
        results = []

        # Check project path exists
        if project.path.exists():
            results.append(CheckResult(
                name="Project path",
                status=CheckStatus.OK,
                message=f"Exists: {project.path}",
            ))
        else:
            results.append(CheckResult(
                name="Project path",
                status=CheckStatus.ERROR,
                message=f"Not found: {project.path}",
                fix_hint="Update project path or remove and re-add project",
            ))

        # Check design doc if specified
        if project.design_doc:
            design_path = project.path / project.design_doc
            if design_path.exists():
                results.append(CheckResult(
                    name="Design doc",
                    status=CheckStatus.OK,
                    message=f"Found: {project.design_doc}",
                ))
            else:
                results.append(CheckResult(
                    name="Design doc",
                    status=CheckStatus.WARNING,
                    message=f"Not found: {project.design_doc}",
                ))

        # Check for loops
        loops = self.db.list_loops(project.id)
        if loops:
            results.append(CheckResult(
                name="Loops",
                status=CheckStatus.OK,
                message=f"{len(loops)} loops registered",
            ))
        else:
            results.append(CheckResult(
                name="Loops",
                status=CheckStatus.WARNING,
                message="No loops registered",
                fix_hint=f"Run: ralphx loops sync --project {project.slug}",
            ))

        # Check for active runs
        runs = self.db.list_runs(project.id)
        active_runs = [r for r in runs if r.get("status") == "active"]
        if active_runs:
            results.append(CheckResult(
                name="Active runs",
                status=CheckStatus.WARNING,
                message=f"{len(active_runs)} active run(s)",
                details="These runs may be stale or still running",
            ))

        # Check for checkpoints
        checkpoint = self.db.get_checkpoint(project.id)
        if checkpoint and checkpoint.get("status") == "in_progress":
            results.append(CheckResult(
                name="Checkpoint",
                status=CheckStatus.WARNING,
                message="In-progress checkpoint found",
                details=f"Run {checkpoint.get('run_id')} may be recoverable",
                fix_hint=f"Run: ralphx run {checkpoint.get('loop_name')} --resume --project {project.slug}",
            ))

        return DiagnosticReport(checks=results)

    def why_stopped(self, project: Project) -> Optional[dict]:
        """Explain why the last run stopped.

        Args:
            project: Project to analyze.

        Returns:
            Dictionary with stop reason analysis or None.
        """
        # Get most recent run
        runs = self.db.list_runs(project.id, limit=1)
        if not runs:
            return None

        run_data = runs[0]
        run = Run.from_dict(run_data)

        result = {
            "run_id": run.id,
            "loop_name": run.loop_name,
            "status": run.status.value,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "iterations_completed": run.iterations_completed,
            "items_generated": run.items_generated,
            "duration_seconds": run.duration_seconds,
            "reason": None,
            "details": None,
        }

        # Determine stop reason
        if run.status == RunStatus.COMPLETED:
            if run.error_message:
                result["reason"] = "Completed with limit"
                result["details"] = run.error_message
            else:
                result["reason"] = "Completed successfully"
                result["details"] = f"Completed {run.iterations_completed} iterations"

        elif run.status == RunStatus.ERROR:
            result["reason"] = "Error"
            result["details"] = run.error_message or "Unknown error"

        elif run.status == RunStatus.ABORTED:
            result["reason"] = "Aborted"
            result["details"] = run.error_message or "User interrupt or signal"

        elif run.status == RunStatus.PAUSED:
            result["reason"] = "Paused"
            result["details"] = "Run is currently paused"

        elif run.status == RunStatus.ACTIVE:
            result["reason"] = "Still running or crashed"
            result["details"] = "Run may still be active or process crashed"

            # Check for stale checkpoint
            checkpoint = self.db.get_checkpoint(project.id)
            if checkpoint and checkpoint.get("status") == "in_progress":
                result["reason"] = "Crashed (recoverable)"
                result["details"] = f"Interrupted at iteration {checkpoint.get('iteration')}"

        return result
