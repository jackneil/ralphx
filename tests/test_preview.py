"""Tests for loop preview functionality."""

import tempfile
from pathlib import Path

import pytest

from ralphx.core.preview import PromptPreviewEngine
from ralphx.core.project_db import ProjectDatabase
from ralphx.core.resources import ResourceManager, ResourceType
from ralphx.models.loop import LoopConfig


@pytest.fixture
def project_dir():
    """Create a temporary project directory with resources."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)

        # Create .ralphx directory structure
        ralphx_dir = project_path / ".ralphx"
        ralphx_dir.mkdir()

        # Create resources directories
        resources_dir = ralphx_dir / "resources"
        for subdir in ["design_doc", "architecture", "coding_standards", "domain_knowledge", "custom"]:
            (resources_dir / subdir).mkdir(parents=True)

        # Create prompts directory
        prompts_dir = project_path / "prompts"
        prompts_dir.mkdir()

        # Create a sample prompt template
        (prompts_dir / "default.md").write_text(
            "# Task\n\n"
            "You are a helpful assistant.\n\n"
            "{{task}}\n\n"
            "Please complete the task above."
        )

        (prompts_dir / "consumer.md").write_text(
            "# Consumer Task\n\n"
            "Process the following item from {{source_loop}}:\n\n"
            "{{input_item}}\n\n"
            "Please implement the above."
        )

        yield project_path


@pytest.fixture
def db(project_dir):
    """Create a project database with workflow context."""
    db = ProjectDatabase(project_dir)

    # Create workflow context for tests
    workflow_id = "wf-preview-test"
    db.create_workflow(
        id=workflow_id,
        name="Preview Test Workflow",
        status="active"
    )
    step = db.create_workflow_step(
        workflow_id=workflow_id,
        step_number=1,
        name="Test Step",
        step_type="autonomous",
        status="pending"
    )
    # Store workflow context for tests
    db._test_workflow_id = workflow_id
    db._test_step_id = step["id"]

    yield db
    db.close()


@pytest.fixture
def generator_loop_config(project_dir):
    """Create a generator loop config."""
    return LoopConfig(
        name="research",
        display_name="Research Loop",
        type="generator",
        modes={
            "turbo": {
                "description": "Fast mode",
                "timeout": 180,
                "model": "sonnet",
                "tools": [],
                "prompt_template": "prompts/default.md",
            },
            "deep": {
                "description": "Thorough mode",
                "timeout": 600,
                "model": "opus",
                "tools": ["WebSearch", "WebFetch"],
                "prompt_template": "prompts/default.md",
            },
        },
        mode_selection={
            "strategy": "weighted_random",
            "weights": {"turbo": 80, "deep": 20},
        },
    )


@pytest.fixture
def consumer_loop_config(project_dir):
    """Create a consumer loop config."""
    return LoopConfig(
        name="implementation",
        display_name="Implementation Loop",
        type="consumer",
        modes={
            "implement": {
                "timeout": 1800,
                "model": "sonnet",
                "tools": ["Read", "Write", "Edit"],
                "prompt_template": "prompts/consumer.md",
            },
        },
        mode_selection={
            "strategy": "fixed",
            "fixed_mode": "implement",
        },
        item_types={
            "input": {
                "singular": "story",
                "plural": "stories",
                "source": "research",
            },
            "output": {
                "singular": "implementation",
                "plural": "implementations",
            },
        },
    )


class TestPromptPreviewEngine:
    """Test PromptPreviewEngine functionality."""

    def test_generate_preview_generator_loop(self, project_dir, db, generator_loop_config):
        """Test generating preview for a generator loop."""
        engine = PromptPreviewEngine(project_dir, generator_loop_config, db)

        preview = engine.generate_preview()

        assert preview.loop_name == "research"
        assert preview.loop_type == "generator"
        assert preview.mode_selection_strategy == "weighted_random"
        assert "80%" in preview.strategy_explanation or "turbo: 80" in preview.strategy_explanation
        assert len(preview.modes) == 2

        # Check mode previews
        mode_names = [m.mode_name for m in preview.modes]
        assert "turbo" in mode_names
        assert "deep" in mode_names

        # Check turbo mode
        turbo = next(m for m in preview.modes if m.mode_name == "turbo")
        assert turbo.model == "sonnet"
        assert turbo.timeout == 180
        assert turbo.total_length > 0
        assert turbo.token_estimate > 0
        assert "Task" in turbo.rendered_prompt

    def test_generate_preview_single_mode(self, project_dir, db, generator_loop_config):
        """Test generating preview for a single mode."""
        engine = PromptPreviewEngine(project_dir, generator_loop_config, db)

        preview = engine.generate_preview(mode_name="turbo")

        assert len(preview.modes) == 1
        assert preview.modes[0].mode_name == "turbo"

    def test_generate_preview_with_resources(self, project_dir, db, generator_loop_config):
        """Test preview includes resources."""
        # Create some resources
        resource_manager = ResourceManager(project_dir, db=db)
        resource_manager.create_resource(
            name="standards",
            resource_type=ResourceType.CODING_STANDARDS,
            content="# Coding Standards\n\nAlways write clean code.",
        )
        resource_manager.create_resource(
            name="design",
            resource_type=ResourceType.DESIGN_DOC,
            content="# Project Design\n\nThe system architecture is...",
        )

        engine = PromptPreviewEngine(project_dir, generator_loop_config, db)
        preview = engine.generate_preview()

        # Check resources are listed
        assert len(preview.resources_used) == 2
        assert any("coding_standards" in r for r in preview.resources_used)
        assert any("design_doc" in r for r in preview.resources_used)

        # Check resources are in rendered prompt
        turbo = next(m for m in preview.modes if m.mode_name == "turbo")
        assert "Coding Standards" in turbo.rendered_prompt
        assert "Project Design" in turbo.rendered_prompt

    def test_generate_preview_consumer_loop(self, project_dir, db, consumer_loop_config):
        """Test preview for a consumer loop with sample item."""
        # Create a sample item in the source step
        db.create_work_item(
            id="item-001",
            workflow_id=db._test_workflow_id,
            source_step_id=db._test_step_id,
            content="As a user, I want to login",
        )
        # Mark as completed so it's available for consumption
        db.complete_work_item("item-001")

        engine = PromptPreviewEngine(project_dir, consumer_loop_config, db)
        preview = engine.generate_preview()

        assert preview.loop_type == "consumer"

        # Sample item should be included
        assert preview.sample_item is not None
        assert "login" in preview.sample_item.get("content", "")

        # Template variables should include consumer variables
        assert "{{input_item}}" in preview.template_variables
        assert "{{workflow_id}}" in preview.template_variables

        # Rendered prompt should have substituted values
        impl = preview.modes[0]
        assert "login" in impl.rendered_prompt or "research" in impl.rendered_prompt

    def test_generate_preview_with_explicit_sample(self, project_dir, db, consumer_loop_config):
        """Test preview with explicitly provided sample item."""
        sample_item = {
            "id": "sample-001",
            "content": "Custom sample content for testing",
            "source_loop": "research",
        }

        engine = PromptPreviewEngine(project_dir, consumer_loop_config, db)
        preview = engine.generate_preview(sample_item=sample_item)

        assert preview.sample_item is not None
        assert preview.sample_item["id"] == "sample-001"

        # Content should be in rendered prompt
        impl = preview.modes[0]
        assert "Custom sample content" in impl.rendered_prompt

    def test_preview_with_annotations(self, project_dir, db, generator_loop_config):
        """Test preview includes section annotations."""
        engine = PromptPreviewEngine(project_dir, generator_loop_config, db)
        preview = engine.generate_preview(include_annotations=True)

        turbo = preview.modes[0]

        # Annotations should be present
        assert "<!-- [" in turbo.rendered_prompt
        assert "TEMPLATE" in turbo.rendered_prompt

    def test_preview_without_annotations(self, project_dir, db, generator_loop_config):
        """Test preview without annotations."""
        engine = PromptPreviewEngine(project_dir, generator_loop_config, db)
        preview = engine.generate_preview(include_annotations=False)

        turbo = preview.modes[0]

        # Annotations should NOT be present
        assert "<!-- [" not in turbo.rendered_prompt

    def test_preview_sections_tracked(self, project_dir, db, generator_loop_config):
        """Test that sections are properly tracked."""
        resource_manager = ResourceManager(project_dir, db=db)
        resource_manager.create_resource(
            name="standards",
            resource_type=ResourceType.CODING_STANDARDS,
            content="# Standards",
        )

        engine = PromptPreviewEngine(project_dir, generator_loop_config, db)
        preview = engine.generate_preview()

        turbo = preview.modes[0]

        # Should have multiple sections
        assert len(turbo.sections) >= 1

        # Template section should exist
        template_sections = [s for s in turbo.sections if s.source == "template"]
        assert len(template_sections) == 1

        # Resource sections should exist
        resource_sections = [s for s in turbo.sections if s.source == "resource"]
        assert len(resource_sections) >= 1

    def test_preview_missing_template_warning(self, project_dir, db):
        """Test preview warns about missing template."""
        loop_config = LoopConfig(
            name="test",
            display_name="Test",
            type="generator",
            modes={
                "default": {
                    "timeout": 300,
                    "model": "sonnet",
                    "prompt_template": "prompts/nonexistent.md",
                }
            },
            mode_selection={"strategy": "fixed", "fixed_mode": "default"},
        )

        engine = PromptPreviewEngine(project_dir, loop_config, db)
        preview = engine.generate_preview()

        # Should have warning about missing template
        mode_preview = preview.modes[0]
        assert len(mode_preview.warnings) > 0
        assert any("not found" in w.lower() for w in mode_preview.warnings)

    def test_strategy_explanation(self, project_dir, db):
        """Test strategy explanations are generated correctly."""
        # Test fixed strategy
        fixed_config = LoopConfig(
            name="test",
            display_name="Test",
            type="generator",
            modes={"default": {"timeout": 300, "model": "sonnet", "prompt_template": "prompts/default.md"}},
            mode_selection={"strategy": "fixed", "fixed_mode": "default"},
        )
        engine = PromptPreviewEngine(project_dir, fixed_config, db)
        preview = engine.generate_preview()
        assert "Fixed" in preview.strategy_explanation
        assert "default" in preview.strategy_explanation

        # Test weighted_random strategy
        weighted_config = LoopConfig(
            name="test2",
            display_name="Test2",
            type="generator",
            modes={
                "a": {"timeout": 300, "model": "sonnet", "prompt_template": "prompts/default.md"},
                "b": {"timeout": 300, "model": "opus", "prompt_template": "prompts/default.md"},
            },
            mode_selection={"strategy": "weighted_random", "weights": {"a": 70, "b": 30}},
        )
        engine = PromptPreviewEngine(project_dir, weighted_config, db)
        preview = engine.generate_preview()
        assert "Weighted" in preview.strategy_explanation
        assert "70" in preview.strategy_explanation or "30" in preview.strategy_explanation

    def test_token_estimation(self, project_dir, db, generator_loop_config):
        """Test token estimation is reasonable."""
        engine = PromptPreviewEngine(project_dir, generator_loop_config, db)
        preview = engine.generate_preview()

        turbo = preview.modes[0]

        # Token estimate should be roughly chars/4
        expected = turbo.total_length // 4
        assert turbo.token_estimate == expected
