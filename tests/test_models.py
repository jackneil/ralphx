"""Tests for RalphX Pydantic models."""

import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from ralphx.models import (
    Project,
    ProjectCreate,
    LoopConfig,
    Mode,
    ModeSelection,
    Limits,
    LoopType,
    ModeSelectionStrategy,
    WorkItem,
    WorkItemStatus,
    WorkItemCreate,
    Run,
    RunStatus,
    Session,
    Guardrail,
    GuardrailCategory,
    GuardrailSource,
)
from ralphx.models.project import generate_slug


class TestSlugGeneration:
    """Test slug generation function."""

    def test_simple_name(self):
        """Test slug from simple name."""
        assert generate_slug("My App") == "my-app"

    def test_underscores_to_hyphens(self):
        """Test underscores convert to hyphens."""
        assert generate_slug("my_app") == "my-app"

    def test_special_chars_removed(self):
        """Test special characters are removed."""
        assert generate_slug("My App (v2)") == "my-app-v2"

    def test_multiple_spaces(self):
        """Test multiple spaces collapse to single hyphen."""
        assert generate_slug("My   App") == "my-app"

    def test_leading_trailing_stripped(self):
        """Test leading/trailing hyphens stripped."""
        assert generate_slug("  My App  ") == "my-app"

    def test_empty_fallback(self):
        """Test empty string falls back to 'project'."""
        assert generate_slug("!!!") == "project"


class TestProjectCreate:
    """Test ProjectCreate model."""

    def test_create_with_auto_slug(self):
        """Test creating project with auto-generated slug."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = ProjectCreate(
                name="My SaaS App",
                path=Path(tmpdir),
            )
            assert project.slug == "my-saas-app"

    def test_create_with_custom_slug(self):
        """Test creating project with custom slug."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = ProjectCreate(
                name="My App",
                path=Path(tmpdir),
                slug="custom-slug",
            )
            assert project.slug == "custom-slug"

    def test_invalid_path_not_exists(self):
        """Test error when path doesn't exist."""
        with pytest.raises(ValidationError) as exc:
            ProjectCreate(
                name="App",
                path=Path("/nonexistent/path"),
            )
        assert "does not exist" in str(exc.value)

    def test_invalid_path_not_absolute(self):
        """Test error when path is relative."""
        with pytest.raises(ValidationError) as exc:
            ProjectCreate(
                name="App",
                path=Path("relative/path"),
            )
        assert "absolute" in str(exc.value)

    def test_to_project(self):
        """Test converting to full Project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            create = ProjectCreate(
                name="My App",
                path=Path(tmpdir),
                design_doc="design/PRD.md",
            )
            project = create.to_project()
            assert project.id is not None
            assert project.name == "My App"
            assert project.design_doc == "design/PRD.md"


class TestProject:
    """Test Project model."""

    def test_design_doc_path(self):
        """Test design_doc_path property."""
        project = Project(
            id="123",
            slug="app",
            name="App",
            path=Path("/home/user/app"),
            design_doc="design/PRD.md",
        )
        assert project.design_doc_path == Path("/home/user/app/design/PRD.md")

    def test_design_doc_path_none(self):
        """Test design_doc_path when no design doc."""
        project = Project(
            id="123",
            slug="app",
            name="App",
            path=Path("/home/user/app"),
        )
        assert project.design_doc_path is None

    def test_to_dict_from_dict(self):
        """Test round-trip serialization."""
        project = Project(
            id="123",
            slug="app",
            name="App",
            path=Path("/home/user/app"),
            design_doc="design/PRD.md",
        )
        data = project.to_dict()
        restored = Project.from_dict(data)
        assert restored.id == project.id
        assert restored.slug == project.slug
        assert restored.name == project.name


class TestLoopConfig:
    """Test LoopConfig model."""

    def test_minimal_config(self):
        """Test minimal valid configuration."""
        config = LoopConfig(
            name="research",
            display_name="Research Loop",
            type=LoopType.GENERATOR,
            modes={
                "default": Mode(
                    timeout=300,
                    model="sonnet",
                    prompt_template="prompts/research.md",
                )
            },
            mode_selection=ModeSelection(
                strategy=ModeSelectionStrategy.FIXED,
                fixed_mode="default",
            ),
        )
        assert config.name == "research"
        assert "default" in config.modes

    def test_invalid_name_uppercase(self):
        """Test error on uppercase in name."""
        with pytest.raises(ValidationError):
            LoopConfig(
                name="Research",  # Invalid - uppercase
                display_name="Research",
                type=LoopType.GENERATOR,
                modes={"default": Mode(timeout=300, model="sonnet", prompt_template="p.md")},
                mode_selection=ModeSelection(strategy=ModeSelectionStrategy.FIXED, fixed_mode="default"),
            )

    def test_weighted_random_must_sum_100(self):
        """Test weighted_random weights must sum to 100."""
        with pytest.raises(ValidationError) as exc:
            LoopConfig(
                name="test",
                display_name="Test",
                type=LoopType.GENERATOR,
                modes={
                    "turbo": Mode(timeout=180, model="sonnet", prompt_template="t.md"),
                    "deep": Mode(timeout=900, model="opus", prompt_template="d.md"),
                },
                mode_selection=ModeSelection(
                    strategy=ModeSelectionStrategy.WEIGHTED_RANDOM,
                    weights={"turbo": 50, "deep": 30},  # Only 80
                ),
            )
        assert "100" in str(exc.value)

    def test_fixed_mode_must_exist(self):
        """Test fixed_mode must reference existing mode."""
        with pytest.raises(ValidationError) as exc:
            LoopConfig(
                name="test",
                display_name="Test",
                type=LoopType.GENERATOR,
                modes={"default": Mode(timeout=300, model="sonnet", prompt_template="p.md")},
                mode_selection=ModeSelection(
                    strategy=ModeSelectionStrategy.FIXED,
                    fixed_mode="nonexistent",
                ),
            )
        assert "not found" in str(exc.value)

    def test_from_yaml_string(self):
        """Test loading from YAML string."""
        yaml_content = """
