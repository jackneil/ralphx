"""Guardrails management for RalphX.

Implements:
- GuardrailsManager for loading and managing guardrails
- 6-layer precedence loading
- Category-based injection positions
- Template variable substitution
- Size limit enforcement
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from ralphx.core.workspace import ensure_project_workspace, get_workspace_path
from ralphx.models.guardrail import Guardrail, GuardrailCategory, GuardrailSource
from ralphx.models.loop import LoopConfig, Mode


# Size limits
MAX_FILE_SIZE = 50 * 1024  # 50KB per file
MAX_TOTAL_SIZE = 500 * 1024  # 500KB total guardrails
MAX_PROMPT_SIZE = 1024 * 1024  # 1MB prompt


class InjectionPosition(str, Enum):
    """Position for injecting guardrails into prompts."""

    BEFORE_PROMPT = "before_prompt"
    AFTER_DESIGN_DOC = "after_design_doc"
    BEFORE_TASK = "before_task"
    AFTER_TASK = "after_task"


@dataclass
class LoadedGuardrail:
    """A guardrail loaded from file."""

    category: GuardrailCategory
    filename: str
    source: GuardrailSource
    file_path: Path
    content: str
    position: InjectionPosition = InjectionPosition.AFTER_DESIGN_DOC
    size: int = 0
    mtime: Optional[float] = None

    def __post_init__(self):
        self.size = len(self.content.encode())


@dataclass
class GuardrailSet:
    """Set of guardrails for a specific context."""

    guardrails: list[LoadedGuardrail] = field(default_factory=list)
    total_size: int = 0

    def add(self, guardrail: LoadedGuardrail) -> None:
        """Add a guardrail to the set."""
        self.guardrails.append(guardrail)
        self.total_size += guardrail.size

    def get_by_category(
        self,
        category: GuardrailCategory,
    ) -> list[LoadedGuardrail]:
        """Get guardrails by category."""
        return [g for g in self.guardrails if g.category == category]

    def get_by_position(
        self,
        position: InjectionPosition,
    ) -> list[LoadedGuardrail]:
        """Get guardrails by injection position."""
        return [g for g in self.guardrails if g.position == position]


class GuardrailsManager:
    """Manages guardrails with 6-layer precedence.

    Precedence (highest to lowest):
    1. Mode-level overrides (in loop config)
    2. Loop-level overrides (in loop config)
    3. Project repo (.ralphx/guardrails/ in project)
    4. Auto-detected files (CLAUDE.md, etc.)
    5. Project workspace (~/.ralphx/projects/{slug}/guardrails/)
    6. Global (~/.ralphx/guardrails/)

    Features:
    - Category-based injection positions
    - Template variable substitution
    - Size limit enforcement
    - Symlink and empty file rejection
    - Per-run caching
    """

    # Category to position mapping
    CATEGORY_POSITIONS = {
        GuardrailCategory.SYSTEM: InjectionPosition.BEFORE_PROMPT,
        GuardrailCategory.SAFETY: InjectionPosition.BEFORE_PROMPT,
        GuardrailCategory.DOMAIN: InjectionPosition.AFTER_DESIGN_DOC,
        GuardrailCategory.OUTPUT: InjectionPosition.BEFORE_TASK,
        GuardrailCategory.CUSTOM: InjectionPosition.AFTER_TASK,
    }

    def __init__(
        self,
        project_path: Path,
        project_slug: str,
    ):
        """Initialize the guardrails manager.

        Args:
            project_path: Path to project directory.
            project_slug: Project slug for workspace.
        """
        self.project_path = project_path
        self.project_slug = project_slug
        self._cache: dict[str, GuardrailSet] = {}

    def _get_global_path(self) -> Path:
        """Get global guardrails directory."""
        return get_workspace_path() / "guardrails"

    def _get_project_workspace_path(self) -> Path:
        """Get project workspace guardrails directory."""
        return ensure_project_workspace(self.project_slug) / "guardrails"

    def _get_project_repo_path(self) -> Path:
        """Get project repo guardrails directory."""
        return self.project_path / ".ralphx" / "guardrails"

    def _validate_file(self, path: Path) -> tuple[bool, Optional[str]]:
        """Validate a guardrail file.

        Args:
            path: Path to file.

        Returns:
            Tuple of (is_valid, error_message).
        """
        # Check exists
        if not path.exists():
            return False, f"File not found: {path}"

        # Check not symlink
        if path.is_symlink():
            return False, f"Symlinks not allowed: {path}"

        # Check not directory
        if path.is_dir():
            return False, f"Directories not allowed: {path}"

        # Check size
        try:
            size = path.stat().st_size
            if size == 0:
                return False, f"Empty files not allowed: {path}"
            if size > MAX_FILE_SIZE:
                return False, f"File too large ({size} > {MAX_FILE_SIZE}): {path}"
        except OSError as e:
            return False, f"Cannot read file: {e}"

        return True, None

    def _load_file(
        self,
        path: Path,
        category: GuardrailCategory,
        source: GuardrailSource,
    ) -> Optional[LoadedGuardrail]:
        """Load a guardrail file.

        Args:
            path: Path to file.
            category: Guardrail category.
            source: Guardrail source layer.

        Returns:
            LoadedGuardrail or None if invalid.
        """
        is_valid, error = self._validate_file(path)
        if not is_valid:
            return None

        try:
            content = path.read_text()
            stat = path.stat()

            return LoadedGuardrail(
                category=category,
                filename=path.name,
                source=source,
                file_path=path,
                content=content,
                position=self.CATEGORY_POSITIONS.get(
                    category, InjectionPosition.AFTER_DESIGN_DOC
                ),
                mtime=stat.st_mtime,
            )
        except (OSError, UnicodeDecodeError):
            return None

    def _load_directory(
        self,
        directory: Path,
        source: GuardrailSource,
    ) -> list[LoadedGuardrail]:
        """Load guardrails from a directory.

        Args:
            directory: Directory to load from.
            source: Source layer.

        Returns:
            List of loaded guardrails.
        """
        guardrails = []

        if not directory.exists():
            return guardrails

        # Map directory names to categories
        category_dirs = {
            "system": GuardrailCategory.SYSTEM,
            "safety": GuardrailCategory.SAFETY,
            "domain": GuardrailCategory.DOMAIN,
            "output": GuardrailCategory.OUTPUT,
            "custom": GuardrailCategory.CUSTOM,
        }

        # Load from category subdirectories
        for dir_name, category in category_dirs.items():
            cat_dir = directory / dir_name
            if cat_dir.exists():
                for file_path in cat_dir.glob("*.md"):
                    guardrail = self._load_file(file_path, category, source)
                    if guardrail:
                        guardrails.append(guardrail)

        # Load from root (default to custom category)
        for file_path in directory.glob("*.md"):
            guardrail = self._load_file(file_path, GuardrailCategory.CUSTOM, source)
            if guardrail:
                guardrails.append(guardrail)

        return guardrails

    def load_all(
        self,
        loop_config: Optional[LoopConfig] = None,
        mode_name: Optional[str] = None,
    ) -> GuardrailSet:
        """Load all guardrails with precedence.

        Args:
            loop_config: Optional loop configuration.
            mode_name: Optional mode name for mode-specific overrides.

        Returns:
            GuardrailSet with all loaded guardrails.
        """
        # Check cache
        cache_key = f"{loop_config.name if loop_config else 'none'}:{mode_name or 'none'}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        guardrail_set = GuardrailSet()
        seen_files: set[str] = set()  # Track by filename for deduplication

        def add_if_new(guardrails: list[LoadedGuardrail]) -> None:
            for g in guardrails:
                # Higher precedence wins (don't add if already seen)
                if g.filename not in seen_files:
                    seen_files.add(g.filename)
                    guardrail_set.add(g)

        # Layer 1: Mode-level overrides
        if loop_config and mode_name:
            mode = loop_config.modes.get(mode_name)
            if mode and mode.guardrails:
                mode_guardrails = self._load_mode_guardrails(mode, loop_config)
                add_if_new(mode_guardrails)

        # Layer 2: Loop-level overrides
        if loop_config and loop_config.context and loop_config.context.guardrails:
            loop_guardrails = self._load_loop_guardrails(loop_config)
            add_if_new(loop_guardrails)

        # Layer 3: Project repo (.ralphx/guardrails/)
        repo_guardrails = self._load_directory(
            self._get_project_repo_path(),
            GuardrailSource.PROJECT,
        )
        add_if_new(repo_guardrails)

        # Layer 4: Auto-detected files are handled separately (Plan 13)

        # Layer 5: Project workspace
        workspace_guardrails = self._load_directory(
            self._get_project_workspace_path(),
            GuardrailSource.WORKSPACE,
        )
        add_if_new(workspace_guardrails)

        # Layer 6: Global
        global_guardrails = self._load_directory(
            self._get_global_path(),
            GuardrailSource.GLOBAL,
        )
        add_if_new(global_guardrails)

        # Check total size limit
        if guardrail_set.total_size > MAX_TOTAL_SIZE:
            # Remove lowest precedence guardrails until within limit
            while guardrail_set.total_size > MAX_TOTAL_SIZE and guardrail_set.guardrails:
                removed = guardrail_set.guardrails.pop()
                guardrail_set.total_size -= removed.size

        # Cache result
        self._cache[cache_key] = guardrail_set
        return guardrail_set

    def _load_mode_guardrails(
        self,
        mode: Mode,
        loop_config: LoopConfig,
    ) -> list[LoadedGuardrail]:
        """Load mode-specific guardrails.

        Args:
            mode: Mode configuration.
            loop_config: Parent loop configuration.

        Returns:
            List of loaded guardrails.
        """
        guardrails = []

        if not mode.guardrails:
            return guardrails

        # Handle include files
        if mode.guardrails.include:
            for filename in mode.guardrails.include:
                path = self.project_path / filename
                guardrail = self._load_file(
                    path, GuardrailCategory.CUSTOM, GuardrailSource.LOOP
                )
                if guardrail:
                    guardrails.append(guardrail)

        return guardrails

    def _load_loop_guardrails(
        self,
        loop_config: LoopConfig,
    ) -> list[LoadedGuardrail]:
        """Load loop-level guardrails.

        Args:
            loop_config: Loop configuration.

        Returns:
            List of loaded guardrails.
        """
        guardrails = []

        if not loop_config.context or not loop_config.context.guardrails:
            return guardrails

        config = loop_config.context.guardrails

        # Handle include files
        if config.include:
            for filename in config.include:
                path = self.project_path / filename
                guardrail = self._load_file(
                    path, GuardrailCategory.CUSTOM, GuardrailSource.LOOP
                )
                if guardrail:
                    guardrails.append(guardrail)

        # Handle additional guardrails
        if config.additional:
            for i, additional in enumerate(config.additional):
                if additional.file:
                    path = self.project_path / additional.file
                    guardrail = self._load_file(
                        path, GuardrailCategory.CUSTOM, GuardrailSource.LOOP
                    )
                    if guardrail:
                        guardrails.append(guardrail)
                elif additional.content:
                    guardrails.append(LoadedGuardrail(
                        category=GuardrailCategory.CUSTOM,
                        filename=f"inline_{i}.md",
                        source=GuardrailSource.LOOP,
                        file_path=Path(f"inline_{i}"),
                        content=additional.content,
                    ))

        return guardrails

    def substitute_variables(
        self,
        content: str,
        variables: dict[str, str],
    ) -> str:
        """Substitute template variables in content.

        Variables are in the format {{variable_name}}.

        Args:
            content: Content with template variables.
            variables: Dictionary of variable values.

        Returns:
            Content with variables substituted.

        Raises:
            ValueError: If undefined variables are found.
        """
        # Find all variables
        pattern = r'\{\{(\w+)\}\}'
        found = set(re.findall(pattern, content))

        # Check for undefined variables
        undefined = found - set(variables.keys())
        if undefined:
            raise ValueError(f"Undefined template variables: {', '.join(undefined)}")

        # Substitute
        result = content
        for var_name, value in variables.items():
            result = result.replace(f"{{{{{var_name}}}}}", value)

        return result

    def build_prompt_section(
        self,
        guardrail_set: GuardrailSet,
        position: InjectionPosition,
        variables: Optional[dict[str, str]] = None,
    ) -> str:
        """Build prompt section for a position.

        Args:
            guardrail_set: Set of loaded guardrails.
            position: Position to build for.
            variables: Optional template variables.

        Returns:
            Combined content for the position.
        """
        guardrails = guardrail_set.get_by_position(position)
        if not guardrails:
            return ""

        sections = []
        for g in guardrails:
            content = g.content
            if variables:
                try:
                    content = self.substitute_variables(content, variables)
                except ValueError:
                    pass  # Skip guardrails with undefined variables

            sections.append(content)

        return "\n\n".join(sections)

    def validate(
        self,
        loop_config: Optional[LoopConfig] = None,
    ) -> list[str]:
        """Validate guardrails configuration.

        Args:
            loop_config: Optional loop configuration.

        Returns:
            List of validation errors.
        """
        errors = []

        # Load and check for errors
        try:
            guardrail_set = self.load_all(loop_config)

            # Check total size
            if guardrail_set.total_size > MAX_TOTAL_SIZE:
                errors.append(
                    f"Total guardrails size ({guardrail_set.total_size}) exceeds "
                    f"limit ({MAX_TOTAL_SIZE})"
                )

            # Check for undefined template variables (basic check)
            for g in guardrail_set.guardrails:
                pattern = r'\{\{(\w+)\}\}'
                found = re.findall(pattern, g.content)
                if found:
                    errors.append(
                        f"Template variables in {g.filename}: {', '.join(found)} "
                        f"(must be defined at runtime)"
                    )

        except Exception as e:
            errors.append(f"Error loading guardrails: {e}")

        return errors

    def clear_cache(self) -> None:
        """Clear the guardrails cache."""
        self._cache.clear()

    def list_files(self) -> list[dict]:
        """List all guardrail files.

        Returns:
            List of file info dictionaries.
        """
        files = []

        # Check each layer
        layers = [
            (self._get_global_path(), GuardrailSource.GLOBAL),
            (self._get_project_workspace_path(), GuardrailSource.WORKSPACE),
            (self._get_project_repo_path(), GuardrailSource.PROJECT),
        ]

        for directory, source in layers:
            if not directory.exists():
                continue

            for file_path in directory.rglob("*.md"):
                try:
                    stat = file_path.stat()
                    files.append({
                        "path": str(file_path),
                        "source": source.value,
                        "size": stat.st_size,
                        "mtime": datetime.fromtimestamp(stat.st_mtime),
                        "valid": self._validate_file(file_path)[0],
                    })
                except OSError:
                    pass

        return files


# AI instruction file patterns to detect
AI_INSTRUCTION_PATTERNS = [
    # Claude/Anthropic
    "CLAUDE.md",
    "claude.md",
    ".claude",
    # Agent-related
    "AGENTS.md",
    "agents.md",
    "AGENT.md",
    # Cursor
    ".cursorrules",
    ".cursor/rules/*.md",
    ".cursorignore",
    # GitHub Copilot
    ".github/copilot-instructions.md",
    # Generic LLM
    "llms.txt",
    "LLMs.txt",
    ".llmconfig",
    # Gemini
    "GEMINI.md",
    "gemini.md",
    # GPT/OpenAI
    "GPT.md",
    "gpt.md",
    ".gptconfig",
    # Other AI tools
    "AI.md",
    "ai.md",
    ".ai-rules",
    "INSTRUCTIONS.md",
    "instructions.md",
    # Project-specific
    "CONTRIBUTING.md",  # Often contains AI instructions
    "DEVELOPMENT.md",
    ".aider",
    ".aider.conf.yml",
]


@dataclass
class DetectedFile:
    """A detected AI instruction file."""

    path: Path
    pattern: str  # Which pattern matched
    size: int
    is_symlink: bool
    preview: str  # First 500 chars
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Check if file is valid for use as guardrail."""
        return not self.is_symlink and self.size > 0 and self.size <= MAX_FILE_SIZE


