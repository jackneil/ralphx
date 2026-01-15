"""Tests for RalphX guardrails management."""

import tempfile
from pathlib import Path

import pytest

from ralphx.core.guardrails import (
    AI_INSTRUCTION_PATTERNS,
    GUARDRAIL_TEMPLATES,
    MAX_FILE_SIZE,
    MAX_TOTAL_SIZE,
    DetectedFile,
    DetectionReport,
    GuardrailDetector,
    GuardrailSet,
    GuardrailsManager,
    InjectionPosition,
    LoadedGuardrail,
    create_template_guardrails,
    list_templates,
)
from ralphx.models.guardrail import GuardrailCategory, GuardrailSource
from ralphx.models.loop import (
    AdditionalGuardrail,
    ContextConfig,
    GuardrailsConfig,
    LoopConfig,
    LoopType,
    Mode,
    ModeGuardrails,
    ModeSelection,
    ModeSelectionStrategy,
)


@pytest.fixture
def project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        # Create guardrails directories
        (project_path / ".ralphx" / "guardrails" / "system").mkdir(parents=True)
        (project_path / ".ralphx" / "guardrails" / "domain").mkdir(parents=True)
        yield project_path


@pytest.fixture
def workspace_dir():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def manager(project_dir, workspace_dir, monkeypatch):
    """Create a guardrails manager."""
    # Patch workspace functions
    def mock_workspace():
        return workspace_dir

    def mock_project_workspace(slug):
        path = workspace_dir / "projects" / slug
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr("ralphx.core.guardrails.get_workspace_path", mock_workspace)
    monkeypatch.setattr("ralphx.core.guardrails.ensure_project_workspace", mock_project_workspace)

    return GuardrailsManager(project_dir, "test")


class TestLoadedGuardrail:
    """Test LoadedGuardrail dataclass."""

    def test_basic_guardrail(self):
        """Test creating a basic guardrail."""
        g = LoadedGuardrail(
            category=GuardrailCategory.SYSTEM,
            filename="test.md",
            source=GuardrailSource.GLOBAL,
            file_path=Path("/test.md"),
            content="Test content",
        )
        assert g.category == GuardrailCategory.SYSTEM
        assert g.filename == "test.md"
        assert g.size == len("Test content".encode())

    def test_custom_position(self):
        """Test guardrail with custom position."""
        g = LoadedGuardrail(
            category=GuardrailCategory.CUSTOM,
            filename="test.md",
            source=GuardrailSource.GLOBAL,
            file_path=Path("/test.md"),
            content="Content",
            position=InjectionPosition.BEFORE_TASK,
        )
        assert g.position == InjectionPosition.BEFORE_TASK


class TestGuardrailSet:
    """Test GuardrailSet class."""

    def test_empty_set(self):
        """Test empty guardrail set."""
        gs = GuardrailSet()
        assert len(gs.guardrails) == 0
        assert gs.total_size == 0

    def test_add_guardrail(self):
        """Test adding guardrail."""
        gs = GuardrailSet()
        g = LoadedGuardrail(
            category=GuardrailCategory.SYSTEM,
            filename="test.md",
            source=GuardrailSource.GLOBAL,
            file_path=Path("/test.md"),
            content="Test content",
        )
        gs.add(g)
        assert len(gs.guardrails) == 1
        assert gs.total_size == g.size

    def test_get_by_category(self):
        """Test getting guardrails by category."""
        gs = GuardrailSet()
        g1 = LoadedGuardrail(
            category=GuardrailCategory.SYSTEM,
            filename="system.md",
            source=GuardrailSource.GLOBAL,
            file_path=Path("/system.md"),
            content="System",
        )
        g2 = LoadedGuardrail(
            category=GuardrailCategory.DOMAIN,
            filename="domain.md",
            source=GuardrailSource.GLOBAL,
            file_path=Path("/domain.md"),
            content="Domain",
        )
        gs.add(g1)
        gs.add(g2)

        system = gs.get_by_category(GuardrailCategory.SYSTEM)
        assert len(system) == 1
        assert system[0].filename == "system.md"

    def test_get_by_position(self):
        """Test getting guardrails by position."""
        gs = GuardrailSet()
        g1 = LoadedGuardrail(
            category=GuardrailCategory.SYSTEM,
            filename="before.md",
            source=GuardrailSource.GLOBAL,
            file_path=Path("/before.md"),
            content="Before",
            position=InjectionPosition.BEFORE_PROMPT,
        )
        g2 = LoadedGuardrail(
            category=GuardrailCategory.DOMAIN,
            filename="after.md",
            source=GuardrailSource.GLOBAL,
            file_path=Path("/after.md"),
            content="After",
            position=InjectionPosition.AFTER_DESIGN_DOC,
        )
        gs.add(g1)
        gs.add(g2)

        before = gs.get_by_position(InjectionPosition.BEFORE_PROMPT)
        assert len(before) == 1
        assert before[0].filename == "before.md"


