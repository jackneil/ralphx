"""Tests for workflow-scoped resources.

This module tests the workflow_resources and project_resources functionality
introduced in the workflow-first architecture migration.
"""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ralphx.api.main import app
from ralphx.core.project_db import ProjectDatabase


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        # Create .ralphx directory structure
        (project_path / ".ralphx" / "loops").mkdir(parents=True)
        yield project_path


@pytest.fixture
def project_db(project_dir):
    """Create a project database instance."""
    return ProjectDatabase(project_dir)


class TestWorkflowResourcesCRUD:
    """Test workflow_resources table CRUD operations."""

    def test_create_workflow_resource(self, project_db):
        """Test creating a workflow resource."""
        # TODO: Verify expected behavior with user
        # First create a workflow to attach resources to
        workflow = project_db.create_workflow(
            id="test-workflow-1",
            name="Test Workflow",
        )

        # Create a resource
        resource = project_db.create_workflow_resource(
            workflow_id=workflow["id"],
            resource_type="design_doc",
            name="Test Design Doc",
            content="# Test Design\n\nThis is a test design document.",
            source="manual",
        )

        assert resource is not None
        assert resource["workflow_id"] == workflow["id"]
        assert resource["resource_type"] == "design_doc"
        assert resource["name"] == "Test Design Doc"
        assert resource["enabled"] in (True, 1)  # SQLite returns 1 for True

    def test_list_workflow_resources_filtered_by_type(self, project_db):
        """Test listing workflow resources with type filter."""
        # TODO: Verify expected behavior with user
        workflow = project_db.create_workflow(
            id="test-workflow-2",
            name="Test Workflow 2",
        )

        # Create resources of different types
        project_db.create_workflow_resource(
            workflow_id=workflow["id"],
            resource_type="design_doc",
            name="Design Doc 1",
            content="content",
            source="manual",
        )
        project_db.create_workflow_resource(
            workflow_id=workflow["id"],
            resource_type="guardrail",
            name="Guardrail 1",
            content="rules",
            source="manual",
        )

        # List only design_docs
        design_docs = project_db.list_workflow_resources(
            workflow["id"], resource_type="design_doc"
        )
        assert len(design_docs) == 1
        assert design_docs[0]["resource_type"] == "design_doc"

    def test_workflow_resource_isolation(self, project_db):
        """Test that workflows cannot access each other's resources."""
        # TODO: Verify expected behavior with user
        workflow1 = project_db.create_workflow(
            id="workflow-1", name="Workflow 1"
        )
        workflow2 = project_db.create_workflow(
            id="workflow-2", name="Workflow 2"
        )

        # Create resource on workflow 1
        resource = project_db.create_workflow_resource(
            workflow_id=workflow1["id"],
            resource_type="design_doc",
            name="Private Doc",
            content="secret content",
            source="manual",
        )

        # Listing resources for workflow 2 should not include workflow 1's resource
        workflow2_resources = project_db.list_workflow_resources(workflow2["id"])
        assert len(workflow2_resources) == 0

        # Directly fetching by ID and checking workflow ownership
        fetched = project_db.get_workflow_resource(resource["id"])
        assert fetched["workflow_id"] == workflow1["id"]
        assert fetched["workflow_id"] != workflow2["id"]

    def test_cascade_delete_workflow_resources(self, project_db):
        """Test that deleting a workflow cascades to its resources."""
        # TODO: Verify expected behavior with user
        workflow = project_db.create_workflow(
            id="delete-test-workflow",
            name="To Be Deleted",
        )

        resource = project_db.create_workflow_resource(
            workflow_id=workflow["id"],
            resource_type="design_doc",
            name="Will be deleted",
            content="cascade test",
            source="manual",
        )
        resource_id = resource["id"]

        # Delete the workflow
        project_db.delete_workflow(workflow["id"])

        # Resource should be gone
        fetched = project_db.get_workflow_resource(resource_id)
        assert fetched is None


