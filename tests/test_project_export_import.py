"""Tests for project export/import functionality."""

import io
import json
import zipfile
from pathlib import Path

import pytest

from ralphx.core.project_db import ProjectDatabase
from ralphx.core.project_export import (
    PROJECT_EXPORT_FORMAT_NAME,
    ProjectExporter,
    ProjectExportOptions,
)
from ralphx.core.project_import import (
    ProjectImporter,
    ProjectImportOptions,
)
from ralphx.core.workflow_export import EXPORT_FORMAT_NAME
from ralphx.core.workflow_import import ConflictResolution


@pytest.fixture
def project_db(tmp_path: Path) -> ProjectDatabase:
    """Create a project database for testing."""
    project_path = tmp_path / "test-project"
    project_path.mkdir(parents=True)
    (project_path / ".ralphx").mkdir()

    return ProjectDatabase(project_path)


@pytest.fixture
def project_info() -> dict:
    """Sample project info."""
    return {
        "id": "prj-test-123",
        "slug": "test-project",
        "name": "Test Project",
        "path": "/tmp/test-project",
        "created_at": "2026-01-01T00:00:00Z",
    }


@pytest.fixture
def project_with_workflows(project_db: ProjectDatabase) -> list[dict]:
    """Create a project with multiple workflows."""
    workflows = []

    for i in range(3):
        workflow = project_db.create_workflow(
            id=f"wf-test-{i}",
            name=f"Workflow {i}",
            namespace=f"workflow-{i}",
            template_id="build-product",
            status="active",
        )

        # Create a step for each workflow
        step = project_db.create_workflow_step(
            workflow_id=workflow["id"],
            step_number=1,
            name="Implementation",
            step_type="autonomous",
        )

        # Create items for each workflow
        for j in range(3):
            project_db.create_work_item(
                id=f"WF{i}-ITEM-{j:03d}",
                workflow_id=workflow["id"],
                source_step_id=step["id"],
                content=f"Item {j} for workflow {i}",
                title=f"Item {j}",
                status="pending",
            )

        # Create a resource for each workflow
        project_db.create_workflow_resource(
            workflow_id=workflow["id"],
            resource_type="design_doc",
            name=f"Design Doc {i}",
            content=f"# Design for Workflow {i}",
            source="manual",
        )

        workflows.append(workflow)

    return workflows


class TestProjectExporter:
    """Tests for ProjectExporter."""

    def test_get_preview(
        self,
        project_db: ProjectDatabase,
        project_info: dict,
        project_with_workflows: list[dict],
    ):
        """Test project export preview."""
        exporter = ProjectExporter(project_db, project_info)

        preview = exporter.get_preview()

        assert preview.project_name == "Test Project"
        assert preview.project_slug == "test-project"
        assert len(preview.workflows) == 3
        assert preview.total_items == 9  # 3 workflows × 3 items
        assert preview.total_resources == 3  # 1 per workflow

    def test_get_preview_with_selected_workflows(
        self,
        project_db: ProjectDatabase,
        project_info: dict,
        project_with_workflows: list[dict],
    ):
        """Test preview with workflow filter."""
        exporter = ProjectExporter(project_db, project_info)

        options = ProjectExportOptions(
            workflow_ids=[project_with_workflows[0]["id"]],
        )
        preview = exporter.get_preview(options)

        assert len(preview.workflows) == 1
        assert preview.total_items == 3  # Only 1 workflow

    def test_export_project(
        self,
        project_db: ProjectDatabase,
        project_info: dict,
        project_with_workflows: list[dict],
    ):
        """Test exporting entire project to ZIP."""
        exporter = ProjectExporter(project_db, project_info)

        zip_bytes, filename = exporter.export_project()

        # Check filename format
        assert filename.startswith("project-test-project-")
        assert filename.endswith(".ralphx.zip")

        # Verify ZIP contents
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            names = zf.namelist()

            assert "manifest.json" in names
            assert "project.json" in names

            # Check manifest
            manifest = json.loads(zf.read("manifest.json").decode())
            assert manifest["format"] == PROJECT_EXPORT_FORMAT_NAME
            assert manifest["contents"]["workflows_count"] == 3

            # Check each workflow directory exists
            for wf in project_with_workflows:
                namespace = wf["namespace"]
                assert f"workflows/{namespace}/workflow.json" in names
                assert f"workflows/{namespace}/items.jsonl" in names
                assert f"workflows/{namespace}/resources/resources.json" in names

    def test_export_selected_workflows(
        self,
        project_db: ProjectDatabase,
        project_info: dict,
        project_with_workflows: list[dict],
    ):
        """Test exporting selected workflows."""
        exporter = ProjectExporter(project_db, project_info)

        selected_ids = [project_with_workflows[0]["id"], project_with_workflows[1]["id"]]
        options = ProjectExportOptions(workflow_ids=selected_ids)

        zip_bytes, _ = exporter.export_project(options)

        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            manifest = json.loads(zf.read("manifest.json").decode())
            assert manifest["contents"]["workflows_count"] == 2