class TestGuardrailsManager:
    """Test GuardrailsManager class."""

    def test_validate_valid_file(self, project_dir, manager):
        """Test validating a valid file."""
        file_path = project_dir / "test.md"
        file_path.write_text("Valid content")

        is_valid, error = manager._validate_file(file_path)
        assert is_valid is True
        assert error is None

    def test_validate_nonexistent_file(self, manager):
        """Test validating nonexistent file."""
        is_valid, error = manager._validate_file(Path("/nonexistent"))
        assert is_valid is False
        assert "not found" in error

    def test_validate_empty_file(self, project_dir, manager):
        """Test validating empty file."""
        file_path = project_dir / "empty.md"
        file_path.touch()

        is_valid, error = manager._validate_file(file_path)
        assert is_valid is False
        assert "Empty" in error

    def test_validate_symlink(self, project_dir, manager):
        """Test validating symlink."""
        target = project_dir / "target.md"
        target.write_text("Content")
        symlink = project_dir / "link.md"
        symlink.symlink_to(target)

        is_valid, error = manager._validate_file(symlink)
        assert is_valid is False
        assert "Symlinks" in error

    def test_validate_large_file(self, project_dir, manager):
        """Test validating file that's too large."""
        file_path = project_dir / "large.md"
        # Write content larger than MAX_FILE_SIZE
        file_path.write_text("x" * (MAX_FILE_SIZE + 1))

        is_valid, error = manager._validate_file(file_path)
        assert is_valid is False
        assert "too large" in error

    def test_load_file(self, project_dir, manager):
        """Test loading a guardrail file."""
        file_path = project_dir / ".ralphx" / "guardrails" / "system" / "test.md"
        file_path.write_text("System guardrail content")

        guardrail = manager._load_file(
            file_path,
            GuardrailCategory.SYSTEM,
            GuardrailSource.PROJECT,
        )

        assert guardrail is not None
        assert guardrail.category == GuardrailCategory.SYSTEM
        assert guardrail.source == GuardrailSource.PROJECT
        assert guardrail.content == "System guardrail content"

    def test_load_directory(self, project_dir, manager):
        """Test loading guardrails from directory."""
        # Create some guardrail files
        system_dir = project_dir / ".ralphx" / "guardrails" / "system"
        (system_dir / "rules.md").write_text("System rules")

        domain_dir = project_dir / ".ralphx" / "guardrails" / "domain"
        (domain_dir / "spec.md").write_text("Domain spec")

        guardrails = manager._load_directory(
            project_dir / ".ralphx" / "guardrails",
            GuardrailSource.PROJECT,
        )

        assert len(guardrails) == 2
        filenames = {g.filename for g in guardrails}
        assert "rules.md" in filenames
        assert "spec.md" in filenames

    def test_load_all_empty(self, manager):
        """Test loading when no guardrails exist."""
        gs = manager.load_all()
        assert len(gs.guardrails) == 0

    def test_load_all_with_project_guardrails(self, project_dir, manager):
        """Test loading project guardrails."""
        # Create guardrail
        system_dir = project_dir / ".ralphx" / "guardrails" / "system"
        (system_dir / "rules.md").write_text("Project rules")

        gs = manager.load_all()

        assert len(gs.guardrails) == 1
        assert gs.guardrails[0].source == GuardrailSource.PROJECT

    def test_precedence_deduplication(self, project_dir, workspace_dir, manager):
        """Test that higher precedence wins for duplicate filenames."""
        # Create same-named file in project and workspace
        project_file = project_dir / ".ralphx" / "guardrails" / "system" / "rules.md"
        project_file.write_text("Project rules")

        workspace_guardrails = workspace_dir / "projects" / "test" / "guardrails" / "system"
        workspace_guardrails.mkdir(parents=True)
        (workspace_guardrails / "rules.md").write_text("Workspace rules")

        gs = manager.load_all()

        # Should only have one rules.md (from project - higher precedence)
        rules = [g for g in gs.guardrails if g.filename == "rules.md"]
        assert len(rules) == 1
        assert rules[0].source == GuardrailSource.PROJECT

    def test_substitute_variables(self, manager):
        """Test variable substitution."""
        content = "Hello {{name}}, welcome to {{project}}!"
        variables = {"name": "Alice", "project": "RalphX"}

        result = manager.substitute_variables(content, variables)

        assert result == "Hello Alice, welcome to RalphX!"

    def test_substitute_undefined_variable(self, manager):
        """Test error on undefined variable."""
        content = "Hello {{undefined}}!"

        with pytest.raises(ValueError, match="undefined"):
            manager.substitute_variables(content, {})

    def test_build_prompt_section(self, manager):
        """Test building prompt section."""
        gs = GuardrailSet()
        gs.add(LoadedGuardrail(
            category=GuardrailCategory.SYSTEM,
            filename="a.md",
            source=GuardrailSource.GLOBAL,
            file_path=Path("/a.md"),
            content="First section",
            position=InjectionPosition.BEFORE_PROMPT,
        ))
        gs.add(LoadedGuardrail(
            category=GuardrailCategory.SYSTEM,
            filename="b.md",
            source=GuardrailSource.GLOBAL,
            file_path=Path("/b.md"),
            content="Second section",
            position=InjectionPosition.BEFORE_PROMPT,
        ))

        section = manager.build_prompt_section(gs, InjectionPosition.BEFORE_PROMPT)

        assert "First section" in section
        assert "Second section" in section

    def test_build_prompt_section_with_variables(self, manager):
        """Test building prompt section with variables."""
        gs = GuardrailSet()
        gs.add(LoadedGuardrail(
            category=GuardrailCategory.SYSTEM,
            filename="a.md",
            source=GuardrailSource.GLOBAL,
            file_path=Path("/a.md"),
            content="Project: {{project}}",
            position=InjectionPosition.BEFORE_PROMPT,
        ))

        section = manager.build_prompt_section(
            gs,
            InjectionPosition.BEFORE_PROMPT,
            {"project": "RalphX"},
        )

        assert "Project: RalphX" in section

    def test_validate_empty(self, manager):
        """Test validation with no guardrails."""
        errors = manager.validate()
        assert len(errors) == 0

    def test_validate_with_template_vars(self, project_dir, manager):
        """Test validation with template variables."""
        file_path = project_dir / ".ralphx" / "guardrails" / "system" / "test.md"
        file_path.write_text("Use {{undefined_var}} here")

        errors = manager.validate()

        # Should warn about template variables
        assert any("undefined_var" in e for e in errors)

    def test_clear_cache(self, manager):
        """Test clearing cache."""
        # Load to populate cache
        manager.load_all()
        assert len(manager._cache) > 0

        manager.clear_cache()
        assert len(manager._cache) == 0

    def test_list_files(self, project_dir, manager):
        """Test listing guardrail files."""
        # Create files
        file_path = project_dir / ".ralphx" / "guardrails" / "system" / "test.md"
        file_path.write_text("Content")

        files = manager.list_files()

        assert len(files) >= 1
        assert any(f["path"].endswith("test.md") for f in files)

    def test_category_position_mapping(self, manager):
        """Test that categories map to correct positions."""
        assert manager.CATEGORY_POSITIONS[GuardrailCategory.SYSTEM] == InjectionPosition.BEFORE_PROMPT
        assert manager.CATEGORY_POSITIONS[GuardrailCategory.SAFETY] == InjectionPosition.BEFORE_PROMPT
        assert manager.CATEGORY_POSITIONS[GuardrailCategory.DOMAIN] == InjectionPosition.AFTER_DESIGN_DOC
        assert manager.CATEGORY_POSITIONS[GuardrailCategory.OUTPUT] == InjectionPosition.BEFORE_TASK
        assert manager.CATEGORY_POSITIONS[GuardrailCategory.CUSTOM] == InjectionPosition.AFTER_TASK