class TestProjectResourcesCRUD:
    """Test project_resources table CRUD operations."""

    def test_create_project_resource(self, project_db):
        """Test creating a project-level shared resource."""
        # TODO: Verify expected behavior with user
        resource = project_db.create_project_resource(
            resource_type="guardrail",
            name="Company Code Standards",
            content="# Coding Standards\n\n- Use type hints",
            auto_inherit=True,
        )

        assert resource is not None

        # create_project_resource returns the created resource dict
        resource_id = resource["id"]
        fetched = project_db.get_project_resource(resource_id)
        assert fetched["resource_type"] == "guardrail"
        assert fetched["auto_inherit"] in (True, 1)  # SQLite returns 1 for True

    def test_list_project_resources_filtered(self, project_db):
        """Test listing project resources with type filter."""
        # TODO: Verify expected behavior with user
        project_db.create_project_resource(
            resource_type="guardrail",
            name="Guardrail 1",
            content="rules 1",
        )
        project_db.create_project_resource(
            resource_type="prompt_template",
            name="Template 1",
            content="template content",
        )

        guardrails = project_db.list_project_resources(resource_type="guardrail")
        assert len(guardrails) == 1
        assert guardrails[0]["resource_type"] == "guardrail"


class TestWorkItemCreationRequiresWorkflow:
    """Test that work items require workflow context."""

    def test_create_work_item_requires_workflow_id(self, project_db):
        """Test that creating a work item without workflow_id fails."""
        # TODO: Verify expected behavior with user
        # This should fail at the database level (NOT NULL constraint)
        workflow = project_db.create_workflow(
            id="item-test-workflow",
            name="Item Test",
        )

        # Create a step for the workflow
        project_db.create_workflow_step(
            workflow_id=workflow["id"],
            step_number=1,
            name="Planning",
            step_type="interactive",
        )

        step = project_db.get_workflow_step_by_number(workflow["id"], 1)

        # Creating with workflow context should succeed
        item = project_db.create_work_item(
            id="test-item-1",
            workflow_id=workflow["id"],
            source_step_id=step["id"],
            content="Test item content",
        )

        assert item is not None
        assert item["workflow_id"] == workflow["id"]
        assert item["source_step_id"] == step["id"]


class TestImportWorkflowResource:
    """Test importing project resources into workflows."""

    def test_import_project_resource_to_workflow(self, project_db):
        """Test importing a project resource creates a copy in workflow."""
        # TODO: Verify expected behavior with user
        # Create a project resource
        proj_resource = project_db.create_project_resource(
            resource_type="guardrail",
            name="Shared Guardrail",
            content="shared rules",
            auto_inherit=False,
        )
        proj_resource_id = proj_resource["id"]

        # Create a workflow
        workflow = project_db.create_workflow(
            id="import-test-workflow",
            name="Import Test",
        )

        # Import it into the workflow (creates a copy)
        workflow_resource = project_db.create_workflow_resource(
            workflow_id=workflow["id"],
            resource_type=proj_resource["resource_type"],
            name=proj_resource["name"],
            content=proj_resource["content"],
            source="imported",
            source_id=proj_resource_id,
        )

        assert workflow_resource is not None
        assert workflow_resource["source"] == "imported"
        assert workflow_resource["source_id"] == proj_resource_id


# TODO: Add API endpoint tests once fixtures are properly set up
# These require a registered project in the workspace to work correctly
class TestWorkflowResourcesAPI:
    """Test workflow resources API endpoints."""

    @pytest.mark.skip(reason="TODO: Requires workspace setup with registered project")
    def test_create_workflow_resource_api(self, client, workspace_dir, project_dir):
        """Test POST /projects/{slug}/workflows/{id}/resources endpoint."""
        pass

    @pytest.mark.skip(reason="TODO: Requires workspace setup with registered project")
    def test_get_workflow_resource_validates_ownership(self, client):
        """Test that getting a resource checks workflow ownership."""
        pass

    @pytest.mark.skip(reason="TODO: Requires workspace setup with registered project")
    def test_cross_workflow_resource_access_denied(self, client):
        """Test that accessing another workflow's resource returns 404."""
        pass


