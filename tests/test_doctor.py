"""Tests for RalphX doctor and diagnostics."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ralphx.core.database import Database
from ralphx.core.doctor import (
    CheckResult,
    CheckStatus,
    DiagnosticReport,
    DoctorCheck,
    ProjectDiagnostics,
)
from ralphx.models.project import Project
from ralphx.models.run import RunStatus


@pytest.fixture
def db():
    """Create in-memory database."""
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture
def project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def project(db, project_dir):
    """Create a test project."""
    db.create_project(
        id="proj-123",
        slug="test",
        name="Test Project",
        path=str(project_dir),
    )
    return Project(
        id="proj-123",
        slug="test",
        name="Test Project",
        path=project_dir,
    )


class TestCheckResult:
    """Test CheckResult dataclass."""

    def test_basic_result(self):
        """Test creating a basic result."""
        result = CheckResult(
            name="Test check",
            status=CheckStatus.OK,
            message="All good",
        )
        assert result.name == "Test check"
        assert result.status == CheckStatus.OK
        assert result.message == "All good"
        assert result.details is None
        assert result.fix_hint is None

    def test_result_with_details(self):
        """Test result with details and fix hint."""
        result = CheckResult(
            name="Test check",
            status=CheckStatus.ERROR,
            message="Failed",
            details="Something went wrong",
            fix_hint="Try again",
        )
        assert result.details == "Something went wrong"
        assert result.fix_hint == "Try again"


class TestDiagnosticReport:
    """Test DiagnosticReport dataclass."""

    def test_empty_report(self):
        """Test empty report properties."""
        report = DiagnosticReport()
        assert report.has_errors is False
        assert report.has_warnings is False
        assert report.all_ok is True
        assert report.summary() == "0 passed, 0 warnings, 0 errors"

    def test_report_with_checks(self):
        """Test report with various checks."""
        report = DiagnosticReport(checks=[
            CheckResult("Check 1", CheckStatus.OK, "OK"),
            CheckResult("Check 2", CheckStatus.WARNING, "Warn"),
            CheckResult("Check 3", CheckStatus.ERROR, "Error"),
        ])
        assert report.has_errors is True
        assert report.has_warnings is True
        assert report.all_ok is False
        assert report.summary() == "1 passed, 1 warnings, 1 errors"

    def test_all_ok_report(self):
        """Test report with all OK checks."""
        report = DiagnosticReport(checks=[
            CheckResult("Check 1", CheckStatus.OK, "OK"),
            CheckResult("Check 2", CheckStatus.OK, "OK"),
        ])
        assert report.all_ok is True
        assert report.has_errors is False
        assert report.has_warnings is False


class TestDoctorCheck:
    """Test DoctorCheck functionality."""

    def test_check_python_version(self):
        """Test Python version check."""
        doc = DoctorCheck()
        doc._results = []
        doc._check_python_version()

        assert len(doc._results) == 1
        # Should be OK since we're running Python 3.11+
        assert doc._results[0].status == CheckStatus.OK

    def test_check_workspace_not_exists(self):
        """Test workspace check when not initialized."""
        with patch("ralphx.core.doctor.workspace_exists", return_value=False):
            doc = DoctorCheck()
            doc._results = []
            doc._check_workspace()

            assert len(doc._results) == 1
            assert doc._results[0].status == CheckStatus.OK
            assert "Not initialized" in doc._results[0].message

    def test_check_workspace_exists_writable(self):
        """Test workspace check when exists and writable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("ralphx.core.doctor.workspace_exists", return_value=True):
                with patch("ralphx.core.doctor.get_workspace_path", return_value=Path(tmpdir)):
                    doc = DoctorCheck()
                    doc._results = []
                    doc._check_workspace()

                    assert len(doc._results) == 1
                    assert doc._results[0].status == CheckStatus.OK
                    assert "Writable" in doc._results[0].message

    def test_check_network_success(self):
        """Test network check success."""
        with patch("socket.create_connection"):
            doc = DoctorCheck()
            doc._results = []
            doc._check_network()

            assert len(doc._results) == 1
            assert doc._results[0].status == CheckStatus.OK

    def test_check_network_failure(self):
        """Test network check failure."""
        import socket
        with patch("socket.create_connection", side_effect=socket.timeout()):
            doc = DoctorCheck()
            doc._results = []
            doc._check_network()

            assert len(doc._results) == 1
            assert doc._results[0].status == CheckStatus.WARNING

    def test_check_nodejs_found(self):
        """Test Node.js check when installed."""
        with patch("shutil.which", return_value="/usr/bin/node"):
            mock_result = MagicMock()
            mock_result.stdout = "v18.0.0\n"
            mock_result.returncode = 0

            with patch("subprocess.run", return_value=mock_result):
                doc = DoctorCheck()
                doc._results = []
                doc._check_nodejs()

                assert len(doc._results) == 1
                assert doc._results[0].status == CheckStatus.OK
                assert "v18.0.0" in doc._results[0].message

    def test_check_nodejs_not_found(self):
        """Test Node.js check when not installed."""
        with patch("shutil.which", return_value=None):
            doc = DoctorCheck()
            doc._results = []
            doc._check_nodejs()

            assert len(doc._results) == 1
            assert doc._results[0].status == CheckStatus.WARNING

    def test_check_claude_cli_found(self):
        """Test Claude CLI check when installed."""
        with patch("shutil.which", return_value="/usr/bin/claude"):
            mock_result = MagicMock()
            mock_result.stdout = "claude-code 1.0.0\n"
            mock_result.returncode = 0

            with patch("subprocess.run", return_value=mock_result):
                doc = DoctorCheck()
                doc._results = []
                doc._check_claude_cli()

                assert len(doc._results) == 1
                assert doc._results[0].status == CheckStatus.OK

    def test_check_claude_cli_not_found(self):
        """Test Claude CLI check when not installed."""
        with patch("shutil.which", return_value=None):
            doc = DoctorCheck()
            doc._results = []
            doc._check_claude_cli()

            assert len(doc._results) == 1
            assert doc._results[0].status == CheckStatus.ERROR

    def test_run_all(self):
        """Test running all checks."""
        doc = DoctorCheck()
        report = doc.run_all()

        # Should have at least 7 checks
        assert len(report.checks) >= 7