class TestGuardrailsWithLoopConfig:
    """Test guardrails with loop configuration."""

    @pytest.fixture
    def loop_config_with_guardrails(self, project_dir):
        """Create loop config with guardrails."""
        # Create include file
        include_file = project_dir / "custom_rules.md"
        include_file.write_text("Custom rules content")

        return LoopConfig(
            name="test",
            display_name="Test Loop",
            type=LoopType.GENERATOR,
            modes={
                "default": Mode(
                    timeout=300,
                    model="sonnet",
                    prompt_template="prompts/default.md",
                ),
            },
            mode_selection=ModeSelection(
                strategy=ModeSelectionStrategy.FIXED,
                fixed_mode="default",
            ),
            context=ContextConfig(
                guardrails=GuardrailsConfig(
                    enabled=True,
                    include=["custom_rules.md"],
                ),
            ),
        )

    def test_load_loop_guardrails(self, project_dir, manager, loop_config_with_guardrails):
        """Test loading guardrails from loop config."""
        gs = manager.load_all(loop_config_with_guardrails)

        # Should have the include file
        assert any(g.filename == "custom_rules.md" for g in gs.guardrails)

    def test_load_inline_guardrails(self, project_dir, manager):
        """Test loading inline guardrails."""
        config = LoopConfig(
            name="test",
            display_name="Test Loop",
            type=LoopType.GENERATOR,
            modes={
                "default": Mode(
                    timeout=300,
                    model="sonnet",
                    prompt_template="prompts/default.md",
                ),
            },
            mode_selection=ModeSelection(
                strategy=ModeSelectionStrategy.FIXED,
                fixed_mode="default",
            ),
            context=ContextConfig(
                guardrails=GuardrailsConfig(
                    enabled=True,
                    additional=[
                        AdditionalGuardrail(content="Inline guardrail content"),
                    ],
                ),
            ),
        )

        gs = manager.load_all(config)

        # Should have inline guardrail
        inline = [g for g in gs.guardrails if "inline" in g.filename]
        assert len(inline) == 1
        assert inline[0].content == "Inline guardrail content"


