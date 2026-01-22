"""Shared pytest fixtures for RalphX tests."""

import tempfile
from pathlib import Path

import pytest

from ralphx.core.project_db import ProjectDatabase


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def project_db(temp_dir):
    """Create an in-memory project database with workflow context."""
    db = ProjectDatabase(":memory:")
    yield db
    db.close()


@pytest.fixture
def workflow_context(project_db):
    """Create a workflow and step for tests that need workflow context.

    Returns a dict with workflow_id and step_id that can be used in tests.
    """
    workflow_id = "wf-test-123"
    project_db.create_workflow(
        id=workflow_id,
        name="Test Workflow",
        status="active"
    )
    step = project_db.create_workflow_step(
        workflow_id=workflow_id,
        step_number=1,
        name="Test Step",
        step_type="autonomous",
        status="pending"
    )
    return {"workflow_id": workflow_id, "step_id": step["id"]}


@pytest.fixture
def db_with_workflow(temp_dir):
    """Create a project database in a temp directory with workflow context.

    Returns a tuple of (db, workflow_context).
    """
    db = ProjectDatabase(temp_dir)

    workflow_id = "wf-test-123"
    db.create_workflow(
        id=workflow_id,
        name="Test Workflow",
        status="active"
    )
    step = db.create_workflow_step(
        workflow_id=workflow_id,
        step_number=1,
        name="Test Step",
        step_type="autonomous",
        status="pending"
    )
    context = {"workflow_id": workflow_id, "step_id": step["id"]}

    yield db, context
    db.close()