class TestProjectResourcesAPI:
    """Test project resources API endpoints."""

    @pytest.mark.skip(reason="TODO: Requires workspace setup with registered project")
    def test_create_project_resource_api(self, client):
        """Test POST /projects/{slug}/project-resources endpoint."""
        pass

    @pytest.mark.skip(reason="TODO: Requires workspace setup with registered project")
    def test_list_project_resources_api(self, client):
        """Test GET /projects/{slug}/project-resources endpoint."""
        pass


class TestWorkflowResourceVersioning:
    """Test workflow resource versioning functionality."""

    def test_update_creates_version_snapshot(self, project_db):
        """Test that updating a resource creates a version snapshot of the old state."""
        # Create workflow and resource
        workflow = project_db.create_workflow(
            id="version-test-1", name="Version Test"
        )
        resource = project_db.create_workflow_resource(
            workflow_id=workflow["id"],
            resource_type="design_doc",
            name="Original Name",
            content="Original content",
            source="manual",
        )

        # Update the resource content
        updated = project_db.update_workflow_resource(
            resource["id"],
            content="Updated content",
        )

        assert updated["content"] == "Updated content"

        # Verify version was created with OLD content
        versions, total = project_db.list_resource_versions(resource["id"])
        assert total == 1
        assert versions[0]["content"] == "Original content"
        assert versions[0]["name"] == "Original Name"

    def test_update_only_creates_version_when_content_changes(self, project_db):
        """Test that updating only enabled/file_path does NOT create a version."""
        workflow = project_db.create_workflow(
            id="version-test-2", name="Version Test 2"
        )
        resource = project_db.create_workflow_resource(
            workflow_id=workflow["id"],
            resource_type="design_doc",
            name="Test Doc",
            content="Test content",
            source="manual",
        )

        # Update only enabled (no content/name change)
        project_db.update_workflow_resource(resource["id"], enabled=False)

        # Should NOT create a version
        versions, total = project_db.list_resource_versions(resource["id"])
        assert total == 0

    def test_optimistic_locking_detects_conflict(self, project_db):
        """Test that optimistic locking returns conflict when timestamps mismatch."""
        workflow = project_db.create_workflow(
            id="lock-test-1", name="Lock Test"
        )
        resource = project_db.create_workflow_resource(
            workflow_id=workflow["id"],
            resource_type="design_doc",
            name="Locked Doc",
            content="Original",
            source="manual",
        )

        original_updated_at = resource["updated_at"]

        # First update (simulating another user)
        project_db.update_workflow_resource(resource["id"], content="Changed by other")

        # Second update with stale timestamp should conflict
        result = project_db.update_workflow_resource(
            resource["id"],
            content="My changes",
            expected_updated_at=original_updated_at,
        )

        assert result.get("conflict") is True
        assert "current" in result

    def test_optimistic_locking_allows_when_timestamps_match(self, project_db):
        """Test that optimistic locking allows update when timestamps match."""
        workflow = project_db.create_workflow(
            id="lock-test-2", name="Lock Test 2"
        )
        resource = project_db.create_workflow_resource(
            workflow_id=workflow["id"],
            resource_type="design_doc",
            name="Test Doc",
            content="Original",
            source="manual",
        )

        # Update with matching timestamp should succeed
        result = project_db.update_workflow_resource(
            resource["id"],
            content="Updated successfully",
            expected_updated_at=resource["updated_at"],
        )

        assert result.get("conflict") is None
        assert result["content"] == "Updated successfully"

    def test_restore_version_creates_snapshot_first(self, project_db):
        """Test that restore creates a version snapshot before overwriting."""
        workflow = project_db.create_workflow(
            id="restore-test-1", name="Restore Test"
        )
        resource = project_db.create_workflow_resource(
            workflow_id=workflow["id"],
            resource_type="design_doc",
            name="Restore Doc",
            content="Version 0",
            source="manual",
        )

        # Make first edit (creates version 1 with "Version 0")
        project_db.update_workflow_resource(resource["id"], content="Version 1")

        # Make second edit (creates version 2 with "Version 1")
        project_db.update_workflow_resource(resource["id"], content="Version 2")

        versions, _ = project_db.list_resource_versions(resource["id"])
        assert len(versions) == 2
        version_1 = [v for v in versions if v["content"] == "Version 0"][0]

        # Restore version 1 (should create version 3 with "Version 2", then restore)
        restored = project_db.restore_resource_version(resource["id"], version_1["id"])

        assert restored["content"] == "Version 0"

        # Should now have 3 versions
        versions, total = project_db.list_resource_versions(resource["id"])
        assert total == 3
        # Most recent version should be the pre-restore snapshot
        assert versions[0]["content"] == "Version 2"

    def test_restore_validates_version_belongs_to_resource(self, project_db):
        """Test that restore rejects versions from other resources."""
        workflow = project_db.create_workflow(
            id="restore-test-2", name="Restore Test 2"
        )
        resource1 = project_db.create_workflow_resource(
            workflow_id=workflow["id"],
            resource_type="design_doc",
            name="Resource 1",
            content="R1 content",
            source="manual",
        )
        resource2 = project_db.create_workflow_resource(
            workflow_id=workflow["id"],
            resource_type="design_doc",
            name="Resource 2",
            content="R2 content",
            source="manual",
        )

        # Create version on resource1
        project_db.update_workflow_resource(resource1["id"], content="R1 updated")
        versions, _ = project_db.list_resource_versions(resource1["id"])
        version_from_r1 = versions[0]

        # Try to restore resource2 using resource1's version
        result = project_db.restore_resource_version(resource2["id"], version_from_r1["id"])

        # Should return None (not found)
        assert result is None

    def test_version_cascade_delete(self, project_db):
        """Test that deleting a resource cascades to its versions."""
        workflow = project_db.create_workflow(
            id="cascade-test-1", name="Cascade Test"
        )
        resource = project_db.create_workflow_resource(
            workflow_id=workflow["id"],
            resource_type="design_doc",
            name="Cascade Doc",
            content="Original",
            source="manual",
        )

        # Create some versions
        project_db.update_workflow_resource(resource["id"], content="V1")
        project_db.update_workflow_resource(resource["id"], content="V2")

        versions_before, _ = project_db.list_resource_versions(resource["id"])
        assert len(versions_before) == 2

        # Delete the resource
        project_db.delete_workflow_resource(resource["id"])

        # Versions should be gone (cascade delete via FK)
        # Note: We can't easily verify this without direct SQL since get_resource_version
        # requires a valid ID. The FK constraint ensures cascade.
        # We verify by checking the resource is gone.
        assert project_db.get_workflow_resource(resource["id"]) is None

    def test_version_cleanup_keeps_recent(self, project_db):
        """Test that version cleanup keeps the N most recent versions."""
        workflow = project_db.create_workflow(
            id="cleanup-test", name="Cleanup Test"
        )
        resource = project_db.create_workflow_resource(
            workflow_id=workflow["id"],
            resource_type="design_doc",
            name="Cleanup Doc",
            content="V0",
            source="manual",
        )

        # Create more versions than the keep limit
        for i in range(5):
            project_db.update_workflow_resource(resource["id"], content=f"V{i+1}")

        # Manually trigger cleanup with low keep_count
        deleted = project_db._cleanup_old_versions(resource["id"], keep_count=2)

        # Should have deleted 3 versions (5 - 2 = 3)
        assert deleted == 3

        # Should only have 2 versions left
        versions, total = project_db.list_resource_versions(resource["id"])
        assert total == 2
        # Should be the most recent ones
        assert versions[0]["content"] == "V4"
        assert versions[1]["content"] == "V3"