class TestProjectImporter:
    """Tests for ProjectImporter."""

    def test_preview_project_export(
        self,
        project_db: ProjectDatabase,
        project_info: dict,
        project_with_workflows: list[dict],
    ):
        """Test previewing a project export."""
        # Export
        exporter = ProjectExporter(project_db, project_info)
        zip_bytes, _ = exporter.export_project()

        # Preview import
        importer = ProjectImporter(project_db)
        preview = importer.get_preview(zip_bytes)

        assert preview.is_project_export
        assert preview.project_name == "Test Project"
        assert len(preview.workflows) == 3
        assert preview.total_items == 9
        assert preview.is_compatible

    def test_preview_single_workflow_export(
        self,
        project_db: ProjectDatabase,
        project_with_workflows: list[dict],
    ):
        """Test previewing a single workflow export (auto-detection)."""
        from ralphx.core.workflow_export import WorkflowExporter

        # Export single workflow
        exporter = WorkflowExporter(project_db)
        zip_bytes, _ = exporter.export_workflow(project_with_workflows[0]["id"])

        # Preview import - should detect as single workflow
        importer = ProjectImporter(project_db)
        preview = importer.get_preview(zip_bytes)

        assert not preview.is_project_export
        assert len(preview.workflows) == 1

    def test_import_project(
        self,
        project_db: ProjectDatabase,
        project_info: dict,
        project_with_workflows: list[dict],
    ):
        """Test importing a project with multiple workflows."""
        # Export
        exporter = ProjectExporter(project_db, project_info)
        zip_bytes, _ = exporter.export_project()

        # Import into same DB (simulating different project)
        importer = ProjectImporter(project_db)
        result = importer.import_project(zip_bytes)

        assert result.success
        assert result.workflows_imported == 3
        assert len(result.workflow_results) == 3

        # Each workflow should have been imported successfully
        for wf_result in result.workflow_results:
            assert wf_result.success
            assert wf_result.items_imported == 3

    def test_import_selected_workflows(
        self,
        project_db: ProjectDatabase,
        project_info: dict,
        project_with_workflows: list[dict],
    ):
        """Test importing only selected workflows."""
        # Export
        exporter = ProjectExporter(project_db, project_info)
        zip_bytes, _ = exporter.export_project()

        # Import only first workflow
        importer = ProjectImporter(project_db)
        options = ProjectImportOptions(
            selected_workflow_ids=[project_with_workflows[0]["id"]],
        )
        result = importer.import_project(zip_bytes, options)

        assert result.success
        assert result.workflows_imported == 1

    def test_import_single_workflow_via_project_importer(
        self,
        project_db: ProjectDatabase,
        project_with_workflows: list[dict],
    ):
        """Test that single workflow exports can be imported via ProjectImporter."""
        from ralphx.core.workflow_export import WorkflowExporter

        # Export single workflow
        exporter = WorkflowExporter(project_db)
        zip_bytes, _ = exporter.export_workflow(project_with_workflows[0]["id"])

        # Import via project importer (should auto-detect)
        importer = ProjectImporter(project_db)
        result = importer.import_project(zip_bytes)

        assert result.success
        assert result.workflows_imported == 1

    def test_import_generates_unique_namespaces(
        self,
        project_db: ProjectDatabase,
        project_info: dict,
        project_with_workflows: list[dict],
    ):
        """Test that importing creates unique namespaces."""
        exporter = ProjectExporter(project_db, project_info)
        zip_bytes, _ = exporter.export_project()

        importer = ProjectImporter(project_db)

        # Import twice
        result1 = importer.import_project(zip_bytes)
        result2 = importer.import_project(zip_bytes)

        # All workflow IDs should be unique
        all_ids = (
            [r.workflow_id for r in result1.workflow_results]
            + [r.workflow_id for r in result2.workflow_results]
        )
        assert len(all_ids) == len(set(all_ids))


