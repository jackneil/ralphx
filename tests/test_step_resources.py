"""Tests for step resources functionality."""

import tempfile
import uuid
from pathlib import Path
import pytest
from ralphx.core.project_db import ProjectDatabase


@pytest.fixture
def project_db():
    """Create a temporary project database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        (project_path / ".ralphx").mkdir(parents=True)
        db = ProjectDatabase(project_path)
        yield db


@pytest.fixture
def workflow_with_step(project_db):
    """Create a workflow with an autonomous step and a workflow resource."""
    # Create workflow
    workflow_id = str(uuid.uuid4())[:8]
    workflow = project_db.create_workflow(
        id=workflow_id,
        name="Test Workflow",
    )

    # Create a step
    step = project_db.create_workflow_step(
        workflow_id=workflow["id"],
        step_number=1,
        name="Implementation",
        step_type="autonomous",
    )

    # Create a workflow resource
    resource = project_db.create_workflow_resource(
        workflow_id=workflow["id"],
        resource_type="guardrail",
        name="Code Standards",
        content="Follow PEP8 and use type hints.",
    )

    return {
        "workflow": workflow,
        "step": step,
        "resource": resource,
        "db": project_db,
    }


class TestStepResourceCRUD:
    """Test step resource CRUD operations."""

    def test_create_step_resource_add(self, workflow_with_step):
        """Create a step-specific resource with 'add' mode."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]

        sr = db.create_step_resource(
            step_id=step["id"],
            mode="add",
            resource_type="guardrail",
            name="Step-Specific Guidelines",
            content="Additional guidelines for this step only.",
        )

        assert sr is not None
        assert sr["id"] is not None
        assert sr["step_id"] == step["id"]
        assert sr["mode"] == "add"
        assert sr["name"] == "Step-Specific Guidelines"
        assert sr["content"] == "Additional guidelines for this step only."
        assert sr["resource_type"] == "guardrail"

    def test_create_step_resource_disable(self, workflow_with_step):
        """Create a step resource to disable an inherited workflow resource."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]
        wr = fixture["resource"]

        sr = db.create_step_resource(
            step_id=step["id"],
            mode="disable",
            workflow_resource_id=wr["id"],
        )

        assert sr is not None
        assert sr["mode"] == "disable"
        assert sr["workflow_resource_id"] == wr["id"]

    def test_create_step_resource_override(self, workflow_with_step):
        """Create a step resource to override workflow resource content."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]
        wr = fixture["resource"]

        sr = db.create_step_resource(
            step_id=step["id"],
            mode="override",
            workflow_resource_id=wr["id"],
            resource_type="guardrail",
            name="Code Standards",  # Same name as workflow resource
            content="Overridden content for this step.",
        )

        assert sr is not None
        assert sr["mode"] == "override"
        assert sr["name"] == "Code Standards"
        assert sr["content"] == "Overridden content for this step."

    def test_create_step_resource_invalid_mode(self, workflow_with_step):
        """Creating with invalid mode should raise ValueError."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]

        with pytest.raises(ValueError, match="Invalid mode"):
            db.create_step_resource(
                step_id=step["id"],
                mode="invalid",
                name="Test",
                resource_type="guardrail",
            )

    def test_create_step_resource_disable_requires_workflow_resource_id(self, workflow_with_step):
        """'disable' mode requires workflow_resource_id."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]

        with pytest.raises(ValueError, match="requires workflow_resource_id"):
            db.create_step_resource(
                step_id=step["id"],
                mode="disable",
            )

    def test_create_step_resource_override_requires_name(self, workflow_with_step):
        """'override' mode requires name to match workflow resource."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]
        wr = fixture["resource"]

        with pytest.raises(ValueError, match="requires name"):
            db.create_step_resource(
                step_id=step["id"],
                mode="override",
                workflow_resource_id=wr["id"],
                content="Override content without name",
            )

    def test_create_step_resource_add_requires_name_and_type(self, workflow_with_step):
        """'add' mode requires name and resource_type."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]

        with pytest.raises(ValueError, match="requires name and resource_type"):
            db.create_step_resource(
                step_id=step["id"],
                mode="add",
                content="Some content",
            )

    def test_list_step_resources(self, workflow_with_step):
        """List all step resources for a step."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]

        # Create two step resources
        db.create_step_resource(
            step_id=step["id"],
            mode="add",
            resource_type="guardrail",
            name="Resource 1",
            content="Content 1",
        )
        db.create_step_resource(
            step_id=step["id"],
            mode="add",
            resource_type="design_doc",
            name="Resource 2",
            content="Content 2",
        )

        resources = db.list_step_resources(step["id"])
        assert len(resources) == 2

    def test_get_step_resource(self, workflow_with_step):
        """Get a step resource by ID."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]

        sr = db.create_step_resource(
            step_id=step["id"],
            mode="add",
            resource_type="guardrail",
            name="Test Resource",
            content="Test content",
        )

        fetched = db.get_step_resource(sr["id"])
        assert fetched is not None
        assert fetched["id"] == sr["id"]
        assert fetched["name"] == "Test Resource"

    def test_update_step_resource(self, workflow_with_step):
        """Update a step resource."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]

        sr = db.create_step_resource(
            step_id=step["id"],
            mode="add",
            resource_type="guardrail",
            name="Original Name",
            content="Original content",
        )

        updated = db.update_step_resource(
            sr["id"],
            name="Updated Name",
            content="Updated content",
        )

        assert updated["name"] == "Updated Name"
        assert updated["content"] == "Updated content"

    def test_delete_step_resource(self, workflow_with_step):
        """Delete a step resource."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]

        sr = db.create_step_resource(
            step_id=step["id"],
            mode="add",
            resource_type="guardrail",
            name="To Delete",
            content="Content",
        )

        assert db.delete_step_resource(sr["id"]) is True
        assert db.get_step_resource(sr["id"]) is None

    def test_get_step_resource_by_workflow_resource(self, workflow_with_step):
        """Find step resource for a specific workflow resource."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]
        wr = fixture["resource"]

        # Create a disable record
        sr = db.create_step_resource(
            step_id=step["id"],
            mode="disable",
            workflow_resource_id=wr["id"],
        )

        found = db.get_step_resource_by_workflow_resource(step["id"], wr["id"])
        assert found is not None
        assert found["id"] == sr["id"]


class TestEffectiveResources:
    """Test the effective resources merge algorithm."""

    def test_get_effective_resources_workflow_only(self, workflow_with_step):
        """When no step resources, effective = workflow resources."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]
        workflow = fixture["workflow"]

        effective = db.get_effective_resources_for_step(step["id"], workflow["id"])

        assert len(effective) == 1
        assert effective[0]["name"] == "Code Standards"
        assert effective[0]["source"] == "workflow"

    def test_get_effective_resources_with_disable(self, workflow_with_step):
        """Disabled workflow resource should not appear in effective."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]
        workflow = fixture["workflow"]
        wr = fixture["resource"]

        # Disable the workflow resource
        db.create_step_resource(
            step_id=step["id"],
            mode="disable",
            workflow_resource_id=wr["id"],
        )

        effective = db.get_effective_resources_for_step(step["id"], workflow["id"])
        assert len(effective) == 0

    def test_get_effective_resources_with_override(self, workflow_with_step):
        """Overridden resource should have step content."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]
        workflow = fixture["workflow"]
        wr = fixture["resource"]

        # Override the workflow resource
        db.create_step_resource(
            step_id=step["id"],
            mode="override",
            workflow_resource_id=wr["id"],
            resource_type="guardrail",
            name="Code Standards",
            content="Step-specific standards override.",
        )

        effective = db.get_effective_resources_for_step(step["id"], workflow["id"])

        assert len(effective) == 1
        assert effective[0]["name"] == "Code Standards"
        assert effective[0]["content"] == "Step-specific standards override."
        assert effective[0]["source"] == "step_override"

    def test_get_effective_resources_with_add(self, workflow_with_step):
        """Added step resource should appear alongside workflow resources."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]
        workflow = fixture["workflow"]

        # Add a step-specific resource
        db.create_step_resource(
            step_id=step["id"],
            mode="add",
            resource_type="design_doc",
            name="Step Design Doc",
            content="Design doc only for this step.",
        )

        effective = db.get_effective_resources_for_step(step["id"], workflow["id"])

        assert len(effective) == 2
        names = {r["name"] for r in effective}
        assert "Code Standards" in names
        assert "Step Design Doc" in names

    def test_get_effective_resources_complex_merge(self, workflow_with_step):
        """Test complex merge: disable one, override another, add new."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]
        workflow = fixture["workflow"]
        wr = fixture["resource"]

        # Add another workflow resource
        wr2 = db.create_workflow_resource(
            workflow_id=workflow["id"],
            resource_type="design_doc",
            name="Architecture Doc",
            content="Main architecture document.",
        )

        # Disable Code Standards
        db.create_step_resource(
            step_id=step["id"],
            mode="disable",
            workflow_resource_id=wr["id"],
        )

        # Override Architecture Doc
        db.create_step_resource(
            step_id=step["id"],
            mode="override",
            workflow_resource_id=wr2["id"],
            resource_type="design_doc",
            name="Architecture Doc",
            content="Step-specific architecture.",
        )

        # Add a new step resource
        db.create_step_resource(
            step_id=step["id"],
            mode="add",
            resource_type="prompt",
            name="Step Prompt",
            content="Custom prompt for this step.",
        )

        effective = db.get_effective_resources_for_step(step["id"], workflow["id"])

        assert len(effective) == 2

        by_name = {r["name"]: r for r in effective}

        # Code Standards should be disabled (not present)
        assert "Code Standards" not in by_name

        # Architecture Doc should be overridden
        assert by_name["Architecture Doc"]["content"] == "Step-specific architecture."
        assert by_name["Architecture Doc"]["source"] == "step_override"

        # Step Prompt should be added
        assert by_name["Step Prompt"]["content"] == "Custom prompt for this step."
        assert by_name["Step Prompt"]["source"] == "step_add"