class TestProjectDiagnostics:
    """Test ProjectDiagnostics functionality."""

    def test_diagnose_project_path_exists(self, db, project):
        """Test diagnosing project with existing path."""
        diag = ProjectDiagnostics(db)
        report = diag.diagnose(project)

        path_check = next(c for c in report.checks if c.name == "Project path")
        assert path_check.status == CheckStatus.OK

    def test_diagnose_project_path_missing(self, db):
        """Test diagnosing project with missing path."""
        project = Project(
            id="proj-123",
            slug="test",
            name="Test",
            path=Path("/nonexistent/path"),
        )
        diag = ProjectDiagnostics(db)
        report = diag.diagnose(project)

        path_check = next(c for c in report.checks if c.name == "Project path")
        assert path_check.status == CheckStatus.ERROR

    def test_diagnose_no_loops(self, db, project):
        """Test diagnosing project with no loops."""
        diag = ProjectDiagnostics(db)
        report = diag.diagnose(project)

        loops_check = next(c for c in report.checks if c.name == "Loops")
        assert loops_check.status == CheckStatus.WARNING
        assert "No loops" in loops_check.message

    def test_diagnose_with_loops(self, db, project):
        """Test diagnosing project with loops."""
        db.create_loop(
            id="loop-123",
            project_id=project.id,
            name="research",
            config_yaml="name: research\ntype: generator",
        )

        diag = ProjectDiagnostics(db)
        report = diag.diagnose(project)

        loops_check = next(c for c in report.checks if c.name == "Loops")
        assert loops_check.status == CheckStatus.OK
        assert "1 loops" in loops_check.message

    def test_diagnose_with_design_doc(self, db, project_dir, project):
        """Test diagnosing project with design doc."""
        design_path = project_dir / "DESIGN.md"
        design_path.write_text("# Design")

        project_with_doc = Project(
            id=project.id,
            slug=project.slug,
            name=project.name,
            path=project.path,
            design_doc="DESIGN.md",
        )

        diag = ProjectDiagnostics(db)
        report = diag.diagnose(project_with_doc)

        doc_check = next(c for c in report.checks if c.name == "Design doc")
        assert doc_check.status == CheckStatus.OK

    def test_why_stopped_no_runs(self, db, project):
        """Test why_stopped with no runs."""
        diag = ProjectDiagnostics(db)
        result = diag.why_stopped(project)
        assert result is None

    def test_why_stopped_completed_run(self, db, project):
        """Test why_stopped with completed run."""
        db.create_run(
            id="run-123",
            project_id=project.id,
            loop_name="research",
            status="completed",
        )
        db.update_run(
            "run-123",
            completed_at=datetime.utcnow().isoformat(),
            iterations_completed=10,
            items_generated=5,
        )

        diag = ProjectDiagnostics(db)
        result = diag.why_stopped(project)

        assert result is not None
        assert result["run_id"] == "run-123"
        assert result["status"] == "completed"
        assert result["reason"] == "Completed successfully"

    def test_why_stopped_error_run(self, db, project):
        """Test why_stopped with error run."""
        db.create_run(
            id="run-123",
            project_id=project.id,
            loop_name="research",
            status="error",
        )
        db.update_run(
            "run-123",
            error_message="API rate limit exceeded",
        )

        diag = ProjectDiagnostics(db)
        result = diag.why_stopped(project)

        assert result is not None
        assert result["reason"] == "Error"
        assert "rate limit" in result["details"]

    def test_why_stopped_aborted_run(self, db, project):
        """Test why_stopped with aborted run."""
        db.create_run(
            id="run-123",
            project_id=project.id,
            loop_name="research",
            status="aborted",
        )

        diag = ProjectDiagnostics(db)
        result = diag.why_stopped(project)

        assert result is not None
        assert result["reason"] == "Aborted"


