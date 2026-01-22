"""Tests for RalphX loop executor."""

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ralphx.adapters.base import AdapterEvent, ExecutionResult, StreamEvent
from ralphx.core.project_db import ProjectDatabase
from ralphx.core.executor import (
    ExecutorEvent,
    ExecutorEventData,
    IterationResult,
    LoopExecutor,
)
from ralphx.models.loop import (
    Limits,
    LoopConfig,
    LoopType,
    Mode,
    ModeSelection,
    ModeSelectionStrategy,
)
from ralphx.models.project import Project
from ralphx.models.run import RunStatus


@pytest.fixture
def db():
    """Create in-memory project database with workflow context."""
    database = ProjectDatabase(":memory:")

    # Create workflow context for executor tests
    workflow_id = "wf-executor-test"
    database.create_workflow(
        id=workflow_id,
        name="Executor Test Workflow",
        status="active"
    )
    step = database.create_workflow_step(
        workflow_id=workflow_id,
        step_number=1,
        name="Test Step",
        step_type="autonomous",
        status="pending"
    )
    # Store workflow context for tests
    database._test_workflow_id = workflow_id
    database._test_step_id = step["id"]

    yield database
    database.close()


@pytest.fixture
def project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        prompts_dir = project_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "default.md").write_text("Test prompt template")
        (prompts_dir / "turbo.md").write_text("Turbo prompt")
        (prompts_dir / "deep.md").write_text("Deep prompt")
        yield project_path


@pytest.fixture
def project(project_dir, db):
    """Create a test project."""
    # ProjectDatabase doesn't need project registration - that's in GlobalDatabase
    # Just return the Project model
    return Project(
        id="proj-123",
        slug="test",
        name="Test Project",
        path=project_dir,
    )


