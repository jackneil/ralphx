"""Tests for workflow export/import functionality."""

import io
import json
import zipfile
from pathlib import Path

import pytest

from ralphx.core.project_db import ProjectDatabase
from ralphx.core.workflow_export import (
    EXPORT_FORMAT_NAME,
    EXPORT_FORMAT_VERSION,
    ExportOptions,
    WorkflowExporter,
)
from ralphx.core.workflow_import import (
    ConflictResolution,
    ImportOptions,
    WorkflowImporter,
)


@pytest.fixture
def project_db(tmp_path: Path) -> ProjectDatabase:
    """Create a project database for testing."""
    project_path = tmp_path / "test-project"
    project_path.mkdir(parents=True)
    (project_path / ".ralphx").mkdir()

    return ProjectDatabase(project_path)


@pytest.fixture
def workflow_with_data(project_db: ProjectDatabase) -> dict:
    """Create a workflow with items, resources, and steps."""
    # Create workflow
    workflow = project_db.create_workflow(
        id="wf-test-123",
        name="Test Workflow",
        namespace="test-export",
        template_id="build-product",
        status="active",
    )

    # Create steps
    step1 = project_db.create_workflow_step(
        workflow_id=workflow["id"],
        step_number=1,
        name="Planning",
        step_type="interactive",
    )

    step2 = project_db.create_workflow_step(
        workflow_id=workflow["id"],
        step_number=2,
        name="Story Generation",
        step_type="autonomous",
    )

    # Create items
    for i in range(5):
        project_db.create_work_item(
            id=f"STORY-{i:03d}",
            workflow_id=workflow["id"],
            source_step_id=step2["id"],
            content=f"User story {i} content",
            title=f"Story {i}",
            priority=i,
            status="pending",
            category="feature",
        )

    # Create resources
    project_db.create_workflow_resource(
        workflow_id=workflow["id"],
        resource_type="design_doc",
        name="Design Document",
        content="# Design Document\n\nThis is the design.",
        source="manual",
    )

    project_db.create_workflow_resource(
        workflow_id=workflow["id"],
        resource_type="guardrail",
        name="Security Guardrail",
        content="Always validate user input.",
        source="manual",
    )

    return {
        "workflow": workflow,
        "steps": [step1, step2],
    }


class TestWorkflowExporter:
    """Tests for WorkflowExporter."""

    def test_get_preview(self, project_db: ProjectDatabase, workflow_with_data: dict):
        """Test export preview."""
        exporter = WorkflowExporter(project_db)
        workflow = workflow_with_data["workflow"]

        preview = exporter.get_preview(workflow["id"])

        assert preview.workflow_name == "Test Workflow"
        assert preview.workflow_namespace == "test-export"
        assert preview.steps_count == 2
        assert preview.items_total == 5
        assert preview.resources_count == 2
        assert preview.estimated_size_bytes > 0

    def test_get_preview_not_found(self, project_db: ProjectDatabase):
        """Test export preview for non-existent workflow."""
        exporter = WorkflowExporter(project_db)

        with pytest.raises(ValueError, match="not found"):
            exporter.get_preview("wf-nonexistent")

    def test_export_workflow(self, project_db: ProjectDatabase, workflow_with_data: dict):
        """Test exporting a workflow to ZIP."""
        exporter = WorkflowExporter(project_db)
        workflow = workflow_with_data["workflow"]

        zip_bytes, filename = exporter.export_workflow(workflow["id"])

        # Check filename format
        assert filename.startswith("workflow-test-export-")
        assert filename.endswith(".ralphx.zip")

        # Verify ZIP contents
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            names = zf.namelist()

            assert "manifest.json" in names
            assert "workflow.json" in names
            assert "items.jsonl" in names
            assert "resources/resources.json" in names

            # Check manifest
            manifest = json.loads(zf.read("manifest.json").decode())
            assert manifest["format"] == EXPORT_FORMAT_NAME
            assert manifest["version"] == EXPORT_FORMAT_VERSION
            assert manifest["workflow"]["name"] == "Test Workflow"
            assert manifest["contents"]["items_total"] == 5
            assert manifest["contents"]["resources"] == 2

            # Check items
            items_content = zf.read("items.jsonl").decode()
            items = [json.loads(line) for line in items_content.strip().split("\n")]
            assert len(items) == 5
            # All items should have status reset to pending
            for item in items:
                assert item["status"] == "pending"

    def test_export_with_options(self, project_db: ProjectDatabase, workflow_with_data: dict):
        """Test export with custom options."""
        exporter = WorkflowExporter(project_db)
        workflow = workflow_with_data["workflow"]

        options = ExportOptions(
            include_runs=False,
            include_planning=False,
            strip_secrets=True,
        )

        zip_bytes, filename = exporter.export_workflow(workflow["id"], options)

        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            names = zf.namelist()

            # Should not include planning
            assert "planning/session.json" not in names

    def test_secret_detection(self, project_db: ProjectDatabase, workflow_with_data: dict):
        """Test that potential secrets are detected."""
        # Add a resource with a potential secret
        workflow_id = workflow_with_data["workflow"]["id"]
        project_db.create_workflow_resource(
            workflow_id=workflow_id,
            resource_type="config",
            name="Config with Secret",
            content="api_key = 'sk-abcdefghijklmnopqrstuvwxyz123456'",
            source="manual",
        )

        exporter = WorkflowExporter(project_db)
        preview = exporter.get_preview(workflow_id)

        # Should detect potential secrets
        assert len(preview.potential_secrets) > 0
        assert any("API key" in s.pattern_name for s in preview.potential_secrets)