name: research
display_name: "Research Loop"
type: generator
modes:
  turbo:
    description: "Fast mode"
    timeout: 180
    model: sonnet
    tools: []
    prompt_template: prompts/turbo.md
  deep:
    timeout: 900
    model: opus
    tools: [WebSearch, WebFetch]
    prompt_template: prompts/deep.md
mode_selection:
  strategy: weighted_random
  weights:
    turbo: 85
    deep: 15
limits:
  max_iterations: 100
  max_consecutive_errors: 5
"""
        config = LoopConfig.from_yaml_string(yaml_content)
        assert config.name == "research"
        assert len(config.modes) == 2
        assert config.mode_selection.weights["turbo"] == 85

    def test_get_mode(self):
        """Test getting mode by name."""
        config = LoopConfig(
            name="test",
            display_name="Test",
            type=LoopType.GENERATOR,
            modes={"default": Mode(timeout=300, model="sonnet", prompt_template="p.md")},
            mode_selection=ModeSelection(strategy=ModeSelectionStrategy.FIXED, fixed_mode="default"),
        )
        mode = config.get_mode("default")
        assert mode.timeout == 300

    def test_get_mode_not_found(self):
        """Test error getting nonexistent mode."""
        config = LoopConfig(
            name="test",
            display_name="Test",
            type=LoopType.GENERATOR,
            modes={"default": Mode(timeout=300, model="sonnet", prompt_template="p.md")},
            mode_selection=ModeSelection(strategy=ModeSelectionStrategy.FIXED, fixed_mode="default"),
        )
        with pytest.raises(KeyError):
            config.get_mode("nonexistent")


class TestWorkItem:
    """Test WorkItem models."""

    def test_create_work_item(self):
        """Test creating a work item."""
        create = WorkItemCreate(
            id="ANS-001",
            content="Implement billing logic",
            priority=1,
            category="ANS",
            tags=["billing", "core"],
        )
        item = create.to_work_item("project-123")
        assert item.id == "ANS-001"
        assert item.project_id == "project-123"
        assert item.status == WorkItemStatus.PENDING

    def test_status_enum_values(self):
        """Test all status enum values."""
        assert WorkItemStatus.PENDING.value == "pending"
        assert WorkItemStatus.IN_PROGRESS.value == "in_progress"
        assert WorkItemStatus.COMPLETED.value == "completed"
        assert WorkItemStatus.FAILED.value == "failed"
        assert WorkItemStatus.SKIPPED.value == "skipped"
        assert WorkItemStatus.DUPLICATE.value == "duplicate"

    def test_is_actionable(self):
        """Test is_actionable method."""
        item = WorkItem(id="1", project_id="p", content="test", status=WorkItemStatus.PENDING)
        assert item.is_actionable() is True

        item.status = WorkItemStatus.COMPLETED
        assert item.is_actionable() is False

    def test_is_terminal(self):
        """Test is_terminal method."""
        item = WorkItem(id="1", project_id="p", content="test", status=WorkItemStatus.PENDING)
        assert item.is_terminal() is False

        item.status = WorkItemStatus.COMPLETED
        assert item.is_terminal() is True


class TestRun:
    """Test Run model."""

    def test_create_run(self):
        """Test creating a run."""
        run = Run(
            id="run-123",
            project_id="project-456",
            loop_name="research",
        )
        assert run.status == RunStatus.ACTIVE
        assert run.is_active is True
        assert run.is_terminal is False

    def test_terminal_states(self):
        """Test terminal state detection."""
        for status in [RunStatus.COMPLETED, RunStatus.ERROR, RunStatus.ABORTED]:
            run = Run(id="r", project_id="p", loop_name="l", status=status)
            assert run.is_terminal is True
            assert run.is_active is False

    def test_duration(self):
        """Test duration calculation."""
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        run = Run(
            id="r",
            project_id="p",
            loop_name="l",
            started_at=now - timedelta(hours=1),
            completed_at=now,
        )
        assert 3599 < run.duration_seconds < 3601  # ~1 hour

    def test_to_dict_from_dict(self):
        """Test round-trip serialization."""
        run = Run(id="r", project_id="p", loop_name="l")
        data = run.to_dict()
        restored = Run.from_dict(data)
        assert restored.id == run.id
        assert restored.status == run.status


class TestSession:
    """Test Session model."""

    def test_create_session(self):
        """Test creating a session."""
        session = Session(
            session_id="abc-123",
            project_id="project",
            run_id="run-1",
            iteration=5,
            mode="turbo",
        )
        assert session.iteration == 5
        assert session.mode == "turbo"

    def test_items_added_json(self):
        """Test items_added from JSON string."""
        data = {
            "session_id": "s1",
            "project_id": "p1",
            "iteration": 1,
            "items_added": '["item-1", "item-2"]',
        }
        session = Session.from_dict(data)
        assert session.items_added == ["item-1", "item-2"]


class TestGuardrail:
    """Test Guardrail model."""

    def test_create_guardrail(self):
        """Test creating a guardrail."""
        guardrail = Guardrail(
            category=GuardrailCategory.SAFETY,
            filename="never-do.md",
            source=GuardrailSource.GLOBAL,
            file_path="/home/user/.ralphx/guardrails/safety/never-do.md",
            file_size=1024,
        )
        assert guardrail.enabled is True
        assert guardrail.category == GuardrailCategory.SAFETY

    def test_applies_to_loop(self):
        """Test applies_to_loop filter."""
        # No filter - applies to all
        g1 = Guardrail(
            category=GuardrailCategory.SAFETY,
            filename="rule.md",
            source=GuardrailSource.GLOBAL,
            file_path="/path",
        )
        assert g1.applies_to_loop("any") is True

        # With filter
        g2 = Guardrail(
            category=GuardrailCategory.SAFETY,
            filename="rule.md",
            source=GuardrailSource.GLOBAL,
            file_path="/path",
            loops=["research", "implement"],
        )
        assert g2.applies_to_loop("research") is True
        assert g2.applies_to_loop("other") is False

    def test_applies_to_mode(self):
        """Test applies_to_mode filter."""
        g = Guardrail(
            category=GuardrailCategory.SAFETY,
            filename="rule.md",
            source=GuardrailSource.GLOBAL,
            file_path="/path",
            modes=["turbo"],
        )
        assert g.applies_to_mode("turbo") is True
        assert g.applies_to_mode("deep") is False

    def test_category_enum_values(self):
        """Test category enum values."""
        assert GuardrailCategory.SYSTEM.value == "system"
        assert GuardrailCategory.SAFETY.value == "safety"
        assert GuardrailCategory.DOMAIN.value == "domain"
        assert GuardrailCategory.OUTPUT.value == "output"
        assert GuardrailCategory.CUSTOM.value == "custom"

    def test_source_enum_values(self):
        """Test source enum values."""
        assert GuardrailSource.GLOBAL.value == "global"
        assert GuardrailSource.WORKSPACE.value == "workspace"
        assert GuardrailSource.REPO.value == "repo"
        assert GuardrailSource.AUTO_DETECTED.value == "auto-detected"