class TestCascadeDeletes:
    """Test cascade delete behavior."""

    def test_step_delete_cascades_resources(self, workflow_with_step):
        """Deleting a step should delete its step resources."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]
        workflow = fixture["workflow"]

        # Create step resources
        sr1 = db.create_step_resource(
            step_id=step["id"],
            mode="add",
            resource_type="guardrail",
            name="Resource 1",
            content="Content",
        )
        sr2 = db.create_step_resource(
            step_id=step["id"],
            mode="add",
            resource_type="guardrail",
            name="Resource 2",
            content="Content",
        )

        # Delete the step
        db.delete_workflow_step(step["id"])

        # Step resources should be gone
        assert db.get_step_resource(sr1["id"]) is None
        assert db.get_step_resource(sr2["id"]) is None

    def test_workflow_resource_delete_cascades_step_resources(self, workflow_with_step):
        """Deleting a workflow resource should cascade to step resources referencing it."""
        fixture = workflow_with_step
        db = fixture["db"]
        step = fixture["step"]
        wr = fixture["resource"]

        # Create a disable step resource for the workflow resource
        sr = db.create_step_resource(
            step_id=step["id"],
            mode="disable",
            workflow_resource_id=wr["id"],
        )

        # Delete the workflow resource
        db.delete_workflow_resource(wr["id"])

        # Step resource should be gone (cascade)
        assert db.get_step_resource(sr["id"]) is None