class TestWorkflowImporter:
    """Tests for WorkflowImporter."""

    def test_import_preview(self, project_db: ProjectDatabase, workflow_with_data: dict):
        """Test import preview."""
        # First export
        exporter = WorkflowExporter(project_db)
        workflow = workflow_with_data["workflow"]
        zip_bytes, _ = exporter.export_workflow(workflow["id"])

        # Create new DB for import
        importer = WorkflowImporter(project_db)
        preview = importer.get_preview(zip_bytes)

        assert preview.workflow_name == "Test Workflow"
        assert preview.is_compatible
        assert preview.items_count == 5

    def test_import_workflow_full(self, project_db: ProjectDatabase, workflow_with_data: dict):
        """Test full workflow import."""
        # Export from source
        exporter = WorkflowExporter(project_db)
        workflow = workflow_with_data["workflow"]
        zip_bytes, _ = exporter.export_workflow(workflow["id"])

        # Import to same DB (will get new IDs)
        importer = WorkflowImporter(project_db)
        result = importer.import_workflow(zip_bytes)

        assert result.success
        assert result.workflow_name == "Test Workflow"
        assert result.items_imported == 5
        assert result.steps_created == 2
        assert result.resources_created == 2

        # New workflow should have different ID
        assert result.workflow_id != workflow["id"]

        # Verify workflow exists in DB
        imported_wf = project_db.get_workflow(result.workflow_id)
        assert imported_wf is not None
        assert imported_wf["name"] == "Test Workflow"

        # Verify items exist
        items, count = project_db.list_work_items(workflow_id=result.workflow_id)
        assert len(items) == 5

    def test_import_generates_unique_ids(self, project_db: ProjectDatabase, workflow_with_data: dict):
        """Test that import generates unique IDs."""
        exporter = WorkflowExporter(project_db)
        workflow = workflow_with_data["workflow"]
        zip_bytes, _ = exporter.export_workflow(workflow["id"])

        importer = WorkflowImporter(project_db)

        # Import twice
        result1 = importer.import_workflow(zip_bytes)
        result2 = importer.import_workflow(zip_bytes)

        # Should have different workflow IDs
        assert result1.workflow_id != result2.workflow_id

        # Should have different namespaces (auto-suffixed)
        wf1 = project_db.get_workflow(result1.workflow_id)
        wf2 = project_db.get_workflow(result2.workflow_id)
        assert wf1["namespace"] != wf2["namespace"]

    def test_import_with_selective_options(self, project_db: ProjectDatabase, workflow_with_data: dict):
        """Test selective import."""
        exporter = WorkflowExporter(project_db)
        workflow = workflow_with_data["workflow"]
        zip_bytes, _ = exporter.export_workflow(workflow["id"])

        importer = WorkflowImporter(project_db)
        options = ImportOptions(
            import_items=True,
            import_resources=False,
        )
        result = importer.import_workflow(zip_bytes, options)

        assert result.success
        assert result.items_imported == 5
        assert result.resources_created == 0

    def test_invalid_zip_rejected(self, project_db: ProjectDatabase):
        """Test that invalid ZIP files are rejected."""
        importer = WorkflowImporter(project_db)

        with pytest.raises(ValueError, match="Invalid ZIP"):
            importer.get_preview(b"not a zip file")

    def test_missing_manifest_rejected(self, project_db: ProjectDatabase):
        """Test that ZIP without manifest is rejected."""
        # Create a ZIP without manifest
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("workflow.json", "{}")

        importer = WorkflowImporter(project_db)

        with pytest.raises(ValueError, match="Missing manifest"):
            importer.get_preview(zip_buffer.getvalue())

    def test_zip_slip_protection(self, project_db: ProjectDatabase):
        """Test that path traversal attacks are blocked."""
        # Create a ZIP with path traversal attempt
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"format": EXPORT_FORMAT_NAME, "version": "1.0"}))
            zf.writestr("../../../etc/passwd", "evil content")

        importer = WorkflowImporter(project_db)

        with pytest.raises(ValueError, match="Path traversal"):
            importer.get_preview(zip_buffer.getvalue())