@dataclass
class DetectionReport:
    """Report from guardrail detection."""

    project_path: Path
    detected_files: list[DetectedFile] = field(default_factory=list)
    is_cloned_repo: bool = False
    remote_url: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    @property
    def has_security_warning(self) -> bool:
        """Check if there are security warnings."""
        return self.is_cloned_repo and len(self.detected_files) > 0

    def summary(self) -> str:
        """Get detection summary."""
        parts = [f"Found {len(self.detected_files)} AI instruction file(s)"]
        if self.is_cloned_repo:
            parts.append(f"Cloned from: {self.remote_url}")
        if self.warnings:
            parts.append(f"Warnings: {len(self.warnings)}")
        return "; ".join(parts)


class GuardrailDetector:
    """Detects AI instruction files in projects.

    Features:
    - Detects 16+ AI instruction file patterns
    - Checks for symlinks and skips with warning
    - Validates file sizes
    - Shows content preview
    - Detects cloned repositories
    - Security warnings for external repos
    """

    def __init__(self, project_path: Path):
        """Initialize the detector.

        Args:
            project_path: Path to project directory.
        """
        self.project_path = project_path

    def detect(self, patterns: Optional[list[str]] = None) -> DetectionReport:
        """Detect AI instruction files in the project.

        Args:
            patterns: Optional list of patterns to check.
                     If None, uses all default patterns.

        Returns:
            DetectionReport with all findings.
        """
        report = DetectionReport(project_path=self.project_path)

        # Check if cloned repo
        report.is_cloned_repo, report.remote_url = self._check_cloned_repo()

        # Use provided patterns or defaults
        check_patterns = patterns or AI_INSTRUCTION_PATTERNS

        # Find matching files
        for pattern in check_patterns:
            detected = self._find_pattern(pattern)
            for df in detected:
                # Avoid duplicates
                if not any(d.path == df.path for d in report.detected_files):
                    report.detected_files.append(df)

        # Add security warning if cloned repo with instruction files
        if report.has_security_warning:
            report.warnings.append(
                f"This is a cloned repository from {report.remote_url}. "
                "Review detected AI instruction files before using them as guardrails."
            )

        return report

    def _check_cloned_repo(self) -> tuple[bool, Optional[str]]:
        """Check if project is a cloned git repository.

        Returns:
            Tuple of (is_cloned, remote_url).
        """
        git_config = self.project_path / ".git" / "config"
        if not git_config.exists():
            return False, None

        try:
            content = git_config.read_text()
            # Look for remote origin URL
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("url = "):
                    url = line[6:].strip()
                    # Check if it's not a local path
                    if url.startswith(("http://", "https://", "git@", "ssh://")):
                        return True, url
        except (OSError, UnicodeDecodeError):
            pass

        return False, None

    def _find_pattern(self, pattern: str) -> list[DetectedFile]:
        """Find files matching a pattern.

        Args:
            pattern: File pattern to match.

        Returns:
            List of detected files.
        """
        detected = []

        if "*" in pattern:
            # Glob pattern
            matches = list(self.project_path.glob(pattern))
        else:
            # Exact file match
            path = self.project_path / pattern
            matches = [path] if path.exists() else []

        for path in matches:
            if path.is_file() or path.is_symlink():
                df = self._analyze_file(path, pattern)
                if df:
                    detected.append(df)

        return detected

    def _analyze_file(self, path: Path, pattern: str) -> Optional[DetectedFile]:
        """Analyze a detected file.

        Args:
            path: Path to file.
            pattern: Pattern that matched.

        Returns:
            DetectedFile or None if cannot analyze.
        """
        warnings = []

        # Check symlink
        is_symlink = path.is_symlink()
        if is_symlink:
            warnings.append("Symlink - will not be used as guardrail")

        try:
            stat = path.stat() if not is_symlink else path.lstat()
            size = stat.st_size

            # Check size
            if size == 0:
                warnings.append("Empty file")
            elif size > MAX_FILE_SIZE:
                warnings.append(f"File too large ({size} > {MAX_FILE_SIZE})")

            # Get preview
            preview = ""
            if not is_symlink and size > 0:
                try:
                    content = path.read_text()
                    preview = content[:500]
                    if len(content) > 500:
                        preview += "..."
                except UnicodeDecodeError:
                    warnings.append("Cannot read file (binary or encoding issue)")

            return DetectedFile(
                path=path,
                pattern=pattern,
                size=size,
                is_symlink=is_symlink,
                preview=preview,
                warnings=warnings,
            )

        except OSError as e:
            return None

    def copy_to_workspace(
        self,
        detected: DetectedFile,
        workspace_path: Path,
        category: GuardrailCategory = GuardrailCategory.CUSTOM,
    ) -> Optional[Path]:
        """Copy a detected file to workspace as guardrail.

        Args:
            detected: Detected file to copy.
            workspace_path: Workspace guardrails directory.
            category: Category to place file in.

        Returns:
            Path to copied file, or None if copy failed.
        """
        if not detected.is_valid:
            return None

        # Create category directory
        target_dir = workspace_path / category.value
        target_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        filename = detected.path.name
        target_path = target_dir / filename

        # Handle name collision
        counter = 1
        while target_path.exists():
            stem = detected.path.stem
            suffix = detected.path.suffix
            target_path = target_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        try:
            content = detected.path.read_text()
            target_path.write_text(content)
            return target_path
        except (OSError, UnicodeDecodeError):
            return None