class TestInjectionPosition:
    """Test InjectionPosition enum."""

    def test_all_positions(self):
        """Test all position values."""
        assert InjectionPosition.BEFORE_PROMPT.value == "before_prompt"
        assert InjectionPosition.AFTER_DESIGN_DOC.value == "after_design_doc"
        assert InjectionPosition.BEFORE_TASK.value == "before_task"
        assert InjectionPosition.AFTER_TASK.value == "after_task"


class TestGuardrailDetector:
    """Test GuardrailDetector class."""

    @pytest.fixture
    def detect_project(self):
        """Create a temporary project for detection tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            yield project_path

    def test_detect_claude_md(self, detect_project):
        """Test detecting CLAUDE.md file."""
        claude_file = detect_project / "CLAUDE.md"
        claude_file.write_text("# Claude Instructions\n\nBe helpful.")

        detector = GuardrailDetector(detect_project)
        report = detector.detect()

        assert len(report.detected_files) == 1
        assert report.detected_files[0].path == claude_file
        assert report.detected_files[0].pattern == "CLAUDE.md"

    def test_detect_multiple_patterns(self, detect_project):
        """Test detecting multiple AI instruction files."""
        (detect_project / "CLAUDE.md").write_text("Claude content")
        (detect_project / ".cursorrules").write_text("Cursor rules")
        (detect_project / "llms.txt").write_text("LLM instructions")

        detector = GuardrailDetector(detect_project)
        report = detector.detect()

        assert len(report.detected_files) == 3
        filenames = {f.path.name for f in report.detected_files}
        assert "CLAUDE.md" in filenames
        assert ".cursorrules" in filenames
        assert "llms.txt" in filenames

    def test_detect_cursor_rules_glob(self, detect_project):
        """Test detecting .cursor/rules/*.md glob pattern."""
        rules_dir = detect_project / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "code-style.md").write_text("Code style rules")
        (rules_dir / "security.md").write_text("Security rules")

        detector = GuardrailDetector(detect_project)
        report = detector.detect()

        cursor_files = [f for f in report.detected_files if ".cursor" in str(f.path)]
        assert len(cursor_files) == 2

    def test_detect_symlink_warning(self, detect_project):
        """Test that symlinks are detected with warning."""
        target = detect_project / "target.md"
        target.write_text("Target content")
        symlink = detect_project / "CLAUDE.md"
        symlink.symlink_to(target)

        detector = GuardrailDetector(detect_project)
        report = detector.detect()

        assert len(report.detected_files) == 1
        assert report.detected_files[0].is_symlink is True
        assert report.detected_files[0].is_valid is False
        assert any("Symlink" in w for w in report.detected_files[0].warnings)

    def test_detect_large_file_warning(self, detect_project):
        """Test that large files get warning."""
        large_file = detect_project / "CLAUDE.md"
        large_file.write_text("x" * (MAX_FILE_SIZE + 1))

        detector = GuardrailDetector(detect_project)
        report = detector.detect()

        assert len(report.detected_files) == 1
        assert report.detected_files[0].is_valid is False
        assert any("too large" in w for w in report.detected_files[0].warnings)

    def test_detect_empty_file_warning(self, detect_project):
        """Test that empty files get warning."""
        empty_file = detect_project / "CLAUDE.md"
        empty_file.touch()

        detector = GuardrailDetector(detect_project)
        report = detector.detect()

        assert len(report.detected_files) == 1
        assert report.detected_files[0].is_valid is False
        assert any("Empty" in w for w in report.detected_files[0].warnings)

    def test_detect_cloned_repo(self, detect_project):
        """Test detecting cloned repository."""
        git_dir = detect_project / ".git"
        git_dir.mkdir()
        config = git_dir / "config"
        config.write_text('[remote "origin"]\n\turl = https://github.com/user/repo.git\n')

        detector = GuardrailDetector(detect_project)
        report = detector.detect()

        assert report.is_cloned_repo is True
        assert "github.com/user/repo.git" in report.remote_url

    def test_detect_cloned_repo_with_files(self, detect_project):
        """Test security warning for cloned repo with AI files."""
        # Set up cloned repo
        git_dir = detect_project / ".git"
        git_dir.mkdir()
        config = git_dir / "config"
        config.write_text('[remote "origin"]\n\turl = https://github.com/user/repo.git\n')

        # Add AI instruction file
        (detect_project / "CLAUDE.md").write_text("Instructions")

        detector = GuardrailDetector(detect_project)
        report = detector.detect()

        assert report.has_security_warning is True
        assert len(report.warnings) > 0
        assert any("cloned repository" in w.lower() for w in report.warnings)

    def test_detect_not_cloned_local_path(self, detect_project):
        """Test that local paths are not flagged as cloned."""
        git_dir = detect_project / ".git"
        git_dir.mkdir()
        config = git_dir / "config"
        config.write_text('[remote "origin"]\n\turl = /home/user/local-repo\n')

        detector = GuardrailDetector(detect_project)
        report = detector.detect()

        assert report.is_cloned_repo is False

    def test_detect_preview_content(self, detect_project):
        """Test that preview shows first 500 chars."""
        content = "Line 1\n" * 100  # More than 500 chars
        (detect_project / "CLAUDE.md").write_text(content)

        detector = GuardrailDetector(detect_project)
        report = detector.detect()

        assert len(report.detected_files) == 1
        preview = report.detected_files[0].preview
        assert len(preview) <= 503  # 500 + "..."
        assert preview.endswith("...")

    def test_detect_custom_patterns(self, detect_project):
        """Test detection with custom pattern list."""
        (detect_project / "MY_RULES.md").write_text("My rules")
        (detect_project / "CLAUDE.md").write_text("Claude")

        detector = GuardrailDetector(detect_project)
        report = detector.detect(patterns=["MY_RULES.md"])

        assert len(report.detected_files) == 1
        assert report.detected_files[0].path.name == "MY_RULES.md"

    def test_detect_empty_project(self, detect_project):
        """Test detection on empty project."""
        detector = GuardrailDetector(detect_project)
        report = detector.detect()

        assert len(report.detected_files) == 0
        assert report.is_cloned_repo is False

    def test_copy_to_workspace(self, detect_project, workspace_dir):
        """Test copying detected file to workspace."""
        claude_file = detect_project / "CLAUDE.md"
        claude_file.write_text("Claude instructions")

        detector = GuardrailDetector(detect_project)
        report = detector.detect()

        target_dir = workspace_dir / "guardrails"
        result = detector.copy_to_workspace(
            report.detected_files[0],
            target_dir,
            GuardrailCategory.CUSTOM,
        )

        assert result is not None
        assert result.exists()
        assert result.read_text() == "Claude instructions"

    def test_copy_to_workspace_invalid_file(self, detect_project, workspace_dir):
        """Test copy fails for invalid file (symlink)."""
        target = detect_project / "target.md"
        target.write_text("content")
        symlink = detect_project / "CLAUDE.md"
        symlink.symlink_to(target)

        detector = GuardrailDetector(detect_project)
        report = detector.detect()

        target_dir = workspace_dir / "guardrails"
        result = detector.copy_to_workspace(
            report.detected_files[0],
            target_dir,
        )

        assert result is None


class TestDetectedFile:
    """Test DetectedFile dataclass."""

    def test_valid_file(self):
        """Test is_valid for normal file."""
        df = DetectedFile(
            path=Path("/test.md"),
            pattern="test.md",
            size=100,
            is_symlink=False,
            preview="content",
        )
        assert df.is_valid is True

    def test_invalid_symlink(self):
        """Test is_valid for symlink."""
        df = DetectedFile(
            path=Path("/test.md"),
            pattern="test.md",
            size=100,
            is_symlink=True,
            preview="content",
        )
        assert df.is_valid is False

    def test_invalid_empty(self):
        """Test is_valid for empty file."""
        df = DetectedFile(
            path=Path("/test.md"),
            pattern="test.md",
            size=0,
            is_symlink=False,
            preview="",
        )
        assert df.is_valid is False

    def test_invalid_too_large(self):
        """Test is_valid for large file."""
        df = DetectedFile(
            path=Path("/test.md"),
            pattern="test.md",
            size=MAX_FILE_SIZE + 1,
            is_symlink=False,
            preview="content",
        )
        assert df.is_valid is False


class TestDetectionReport:
    """Test DetectionReport dataclass."""

    def test_summary(self):
        """Test report summary."""
        report = DetectionReport(
            project_path=Path("/test"),
            detected_files=[
                DetectedFile(Path("/a.md"), "a.md", 10, False, ""),
                DetectedFile(Path("/b.md"), "b.md", 20, False, ""),
            ],
            is_cloned_repo=True,
            remote_url="https://github.com/test/repo",
        )
        summary = report.summary()
        assert "2" in summary
        assert "github.com" in summary

    def test_has_security_warning(self):
        """Test security warning detection."""
        report = DetectionReport(
            project_path=Path("/test"),
            detected_files=[DetectedFile(Path("/a.md"), "a.md", 10, False, "")],
            is_cloned_repo=True,
            remote_url="https://github.com/test/repo",
        )
        assert report.has_security_warning is True

    def test_no_security_warning_local(self):
        """Test no warning for local repo."""
        report = DetectionReport(
            project_path=Path("/test"),
            detected_files=[DetectedFile(Path("/a.md"), "a.md", 10, False, "")],
            is_cloned_repo=False,
        )
        assert report.has_security_warning is False


class TestGuardrailTemplates:
    """Test guardrail template functionality."""

    def test_list_templates(self):
        """Test listing available templates."""
        templates = list_templates()
        assert "web-app" in templates
        assert "backend-api" in templates
        assert "healthcare" in templates
        assert "e-commerce" in templates
        assert "cli-tool" in templates

    def test_create_template_web_app(self, workspace_dir):
        """Test creating web-app template."""
        output_dir = workspace_dir / "guardrails"
        created = create_template_guardrails("web-app", output_dir)

        assert len(created) == 2
        assert (output_dir / "system" / "web-app.md").exists()
        assert (output_dir / "safety" / "web-app.md").exists()

    def test_create_template_healthcare(self, workspace_dir):
        """Test creating healthcare template with HIPAA content."""
        output_dir = workspace_dir / "guardrails"
        created = create_template_guardrails("healthcare", output_dir)

        safety_file = output_dir / "safety" / "healthcare.md"
        assert safety_file.exists()

        content = safety_file.read_text()
        assert "HIPAA" in content

    def test_create_template_invalid(self, workspace_dir):
        """Test creating unknown template raises error."""
        output_dir = workspace_dir / "guardrails"
        with pytest.raises(ValueError, match="Unknown template"):
            create_template_guardrails("nonexistent", output_dir)

    def test_template_patterns_constant(self):
        """Test AI instruction patterns are defined."""
        assert len(AI_INSTRUCTION_PATTERNS) >= 16
        assert "CLAUDE.md" in AI_INSTRUCTION_PATTERNS
        assert ".cursorrules" in AI_INSTRUCTION_PATTERNS
