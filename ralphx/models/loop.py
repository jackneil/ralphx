"""Loop configuration models for RalphX."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class LoopType(str, Enum):
    """Type of loop execution."""

    GENERATOR = "generator"
    CONSUMER = "consumer"
    HYBRID = "hybrid"


class ModeSelectionStrategy(str, Enum):
    """Strategy for selecting modes each iteration."""

    FIXED = "fixed"
    RANDOM = "random"
    WEIGHTED_RANDOM = "weighted_random"
    ADAPTIVE = "adaptive"
    PHASE_AWARE = "phase_aware"  # Use Phase 1 logic then switch to fixed mode


class PermissionMode(str, Enum):
    """How to handle Claude CLI permission prompts."""

    DEFAULT = "default"
    AUTO_APPROVE = "auto-approve"
    FAIL_FAST = "fail-fast"


class OnPermissionBlock(str, Enum):
    """Action when permission prompt would block."""

    SKIP = "skip"
    RETRY = "retry"
    ABORT = "abort"
    NOTIFY = "notify"


class OnError(str, Enum):
    """Action on error."""

    RETRY = "retry"
    SKIP = "skip"
    ABORT = "abort"


class ModeGuardrails(BaseModel):
    """Mode-specific guardrail overrides."""

    categories: Optional[dict[str, bool]] = None
    include: Optional[list[str]] = None
    exclude: Optional[list[str]] = None


class Mode(BaseModel):
    """Configuration for a single execution mode."""

    description: Optional[str] = None
    timeout: int = Field(300, ge=1, le=7200, description="Timeout in seconds")
    model: str = Field("sonnet", description="Model to use (sonnet, opus, haiku, etc.)")
    tools: list[str] = Field(default_factory=list, description="Allowed tools")
    prompt_template: str = Field(..., description="Path to prompt template file")
    guardrails: Optional[ModeGuardrails] = None
    phase: Optional[str] = Field(
        None,
        description="Phase this mode belongs to (e.g., 'phase_1' for architecture grouping)",
    )


class ModeSelection(BaseModel):
    """Configuration for mode selection strategy."""

    strategy: ModeSelectionStrategy = ModeSelectionStrategy.FIXED
    fixed_mode: Optional[str] = None
    weights: Optional[dict[str, int]] = None

    @model_validator(mode="after")
    def validate_strategy_params(self) -> "ModeSelection":
        """Validate strategy-specific parameters."""
        if self.strategy == ModeSelectionStrategy.FIXED:
            if not self.fixed_mode:
                raise ValueError("fixed_mode is required when strategy=fixed")
        elif self.strategy == ModeSelectionStrategy.WEIGHTED_RANDOM:
            if not self.weights:
                raise ValueError("weights are required when strategy=weighted_random")
            total = sum(self.weights.values())
            if total != 100:
                raise ValueError(f"weights must sum to 100, got {total}")
        elif self.strategy == ModeSelectionStrategy.PHASE_AWARE:
            # Phase-aware uses Phase 1 modes first, then switches to fixed_mode
            if not self.fixed_mode:
                raise ValueError("fixed_mode is required when strategy=phase_aware (used after Phase 1)")
        return self


class CategoryConfig(BaseModel):
    """Configuration for categories."""

    source: str = Field("none", pattern="^(file|inline|none)$")
    file: Optional[str] = None
    inline: Optional[dict[str, Any]] = None
    selection: Optional[dict[str, Any]] = None


class PhaseConfig(BaseModel):
    """Configuration for phases (legacy - for file/inline phase definitions)."""

    source: str = Field("none", pattern="^(file|inline|none)$")
    file: Optional[str] = None
    inline: Optional[dict[int, Any]] = None


class ImplementationPhaseConfig(BaseModel):
    """Configuration for Phase 1 implementation logic.

    Phase 1 groups architecture/infrastructure stories together for batch
    implementation before processing remaining stories one-by-one.
    """

    enabled: bool = Field(
        True,
        description="Enable Phase 1 grouping for architecture stories",
    )
    auto_group: bool = Field(
        True,
        description="Let Claude analyze and group architecture stories automatically",
    )
    max_phase1_items: int = Field(
        10,
        ge=1,
        le=50,
        description="Maximum number of stories to include in Phase 1 batch",
    )
    phase1_categories: list[str] = Field(
        default_factory=lambda: ["architecture", "infrastructure", "setup", "foundation"],
        description="Categories that indicate Phase 1 stories",
    )


class PhaseDefinition(BaseModel):
    """Definition of a single phase for multi-phase implementation."""

    name: str = Field(..., description="Human-readable phase name")
    categories: list[str] = Field(
        default_factory=list,
        description="Categories that belong to this phase (lowercase)",
    )
    description: Optional[str] = Field(None, description="Phase description")


class MultiPhaseConfig(BaseModel):
    """Configuration for multi-phase implementation with dependency awareness.

    Supports two modes:
    1. auto_phase=True: Automatically detect phases from dependency chains
    2. auto_phase=False: Use manual phase definitions based on categories

    Stories are processed phase by phase, respecting dependencies within each phase.
    """

    enabled: bool = Field(
        False,
        description="Enable multi-phase processing",
    )
    auto_phase: bool = Field(
        True,
        description="Auto-detect phases from dependency chains (vs manual category mapping)",
    )
    max_batch_size: int = Field(
        10,
        ge=1,
        le=50,
        description="Maximum stories per phase batch",
    )
    respect_dependencies: bool = Field(
        True,
        description="Process stories in dependency order within phases",
    )
    definitions: Optional[dict[int, PhaseDefinition]] = Field(
        None,
        description="Manual phase definitions (phase number -> definition). Used when auto_phase=False.",
    )

    def get_category_to_phase(self) -> dict[str, int]:
        """Build category-to-phase mapping from definitions.

        Returns:
            Dict mapping lowercase category name to phase number.
        """
        if not self.definitions:
            return {}
        mapping = {}
        for phase_num, phase_def in self.definitions.items():
            for cat in phase_def.categories:
                mapping[cat.lower()] = phase_num
        return mapping


class OutputSchema(BaseModel):
    """Schema for work items."""

    required: list[str] = Field(default_factory=lambda: ["id", "content", "status"])
    optional: list[str] = Field(default_factory=list)
    custom_fields: Optional[dict[str, Any]] = None


class ItemTypeConfig(BaseModel):
    """Configuration for an item type (input or output)."""

    singular: str = Field("item", description="Singular form (e.g., 'story')")
    plural: str = Field("items", description="Plural form (e.g., 'stories')")
    description: str = Field("", description="Description of this item type")
    source: Optional[str] = Field(
        None, description="For input types: which loop's output to consume"
    )


class ItemTypes(BaseModel):
    """Item type configuration for a loop."""

    input: Optional[ItemTypeConfig] = Field(
        None, description="Input item type (for consumer loops)"
    )
    output: ItemTypeConfig = Field(
        default_factory=ItemTypeConfig, description="Output item type"
    )


class OutputConfig(BaseModel):
    """Output configuration."""

    format: str = Field("sqlite", pattern="^sqlite$")
    schema_: OutputSchema = Field(default_factory=OutputSchema, alias="schema")

    model_config = {"populate_by_name": True}


class GuardrailCategories(BaseModel):
    """Enable/disable guardrail categories."""

    system: bool = True
    safety: bool = True
    domain: bool = True
    output: bool = True
    custom: bool = True


class AdditionalGuardrail(BaseModel):
    """Additional guardrail (file or inline content)."""

    file: Optional[str] = None
    content: Optional[str] = None

    @model_validator(mode="after")
    def validate_exclusive(self) -> "AdditionalGuardrail":
        """Validate that exactly one of file or content is provided."""
        if self.file and self.content:
            raise ValueError("Cannot specify both 'file' and 'content'")
        if not self.file and not self.content:
            raise ValueError("Must specify either 'file' or 'content'")
        return self


class GuardrailsConfig(BaseModel):
    """Guardrails configuration."""

    enabled: bool = True
    inherit_global: bool = True
    categories: Optional[GuardrailCategories] = None
    include: Optional[list[str]] = None
    exclude: Optional[list[str]] = None
    additional: Optional[list[AdditionalGuardrail]] = None


class ResourceConfig(BaseModel):
    """Configuration for project resource inheritance.

    Controls which project-level resources are injected into loop prompts.
    Resources are markdown files in <project>/.ralphx/resources/ organized
    by type (design_doc, architecture, coding_standards, domain_knowledge, custom).
    """

    inherit_project_resources: bool = Field(
        True,
        description="Whether to inherit resources from the project",
    )
    include: Optional[list[str]] = Field(
        None,
        description="Explicit list of resources to include (by name, e.g. 'design_doc/main')",
    )
    exclude: Optional[list[str]] = Field(
        None,
        description="List of resources to exclude (by name)",
    )


class ContextConfig(BaseModel):
    """Context configuration for prompt templates."""

    design_doc: Optional[str] = None
    inputs_dir: Optional[str] = Field(
        None,
        description="Directory containing imported input files (relative to loop directory)",
    )
    custom_context: Optional[dict[str, str]] = None
    guardrails: Optional[GuardrailsConfig] = None
    resources: Optional[ResourceConfig] = Field(
        None,
        description="Configuration for project resource inheritance",
    )


class Limits(BaseModel):
    """Execution limits."""

    max_iterations: int = Field(100, ge=0, description="0 = unlimited")
    max_runtime_seconds: int = Field(28800, ge=0, description="0 = unlimited")
    max_consecutive_errors: int = Field(5, ge=1)
    max_no_progress_iterations: int = Field(3, ge=1)
    cooldown_between_iterations: int = Field(5, ge=0)


class ActivityTimeout(BaseModel):
    """Activity/silence detection timeouts."""

    warn: int = Field(45, ge=1, description="Seconds of silence before warning")
    kill: int = Field(180, ge=1, description="Seconds of silence before killing")


class ExecutionConfig(BaseModel):
    """Execution behavior configuration."""

    permission_mode: PermissionMode = PermissionMode.DEFAULT
    permission_timeout: int = Field(30, ge=1)
    on_permission_block: OnPermissionBlock = OnPermissionBlock.SKIP
    activity_timeout: Optional[ActivityTimeout] = None


class ErrorHandling(BaseModel):
    """Error handling configuration."""

    on_timeout: OnError = OnError.SKIP
    max_retries: int = Field(2, ge=0)
    retry_delay: int = Field(10, ge=0)
    on_parse_error: OnError = OnError.SKIP
    on_api_error: OnError = OnError.RETRY


class Hook(BaseModel):
    """Lifecycle hook configuration."""

    type: str = Field(..., pattern="^(shell|webhook|log)$")
    command: Optional[str] = None
    url: Optional[str] = None
    message: Optional[str] = None


class HooksConfig(BaseModel):
    """Lifecycle hooks configuration."""

    on_start: Optional[list[Hook]] = None
    on_iteration_complete: Optional[list[Hook]] = None
    on_item_added: Optional[list[Hook]] = None
    on_complete: Optional[list[Hook]] = None
    on_error: Optional[list[Hook]] = None


class GitConfig(BaseModel):
    """Git integration configuration."""

    enabled: bool = False
    auto_commit: bool = False
    commit_template: Optional[str] = None
    branch: Optional[str] = None
    fail_on_error: bool = False  # If True, fail iteration on git error


class AuthConfig(BaseModel):
    """Authentication configuration."""

    adapter: str = Field("default", pattern="^(default|file|env)$")
    credentials_file: Optional[str] = None
    env_var: Optional[str] = None


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field("info", pattern="^(debug|info|warning|error)$")
    file: Optional[str] = None
    max_size_mb: int = Field(10, ge=1)
    keep_files: int = Field(5, ge=1)
    verbose: bool = False
    debug_dir: Optional[str] = None


class LoopConfig(BaseModel):
    """Complete loop configuration model."""

    # Required fields
    name: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Unique identifier (lowercase, alphanumeric + underscores)",
    )
    display_name: str = Field(..., min_length=1, max_length=100)
    type: LoopType

    # Mode configuration
    modes: dict[str, Mode] = Field(..., min_length=1)
    mode_selection: ModeSelection

    # Output configuration
    output: OutputConfig = Field(default_factory=OutputConfig)

    # Item type configuration
    item_types: ItemTypes = Field(default_factory=ItemTypes)

    # Limits
    limits: Limits = Field(default_factory=Limits)

    # Optional fields
    description: Optional[str] = None
    categories: Optional[CategoryConfig] = None
    phases: Optional[PhaseConfig] = None
    phase_config: Optional[ImplementationPhaseConfig] = Field(
        None,
        description="Phase 1 implementation logic configuration (legacy)",
    )
    multi_phase: Optional[MultiPhaseConfig] = Field(
        None,
        description="Multi-phase configuration with dependency awareness",
    )
    context: Optional[ContextConfig] = None
    execution: Optional[ExecutionConfig] = None
    error_handling: Optional[ErrorHandling] = None
    hooks: Optional[HooksConfig] = None
    git: Optional[GitConfig] = None
    auth: Optional[AuthConfig] = None
    logging: Optional[LoggingConfig] = None

    @model_validator(mode="after")
    def validate_no_self_source(self) -> "LoopConfig":
        """Validate that a loop doesn't source from itself."""
        if self.item_types and self.item_types.input:
            source = self.item_types.input.source
            if source and source == self.name:
                raise ValueError(f"Loop cannot source from itself: {source}")
        return self

    @model_validator(mode="after")
    def validate_mode_references(self) -> "LoopConfig":
        """Validate that mode references exist."""
        # Check fixed_mode exists
        if (
            self.mode_selection.strategy == ModeSelectionStrategy.FIXED
            and self.mode_selection.fixed_mode
        ):
            if self.mode_selection.fixed_mode not in self.modes:
                raise ValueError(
                    f"fixed_mode '{self.mode_selection.fixed_mode}' not found in modes"
                )

        # Check weighted_random mode names exist
        if (
            self.mode_selection.strategy == ModeSelectionStrategy.WEIGHTED_RANDOM
            and self.mode_selection.weights
        ):
            for mode_name in self.mode_selection.weights:
                if mode_name not in self.modes:
                    raise ValueError(
                        f"weight references unknown mode '{mode_name}'"
                    )

        # Check phase_aware strategy has Phase 1 modes
        if self.mode_selection.strategy == ModeSelectionStrategy.PHASE_AWARE:
            phase1_modes = [
                name for name, mode in self.modes.items()
                if mode.phase == "phase_1"
            ]
            if not phase1_modes:
                raise ValueError(
                    "phase_aware strategy requires at least one mode with phase='phase_1'"
                )

        return self

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "LoopConfig":
        """Load loop configuration from YAML file.

        Args:
            yaml_path: Path to YAML configuration file.

        Returns:
            Validated LoopConfig instance.

        Raises:
            FileNotFoundError: If file doesn't exist.
            yaml.YAMLError: If YAML is invalid.
            ValidationError: If configuration is invalid.
        """
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)

    @classmethod
    def from_yaml_string(cls, yaml_content: str) -> "LoopConfig":
        """Load loop configuration from YAML string.

        Args:
            yaml_content: YAML content as string.

        Returns:
            Validated LoopConfig instance.
        """
        data = yaml.safe_load(yaml_content)
        return cls.model_validate(data)

    def to_yaml(self) -> str:
        """Serialize to YAML string."""
        return yaml.dump(
            self.model_dump(mode="json", exclude_none=True, by_alias=True),
            default_flow_style=False,
            sort_keys=False,
        )

    def get_mode(self, name: str) -> Mode:
        """Get a mode by name.

        Raises:
            KeyError: If mode doesn't exist.
        """
        if name not in self.modes:
            raise KeyError(f"Mode '{name}' not found. Available: {list(self.modes.keys())}")
        return self.modes[name]