# Built-in guardrail templates for common project types
GUARDRAIL_TEMPLATES = {
    "web-app": {
        "system": [
            "You are building a web application. Follow these guidelines:",
            "- Use modern ES6+ JavaScript/TypeScript",
            "- Follow React best practices if using React",
            "- Ensure responsive design",
            "- Consider accessibility (WCAG 2.1 AA)",
        ],
        "safety": [
            "Security requirements:",
            "- Sanitize all user inputs",
            "- Use HTTPS for all external requests",
            "- Implement proper CORS configuration",
            "- Never expose sensitive data in client-side code",
            "- Use secure cookie settings",
        ],
    },
    "backend-api": {
        "system": [
            "You are building a backend API. Follow these guidelines:",
            "- Use RESTful design principles",
            "- Implement proper error handling",
            "- Document all endpoints",
            "- Use appropriate HTTP status codes",
        ],
        "safety": [
            "Security requirements:",
            "- Validate all input data",
            "- Implement rate limiting",
            "- Use parameterized queries (no SQL injection)",
            "- Implement proper authentication",
            "- Log security-relevant events",
        ],
    },
    "healthcare": {
        "system": [
            "You are working on healthcare-related software. Follow these guidelines:",
            "- Prioritize data accuracy and integrity",
            "- Follow healthcare data standards (HL7, FHIR)",
            "- Implement comprehensive audit logging",
        ],
        "safety": [
            "HIPAA Compliance Requirements:",
            "- Encrypt all PHI at rest and in transit",
            "- Implement role-based access control",
            "- Maintain detailed access logs",
            "- Never expose PHI in logs or error messages",
            "- Implement session timeout for PHI access",
            "- Require strong authentication",
        ],
    },
    "e-commerce": {
        "system": [
            "You are building e-commerce functionality. Follow these guidelines:",
            "- Implement proper inventory management",
            "- Handle currency with appropriate precision",
            "- Consider tax and shipping calculations",
        ],
        "safety": [
            "Payment Security Requirements (PCI-DSS):",
            "- Never store full credit card numbers",
            "- Never log payment details",
            "- Use tokenization for stored cards",
            "- Implement fraud detection",
            "- Secure checkout process",
        ],
    },
    "cli-tool": {
        "system": [
            "You are building a CLI tool. Follow these guidelines:",
            "- Provide clear help text for all commands",
            "- Use consistent argument naming",
            "- Implement proper exit codes",
            "- Support --quiet and --verbose flags",
        ],
        "safety": [
            "Security considerations:",
            "- Validate all file paths",
            "- Avoid command injection vulnerabilities",
            "- Handle credentials securely (use keyring/env)",
            "- Warn before destructive operations",
        ],
    },
}


def create_template_guardrails(
    template_name: str,
    output_dir: Path,
) -> list[Path]:
    """Create guardrail files from a template.

    Args:
        template_name: Template name (web-app, backend-api, etc.).
        output_dir: Directory to create files in.

    Returns:
        List of created file paths.

    Raises:
        ValueError: If template name is unknown.
    """
    if template_name not in GUARDRAIL_TEMPLATES:
        available = ", ".join(GUARDRAIL_TEMPLATES.keys())
        raise ValueError(f"Unknown template: {template_name}. Available: {available}")

    template = GUARDRAIL_TEMPLATES[template_name]
    created = []

    for category, lines in template.items():
        # Create category directory
        cat_dir = output_dir / category
        cat_dir.mkdir(parents=True, exist_ok=True)

        # Create guardrail file
        filename = f"{template_name}.md"
        filepath = cat_dir / filename

        content = "\n".join(lines)
        filepath.write_text(content)
        created.append(filepath)

    return created


def list_templates() -> list[str]:
    """Get list of available guardrail templates.

    Returns:
        List of template names.
    """
    return list(GUARDRAIL_TEMPLATES.keys())
