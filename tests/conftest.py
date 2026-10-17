"""Shared pytest fixtures for RalphX tests."""

import tempfile
from pathlib import Path

import pytest

from ralphx.core.project_db import ProjectDatabase

# Fixed API token for tests. The autouse fixture below puts it in
# RALPHX_API_TOKEN, so the API guard accepts it whatever RALPHX_HOME is.
TEST_API_TOKEN = "test-api-token-0123456789abcdefghijklmnop"


@pytest.fixture(autouse=True)
def _isolated_workspace(monkeypatch, tmp_path_factory):
    """Keep every test away from the real ~/.ralphx workspace.

    Tests that need their own workspace still set RALPHX_HOME themselves.
    """
    monkeypatch.setenv("RALPHX_HOME", str(tmp_path_factory.mktemp("ralphx-home")))
    monkeypatch.setenv("RALPHX_API_TOKEN", TEST_API_TOKEN)
    monkeypatch.delenv("RALPHX_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("RALPHX_ALLOWED_ORIGINS", raising=False)


def make_api_client(**kwargs):
    """Return a TestClient that talks to the API as the local, logged-in user."""
    from fastapi.testclient import TestClient

    from ralphx.api.main import app

    headers = {"Authorization": f"Bearer {TEST_API_TOKEN}"}
    headers.update(kwargs.pop("headers", {}))
    return TestClient(app, base_url="http://127.0.0.1", headers=headers, **kwargs)


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
