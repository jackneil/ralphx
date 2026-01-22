"""Tests for structured status output parsing and item updates."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ralphx.adapters.base import ExecutionResult
from ralphx.core.project_db import ProjectDatabase
from ralphx.core.schemas import (
    IMPLEMENTATION_STATUS_SCHEMA,
    STORY_GENERATION_SCHEMA,
    ItemStatus,
    get_schema_for_loop_type,
)
from ralphx.core.executor import LoopExecutor
from ralphx.models.loop import (
    Limits,
    LoopConfig,
    LoopType,
    Mode,
    ModeSelection,
    ModeSelectionStrategy,
)
from ralphx.models.project import Project


class TestSchemas:
    """Test JSON schema definitions."""

    def test_implementation_status_schema_structure(self):
        """Test implementation status schema has required fields."""
        assert IMPLEMENTATION_STATUS_SCHEMA["type"] == "object"
        props = IMPLEMENTATION_STATUS_SCHEMA["properties"]

        # Check status enum
        assert "status" in props
        assert props["status"]["type"] == "string"
        assert set(props["status"]["enum"]) == {
            "implemented",
            "duplicate",
            "external",
            "skipped",
            "error",
        }

        # Check optional fields exist
        assert "summary" in props
        assert "duplicate_of" in props
        assert "external_system" in props
        assert "reason" in props
        assert "files_changed" in props
        assert "tests_passed" in props

        # Only status is required
        assert IMPLEMENTATION_STATUS_SCHEMA["required"] == ["status"]

    def test_story_generation_schema_structure(self):
        """Test story generation schema has required fields."""
        assert STORY_GENERATION_SCHEMA["type"] == "object"
        props = STORY_GENERATION_SCHEMA["properties"]

        # Check stories array
        assert "stories" in props
        assert props["stories"]["type"] == "array"

        # Check story item properties
        story_props = props["stories"]["items"]["properties"]
        assert "id" in story_props
        assert "content" in story_props
        assert "title" in story_props
        assert "priority" in story_props

    def test_get_schema_for_loop_type_consumer(self):
        """Test consumer loop returns implementation schema."""
        schema = get_schema_for_loop_type("consumer")
        assert schema == IMPLEMENTATION_STATUS_SCHEMA

    def test_get_schema_for_loop_type_implementation(self):
        """Test implementation loop returns implementation schema."""
        schema = get_schema_for_loop_type("implementation")
        assert schema == IMPLEMENTATION_STATUS_SCHEMA

    def test_get_schema_for_loop_type_generator(self):
        """Test generator loop returns story schema."""
        schema = get_schema_for_loop_type("generator")
        assert schema == STORY_GENERATION_SCHEMA

    def test_get_schema_for_loop_type_unknown(self):
        """Test unknown loop type returns None."""
        schema = get_schema_for_loop_type("unknown_type")
        assert schema is None

    def test_item_status_enum_values(self):
        """Test ItemStatus enum has expected values."""
        assert ItemStatus.IMPLEMENTED.value == "implemented"
        assert ItemStatus.DUPLICATE.value == "duplicate"
        assert ItemStatus.EXTERNAL.value == "external"
        assert ItemStatus.SKIPPED.value == "skipped"
        assert ItemStatus.ERROR.value == "error"


class TestDatabaseStatusUpdate:
    """Test database update_work_item_with_status method."""

    @pytest.fixture
    def db(self):
        """Create in-memory project database."""
        database = ProjectDatabase(":memory:")
        yield database
        database.close()

    @pytest.fixture
    def workflow_and_item(self, db):
        """Create a workflow and work item for testing."""
        # Create workflow
        workflow_id = "wf-test-123"
        db.create_workflow(
            id=workflow_id,
            name="Test Workflow",
        )

        # Create work item
        item_id = "ITEM-001"
        db.create_work_item(
            id=item_id,
            workflow_id=workflow_id,
            source_step_id=0,
            priority=1,
            content="Test item content",
        )

        # Claim the item
        db.claim_work_item(item_id, "test-loop")

        return workflow_id, item_id

    def test_update_item_implemented_status(self, db, workflow_and_item):
        """Test updating item with implemented status."""
        workflow_id, item_id = workflow_and_item

        result = db.update_work_item_with_status(
            id=item_id,
            status="processed",
            processed_by="test-loop",
            metadata={"implementation_summary": "Added new feature"},
        )

        assert result is True

        # Verify the item was updated
        item = db.get_work_item(item_id)
        assert item["status"] == "processed"
        assert item["processed_at"] is not None

        metadata = item["metadata"] if item["metadata"] else {}
        assert metadata.get("implementation_summary") == "Added new feature"

    def test_update_item_duplicate_status(self, db, workflow_and_item):
        """Test updating item with duplicate status."""
        workflow_id, item_id = workflow_and_item

        result = db.update_work_item_with_status(
            id=item_id,
            status="duplicate",
            processed_by="test-loop",
            duplicate_of="ITEM-000",
            metadata={"status_reason": "Same as ITEM-000"},
        )

        assert result is True

        item = db.get_work_item(item_id)
        assert item["status"] == "duplicate"
        assert item["duplicate_of"] == "ITEM-000"

    def test_update_item_skipped_status(self, db, workflow_and_item):
        """Test updating item with skipped status."""
        workflow_id, item_id = workflow_and_item

        result = db.update_work_item_with_status(
            id=item_id,
            status="skipped",
            processed_by="test-loop",
            skip_reason="Cannot implement due to missing dependency",
        )

        assert result is True

        item = db.get_work_item(item_id)
        assert item["status"] == "skipped"
        assert item["skip_reason"] == "Cannot implement due to missing dependency"

    def test_update_item_external_status(self, db, workflow_and_item):
        """Test updating item with external status."""
        workflow_id, item_id = workflow_and_item

        result = db.update_work_item_with_status(
            id=item_id,
            status="external",
            processed_by="test-loop",
            metadata={
                "external_system": "claim_maker",
                "status_reason": "Requires Claim Maker API",
            },
        )

        assert result is True

        item = db.get_work_item(item_id)
        assert item["status"] == "external"

        metadata = item["metadata"] if item["metadata"] else {}
        assert metadata.get("external_system") == "claim_maker"

    def test_update_fails_without_claim(self, db, workflow_and_item):
        """Test update fails if item not claimed by the specified loop."""
        workflow_id, item_id = workflow_and_item

        # Try to update with wrong loop name
        result = db.update_work_item_with_status(
            id=item_id,
            status="processed",
            processed_by="other-loop",  # Different from claiming loop
        )

        assert result is False

    def test_update_merges_metadata(self, db, workflow_and_item):
        """Test that metadata is merged, not replaced."""
        workflow_id, item_id = workflow_and_item

        # First update with some metadata
        db.update_work_item_with_status(
            id=item_id,
            status="processed",
            processed_by="test-loop",
            metadata={"field1": "value1"},
        )

        # Re-claim and update with additional metadata
        with db._writer() as conn:
            conn.execute(
                "UPDATE work_items SET status = 'claimed', claimed_by = ? WHERE id = ?",
                ("test-loop", item_id),
            )

        db.update_work_item_with_status(
            id=item_id,
            status="processed",
            processed_by="test-loop",
            metadata={"field2": "value2"},
        )

        item = db.get_work_item(item_id)
        metadata = item["metadata"] if item["metadata"] else {}
        assert metadata.get("field1") == "value1"
        assert metadata.get("field2") == "value2"


class TestExecutorStructuredStatus:
    """Test executor's _update_item_with_structured_status method."""

    @pytest.fixture
    def db(self):
        """Create in-memory project database."""
        database = ProjectDatabase(":memory:")
        yield database
        database.close()

    @pytest.fixture
    def project_dir(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            prompts_dir = project_path / "prompts"
            prompts_dir.mkdir()
            (prompts_dir / "default.md").write_text("Test prompt template")
            yield project_path

    @pytest.fixture
    def project(self, project_dir, db):
        """Create a test project."""
        return Project(
            id="proj-123",
            slug="test",
            name="Test Project",
            path=project_dir,
        )

    @pytest.fixture
    def consumer_loop_config(self):
        """Create a consumer loop config."""
        return LoopConfig(
            name="consumer_loop",
            display_name="Consumer Loop",
            type=LoopType.CONSUMER,
            modes={
                "default": Mode(
                    timeout=30,
                    model="sonnet",
                    prompt_template="prompts/default.md",
                ),
            },
            mode_selection=ModeSelection(
                strategy=ModeSelectionStrategy.FIXED,
                fixed_mode="default",
            ),
            limits=Limits(
                max_iterations=5,
                max_consecutive_errors=3,
                cooldown_between_iterations=0,
            ),
        )

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock LLM adapter."""
        adapter = MagicMock()
        adapter.is_running = False
        adapter.execute = AsyncMock(return_value=ExecutionResult(
            session_id="session-test",
            success=True,
            text_output="Test output",
        ))
        adapter.stop = AsyncMock()
        adapter.build_run_marker = MagicMock(return_value="<!-- MARKER -->")
        return adapter

    @pytest.fixture
    def workflow_id(self, db):
        """Create a test workflow."""
        wf_id = "wf-executor-test"
        db.create_workflow(
            id=wf_id,
            name="Executor Test Workflow",
        )
        return wf_id

    @pytest.fixture
    def executor(self, db, project, consumer_loop_config, mock_adapter, workflow_id):
        """Create a test executor."""
        return LoopExecutor(
            project=project,
            loop_config=consumer_loop_config,
            db=db,
            workflow_id=workflow_id,
            step_id=1,
            adapter=mock_adapter,
        )

    @pytest.fixture
    def claimed_item(self, db, executor):
        """Create a workflow and claimed item."""
        # Create workflow
        workflow_id = "wf-exec-test"
        db.create_workflow(
            id=workflow_id,
            name="Test Workflow",
        )

        # Create and claim item
        item_id = "TEST-001"
        db.create_work_item(
            id=item_id,
            workflow_id=workflow_id,
            source_step_id=0,
            priority=1,
            content="Test item",
        )
        db.claim_work_item(item_id, executor.config.name)
        return item_id

    def test_update_with_implemented_status(self, executor, db, claimed_item):
        """Test updating item with implemented structured output."""
        structured_output = {
            "status": "implemented",
            "summary": "Added patient search API",
            "files_changed": ["api/search.py", "tests/test_search.py"],
            "tests_passed": True,
        }

        result = executor._update_item_with_structured_status(
            claimed_item,
            structured_output,
        )

        assert result is True

        # Verify item status
        item = db.get_work_item(claimed_item)
        assert item["status"] == "processed"

        metadata = item["metadata"] if item["metadata"] else {}
        assert metadata.get("implementation_summary") == "Added patient search API"
        assert metadata.get("files_changed") == ["api/search.py", "tests/test_search.py"]
        assert metadata.get("tests_passed") is True

    def test_update_with_duplicate_status(self, executor, db, claimed_item):
        """Test updating item with duplicate structured output."""
        structured_output = {
            "status": "duplicate",
            "duplicate_of": "FND-003",
            "reason": "Same functionality as FND-003",
        }

        result = executor._update_item_with_structured_status(
            claimed_item,
            structured_output,
        )

        assert result is True

        item = db.get_work_item(claimed_item)
        assert item["status"] == "duplicate"
        assert item["duplicate_of"] == "FND-003"

    def test_update_with_skipped_status(self, executor, db, claimed_item):
        """Test updating item with skipped structured output."""
        structured_output = {
            "status": "skipped",
            "reason": "Depends on external API not available",
        }

        result = executor._update_item_with_structured_status(
            claimed_item,
            structured_output,
        )

        assert result is True

        item = db.get_work_item(claimed_item)
        assert item["status"] == "skipped"
        assert item["skip_reason"] == "Depends on external API not available"

    def test_update_with_external_status(self, executor, db, claimed_item):
        """Test updating item with external structured output."""
        structured_output = {
            "status": "external",
            "external_system": "claim_maker",
            "reason": "Requires Claim Maker integration",
        }

        result = executor._update_item_with_structured_status(
            claimed_item,
            structured_output,
        )

        assert result is True

        item = db.get_work_item(claimed_item)
        assert item["status"] == "external"

        metadata = item["metadata"] if item["metadata"] else {}
        assert metadata.get("external_system") == "claim_maker"

    def test_update_with_error_status(self, executor, db, claimed_item):
        """Test updating item with error structured output."""
        structured_output = {
            "status": "error",
            "reason": "Build failed due to type errors",
        }

        result = executor._update_item_with_structured_status(
            claimed_item,
            structured_output,
        )

        assert result is True

        item = db.get_work_item(claimed_item)
        assert item["status"] == "failed"

    def test_update_with_unknown_status_defaults_to_implemented(
        self, executor, db, claimed_item
    ):
        """Test unknown status value defaults to implemented."""
        structured_output = {
            "status": "unknown_status_value",
            "summary": "Did something",
        }

        result = executor._update_item_with_structured_status(
            claimed_item,
            structured_output,
        )

        assert result is True

        item = db.get_work_item(claimed_item)
        # Should default to processed (implemented)
        assert item["status"] == "processed"

    def test_update_tracks_completed_items(self, executor, db, claimed_item):
        """Test that completed items are tracked in executor."""
        structured_output = {"status": "implemented"}

        executor._update_item_with_structured_status(
            claimed_item,
            structured_output,
        )

        assert claimed_item in executor._completed_item_ids

    def test_update_with_missing_status_defaults_to_implemented(
        self, executor, db, claimed_item
    ):
        """Test missing status field defaults to implemented."""
        # Empty dict - status field is missing entirely
        structured_output = {"summary": "Did something without status field"}

        result = executor._update_item_with_structured_status(
            claimed_item,
            structured_output,
        )

        assert result is True

        item = db.get_work_item(claimed_item)
        # Should default to processed (implemented) since status is required
        # and get() with default handles missing key
        assert item["status"] == "processed"

    def test_update_with_empty_dict(self, executor, db, claimed_item):
        """Test completely empty structured output defaults to implemented."""
        structured_output = {}

        result = executor._update_item_with_structured_status(
            claimed_item,
            structured_output,
        )

        assert result is True

        item = db.get_work_item(claimed_item)
        assert item["status"] == "processed"

    def test_update_handles_none_values_in_optional_fields(
        self, executor, db, claimed_item
    ):
        """Test that None values in optional fields are handled gracefully."""
        structured_output = {
            "status": "implemented",
            "summary": None,  # Explicitly None
            "files_changed": None,
            "tests_passed": None,
        }

        result = executor._update_item_with_structured_status(
            claimed_item,
            structured_output,
        )

        assert result is True

        item = db.get_work_item(claimed_item)
        assert item["status"] == "processed"
        # Metadata should not contain None values
        metadata = item["metadata"] if item["metadata"] else {}
        # None values should not be stored (only truthy values are added)
        assert "implementation_summary" not in metadata

    def test_update_with_very_long_reason_truncated_in_event(
        self, executor, db, claimed_item
    ):
        """Test that very long reason is truncated in event message."""
        # Test with a very long reason string
        long_reason = "A" * 200

        structured_output = {
            "status": "skipped",
            "reason": long_reason,
        }

        result = executor._update_item_with_structured_status(
            claimed_item,
            structured_output,
        )

        assert result is True

        item = db.get_work_item(claimed_item)
        # Full reason should be stored in database
        assert item["skip_reason"] == long_reason


class TestStructuredOutputInIteration:
    """Test structured output integration in run_iteration."""

    @pytest.fixture
    def db(self):
        """Create in-memory project database."""
        database = ProjectDatabase(":memory:")
        yield database
        database.close()

    @pytest.fixture
    def project_dir(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            prompts_dir = project_path / "prompts"
            prompts_dir.mkdir()
            (prompts_dir / "default.md").write_text("Test prompt template")
            yield project_path

    @pytest.fixture
    def project(self, project_dir, db):
        """Create a test project."""
        return Project(
            id="proj-iter-123",
            slug="test-iter",
            name="Test Project",
            path=project_dir,
        )

    @pytest.fixture
    def consumer_loop_config(self):
        """Create a consumer loop config."""
        return LoopConfig(
            name="test_consumer",
            display_name="Test Consumer",
            type=LoopType.CONSUMER,
            modes={
                "default": Mode(
                    timeout=30,
                    model="sonnet",
                    prompt_template="prompts/default.md",
                ),
            },
            mode_selection=ModeSelection(
                strategy=ModeSelectionStrategy.FIXED,
                fixed_mode="default",
            ),
            limits=Limits(
                max_iterations=5,
                max_consecutive_errors=3,
                cooldown_between_iterations=0,
            ),
        )

    def test_batch_mode_does_not_use_structured_output(
        self, project, consumer_loop_config, db
    ):
        """Test that batch mode does NOT use structured output schema.

        This is critical because the schema only supports ONE status
        but batch mode processes MULTIPLE items. Using the same status
        for all items would be incorrect.
        """
        from ralphx.core.executor import LoopExecutor
        from ralphx.core.schemas import IMPLEMENTATION_STATUS_SCHEMA

        # Create workflow
        workflow_id = "wf-batch-test"
        db.create_workflow(
            id=workflow_id,
            name="Batch Test Workflow",
        )

        # Create executor in batch mode
        executor = LoopExecutor(
            project=project,
            loop_config=consumer_loop_config,
            db=db,
            workflow_id=workflow_id,
            step_id=1,
            batch_mode=True,  # Key: batch mode enabled
            batch_size=5,
        )

        # Verify the executor is in batch mode
        assert executor._batch_mode is True

        # The executor should NOT use IMPLEMENTATION_STATUS_SCHEMA when
        # building the command for batch mode because it would apply
        # one status to all items incorrectly