class TestProjectRoundTrip:
    """Tests for project export -> import round-trips."""

    def test_round_trip_preserves_workflow_data(
        self,
        project_db: ProjectDatabase,
        project_info: dict,
        project_with_workflows: list[dict],
    ):
        """Test that project export -> import preserves workflow data."""
        # Export
        exporter = ProjectExporter(project_db, project_info)
        zip_bytes, _ = exporter.export_project()

        # Import
        importer = ProjectImporter(project_db)
        result = importer.import_project(zip_bytes)

        # Verify each imported workflow has the correct data
        workflow_names = set()
        for wf_result in result.workflow_results:
            workflow = project_db.get_workflow(wf_result.workflow_id)
            assert workflow is not None
            workflow_names.add(workflow["name"])

            items, _ = project_db.list_work_items(workflow_id=wf_result.workflow_id)
            assert len(items) == 3

            resources = project_db.list_workflow_resources(wf_result.workflow_id)
            assert len(resources) == 1

        # Verify all workflow names were imported (order may vary)
        assert workflow_names == {"Workflow 0", "Workflow 1", "Workflow 2"}


class TestMixedFormatHandling:
    """Tests for handling different export formats."""

    def test_project_importer_handles_both_formats(
        self,
        project_db: ProjectDatabase,
        project_info: dict,
        project_with_workflows: list[dict],
    ):
        """Test that ProjectImporter handles both project and workflow exports."""
        from ralphx.core.workflow_export import WorkflowExporter

        importer = ProjectImporter(project_db)

        # Single workflow export
        wf_exporter = WorkflowExporter(project_db)
        wf_zip, _ = wf_exporter.export_workflow(project_with_workflows[0]["id"])

        wf_preview = importer.get_preview(wf_zip)
        assert not wf_preview.is_project_export

        # Project export
        proj_exporter = ProjectExporter(project_db, project_info)
        proj_zip, _ = proj_exporter.export_project()

        proj_preview = importer.get_preview(proj_zip)
        assert proj_preview.is_project_export


class TestSecurityValidation:
    """Tests for security validation in project import."""

    def test_invalid_zip_rejected(self, project_db: ProjectDatabase):
        """Test that invalid ZIP files are rejected."""
        importer = ProjectImporter(project_db)

        with pytest.raises(ValueError, match="Invalid ZIP"):
            importer.get_preview(b"not a zip file")

    def test_missing_manifest_rejected(self, project_db: ProjectDatabase):
        """Test that ZIP without manifest is rejected."""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("project.json", "{}")

        importer = ProjectImporter(project_db)

        with pytest.raises(ValueError, match="Missing manifest"):
            importer.get_preview(zip_buffer.getvalue())

    def test_path_traversal_blocked(self, project_db: ProjectDatabase):
        """Test that path traversal attacks are blocked."""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("manifest.json", json.dumps({
                "format": PROJECT_EXPORT_FORMAT_NAME,
                "version": "1.0"
            }))
            zf.writestr("../../../malicious.txt", "evil")

        importer = ProjectImporter(project_db)

        with pytest.raises(ValueError, match="Path traversal"):
            importer.get_preview(zip_buffer.getvalue())