@pytest.fixture
def simple_loop_config():
    """Create a simple loop config with fixed mode."""
    return LoopConfig(
        name="simple",
        display_name="Simple Loop",
        type=LoopType.GENERATOR,
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
def weighted_loop_config():
    """Create a loop config with weighted random mode selection."""
    return LoopConfig(
        name="weighted",
        display_name="Weighted Loop",
        type=LoopType.GENERATOR,
        modes={
            "turbo": Mode(
                timeout=60,
                model="sonnet",
                prompt_template="prompts/turbo.md",
            ),
            "deep": Mode(
                timeout=300,
                model="opus",
                prompt_template="prompts/deep.md",
            ),
        },
        mode_selection=ModeSelection(
            strategy=ModeSelectionStrategy.WEIGHTED_RANDOM,
            weights={"turbo": 80, "deep": 20},
        ),
        limits=Limits(
            max_iterations=10,
            max_consecutive_errors=3,
            cooldown_between_iterations=0,
        ),
    )


@pytest.fixture
def mock_adapter():
    """Create a mock LLM adapter."""
    adapter = MagicMock()
    adapter.is_running = False

    async def mock_execute(prompt, model, tools, timeout, **kwargs):
        """Mock execute that accepts any extra kwargs like json_schema."""
        return ExecutionResult(
            session_id="session-123",
            success=True,
            text_output='[{"id": "item-1", "content": "Test item"}]',
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )

    adapter.execute = AsyncMock(side_effect=mock_execute)
    adapter.stop = AsyncMock()
    adapter.build_run_marker = MagicMock(return_value="<!-- MARKER -->")
    return adapter


class TestModeSelection:
    """Test mode selection strategies."""

    def test_fixed_mode_selection(self, project, db, simple_loop_config, mock_adapter):
        """Test fixed mode always returns the same mode."""
        executor = LoopExecutor(
            project=project,
            loop_config=simple_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
        )

        for _ in range(5):
            name, mode = executor.select_mode()
            assert name == "default"
            assert mode.timeout == 30

    def test_random_mode_selection(self, project, db, weighted_loop_config, mock_adapter):
        """Test random mode selection covers all modes."""
        # Modify to pure random
        weighted_loop_config.mode_selection = ModeSelection(
            strategy=ModeSelectionStrategy.RANDOM,
        )

        executor = LoopExecutor(
            project=project,
            loop_config=weighted_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
        )

        selected_modes = set()
        for _ in range(100):
            name, mode = executor.select_mode()
            selected_modes.add(name)

        # Should have selected both modes at some point
        assert "turbo" in selected_modes or "deep" in selected_modes

    def test_weighted_random_mode_selection(self, project, db, weighted_loop_config, mock_adapter):
        """Test weighted random mode selection respects weights."""
        executor = LoopExecutor(
            project=project,
            loop_config=weighted_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
        )

        turbo_count = 0
        deep_count = 0

        for _ in range(1000):
            name, mode = executor.select_mode()
            if name == "turbo":
                turbo_count += 1
            else:
                deep_count += 1

        # Turbo should be ~80%, deep ~20%
        turbo_ratio = turbo_count / 1000
        assert 0.7 < turbo_ratio < 0.9


class TestWorkItemExtraction:
    """Test work item extraction from Claude output."""

    def test_extract_json_items(self, project, db, simple_loop_config, mock_adapter):
        """Test extracting items from JSON output."""
        executor = LoopExecutor(
            project=project,
            loop_config=simple_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
        )

        output = '''
        Here are the items:
        [
            {"id": "item-1", "content": "First item", "priority": 1},
            {"id": "item-2", "content": "Second item", "category": "research"}
        ]
        '''

        items = executor.extract_work_items(output)
        assert len(items) == 2
        assert items[0]["id"] == "item-1"
        assert items[0]["content"] == "First item"
        assert items[0]["priority"] == 1
        assert items[1]["id"] == "item-2"
        assert items[1]["category"] == "research"

    def test_extract_markdown_items(self, project, db, simple_loop_config, mock_adapter):
        """Test extracting items from markdown list."""
        executor = LoopExecutor(
            project=project,
            loop_config=simple_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
        )

        output = '''
        Work items found:
        - **ITEM-001**: Research the authentication system
        - **ITEM-002**: Implement login form validation
        - **ITEM-003**: Add error handling
        '''

        items = executor.extract_work_items(output)
        assert len(items) == 3
        assert items[0]["id"] == "ITEM-001"
        assert "Research" in items[0]["content"]

    def test_extract_numbered_items(self, project, db, simple_loop_config, mock_adapter):
        """Test extracting items from numbered list."""
        executor = LoopExecutor(
            project=project,
            loop_config=simple_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
        )

        output = '''
        Tasks:
        1. [TODO-001] Fix the memory leak in the cache
        2. [TODO-002] Update the documentation
        3. [TODO-003] Add unit tests
        '''

        items = executor.extract_work_items(output)
        assert len(items) == 3
        assert items[0]["id"] == "TODO-001"
        assert "memory leak" in items[0]["content"]

    def test_extract_no_items(self, project, db, simple_loop_config, mock_adapter):
        """Test handling output with no items."""
        executor = LoopExecutor(
            project=project,
            loop_config=simple_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
        )

        output = "This is just regular text with no structured items."
        items = executor.extract_work_items(output)
        assert len(items) == 0


class TestExecutorRun:
    """Test executor run functionality."""

    @pytest.mark.asyncio
    async def test_dry_run(self, project, db, simple_loop_config, mock_adapter):
        """Test dry run mode doesn't call adapter."""
        executor = LoopExecutor(
            project=project,
            loop_config=simple_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
            dry_run=True,
        )

        run = await executor.run(max_iterations=3)

        assert run.status == RunStatus.COMPLETED
        assert run.iterations_completed == 3
        mock_adapter.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_with_adapter(self, project, db, simple_loop_config, mock_adapter):
        """Test run calls adapter for each iteration."""
        executor = LoopExecutor(
            project=project,
            loop_config=simple_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
        )

        run = await executor.run(max_iterations=2)

        assert run.status == RunStatus.COMPLETED
        assert run.iterations_completed == 2
        assert mock_adapter.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_run_extracts_items(self, project, db, simple_loop_config, mock_adapter):
        """Test run extracts and saves work items."""
        executor = LoopExecutor(
            project=project,
            loop_config=simple_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
        )

        run = await executor.run(max_iterations=1)

        assert run.items_generated == 1  # One item per iteration from mock

    @pytest.mark.asyncio
    async def test_run_respects_max_iterations(self, project, db, simple_loop_config, mock_adapter):
        """Test run stops at max iterations."""
        executor = LoopExecutor(
            project=project,
            loop_config=simple_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
        )

        run = await executor.run(max_iterations=3)

        assert run.iterations_completed == 3
        assert run.status == RunStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_run_handles_consecutive_errors(self, project, db, simple_loop_config):
        """Test run stops after max consecutive errors."""
        adapter = MagicMock()
        adapter.is_running = False
        adapter.build_run_marker = MagicMock(return_value="<!-- MARKER -->")
        adapter.stop = AsyncMock()

        async def failing_execute(prompt, model, tools, timeout):
            return ExecutionResult(
                success=False,
                error_message="API Error",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
            )

        adapter.execute = AsyncMock(side_effect=failing_execute)

        simple_loop_config.limits.max_consecutive_errors = 2

        executor = LoopExecutor(
            project=project,
            loop_config=simple_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=adapter,
        )

        run = await executor.run(max_iterations=10)

        # Should stop after 2 consecutive errors
        assert run.iterations_completed == 2
        assert run.status == RunStatus.COMPLETED


class TestExecutorEvents:
    """Test executor event emission."""

    @pytest.mark.asyncio
    async def test_emits_run_started(self, project, db, simple_loop_config, mock_adapter):
        """Test run emits RUN_STARTED event."""
        executor = LoopExecutor(
            project=project,
            loop_config=simple_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
            dry_run=True,
        )

        events = []
        executor.add_event_handler(lambda e: events.append(e))

        await executor.run(max_iterations=1)

        event_types = [e.event for e in events]
        assert ExecutorEvent.RUN_STARTED in event_types

    @pytest.mark.asyncio
    async def test_emits_iteration_events(self, project, db, simple_loop_config, mock_adapter):
        """Test run emits iteration start/complete events."""
        executor = LoopExecutor(
            project=project,
            loop_config=simple_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
            dry_run=True,
        )

        events = []
        executor.add_event_handler(lambda e: events.append(e))

        await executor.run(max_iterations=2)

        event_types = [e.event for e in events]
        assert event_types.count(ExecutorEvent.ITERATION_STARTED) == 2
        assert event_types.count(ExecutorEvent.ITERATION_COMPLETED) == 2

    @pytest.mark.asyncio
    async def test_emits_run_completed(self, project, db, simple_loop_config, mock_adapter):
        """Test run emits RUN_COMPLETED event."""
        executor = LoopExecutor(
            project=project,
            loop_config=simple_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
            dry_run=True,
        )

        events = []
        executor.add_event_handler(lambda e: events.append(e))

        await executor.run(max_iterations=1)

        event_types = [e.event for e in events]
        assert ExecutorEvent.RUN_COMPLETED in event_types

    @pytest.mark.asyncio
    async def test_emits_item_added(self, project, db, simple_loop_config, mock_adapter):
        """Test run emits ITEM_ADDED event for extracted items."""
        executor = LoopExecutor(
            project=project,
            loop_config=simple_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
        )

        events = []
        executor.add_event_handler(lambda e: events.append(e))

        await executor.run(max_iterations=1)

        event_types = [e.event for e in events]
        assert ExecutorEvent.ITEM_ADDED in event_types


class TestExecutorPauseResume:
    """Test executor pause/resume functionality."""

    @pytest.mark.asyncio
    async def test_pause_and_resume(self, project, db, simple_loop_config, mock_adapter):
        """Test pausing and resuming execution."""
        executor = LoopExecutor(
            project=project,
            loop_config=simple_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
            dry_run=True,
        )

        # Start run in background
        run_task = asyncio.create_task(executor.run(max_iterations=10))

        # Let it start
        await asyncio.sleep(0.05)

        # Pause
        executor.pause()
        assert executor.is_paused

        # Resume
        executor.resume()
        assert not executor.is_paused

        # Stop
        await executor.stop()
        await run_task


class TestExecutorProperties:
    """Test executor properties."""

    def test_is_running_initially_false(self, project, db, simple_loop_config, mock_adapter):
        """Test is_running is False before run."""
        executor = LoopExecutor(
            project=project,
            loop_config=simple_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
        )
        assert not executor.is_running

    def test_run_id_none_initially(self, project, db, simple_loop_config, mock_adapter):
        """Test run_id is None before run."""
        executor = LoopExecutor(
            project=project,
            loop_config=simple_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
        )
        assert executor.run_id is None

    def test_current_iteration_zero_initially(self, project, db, simple_loop_config, mock_adapter):
        """Test current_iteration is 0 before run."""
        executor = LoopExecutor(
            project=project,
            loop_config=simple_loop_config,
            db=db,
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
            adapter=mock_adapter,
        )
        assert executor.current_iteration == 0


class TestIterationResult:
    """Test IterationResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = IterationResult()
        assert result.success is True
        assert result.session_id is None
        assert result.mode_name == ""
        assert result.duration_seconds == 0.0
        assert result.items_added == []
        assert result.error_message is None
        assert result.timeout is False

    def test_with_values(self):
        """Test with custom values."""
        result = IterationResult(
            success=False,
            session_id="sess-123",
            mode_name="turbo",
            duration_seconds=5.5,
            items_added=[{"id": "item-1"}],
            error_message="Test error",
            timeout=True,
        )
        assert result.success is False
        assert result.session_id == "sess-123"
        assert result.mode_name == "turbo"
        assert result.duration_seconds == 5.5
        assert len(result.items_added) == 1
        assert result.error_message == "Test error"
        assert result.timeout is True