class TestCheckStatus:
    """Test CheckStatus enum."""

    def test_all_statuses(self):
        """Test all status values."""
        assert CheckStatus.OK.value == "ok"
        assert CheckStatus.WARNING.value == "warning"
        assert CheckStatus.ERROR.value == "error"
        assert CheckStatus.SKIPPED.value == "skipped"


class TestStaleRunDetection:
    """Test stale run detection and cleanup.

    These tests verify the detect_stale_runs() and cleanup_stale_runs() functions
    that identify and clean up runs that appear stuck or crashed.
    """

    @pytest.fixture
    def project_db(self, project_dir):
        """Create a ProjectDatabase for testing."""
        from ralphx.core.project_db import ProjectDatabase
        db = ProjectDatabase(project_dir)
        yield db
        # Cleanup handled by tempdir fixture

    def _create_test_run(self, project_db, run_id: str, status: str = "running"):
        """Helper to create a test run with proper schema."""
        from datetime import datetime
        # ProjectDatabase.create_run always creates with status='running'
        project_db.create_run(
            id=run_id,
            loop_name="test-loop",
            workflow_id="wf-1",
            step_id=1,
        )
        # Update status if not running
        if status != "running":
            project_db.update_run(run_id, status=status)

    def test_detect_stale_run_pid_not_running(self, project_db):
        """Test detection when executor PID is not running.

        TODO: Verify expected behavior with user - should a run with dead PID
        always be marked stale regardless of activity timestamp?
        """
        from ralphx.core.doctor import detect_stale_runs
        from datetime import datetime, timedelta

        # Create a run with a PID that doesn't exist
        now = datetime.utcnow()
        self._create_test_run(project_db, "run-stale-pid")
        project_db.update_run(
            "run-stale-pid",
            executor_pid=999999,  # Very unlikely to be a real PID
            last_activity_at=now.isoformat(),
        )

        with patch("ralphx.core.doctor.is_pid_running", return_value=False):
            stale = detect_stale_runs(project_db, max_inactivity_minutes=15)

        assert len(stale) == 1
        assert stale[0]["run_id"] == "run-stale-pid"
        assert "not running" in stale[0]["reason"]

    def test_detect_stale_run_activity_timeout(self, project_db):
        """Test detection when activity is older than threshold."""
        from ralphx.core.doctor import detect_stale_runs
        from datetime import datetime, timedelta

        # Create a run with old activity timestamp
        old_time = datetime.utcnow() - timedelta(minutes=30)
        self._create_test_run(project_db, "run-stale-activity")
        project_db.update_run(
            "run-stale-activity",
            last_activity_at=old_time.isoformat(),
            # No PID set - simulates case where we only have activity tracking
        )

        stale = detect_stale_runs(project_db, max_inactivity_minutes=15)

        assert len(stale) == 1
        assert stale[0]["run_id"] == "run-stale-activity"
        assert "No activity since" in stale[0]["reason"]

    def test_detect_stale_run_legacy_no_tracking(self, project_db):
        """Test detection of legacy runs without PID or activity tracking."""
        from ralphx.core.doctor import detect_stale_runs
        from datetime import datetime, timedelta

        # Create an old run with no PID or activity tracking (legacy)
        old_time = datetime.utcnow() - timedelta(hours=2)
        self._create_test_run(project_db, "run-legacy")
        # Manually update started_at to be old (simulating legacy run)
        with project_db._writer() as conn:
            conn.execute(
                "UPDATE runs SET started_at = ?, last_activity_at = NULL WHERE id = ?",
                (old_time.isoformat(), "run-legacy"),
            )

        stale = detect_stale_runs(project_db, max_inactivity_minutes=15)

        assert len(stale) == 1
        assert stale[0]["run_id"] == "run-legacy"
        assert "Legacy run" in stale[0]["reason"]

    def test_detect_stale_run_pid_reuse_scenario(self, project_db):
        """Test detection when PID appears running but activity is very stale.

        This handles the PID reuse case where the original executor died but
        another process got the same PID.

        TODO: Verify with user that 2x threshold for PID reuse detection is acceptable.
        """
        from ralphx.core.doctor import detect_stale_runs
        from datetime import datetime, timedelta

        # Create a run with very old activity but "running" PID
        very_old_time = datetime.utcnow() - timedelta(minutes=60)  # 60 min old
        self._create_test_run(project_db, "run-pid-reuse")
        project_db.update_run(
            "run-pid-reuse",
            executor_pid=12345,
            last_activity_at=very_old_time.isoformat(),
        )

        # PID appears to be running (could be reused by another process)
        with patch("ralphx.core.doctor.is_pid_running", return_value=True):
            stale = detect_stale_runs(project_db, max_inactivity_minutes=15)

        # Should be detected as stale because activity is 2x threshold
        assert len(stale) == 1
        assert stale[0]["run_id"] == "run-pid-reuse"
        assert "may be reused" in stale[0]["reason"]

    def test_active_run_not_detected_as_stale(self, project_db):
        """Test that active runs are NOT marked as stale."""
        from ralphx.core.doctor import detect_stale_runs
        from datetime import datetime
        import os

        # Create a run with current activity and our real PID
        now = datetime.utcnow()
        self._create_test_run(project_db, "run-active")
        project_db.update_run(
            "run-active",
            executor_pid=os.getpid(),  # Use our real PID
            last_activity_at=now.isoformat(),
        )

        stale = detect_stale_runs(project_db, max_inactivity_minutes=15)

        assert len(stale) == 0

    def test_cleanup_stale_runs_updates_status(self, project_db):
        """Test that cleanup marks stale runs as aborted."""
        from ralphx.core.doctor import cleanup_stale_runs
        from datetime import datetime, timedelta

        # Create a stale run
        old_time = datetime.utcnow() - timedelta(minutes=30)
        self._create_test_run(project_db, "run-to-cleanup")
        project_db.update_run(
            "run-to-cleanup",
            last_activity_at=old_time.isoformat(),
        )

        cleaned = cleanup_stale_runs(project_db, max_inactivity_minutes=15)

        assert len(cleaned) == 1

        # Verify the run was actually updated
        runs = project_db.list_runs()
        run = next(r for r in runs if r["id"] == "run-to-cleanup")
        assert run["status"] == "aborted"
        assert "Marked stale" in run["error_message"]

    def test_cleanup_stale_runs_dry_run(self, project_db):
        """Test that dry_run mode doesn't modify anything."""
        from ralphx.core.doctor import cleanup_stale_runs
        from datetime import datetime, timedelta

        # Create a stale run
        old_time = datetime.utcnow() - timedelta(minutes=30)
        self._create_test_run(project_db, "run-dry-run")
        project_db.update_run(
            "run-dry-run",
            last_activity_at=old_time.isoformat(),
        )

        cleaned = cleanup_stale_runs(project_db, max_inactivity_minutes=15, dry_run=True)

        assert len(cleaned) == 1

        # Verify the run was NOT updated
        runs = project_db.list_runs()
        run = next(r for r in runs if r["id"] == "run-dry-run")
        assert run["status"] == "running"  # Still running

    def test_completed_runs_not_affected(self, project_db):
        """Test that already completed runs are not detected as stale."""
        from ralphx.core.doctor import detect_stale_runs
        from datetime import datetime, timedelta

        # Create a completed run with old activity
        old_time = datetime.utcnow() - timedelta(hours=2)
        self._create_test_run(project_db, "run-completed", status="completed")
        project_db.update_run(
            "run-completed",
            last_activity_at=old_time.isoformat(),
            completed_at=old_time.isoformat(),
        )

        stale = detect_stale_runs(project_db, max_inactivity_minutes=15)

        assert len(stale) == 0

    def test_paused_runs_can_be_stale(self, project_db):
        """Test that paused runs with no activity can be marked stale."""
        from ralphx.core.doctor import detect_stale_runs
        from datetime import datetime, timedelta

        # Create a paused run with old activity
        old_time = datetime.utcnow() - timedelta(minutes=30)
        self._create_test_run(project_db, "run-paused-stale", status="paused")
        project_db.update_run(
            "run-paused-stale",
            last_activity_at=old_time.isoformat(),
        )

        stale = detect_stale_runs(project_db, max_inactivity_minutes=15)

        assert len(stale) == 1
        assert stale[0]["run_id"] == "run-paused-stale"

    # TODO: Test concurrent cleanup calls - need to verify SQLite handles
    # concurrent writes correctly. May need explicit locking if issues arise.

    # TODO: Test very long running legitimate tasks (>15 min between updates).
    # Current implementation may false positive if Claude iteration takes too long.
    # Consider: should we also check if any subprocess is actively running?
