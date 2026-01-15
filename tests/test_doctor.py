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