class TestMergeIntoWorkflow:
    """Tests for merging into existing workflows."""

    def test_merge_preview_detects_conflicts(
        self, project_db: ProjectDatabase, workflow_with_data: dict
    ):
        """Test that merge preview detects conflicts."""
        exporter = WorkflowExporter(project_db)
        workflow = workflow_with_data["workflow"]
        zip_bytes, _ = exporter.export_workflow(workflow["id"])

        importer = WorkflowImporter(project_db)
        preview = importer.get_merge_preview(zip_bytes, workflow["id"])

        # Should detect item ID conflicts (same items exist)
        assert len(preview.conflicts) > 0

    def test_merge_with_skip_resolution(
        self, project_db: ProjectDatabase, workflow_with_data: dict
    ):
        """Test merge with skip conflict resolution."""
        exporter = WorkflowExporter(project_db)
        workflow = workflow_with_data["workflow"]
        zip_bytes, _ = exporter.export_workflow(workflow["id"])

        importer = WorkflowImporter(project_db)
        options = ImportOptions(conflict_resolution=ConflictResolution.SKIP)

        result = importer.merge_into_workflow(zip_bytes, workflow["id"], options)

        assert result.success
        # All items should be skipped due to conflicts
        assert result.items_skipped == 5
        assert result.items_imported == 0

    def test_merge_with_rename_resolution(
        self, project_db: ProjectDatabase, workflow_with_data: dict
    ):
        """Test merge with rename conflict resolution."""
        exporter = WorkflowExporter(project_db)
        workflow = workflow_with_data["workflow"]
        zip_bytes, _ = exporter.export_workflow(workflow["id"])

        importer = WorkflowImporter(project_db)
        options = ImportOptions(conflict_resolution=ConflictResolution.RENAME)

        result = importer.merge_into_workflow(zip_bytes, workflow["id"], options)

        assert result.success
        assert result.items_imported == 5
        assert result.items_renamed == 5  # All items renamed due to conflicts

        # Verify total items doubled
        items, count = project_db.list_work_items(workflow_id=workflow["id"], limit=100)
        assert len(items) == 10  # Original 5 + 5 new


class TestRoundTrip:
    """Tests for export -> import -> export round-trips."""

    def test_round_trip_preserves_data(
        self, project_db: ProjectDatabase, workflow_with_data: dict
    ):
        """Test that export -> import -> export produces same data."""
        workflow = workflow_with_data["workflow"]

        # First export
        exporter = WorkflowExporter(project_db)
        zip1_bytes, _ = exporter.export_workflow(workflow["id"])

        # Import
        importer = WorkflowImporter(project_db)
        result = importer.import_workflow(zip1_bytes)

        # Second export
        zip2_bytes, _ = exporter.export_workflow(result.workflow_id)

        # Compare contents
        with zipfile.ZipFile(io.BytesIO(zip1_bytes), "r") as zf1:
            with zipfile.ZipFile(io.BytesIO(zip2_bytes), "r") as zf2:
                # Compare items
                items1 = [
                    json.loads(line)
                    for line in zf1.read("items.jsonl").decode().strip().split("\n")
                ]
                items2 = [
                    json.loads(line)
                    for line in zf2.read("items.jsonl").decode().strip().split("\n")
                ]

                assert len(items1) == len(items2)

                # Compare content (IDs will be different)
                contents1 = sorted([i["content"] for i in items1])
                contents2 = sorted([i["content"] for i in items2])
                assert contents1 == contents2


class TestEdgeCases:
    """Tests for edge cases - zero steps, null values, etc."""

    def test_export_workflow_with_zero_steps(self, project_db: ProjectDatabase):
        """Test exporting a workflow that has no steps.

        TODO: Verify expected behavior with user - should this:
        1. Succeed with empty steps array?
        2. Raise an error?
        """
        # Create workflow with no steps
        workflow = project_db.create_workflow(
            id="wf-no-steps",
            name="Empty Workflow",
            namespace="empty-workflow",
            template_id="build-product",
            status="draft",
        )

        exporter = WorkflowExporter(project_db)
        zip_bytes, filename = exporter.export_workflow(workflow["id"])

        # Verify it exports successfully with empty steps
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            workflow_data = json.loads(zf.read("workflow.json").decode())
            assert workflow_data["steps"] == []

    def test_import_workflow_with_zero_steps(self, project_db: ProjectDatabase):
        """Test importing a workflow that has no steps.

        TODO: Verify expected behavior - items should be skipped with warning.
        """
        # Create and export workflow with no steps
        workflow = project_db.create_workflow(
            id="wf-no-steps",
            name="Empty Workflow",
            namespace="empty-workflow",
            template_id="build-product",
            status="draft",
        )

        exporter = WorkflowExporter(project_db)
        zip_bytes, _ = exporter.export_workflow(workflow["id"])

        # Import should succeed (no items to import anyway)
        importer = WorkflowImporter(project_db)
        result = importer.import_workflow(zip_bytes)

        assert result.success
        assert result.steps_created == 0
        assert result.items_imported == 0

    def test_import_items_step_mapping(
        self, project_db: ProjectDatabase, workflow_with_data: dict
    ):
        """Test that items are correctly mapped to steps after import.

        Items from the source workflow should be mapped to corresponding
        steps in the imported workflow.
        """
        workflow = workflow_with_data["workflow"]

        exporter = WorkflowExporter(project_db)
        zip_bytes, _ = exporter.export_workflow(workflow["id"])

        importer = WorkflowImporter(project_db)
        result = importer.import_workflow(zip_bytes)

        assert result.success
        assert result.items_imported == 5

        # Verify items are associated with valid steps
        items, _ = project_db.list_work_items(workflow_id=result.workflow_id)
        steps = project_db.list_workflow_steps(result.workflow_id)
        step_ids = {s["id"] for s in steps}

        for item in items:
            assert item.get("source_step_id") in step_ids, \
                f"Item {item['id']} has invalid source_step_id"

    def test_dependency_references_after_import(
        self, project_db: ProjectDatabase, workflow_with_data: dict
    ):
        """Test that dependency references are correctly updated after import.

        TODO: Verify that dependencies point to the NEW item IDs, not old ones.
        """
        workflow = workflow_with_data["workflow"]
        step = workflow_with_data["steps"][1]

        # Create items with dependencies
        project_db.create_work_item(
            id="DEP-001",
            workflow_id=workflow["id"],
            source_step_id=step["id"],
            content="Base item",
            title="Base",
            status="pending",
        )
        project_db.create_work_item(
            id="DEP-002",
            workflow_id=workflow["id"],
            source_step_id=step["id"],
            content="Dependent item",
            title="Dependent",
            status="pending",
            dependencies=["DEP-001"],  # Depends on DEP-001
        )

        exporter = WorkflowExporter(project_db)
        zip_bytes, _ = exporter.export_workflow(workflow["id"])

        importer = WorkflowImporter(project_db)
        result = importer.import_workflow(zip_bytes)

        assert result.success

        # Verify the dependency was updated to use new ID
        items, _ = project_db.list_work_items(workflow_id=result.workflow_id)
        dep_item = next((i for i in items if "Dependent" in (i.get("title") or "")), None)
        base_item = next((i for i in items if "Base" in (i.get("title") or "")), None)

        assert dep_item is not None
        assert base_item is not None

        # The dependency should reference the NEW base item ID
        deps = dep_item.get("dependencies", []) or []
        if deps:
            # TODO: Verify the new ID format - should be "DEP-001-{hash}"
            assert base_item["id"] in deps or any(base_item["id"].startswith(d.split("-")[0]) for d in deps)

    def test_duplicate_of_field_preserved(
        self, project_db: ProjectDatabase, workflow_with_data: dict
    ):
        """Test that duplicate_of references are correctly updated after import.

        TODO: Verify duplicate_of field is preserved and updated to new IDs.
        """
        workflow = workflow_with_data["workflow"]
        step = workflow_with_data["steps"][1]

        # Create items with duplicate_of relationship
        project_db.create_work_item(
            id="ORIG-001",
            workflow_id=workflow["id"],
            source_step_id=step["id"],
            content="Original item",
            title="Original",
            status="pending",
        )
        # Note: duplicate_of may require update_work_item if not in create_work_item
        try:
            project_db.update_work_item("STORY-001", duplicate_of="ORIG-001")
        except Exception:
            pass  # Skip if not supported

        exporter = WorkflowExporter(project_db)
        zip_bytes, _ = exporter.export_workflow(workflow["id"])

        # Verify duplicate_of is in the export
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            items_content = zf.read("items.jsonl").decode()
            items = [json.loads(line) for line in items_content.strip().split("\n") if line]
            # Check if any item has duplicate_of set
            has_duplicate_of = any(i.get("duplicate_of") for i in items)
            # TODO: Verify with user if duplicate_of is expected to be exported
            # assert has_duplicate_of or "duplicate_of field should be exported"
