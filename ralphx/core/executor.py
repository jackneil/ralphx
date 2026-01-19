"""Loop executor for RalphX.

Implements the main loop execution with:
- Mode selection (fixed, random, weighted_random)
- Iteration tracking with cooldown
- Consecutive error handling
- Limit enforcement (max_iterations, max_runtime)
- Work item extraction from Claude output
- Event emission
- Graceful shutdown (SIGINT)
"""

import asyncio
import os
import random
import re
import signal
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

from ralphx.adapters.base import ExecutionResult, LLMAdapter
from ralphx.adapters.claude_cli import ClaudeCLIAdapter
from ralphx.core.dependencies import DependencyGraph, order_items_by_dependency
from ralphx.core.project_db import ProjectDatabase
from ralphx.core.resources import InjectionPosition, ResourceManager
from ralphx.core.schemas import IMPLEMENTATION_STATUS_SCHEMA, ItemStatus
from ralphx.core.workspace import get_loop_settings_path
from ralphx.models.loop import LoopConfig, Mode, ModeSelectionStrategy
from ralphx.models.project import Project
from ralphx.models.run import Run, RunStatus
from ralphx.core.logger import run_log, iteration_log


class ExecutorEvent(str, Enum):
    """Events emitted by the executor."""

    RUN_STARTED = "run_started"
    ITERATION_STARTED = "iteration_started"
    ITERATION_COMPLETED = "iteration_completed"
    PROMPT_PREPARED = "prompt_prepared"  # Before Claude call, includes prompt stats
    ITEM_ADDED = "item_added"
    GIT_COMMIT = "git_commit"  # Git commit after successful iteration
    ERROR = "error"
    WARNING = "warning"
    HEARTBEAT = "heartbeat"
    RUN_PAUSED = "run_paused"
    RUN_RESUMED = "run_resumed"
    RUN_COMPLETED = "run_completed"
    RUN_ABORTED = "run_aborted"


@dataclass
class ExecutorEventData:
    """Data for an executor event."""

    event: ExecutorEvent
    timestamp: datetime = field(default_factory=datetime.utcnow)
    run_id: Optional[str] = None
    iteration: Optional[int] = None
    mode: Optional[str] = None
    data: dict = field(default_factory=dict)
    message: Optional[str] = None


@dataclass
class IterationResult:
    """Result of a single iteration."""

    success: bool = True
    session_id: Optional[str] = None
    mode_name: str = ""
    duration_seconds: float = 0.0
    items_added: list = field(default_factory=list)
    error_message: Optional[str] = None
    timeout: bool = False
    no_items_available: bool = False  # For consumer loops: no source items to process
    claimed_item: Optional[dict] = None  # For consumer loops: the item that was processed
    generator_complete: bool = False  # For generator loops: Claude signaled completion


# Regex patterns for extracting work items from Claude output
ITEM_PATTERNS = [
    # JSON array pattern: [{"id": "...", "content": "..."}]
    re.compile(r'\[\s*\{[^}]*"id"\s*:\s*"[^"]+"\s*,\s*"content"\s*:', re.DOTALL),
    # Markdown list with ID: - **ID-001**: Item content
    re.compile(r'-\s+\*\*([A-Za-z0-9_-]+)\*\*:\s*(.+?)(?=\n-|\n\n|$)', re.MULTILINE),
    # Simple numbered list with ID: 1. [ID-001] Item content
    re.compile(r'\d+\.\s*\[([A-Za-z0-9_-]+)\]\s*(.+?)(?=\n\d+\.|\n\n|$)', re.MULTILINE),
]


class LoopExecutor:
    """Executes loop iterations with mode selection and error handling.

    Features:
    - Mode selection (fixed, random, weighted_random)
    - Iteration loop with configurable cooldown
    - Consecutive error tracking
    - Limit enforcement (max_iterations, max_runtime)
    - Work item extraction from Claude output
    - Event emission for progress tracking
    - Graceful shutdown on SIGINT
    """

    def __init__(
        self,
        project: Project,
        loop_config: LoopConfig,
        db: ProjectDatabase,
        workflow_id: str,
        step_id: int,
        adapter: Optional[LLMAdapter] = None,
        dry_run: bool = False,
        phase: Optional[int] = None,
        category: Optional[str] = None,
        respect_dependencies: bool = True,
        batch_mode: bool = False,
        batch_size: int = 10,
        consume_from_step_id: Optional[int] = None,
        architecture_first: bool = False,
    ):
        """Initialize the executor.

        Args:
            project: Project to run loop against.
            loop_config: Loop configuration.
            db: Project-local database instance for persistence.
            workflow_id: Parent workflow ID (required).
            step_id: Parent workflow step ID (required).
            adapter: LLM adapter (defaults to ClaudeCLIAdapter).
            dry_run: If True, simulate execution without calling LLM.
            phase: Optional phase number to filter items (consumer loops only).
            category: Optional category to filter items (consumer loops only).
            respect_dependencies: If True, process items in dependency order.
            batch_mode: If True, claim multiple items for batch implementation.
            batch_size: Maximum items to claim for batch mode.
            consume_from_step_id: For consumer loops, the step ID to consume items from.
            architecture_first: If True, prioritize foundational stories (FND, DBM, SEC, ARC)
                               for new codebases. Batches them together for initial build.
        """
        self.project = project
        self.config = loop_config
        self.db = db
        self.workflow_id = workflow_id
        self.step_id = step_id
        self._consume_from_step_id = consume_from_step_id
        # Create adapter with per-loop settings path for permission templates
        # Pass project_id for credential lookup (project-scoped auth)
        if adapter is None:
            settings_path = get_loop_settings_path(project.path, loop_config.name)
            self.adapter = ClaudeCLIAdapter(
                project.path,
                settings_path=settings_path,
                project_id=project.id,
            )
        else:
            self.adapter = adapter
        self.dry_run = dry_run

        # Phase and category filtering (for consumer loops)
        self._phase_filter = phase
        self._category_filter = category.lower() if category else None
        self._respect_dependencies = respect_dependencies
        self._batch_mode = batch_mode
        self._batch_size = min(batch_size, 50)  # Cap at 50
        self._architecture_first = architecture_first
        self._architecture_phase_complete = False

        # Foundational categories to prioritize in architecture-first mode
        # These are typically infrastructure, database, security, architecture stories
        self._foundation_categories = frozenset({
            "fnd", "foundation",
            "dbm", "database",
            "sec", "security",
            "arc", "architecture",
            "adm", "admin",
            "dat", "data",
            "dep", "deployment",
            "sys", "system",
            "inf", "infrastructure",
        })

        # Dependency graph for ordering (built on first claim)
        self._dependency_graph: Optional[DependencyGraph] = None
        self._detected_phases: Optional[dict[int, list[str]]] = None
        self._completed_item_ids: set[str] = set()

        # Run state
        self._run: Optional[Run] = None
        self._iteration = 0
        self._consecutive_errors = 0
        self._items_generated = 0
        self._no_items_streak = 0  # Consecutive iterations with 0 items (for generator completion)
        self._start_time: Optional[datetime] = None
        self._paused = False
        self._stopping = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially

        # Phase 1 state (for phase_aware strategy)
        self._phase1_complete = False
        self._phase1_mode_index = 0
        self._phase1_story_ids: list[str] = []
        self._phase1_analysis: Optional[dict] = None

        # Event handlers
        self._event_handlers: list[Callable[[ExecutorEventData], None]] = []

    @property
    def run_id(self) -> Optional[str]:
        """Get the current run ID."""
        return self._run.id if self._run else None

    @property
    def is_running(self) -> bool:
        """Check if executor is currently running."""
        return self._run is not None and self._run.is_active

    @property
    def is_paused(self) -> bool:
        """Check if executor is paused."""
        return self._paused

    @property
    def current_iteration(self) -> int:
        """Get the current iteration number."""
        return self._iteration

    def add_event_handler(
        self, handler: Callable[[ExecutorEventData], None]
    ) -> None:
        """Add an event handler.

        Args:
            handler: Callable that receives ExecutorEventData.
        """
        self._event_handlers.append(handler)

    def remove_event_handler(
        self, handler: Callable[[ExecutorEventData], None]
    ) -> None:
        """Remove an event handler."""
        if handler in self._event_handlers:
            self._event_handlers.remove(handler)

    def _emit_event(
        self,
        event: ExecutorEvent,
        message: Optional[str] = None,
        **data: Any,
    ) -> None:
        """Emit an event to all handlers.

        Args:
            event: Event type.
            message: Optional message.
            **data: Additional event data.
        """
        event_data = ExecutorEventData(
            event=event,
            run_id=self.run_id,
            iteration=self._iteration,
            mode=data.get("mode"),
            message=message,
            data=data,
        )
        for handler in self._event_handlers:
            try:
                handler(event_data)
            except Exception:
                pass  # Don't let handler errors affect execution

        # Log significant events to database
        self._log_event(event, message, data)

    def _log_event(
        self,
        event: ExecutorEvent,
        message: Optional[str],
        data: dict,
    ) -> None:
        """Log significant events to database.

        Only logs run-level and iteration-level events, not low-level ones.
        """
        # Common context for all logs
        ctx = {
            "project_id": self.project.id,
            "run_id": self.run_id,
            "loop_name": self.config.name,
        }

        if event == ExecutorEvent.RUN_STARTED:
            run_log.info(
                "started",
                f"Run started: {self.config.name}",
                **ctx,
            )
        elif event == ExecutorEvent.RUN_COMPLETED:
            run_log.info(
                "completed",
                message or f"Run completed: {self.config.name}",
                iterations=self._iteration,
                items_generated=data.get("items_generated", 0),
                **ctx,
            )
        elif event == ExecutorEvent.RUN_ABORTED:
            run_log.warning(
                "aborted",
                message or f"Run aborted: {self.config.name}",
                iterations=self._iteration,
                **ctx,
            )
        elif event == ExecutorEvent.RUN_PAUSED:
            run_log.info(
                "paused",
                message or f"Run paused: {self.config.name}",
                iterations=self._iteration,
                **ctx,
            )
        elif event == ExecutorEvent.RUN_RESUMED:
            run_log.info(
                "resumed",
                message or f"Run resumed: {self.config.name}",
                iterations=self._iteration,
                **ctx,
            )
        elif event == ExecutorEvent.ITERATION_STARTED:
            iteration_log.info(
                "started",
                f"Iteration {self._iteration} started",
                iteration_num=self._iteration,
                mode=data.get("mode"),
                **ctx,
            )
        elif event == ExecutorEvent.ITERATION_COMPLETED:
            iteration_log.info(
                "completed",
                f"Iteration {self._iteration} completed",
                iteration_num=self._iteration,
                mode=data.get("mode"),
                items_added=data.get("items_added", 0),
                duration_seconds=data.get("duration_seconds"),
                **ctx,
            )
        elif event == ExecutorEvent.ERROR:
            run_log.error(
                "error",
                message or "Run error",
                error=message,
                **ctx,
            )
        # Note: ITEM_ADDED, WARNING, HEARTBEAT are not logged to reduce noise

    def select_mode(self) -> tuple[str, Mode]:
        """Select a mode based on the selection strategy.

        Returns:
            Tuple of (mode_name, Mode).
        """
        selection = self.config.mode_selection
        modes = self.config.modes

        if selection.strategy == ModeSelectionStrategy.FIXED:
            mode_name = selection.fixed_mode
            return mode_name, modes[mode_name]

        elif selection.strategy == ModeSelectionStrategy.RANDOM:
            mode_name = random.choice(list(modes.keys()))
            return mode_name, modes[mode_name]

        elif selection.strategy == ModeSelectionStrategy.WEIGHTED_RANDOM:
            weights = selection.weights
            mode_names = list(weights.keys())
            mode_weights = [weights[name] for name in mode_names]
            mode_name = random.choices(mode_names, weights=mode_weights, k=1)[0]
            return mode_name, modes[mode_name]

        elif selection.strategy == ModeSelectionStrategy.PHASE_AWARE:
            # Phase-aware: Use Phase 1 modes until complete, then fixed_mode
            if not self._phase1_complete:
                # Get Phase 1 modes
                phase1_modes = [
                    (name, mode) for name, mode in modes.items()
                    if mode.phase == "phase_1"
                ]
                if phase1_modes:
                    # Use Phase 1 modes in order
                    mode_name, mode = phase1_modes[self._phase1_mode_index % len(phase1_modes)]
                    return mode_name, mode

            # After Phase 1, use fixed_mode
            mode_name = selection.fixed_mode
            return mode_name, modes[mode_name]

        else:
            # Default to first mode
            mode_name = list(modes.keys())[0]
            return mode_name, modes[mode_name]

    def _resolve_loop_resource_content(self, resource: dict) -> Optional[str]:
        """Resolve content for a loop resource based on its source_type.

        Args:
            resource: Loop resource dict from database.

        Returns:
            Resolved content string, or None if unable to resolve.
        """
        source_type = resource.get("source_type", "")

        if source_type == "system":
            # Load from system default templates
            resource_type = resource.get("resource_type", "")
            default_path = (
                Path(__file__).parent.parent / "templates" / "loop_templates" / f"{resource_type}.md"
            )
            if default_path.exists():
                return default_path.read_text()
            return None

        elif source_type == "project_file":
            # Load from project file path
            source_path = resource.get("source_path")
            if source_path:
                file_path = Path(self.project.path) / source_path
                if file_path.exists():
                    return file_path.read_text()
            return None

        elif source_type == "loop_ref":
            # Load from another loop's resource (recursively)
            source_loop = resource.get("source_loop")
            source_resource_id = resource.get("source_resource_id")
            if source_loop and source_resource_id:
                source_resource = self.db.get_loop_resource(source_resource_id)
                if source_resource:
                    return self._resolve_loop_resource_content(source_resource)
            return None

        elif source_type == "project_resource":
            # Load from project-level resource
            source_resource_id = resource.get("source_resource_id")
            if source_resource_id:
                resource_manager = ResourceManager(self.project.path, db=self.db)
                proj_resource = resource_manager.db.get_resource(source_resource_id)
                if proj_resource:
                    loaded = resource_manager.load_resource(proj_resource)
                    if loaded:
                        return loaded.content
            return None

        elif source_type == "inline":
            # Content is stored directly
            return resource.get("inline_content")

        return None

    def _load_loop_resources(self) -> list[dict]:
        """Load all enabled resources for this loop from the loop_resources table.

        Returns:
            List of loop resource dicts with resolved content.
        """
        resources = self.db.list_loop_resources(
            loop_name=self.config.name,
            enabled=True,
        )

        # Resolve content for each resource
        result = []
        for resource in resources:
            content = self._resolve_loop_resource_content(resource)
            if content:
                resource["_resolved_content"] = content
                result.append(resource)

        # Sort by priority, then name
        result.sort(key=lambda r: (r.get("priority", 0), r.get("name", "")))
        return result

    def _build_loop_resource_section(
        self,
        resources: list[dict],
        position: str,
        include_headers: bool = True,
    ) -> str:
        """Build prompt section from loop resources at a specific injection position.

        Args:
            resources: List of loop resources with resolved content.
            position: Injection position to filter by.
            include_headers: Whether to include section headers.

        Returns:
            Combined content for this position.
        """
        position_resources = [r for r in resources if r.get("injection_position") == position]

        if not position_resources:
            return ""

        sections = []
        for resource in position_resources:
            content = resource.get("_resolved_content", "")
            if not content:
                continue

            if include_headers:
                name = resource.get("name", "Resource")
                resource_type = resource.get("resource_type", "custom")
                type_labels = {
                    "loop_template": "Loop Template",
                    "design_doc": "Design Document",
                    "guardrails": "Guardrails",
                    "custom": "Additional Context",
                }
                label = type_labels.get(resource_type, "Resource")
                header = f"## {label}: {name}" if name != resource_type else f"## {label}"
                sections.append(f"\n{header}\n{content}\n")
            else:
                sections.append(content)

        return "\n".join(sections)

    def _load_prompt_template(self, mode: Mode) -> str:
        """Load prompt template for a mode.

        Priority order:
        1. Loop-level LOOP_TEMPLATE resource with position=template_body (from loop_resources table)
        2. Project-level LOOP_TEMPLATE resource with position=TEMPLATE_BODY (from resources table)
        3. Mode's prompt_template file path
        4. Default template from ralphx/templates/loop_templates/{loop_type}.md

        Args:
            mode: Mode configuration.

        Returns:
            Prompt template content.
        """
        # Priority 1: Check for loop-level LOOP_TEMPLATE resource
        loop_resources = self._load_loop_resources()
        for resource in loop_resources:
            if (resource.get("resource_type") == "loop_template" and
                resource.get("injection_position") == "template_body"):
                content = resource.get("_resolved_content")
                if content:
                    return content

        # Priority 2: Check for project-level LOOP_TEMPLATE resource with TEMPLATE_BODY position
        resource_manager = ResourceManager(self.project.path, db=self.db)
        resource_set = resource_manager.load_for_loop(self.config)
        template_resources = resource_set.by_position(InjectionPosition.TEMPLATE_BODY)

        if template_resources:
            # Use the first LOOP_TEMPLATE resource as the base template
            resource = template_resources[0]
            if resource.content:
                return resource.content

        # Priority 3: Mode's prompt_template file
        template_path = self.project.path / mode.prompt_template
        if template_path.exists():
            return template_path.read_text()

        # Priority 4: Default template for loop type
        default_template_path = (
            Path(__file__).parent.parent / "templates" / "loop_templates" / f"{self.config.type.value}.md"
        )
        if default_template_path.exists():
            return default_template_path.read_text()

        return f"Prompt template not found: {mode.prompt_template}"

    def _escape_template_vars(self, value: str) -> str:
        """Escape template variable syntax in user-provided values.

        Prevents template injection attacks by escaping {{ and }} sequences
        in content that will be substituted into templates.

        Args:
            value: User-provided string that may contain template syntax.

        Returns:
            String with {{ and }} escaped as {​{ and }​} (zero-width space inserted).
        """
        # Insert zero-width space to break template syntax without visible change
        # Using \u200b (zero-width space) between braces
        escaped = value.replace("{{", "{\u200b{")
        escaped = escaped.replace("}}", "}\u200b}")
        return escaped

    def _build_prompt(
        self,
        mode: Mode,
        mode_name: str,
        claimed_item: Optional[dict] = None,
        batch_items: Optional[list[dict]] = None,
    ) -> str:
        """Build the complete prompt for an iteration.

        Assembles the prompt from multiple sources in this order:
        1. Loop-level resources (from loop_resources table) - preferred if available
        2. Project-level resources (from resources table) - fallback
        3. Template content (loop-specific or project-level)
        4. Variable substitution (consumer loop variables)
        5. Batch items context (if batch mode)
        6. Run tracking marker

        Resource injection positions:
        - BEFORE_PROMPT: Coding standards, system guardrails (at the very start)
        - AFTER_DESIGN_DOC: Design docs, architecture, domain knowledge
        - BEFORE_TASK: Output guardrails
        - AFTER_TASK: Custom resources

        Args:
            mode: Mode configuration.
            mode_name: Name of the mode.
            claimed_item: For consumer loops, the item being processed (first item in batch mode).
            batch_items: For batch mode, all items to process together.

        Returns:
            Complete prompt with all resources and tracking marker.
        """
        template = self._load_prompt_template(mode)

        # Load loop-specific resources first (from loop_resources table)
        loop_resources = self._load_loop_resources()

        # Also load project-level resources as fallback
        resource_manager = ResourceManager(self.project.path, db=self.db)
        resource_set = resource_manager.load_for_loop(self.config, mode_name)

        # For each injection position, prefer loop resources if available,
        # otherwise fall back to project-level resources
        def get_section(position_key: str, injection_pos: InjectionPosition) -> str:
            loop_section = self._build_loop_resource_section(loop_resources, position_key)
            if loop_section:
                return loop_section
            return resource_manager.build_prompt_section(resource_set, injection_pos)

        before_prompt = get_section("before_prompt", InjectionPosition.BEFORE_PROMPT)
        after_design_doc = get_section("after_design_doc", InjectionPosition.AFTER_DESIGN_DOC)
        before_task = get_section("before_task", InjectionPosition.BEFORE_TASK)
        after_task = get_section("after_task", InjectionPosition.AFTER_TASK)

        # Assemble prompt with resources at their positions
        # BEFORE_PROMPT goes at the very start
        if before_prompt:
            template = before_prompt + "\n\n" + template

        # AFTER_DESIGN_DOC: Insert after any design doc marker or at start of template
        # For now, insert after BEFORE_PROMPT content and before main template
        if after_design_doc:
            # If template has a design doc marker, insert after it
            # Otherwise prepend to template content (after BEFORE_PROMPT)
            if "{{design_doc}}" in template:
                template = template.replace("{{design_doc}}", "{{design_doc}}\n\n" + after_design_doc)
            else:
                # Insert after any BEFORE_PROMPT content already added
                if before_prompt:
                    # Already have before_prompt + template, insert after before_prompt
                    parts = template.split("\n\n", 1)
                    if len(parts) == 2:
                        template = parts[0] + "\n\n" + after_design_doc + "\n\n" + parts[1]
                    else:
                        template = after_design_doc + "\n\n" + template
                else:
                    template = after_design_doc + "\n\n" + template

        # Get design doc content for direct substitution (hank-rcm {DESIGN_DOC} style)
        # This finds the first design_doc type resource and uses its content
        design_doc_content = ""
        for resource in loop_resources:
            if resource.get("resource_type") == "design_doc":
                design_doc_content = resource.get("_resolved_content", "")
                break
        if not design_doc_content:
            # Fallback to project-level resources
            for resource in resource_set.resources:
                if resource.resource_type.value == "design_doc":
                    design_doc_content = resource.content or ""
                    break

        # Substitute {DESIGN_DOC} (hank-rcm style) - escape content to prevent injection
        if "{DESIGN_DOC}" in template and design_doc_content:
            escaped_design_doc = self._escape_template_vars(design_doc_content)
            template = template.replace("{DESIGN_DOC}", escaped_design_doc)

        # BEFORE_TASK: Insert before the main task instruction
        # Look for {{task}} marker or insert near the end
        if before_task:
            if "{{task}}" in template:
                template = template.replace("{{task}}", before_task + "\n\n{{task}}")
            else:
                # Append before the final section
                template = template + "\n\n" + before_task

        # AFTER_TASK: Append at the end
        if after_task:
            template = template + "\n\n" + after_task

        # Inject generator loop context (existing stories, category stats, inputs)
        # This MUST happen before any variable substitution
        if self._is_generator_loop():
            template = self._inject_generator_context(template)

        # Inject consumer loop variables if we have a claimed item
        if claimed_item:
            import json

            # Escape user-provided values to prevent template injection
            content = self._escape_template_vars(
                claimed_item.get("content") or "[No content]"
            )
            title = self._escape_template_vars(
                claimed_item.get("title") or ""
            )
            metadata = claimed_item.get("metadata") or {}
            # json.dumps does NOT escape {{ }} so we must escape the result
            metadata_json = self._escape_template_vars(
                json.dumps(metadata) if metadata else "{}"
            )
            # workflow_id from our DB, escape for defense in depth
            workflow_id_val = self._escape_template_vars(
                claimed_item.get("workflow_id", self.workflow_id)
            )

            # Extract hank-rcm style fields for PROMPT_IMPL.md compatibility
            # These match the variables used by ralph_impl.sh:
            # - {STORY_ID}: Item ID
            # - {PRIORITY}: Priority number
            # - {STORY_TEXT}: Content (same as story)
            # - {NOTES}: Implementation notes from metadata
            # - {ACCEPTANCE_CRITERIA}: Formatted as numbered list (NOT JSON)
            story_id = self._escape_template_vars(claimed_item.get("id") or "UNKNOWN")
            priority = str(claimed_item.get("priority") or 50)
            story_text = content  # Already escaped
            notes = self._escape_template_vars(
                metadata.get("notes") or ""
            )

            # Format acceptance_criteria as numbered list (matching ralph_impl.sh)
            # ralph_impl.sh extracts this and formats as "1. Criterion\n2. Criterion\n..."
            acceptance_criteria_raw = metadata.get("acceptance_criteria") or []
            if isinstance(acceptance_criteria_raw, list):
                acceptance_criteria_lines = []
                for i, criterion in enumerate(acceptance_criteria_raw, 1):
                    criterion_escaped = self._escape_template_vars(str(criterion))
                    acceptance_criteria_lines.append(f"{i}. {criterion_escaped}")
                acceptance_criteria = "\n".join(acceptance_criteria_lines)
            else:
                acceptance_criteria = str(acceptance_criteria_raw)

            # Substitution order: most specific first to avoid partial matches
            template = template.replace("{{input_item.metadata}}", metadata_json)
            template = template.replace("{{input_item.content}}", content)
            template = template.replace("{{input_item.title}}", title)
            template = template.replace("{{input_item}}", content)  # Alias
            template = template.replace("{{workflow_id}}", workflow_id_val)
            # Backward compatibility for old templates using namespace/source_loop
            template = template.replace("{{namespace}}", workflow_id_val)
            template = template.replace("{{source_loop}}", workflow_id_val)

            # hank-rcm style variables (for PROMPT_IMPL.md compatibility)
            # Using {VAR} format to match ralph_impl.sh templates exactly
            template = template.replace("{STORY_ID}", story_id)
            template = template.replace("{PRIORITY}", priority)
            template = template.replace("{STORY_TEXT}", story_text)
            template = template.replace("{NOTES}", notes)
            template = template.replace("{ACCEPTANCE_CRITERIA}", acceptance_criteria)

        # Add implemented summary for consumer loops (shows what's already been done)
        # Support both {{implemented_summary}} (RalphX style) and {IMPLEMENTED_SUMMARY} (hank-rcm style)
        if self._is_consumer_loop():
            if "{{implemented_summary}}" in template or "{IMPLEMENTED_SUMMARY}" in template:
                impl_summary = self._build_implemented_summary()
                template = template.replace("{{implemented_summary}}", impl_summary)
                template = template.replace("{IMPLEMENTED_SUMMARY}", impl_summary)

        # Add batch items context if in batch mode
        if batch_items and len(batch_items) > 1:
            import json

            batch_context = "\n\n---\n## BATCH MODE: Implement the following items together\n\n"
            for i, item in enumerate(batch_items, 1):
                item_id = self._escape_template_vars(item.get("id", f"item-{i}"))
                item_title = self._escape_template_vars(item.get("title") or "")
                item_content = self._escape_template_vars(item.get("content") or "")
                batch_context += f"### Item {i}: {item_id}\n"
                if item_title:
                    batch_context += f"**Title:** {item_title}\n"
                batch_context += f"**Content:**\n{item_content}\n\n"

            batch_context += f"---\nTotal items in this batch: {len(batch_items)}\n"
            template = template + batch_context

        # Add run tracking marker
        if self.adapter and self._run:
            marker = self.adapter.build_run_marker(
                run_id=self._run.id,
                project_slug=self.project.slug,
                iteration=self._iteration,
                mode=mode_name,
            )
            template = template + marker

        return template

    def _is_consumer_loop(self) -> bool:
        """Check if this loop consumes items from another loop.

        Returns True if either:
        - The loop config has item_types.input.source set (config-based)
        - The consume_from_step_id was passed to constructor (workflow-based)
        """
        # Workflow-based consumer: consume_from_step_id was explicitly set
        if self._consume_from_step_id is not None:
            return True
        # Config-based consumer: source defined in loop config
        if not self.config.item_types:
            return False
        if not self.config.item_types.input:
            return False
        return bool(self.config.item_types.input.source)

    def _is_generator_loop(self) -> bool:
        """Check if this loop generates items (not a consumer).

        Generator loops produce work items from design docs/research.
        They need context about existing stories to avoid duplicates
        and to assign correct IDs.
        """
        # If it's a consumer loop, it's not a generator
        if self._is_consumer_loop():
            return False
        # If it has output types defined, it's a generator
        if self.config.item_types and self.config.item_types.output:
            return True
        # Check type field if present (for template-based loops)
        if hasattr(self.config, 'type') and str(self.config.type) == 'generator':
            return True
        return False

    def _inject_generator_context(self, template: str) -> str:
        """Inject existing stories and category stats for generator loops.

        This is CRITICAL for planning loops to:
        1. Know what stories already exist (to avoid duplicates)
        2. Know what IDs have been used (to assign new IDs correctly)
        3. Reference existing story IDs when specifying dependencies

        Template variables substituted:
        - {{existing_stories}}: JSON array of {id, title, category}
        - {{category_stats}}: JSON object with per-category count and next_id
        - {{total_stories}}: Total number of existing stories
        - {{inputs_list}}: List of input files in the loop's inputs directory

        Args:
            template: Prompt template string.

        Returns:
            Template with generator context variables substituted.
        """
        import json

        # 1. Get all items generated by this workflow step
        existing_items, _ = self.db.list_work_items(
            workflow_id=self.workflow_id,
            source_step_id=self.step_id,
            limit=10000,  # Get all existing items
        )

        # 2. Build category stats with next available ID
        category_stats: dict[str, dict] = {}
        for item in existing_items:
            cat = (item.get("category") or "MISC").upper()
            if cat not in category_stats:
                category_stats[cat] = {"count": 0, "ids": [], "max_num": 0}
            category_stats[cat]["count"] += 1
            category_stats[cat]["ids"].append(item["id"])

            # Parse numeric suffix: "AUTH-042" -> 42
            item_id = item.get("id", "")
            match = re.match(r'^[A-Za-z]+-(\d+)$', item_id)
            if match:
                num = int(match.group(1))
                category_stats[cat]["max_num"] = max(category_stats[cat]["max_num"], num)

        # Add next_id to each category
        for cat in category_stats:
            category_stats[cat]["next_id"] = category_stats[cat]["max_num"] + 1
            # Remove max_num from output (internal use only)
            del category_stats[cat]["max_num"]

        # 3. Build existing stories summary (for dependency reference)
        stories_summary = []
        for item in existing_items:
            stories_summary.append({
                "id": item.get("id", ""),
                "title": item.get("title", ""),
                "category": item.get("category", ""),
            })

        # 4. Handle inputs_list (input files for this loop)
        inputs_dir = Path(self.project.path) / self.config.name / "inputs"
        if inputs_dir.exists():
            input_files = [f.name for f in inputs_dir.iterdir() if f.is_file()]
            inputs_list = "\n".join(f"- {f}" for f in sorted(input_files))
        else:
            inputs_list = "(No input files found)"

        # 5. Substitute template variables (escape values first)
        existing_stories_json = self._escape_template_vars(
            json.dumps(stories_summary, indent=2)
        )
        category_stats_json = self._escape_template_vars(
            json.dumps(category_stats, indent=2)
        )

        template = template.replace("{{existing_stories}}", existing_stories_json)
        template = template.replace("{{category_stats}}", category_stats_json)
        template = template.replace("{{total_stories}}", str(len(existing_items)))
        template = template.replace("{{inputs_list}}", inputs_list)

        return template

    def _get_source_step_id(self) -> Optional[int]:
        """Get the source step ID for consumer loops.

        For consumer loops, this is the step that produced the items to consume.
        Set via consume_from_step_id constructor parameter.
        """
        if not self._is_consumer_loop():
            return None
        return self._consume_from_step_id

    def _check_consumer_completion(self) -> tuple[bool, int, int]:
        """Check if consumer loop has processed all available items.

        Returns:
            Tuple of (all_done, pending_count, total_count).
            - all_done: True if items exist and all are processed
            - pending_count: Number of items still pending/claimed
            - total_count: Total items from source step
        """
        source_step_id = self._get_source_step_id()
        if source_step_id is None:
            return False, 0, 0

        # Get total items from source (any status)
        _, total_count = self.db.list_work_items(
            workflow_id=self.workflow_id,
            source_step_id=source_step_id,
            limit=1,  # We just need the count
        )

        if total_count == 0:
            # No items exist yet - might be waiting for generator
            return False, 0, 0

        # Get pending items (status=completed from generator, unclaimed)
        pending_items, pending_count = self.db.list_work_items(
            workflow_id=self.workflow_id,
            source_step_id=source_step_id,
            status="completed",  # Items ready for consumption
            unclaimed_only=True,
            limit=1,
        )

        # Also check for claimed but not yet processed items
        # These are in-progress by another executor (or stale)
        # For now, if pending is 0, we're done
        all_done = pending_count == 0 and total_count > 0

        return all_done, pending_count, total_count

    def _is_foundational_item(self, item: dict) -> bool:
        """Check if an item is foundational (for architecture-first mode).

        Foundational items are identified by:
        1. Category matching foundation categories (FND, DBM, SEC, etc.)
        2. ID prefix matching foundation category codes

        Args:
            item: Work item dict.

        Returns:
            True if item is foundational.
        """
        # Check category
        category = (item.get("category") or "").lower()
        if category in self._foundation_categories:
            return True

        # Check ID prefix (e.g., "FND-001" -> "fnd")
        item_id = item.get("id", "")
        if "-" in item_id:
            prefix = item_id.split("-")[0].lower()
            if prefix in self._foundation_categories:
                return True

        return False

    def _build_dependency_graph(self) -> None:
        """Build/rebuild the dependency graph from source items.

        Called on first claim or when needed for phase detection.
        """
        source_step_id = self._get_source_step_id()
        if source_step_id is None:
            return

        # Get ALL items from source step (not just unclaimed)
        # Using limit of 10000 - warn if there are more items
        all_items, total_count = self.db.list_work_items(
            workflow_id=self.workflow_id,
            source_step_id=source_step_id,
            limit=10000,
        )

        if not all_items:
            return

        # Warn if items were truncated (dependency graph may be incomplete)
        if total_count > 10000:
            self._emit_event(
                ExecutorEvent.WARNING,
                f"Namespace has {total_count} items but only loaded 10000. "
                f"Dependency graph may be incomplete. Some items may be processed out of order.",
            )

        # Build dependency graph
        self._dependency_graph = DependencyGraph(all_items)

        # Warn about missing dependencies (items reference non-existent IDs)
        if self._dependency_graph.missing_dependencies:
            missing_count = sum(
                len(deps) for deps in self._dependency_graph.missing_dependencies.values()
            )
            affected_items = list(self._dependency_graph.missing_dependencies.keys())[:5]
            self._emit_event(
                ExecutorEvent.WARNING,
                f"Found {missing_count} invalid dependency references in {len(self._dependency_graph.missing_dependencies)} items. "
                f"Affected items (first 5): {affected_items}. These dependencies will be ignored.",
            )

        # Track already-completed items
        for item in all_items:
            status = item.get("status", "")
            if status in ("processed", "failed", "skipped", "duplicate"):
                self._completed_item_ids.add(item["id"])

        # Auto-detect phases if multi_phase is enabled
        if self.config.multi_phase and self.config.multi_phase.enabled:
            if self.config.multi_phase.auto_phase:
                # Auto-detect phases from dependencies
                self._detected_phases = self._dependency_graph.detect_phases(
                    max_batch_size=self.config.multi_phase.max_batch_size
                )
            else:
                # Use category-based phase mapping
                cat_to_phase = self.config.multi_phase.get_category_to_phase()
                if cat_to_phase:
                    self._detected_phases = self._dependency_graph.detect_phases_by_category(
                        cat_to_phase,
                        max_batch_size=self.config.multi_phase.max_batch_size,
                    )

            if self._detected_phases:
                self._emit_event(
                    ExecutorEvent.HEARTBEAT,
                    f"Detected {len(self._detected_phases)} phases with "
                    f"{sum(len(items) for items in self._detected_phases.values())} total items",
                )

    def _get_items_for_phase(self, phase: int) -> list[str]:
        """Get item IDs for a specific phase.

        Args:
            phase: Phase number.

        Returns:
            List of item IDs in that phase.
        """
        if not self._detected_phases:
            return []
        return self._detected_phases.get(phase, [])

    async def _claim_source_item(self, _retry_count: int = 0) -> Optional[dict]:
        """Claim an item from the source step for processing.

        Respects:
        - Phase filtering (if _phase_filter is set)
        - Category filtering (if _category_filter is set)
        - Dependency ordering (if _respect_dependencies is True)

        Args:
            _retry_count: Internal counter for race condition retries (max 5).

        Returns:
            Claimed item dict or None if no items available.
        """
        MAX_CLAIM_RETRIES = 5

        source_step_id = self._get_source_step_id()
        if source_step_id is None:
            return None

        # Build dependency graph on first call
        if self._dependency_graph is None and self._respect_dependencies:
            self._build_dependency_graph()

        # Query for available items with optional category filter
        items, _ = self.db.list_work_items(
            workflow_id=self.workflow_id,
            source_step_id=source_step_id,
            status="completed",
            unclaimed_only=True,
            category=self._category_filter,
            limit=100,  # Get more items to filter and order
        )

        if not items:
            return None

        # Apply phase filtering
        if self._phase_filter is not None and self._detected_phases:
            phase_item_ids = set(self._get_items_for_phase(self._phase_filter))
            items = [item for item in items if item["id"] in phase_item_ids]

            if not items:
                return None

        # Apply architecture-first prioritization
        # When enabled, foundational items (FND, DBM, SEC, ARC, etc.) are
        # prioritized until all foundational items are complete
        if self._architecture_first and not self._architecture_phase_complete:
            foundational = [item for item in items if self._is_foundational_item(item)]
            non_foundational = [item for item in items if not self._is_foundational_item(item)]

            if foundational:
                # Still have foundational items - prioritize them
                items = foundational
                self._emit_event(
                    ExecutorEvent.INFO,
                    f"Architecture-first mode: prioritizing {len(foundational)} foundational items",
                )
            else:
                # No more foundational items - mark phase complete
                self._architecture_phase_complete = True
                self._emit_event(
                    ExecutorEvent.INFO,
                    "Architecture-first mode: foundational phase complete, switching to normal processing",
                )
                items = non_foundational

        # Apply dependency ordering
        if self._respect_dependencies and self._dependency_graph:
            ready_ids = self._dependency_graph.get_ready_items(self._completed_item_ids)
            ready_set = set(ready_ids)
            # Filter to only items whose dependencies are complete
            items = [item for item in items if item["id"] in ready_set]

            if not items:
                # All available items have unsatisfied dependencies
                # Check if this is a deadlock (cycle) situation
                if self._dependency_graph.has_cycle():
                    self._emit_event(
                        ExecutorEvent.WARNING,
                        "Dependency cycle detected - will process items with unmet dependencies",
                    )
                    # Fall back to any unclaimed items
                    items, _ = self.db.list_work_items(
                        workflow_id=self.workflow_id,
                        source_step_id=source_step_id,
                        status="completed",
                        unclaimed_only=True,
                        category=self._category_filter,
                        limit=1,
                    )
                    if not items:
                        return None
                else:
                    # No ready items but no cycle - waiting for dependencies
                    return None

        if not items:
            return None

        # Take the first item (already sorted by priority)
        item = items[0]

        # Attempt to claim the item
        success = self.db.claim_work_item(
            id=item["id"],
            claimed_by=self.config.name,
        )

        if not success:
            # Race condition - another consumer claimed it first
            if _retry_count >= MAX_CLAIM_RETRIES:
                self._emit_event(
                    ExecutorEvent.WARNING,
                    f"Failed to claim item after {MAX_CLAIM_RETRIES} retries - high contention",
                )
                return None
            # Brief yield to reduce contention, then retry
            await asyncio.sleep(0.01 * (_retry_count + 1))
            return await self._claim_source_item(_retry_count=_retry_count + 1)

        return item

    async def _claim_batch_items(self) -> list[dict]:
        """Claim multiple items for batch implementation.

        Respects phase/category filters and dependency ordering.
        Claims up to batch_size items that can be implemented together.

        Returns:
            List of claimed items (may be empty).
        """
        claimed_items = []

        for _ in range(self._batch_size):
            item = await self._claim_source_item()
            if item is None:
                break
            claimed_items.append(item)

        return claimed_items

    def _build_implemented_summary(self) -> str:
        """Build a summary of already-processed items for this consumer loop.

        Matches the format of `prd_jsonl.py implemented-summary` from hank-rcm:
        - Groups items by CATEGORY (not by status)
        - Shows count per category
        - Lists implemented items with brief summaries
        - Helps Claude understand context and avoid duplicating work

        Format:
            ## FND (12 implemented)
            - FND-001: Core database models and migrations
            - FND-002: Base model classes with audit fields
            ...
            Total implemented: 247

        Returns:
            Formatted summary string, or empty string if no items processed yet.
        """
        source_step_id = self._get_source_step_id()
        if source_step_id is None:
            return ""

        # Get items that have been successfully implemented (status=processed)
        # This matches ralph_impl.sh's `implemented-summary` which only shows implemented items
        processed_items, _ = self.db.list_work_items(
            workflow_id=self.workflow_id,
            source_step_id=source_step_id,
            status="processed",
            limit=1000,  # Get more items to show comprehensive context
        )

        if not processed_items:
            return "No stories implemented yet."

        # Group by CATEGORY (matching prd_jsonl.py implemented-summary format)
        by_category: dict[str, list[dict]] = {}
        for item in processed_items:
            # Extract category from item or from ID prefix (e.g., "FND-001" -> "FND")
            category = item.get("category")
            if not category and item.get("id") and "-" in item["id"]:
                category = item["id"].split("-")[0].upper()
            category = category or "MISC"

            if category not in by_category:
                by_category[category] = []
            by_category[category].append(item)

        # Build summary matching prd_jsonl.py format
        lines = []

        # Sort categories alphabetically for consistent output
        for category in sorted(by_category.keys()):
            items = by_category[category]
            lines.append(f"\n## {category} ({len(items)} implemented)")

            # Show items sorted by ID
            items_sorted = sorted(items, key=lambda x: x.get("id") or "")
            for item in items_sorted[:30]:  # Cap at 30 per category to avoid huge prompts
                item_id = item.get("id", "?")

                # Get brief summary: prefer implementation_summary, then title, then content
                metadata = item.get("metadata") or {}
                summary = metadata.get("implementation_summary") or metadata.get("impl_notes")
                if not summary:
                    summary = item.get("title") or (item.get("content") or "")[:80]
                if len(summary) > 80:
                    summary = summary[:77] + "..."

                lines.append(f"- {item_id}: {summary}")

            if len(items) > 30:
                lines.append(f"... and {len(items) - 30} more")

        lines.append(f"\nTotal implemented: {len(processed_items)}")

        return "\n".join(lines)

    def _release_claimed_item(self, item_id: str) -> None:
        """Release a claim on an item (on iteration failure)."""
        self.db.release_work_item(item_id)

    def _mark_item_processed(self, item_id: str) -> bool:
        """Mark an item as processed (on iteration success).

        Also tracks the item as completed for dependency ordering.

        Returns:
            True if item was marked processed, False if failed (already processed, etc.)
        """
        success = self.db.mark_work_item_processed(
            id=item_id,
            processed_by=self.config.name,
        )
        if success:
            self._completed_item_ids.add(item_id)
        return success

    def _update_item_with_structured_status(
        self,
        item_id: str,
        structured_output: dict,
    ) -> bool:
        """Update item status using structured output from Claude.

        Parses the structured output from --json-schema and updates the
        work item with the specific status (implemented, duplicate, external,
        skipped, error) along with associated metadata.

        Args:
            item_id: Work item ID to update.
            structured_output: Parsed JSON from Claude's structured output.

        Returns:
            True if item was updated, False otherwise.
        """
        # Extract status and related fields from structured output
        status = structured_output.get("status", "implemented")

        # Validate status is a known value
        try:
            validated_status = ItemStatus(status)
        except ValueError:
            # Unknown status, default to implemented
            validated_status = ItemStatus.IMPLEMENTED

        # Map ItemStatus to database status values
        status_map = {
            ItemStatus.IMPLEMENTED: "processed",
            ItemStatus.DUPLICATE: "duplicate",
            ItemStatus.EXTERNAL: "external",
            ItemStatus.SKIPPED: "skipped",
            ItemStatus.ERROR: "failed",
        }
        db_status = status_map.get(validated_status, "processed")

        # Extract optional fields
        summary = structured_output.get("summary")
        duplicate_of = structured_output.get("duplicate_of")
        external_system = structured_output.get("external_system")
        reason = structured_output.get("reason")
        files_changed = structured_output.get("files_changed", [])
        tests_passed = structured_output.get("tests_passed")

        # Build metadata dict for extra fields
        metadata = {}
        if summary:
            metadata["implementation_summary"] = summary
        if external_system:
            metadata["external_system"] = external_system
        if reason:
            metadata["status_reason"] = reason
        if files_changed:
            metadata["files_changed"] = files_changed
        if tests_passed is not None:
            metadata["tests_passed"] = tests_passed

        success = self.db.update_work_item_with_status(
            id=item_id,
            status=db_status,
            processed_by=self.config.name,
            duplicate_of=duplicate_of,
            skip_reason=reason if validated_status == ItemStatus.SKIPPED else None,
            metadata=metadata,
        )

        if success:
            self._completed_item_ids.add(item_id)

            # Log the specific status for visibility
            status_msg = f"Item {item_id} marked as {validated_status.value}"
            if duplicate_of:
                status_msg += f" (duplicate of {duplicate_of})"
            elif reason:
                status_msg += f": {reason[:50]}..." if len(reason) > 50 else f": {reason}"

            self._emit_event(ExecutorEvent.ITERATION_COMPLETED, status_msg)

        return success

    def extract_work_items(self, output: str) -> list[dict]:
        """Extract work items from Claude output.

        Tries multiple patterns to extract structured items.

        Args:
            output: Raw text output from Claude.

        Returns:
            List of work item dictionaries with 'id' and 'content' keys.
        """
        items = []

        # Try JSON pattern first
        import json

        def extract_items_from_list(parsed: list) -> list[dict]:
            """Extract work items from a parsed JSON list."""
            extracted = []
            for item in parsed:
                if isinstance(item, dict) and 'id' in item:
                    # Support both 'content' (RalphX style) and 'story' (hank-rcm style)
                    item_content = item.get('content') or item.get('story')
                    if not item_content:
                        continue  # Skip items without content

                    # Extract known fields explicitly
                    known_fields = {
                        'id', 'content', 'story', 'title', 'priority', 'category',
                        'tags', 'dependencies', 'acceptance_criteria', 'complexity'
                    }
                    extracted.append({
                        'id': str(item['id']),
                        'content': str(item_content),
                        'title': item.get('title'),
                        'priority': item.get('priority'),
                        'category': item.get('category'),
                        'tags': item.get('tags'),
                        'dependencies': item.get('dependencies'),
                        'metadata': {k: v for k, v in item.items()
                                     if k not in known_fields},
                    })
            return extracted

        try:
            # Try 1: Look for JSON object with stories/items array
            # Pattern: {"stories": [...]} or {"items": [...]}
            obj_match = re.search(r'\{[\s\S]*"(?:stories|items)"\s*:\s*\[[\s\S]*\][\s\S]*\}', output)
            if obj_match:
                try:
                    parsed = json.loads(obj_match.group())
                    if isinstance(parsed, dict):
                        stories_list = parsed.get('stories') or parsed.get('items') or []
                        if isinstance(stories_list, list):
                            items = extract_items_from_list(stories_list)
                            if items:
                                return items
                except json.JSONDecodeError:
                    pass

            # Try 2: Look for JSON array directly (greedy to get outer array)
            # Use greedy matching to find the largest array
            json_match = re.search(r'\[[\s\S]*\]', output)
            if json_match:
                parsed = json.loads(json_match.group())
                if isinstance(parsed, list):
                    items = extract_items_from_list(parsed)
                    if items:
                        return items
        except (json.JSONDecodeError, ValueError):
            pass

        # Try markdown list pattern: - **ID-001**: Content
        for match in ITEM_PATTERNS[1].finditer(output):
            item_id = match.group(1)
            content = match.group(2).strip()
            items.append({
                'id': item_id,
                'content': content,
            })

        if items:
            return items

        # Try numbered list pattern: 1. [ID-001] Content
        for match in ITEM_PATTERNS[2].finditer(output):
            item_id = match.group(1)
            content = match.group(2).strip()
            items.append({
                'id': item_id,
                'content': content,
            })

        return items

    def _save_work_items(self, items: list[dict]) -> int:
        """Save work items to database.

        Args:
            items: List of work item dictionaries.

        Returns:
            Number of items saved.
        """
        saved = 0

        # Determine item_type from loop config
        item_type = "item"
        if self.config.item_types and self.config.item_types.output:
            item_type = self.config.item_types.output.singular

        for item in items:
            try:
                item_id = item.get('id', str(uuid.uuid4())[:8])
                self.db.create_work_item(
                    id=item_id,
                    workflow_id=self.workflow_id,
                    source_step_id=self.step_id,
                    content=item.get('content', ''),
                    title=item.get('title'),
                    priority=item.get('priority'),
                    status='completed',  # Items from loops are ready for consumption
                    category=item.get('category'),
                    metadata=item.get('metadata'),
                    dependencies=item.get('dependencies'),
                    item_type=item_type,
                )
                saved += 1
                self._emit_event(
                    ExecutorEvent.ITEM_ADDED,
                    f"Added item: {item_id}",
                    item_id=item_id,
                    content=item.get('content', '')[:100],
                )
            except Exception as e:
                # Item may already exist (duplicate)
                import logging
                _save_log = logging.getLogger(__name__)
                _save_log.warning(f"[SAVE] Failed to save item {item.get('id')}: {e}")
                import traceback
                _save_log.warning(f"[SAVE] Traceback: {traceback.format_exc()}")
                self._emit_event(
                    ExecutorEvent.WARNING,
                    f"Failed to save item {item.get('id')}: {e}",
                )
        return saved

    async def _run_iteration(self, mode_name: str, mode: Mode) -> IterationResult:
        """Run a single iteration.

        Args:
            mode_name: Name of the selected mode.
            mode: Mode configuration.

        Returns:
            IterationResult with success status and items.
        """
        result = IterationResult(mode_name=mode_name)
        start_time = datetime.utcnow()
        claimed_item = None
        claimed_items: list[dict] = []  # For batch mode

        try:
            # For consumer loops, claim item(s) first
            if self._is_consumer_loop():
                if self._batch_mode:
                    # Batch mode: claim multiple items
                    claimed_items = await self._claim_batch_items()
                    if not claimed_items:
                        result.success = True
                        result.no_items_available = True
                        result.error_message = "No items available from source loop"
                        return result
                    # Use first item for template (backward compatibility)
                    claimed_item = claimed_items[0]
                else:
                    # Single item mode
                    claimed_item = await self._claim_source_item()
                    if not claimed_item:
                        # No items available to process - signal to main loop
                        result.success = True
                        result.no_items_available = True
                        result.error_message = "No items available from source loop"
                        return result

            # Build prompt - include batch items if in batch mode
            prompt = self._build_prompt(mode, mode_name, claimed_item, claimed_items if self._batch_mode else None)

            # Emit prompt prepared event with size stats
            prompt_chars = len(prompt)
            prompt_lines = prompt.count("\n") + 1 if prompt else 0
            estimated_tokens = prompt_chars // 4  # Rough estimate
            self._emit_event(
                ExecutorEvent.PROMPT_PREPARED,
                f"Prompt: {prompt_chars:,} chars, {prompt_lines:,} lines, ~{estimated_tokens:,} tokens",
                prompt_chars=prompt_chars,
                prompt_lines=prompt_lines,
                estimated_tokens=estimated_tokens,
                mode=mode_name,
            )

            if self.dry_run:
                # Simulate execution
                await asyncio.sleep(0.1)
                result.success = True
                result.duration_seconds = 0.1
                # Mark items processed in dry run too
                items_to_mark = claimed_items if self._batch_mode else ([claimed_item] if claimed_item else [])
                for item in items_to_mark:
                    if not self._mark_item_processed(item["id"]):
                        self._emit_event(
                            ExecutorEvent.WARNING,
                            f"Failed to mark item {item['id']} as processed in dry run",
                        )
                return result

            # Execute with adapter
            # For consumer loops, use structured output schema for status reporting
            # Note: Structured output only works for single-item mode because the
            # schema reports ONE status, which would incorrectly apply to ALL items
            # in batch mode. Batch mode falls back to generic "processed" status.
            json_schema = None
            if self._is_consumer_loop() and not self._batch_mode:
                json_schema = IMPLEMENTATION_STATUS_SCHEMA

            # Callback to register session immediately when it starts
            # This enables live streaming in the UI before execution completes
            def register_session_early(session_id: str) -> None:
                if self._run:
                    self.db.create_session(
                        session_id=session_id,
                        run_id=self._run.id,
                        iteration=self._iteration,
                        mode=mode_name,
                        status="running",
                    )

            exec_result = await self.adapter.execute(
                prompt=prompt,
                model=mode.model,
                tools=mode.tools if mode.tools else None,
                timeout=mode.timeout,
                json_schema=json_schema,
                on_session_start=register_session_early,
            )

            result.session_id = exec_result.session_id
            result.success = exec_result.success
            result.timeout = exec_result.timeout

            if exec_result.error_message:
                result.error_message = exec_result.error_message

            # Extract work items from output
            import logging
            _log = logging.getLogger(__name__)
            _log.warning(f"[EXTRACT] text_output len={len(exec_result.text_output) if exec_result.text_output else 0}")
            if exec_result.text_output:
                _log.warning(f"[EXTRACT] text_output[:200]={exec_result.text_output[:200]}")
                # Check if JSON with stories is present
                has_stories = '"stories"' in exec_result.text_output
                has_json_start = '```json' in exec_result.text_output or '{"stories"' in exec_result.text_output
                _log.warning(f"[EXTRACT] has_stories={has_stories}, has_json_start={has_json_start}")
                if has_stories:
                    # Find and log the stories section
                    idx = exec_result.text_output.find('"stories"')
                    _log.warning(f"[EXTRACT] stories found at idx={idx}, context: {exec_result.text_output[max(0,idx-50):idx+200]}")
                items = self.extract_work_items(exec_result.text_output)
                _log.warning(f"[EXTRACT] extracted {len(items)} items")
                if items:
                    saved = self._save_work_items(items)
                    result.items_added = items
                    self._items_generated += saved
                    self._no_items_streak = 0  # Reset streak when items are generated
                    _log.warning(f"[EXTRACT] saved {saved} items")
                else:
                    # No items generated this iteration - track for completion detection
                    self._no_items_streak += 1
                    _log.warning(f"[EXTRACT] no items extracted, streak={self._no_items_streak}")

                # Check for explicit completion signal from Claude
                if "[GENERATION_COMPLETE]" in exec_result.text_output:
                    result.generator_complete = True  # type: ignore
                    _log.warning("[EXTRACT] found [GENERATION_COMPLETE] signal")

            # Update session status (session was registered early via callback)
            if exec_result.session_id and self._run:
                self.db.update_session_status(
                    session_id=exec_result.session_id,
                    status="completed" if exec_result.success else "error",
                )

            # Mark claimed item(s) based on structured output or as processed
            if result.success:
                items_to_mark = claimed_items if self._batch_mode else ([claimed_item] if claimed_item else [])
                for item in items_to_mark:
                    # Use structured output status if available and valid
                    # structured_output must be a dict for _update_item_with_structured_status
                    if isinstance(exec_result.structured_output, dict):
                        if not self._update_item_with_structured_status(
                            item["id"],
                            exec_result.structured_output,
                        ):
                            self._emit_event(
                                ExecutorEvent.WARNING,
                                f"Failed to update item {item['id']} with structured status",
                            )
                    else:
                        # Fallback to generic processed status
                        if not self._mark_item_processed(item["id"]):
                            self._emit_event(
                                ExecutorEvent.WARNING,
                                f"Failed to mark item {item['id']} as processed - may already be processed",
                            )

        except asyncio.TimeoutError:
            result.success = False
            result.timeout = True
            result.error_message = f"Timeout after {mode.timeout}s"

        except asyncio.CancelledError:
            result.success = False
            result.error_message = "Cancelled"
            raise

        except Exception as e:
            result.success = False
            result.error_message = str(e)

        finally:
            result.duration_seconds = (
                datetime.utcnow() - start_time
            ).total_seconds()

            # Store claimed item for git commit message templating
            result.claimed_item = claimed_item

            # Release claimed item(s) on failure
            if not result.success:
                items_to_release = claimed_items if self._batch_mode else ([claimed_item] if claimed_item else [])
                for item in items_to_release:
                    try:
                        self._release_claimed_item(item["id"])
                    except Exception:
                        pass  # Don't fail on cleanup errors

        return result

    def _check_limits(self) -> Optional[str]:
        """Check if any limits have been reached.

        Returns:
            Stop reason string if limit reached, None otherwise.
        """
        limits = self.config.limits

        # Check max iterations
        if limits.max_iterations > 0 and self._iteration >= limits.max_iterations:
            return f"Max iterations reached ({limits.max_iterations})"

        # Check max runtime
        if limits.max_runtime_seconds > 0 and self._start_time:
            elapsed = (datetime.utcnow() - self._start_time).total_seconds()
            if elapsed >= limits.max_runtime_seconds:
                return f"Max runtime reached ({limits.max_runtime_seconds}s)"

        # Check consecutive errors
        if self._consecutive_errors >= limits.max_consecutive_errors:
            return f"Max consecutive errors reached ({limits.max_consecutive_errors})"

        return None

    async def run(self, max_iterations: Optional[int] = None) -> Run:
        """Run the loop until completion or limit.

        Args:
            max_iterations: Override max iterations from config.

        Returns:
            Completed Run instance.
        """
        # Clean up any stale claims from crashed executors before starting
        # This prevents items being stuck in limbo indefinitely
        if self._is_consumer_loop():
            stale_released = self.db.release_stale_claims(
                max_age_minutes=30,
            )
            if stale_released > 0:
                self._emit_event(
                    ExecutorEvent.WARNING,
                    f"Released {stale_released} stale item claims from crashed executors",
                )

        # Clean up stale runs before starting a new one
        from ralphx.core.doctor import cleanup_stale_runs
        cleaned_runs = cleanup_stale_runs(self.db, max_inactivity_minutes=15)
        if cleaned_runs:
            self._emit_event(
                ExecutorEvent.WARNING,
                f"Cleaned up {len(cleaned_runs)} stale run(s) from crashed executors",
            )

        # Create run record
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        current_pid = os.getpid()
        now = datetime.utcnow()
        self._run = Run(
            id=run_id,
            project_id=self.project.id,
            loop_name=self.config.name,
            status=RunStatus.RUNNING,
            started_at=now,
            executor_pid=current_pid,
            last_activity_at=now,
        )
        self._start_time = self._run.started_at
        self._iteration = 0
        self._consecutive_errors = 0
        self._items_generated = 0

        # Save run to database (ProjectDatabase.create_run starts as active by default)
        self.db.create_run(
            id=run_id,
            loop_name=self.config.name,
            workflow_id=self.workflow_id,
            step_id=self.step_id,
        )
        # Store PID and initial activity timestamp for stale detection
        self.db.update_run(
            run_id,
            executor_pid=current_pid,
            last_activity_at=now.isoformat(),
        )

        self._emit_event(
            ExecutorEvent.RUN_STARTED,
            f"Starting loop '{self.config.name}'",
            loop_name=self.config.name,
            max_iterations=max_iterations or self.config.limits.max_iterations,
        )

        # Set up SIGINT handler
        loop = asyncio.get_running_loop()
        original_handler = signal.getsignal(signal.SIGINT)

        def sigint_handler(signum, frame):
            self._stopping = True

        signal.signal(signal.SIGINT, sigint_handler)

        try:
            effective_max = max_iterations or self.config.limits.max_iterations

            while not self._stopping:
                # Check limits
                stop_reason = self._check_limits()
                if stop_reason:
                    self._emit_event(ExecutorEvent.RUN_COMPLETED, stop_reason)
                    self._run.status = RunStatus.COMPLETED
                    break

                # Override max_iterations check
                if effective_max > 0 and self._iteration >= effective_max:
                    stop_reason = f"Requested iterations completed ({effective_max})"
                    self._emit_event(ExecutorEvent.RUN_COMPLETED, stop_reason)
                    self._run.status = RunStatus.COMPLETED
                    break

                # Wait if paused
                await self._pause_event.wait()

                # Select mode
                mode_name, mode = self.select_mode()
                self._iteration += 1

                self._emit_event(
                    ExecutorEvent.ITERATION_STARTED,
                    f"Starting iteration {self._iteration}",
                    mode=mode_name,
                )

                # Run iteration
                result = await self._run_iteration(mode_name, mode)

                # Handle consumer loop with no items specially
                if result.no_items_available:
                    # Don't count this against max_iterations - we didn't actually do work
                    self._iteration -= 1  # Undo the increment

                    # Check if ALL items have been processed (consumer complete)
                    # vs just waiting for items to arrive (generator still working)
                    all_done, pending, total = self._check_consumer_completion()

                    if all_done:
                        # All items from source have been processed - consumer is done!
                        stop_reason = f"All items processed ({total} total)"
                        self._emit_event(ExecutorEvent.RUN_COMPLETED, stop_reason)
                        self._run.status = RunStatus.COMPLETED
                        break

                    if total == 0:
                        # No items exist yet - waiting for generator
                        self._emit_event(
                            ExecutorEvent.HEARTBEAT,
                            f"Consumer loop waiting for items from source (none exist yet)",
                            mode=mode_name,
                        )
                    else:
                        # Items exist but all are claimed/in-progress
                        self._emit_event(
                            ExecutorEvent.HEARTBEAT,
                            f"Consumer loop waiting ({pending} pending, {total} total)",
                            mode=mode_name,
                        )

                    # Use longer back-off when no items available
                    wait_time = max(5.0, self.config.limits.cooldown_between_iterations)
                    if not self._stopping:
                        await asyncio.sleep(wait_time)
                    continue

                # Check for generator loop completion (until-done mode)
                # A generator is complete if:
                #   1. Claude explicitly signals [GENERATION_COMPLETE], OR
                #   2. 3+ consecutive iterations with 0 items AND max_iterations is unlimited (0 or -1)
                if not self._is_consumer_loop():
                    generator_done = False
                    stop_reason = None

                    if result.generator_complete:
                        generator_done = True
                        stop_reason = f"Generator signaled completion after {self._iteration} iterations, {self._items_generated} items"

                    elif effective_max <= 0 and self._no_items_streak >= 3:
                        # Unlimited mode (-1 or 0) and 3 consecutive empty iterations
                        generator_done = True
                        stop_reason = f"Generator exhausted (3 empty iterations), {self._items_generated} items generated"

                    if generator_done:
                        self._emit_event(ExecutorEvent.RUN_COMPLETED, stop_reason)
                        self._run.status = RunStatus.COMPLETED
                        break

                # Handle Phase 1 mode progression
                if (
                    self.config.mode_selection.strategy == ModeSelectionStrategy.PHASE_AWARE
                    and not self._phase1_complete
                ):
                    mode = self.config.modes.get(mode_name)
                    if mode and mode.phase == "phase_1":
                        if result.success:
                            # Get all Phase 1 modes
                            phase1_modes = [
                                name for name, m in self.config.modes.items()
                                if m.phase == "phase_1"
                            ]
                            # Advance to next Phase 1 mode
                            self._phase1_mode_index += 1

                            if self._phase1_mode_index >= len(phase1_modes):
                                # All Phase 1 modes completed
                                self._phase1_complete = True
                                self._emit_event(
                                    ExecutorEvent.HEARTBEAT,
                                    "Phase 1 complete, switching to normal mode",
                                )
                            else:
                                # More Phase 1 modes remaining
                                next_mode_name = phase1_modes[self._phase1_mode_index]
                                self._emit_event(
                                    ExecutorEvent.HEARTBEAT,
                                    f"Phase 1 mode {self._phase1_mode_index}/{len(phase1_modes)} complete, "
                                    f"advancing to '{next_mode_name}'",
                                )

                if result.success:
                    self._consecutive_errors = 0

                    # Handle git commit for consumer loops after successful implementation
                    if self._is_consumer_loop():
                        # Pass the processed item for commit message templating
                        git_success = await self._handle_git_commit(
                            mode_name,
                            result,
                            item=result.claimed_item,
                        )
                        if not git_success:
                            # Git commit failed with fail_on_error=True
                            result.success = False
                            result.error_message = "Git commit failed"
                else:
                    self._consecutive_errors += 1
                    self._emit_event(
                        ExecutorEvent.ERROR,
                        result.error_message or "Iteration failed",
                        mode=mode_name,
                        consecutive_errors=self._consecutive_errors,
                        max_consecutive_errors=self.config.limits.max_consecutive_errors,
                    )

                self._emit_event(
                    ExecutorEvent.ITERATION_COMPLETED,
                    f"Iteration {self._iteration} completed",
                    mode=mode_name,
                    success=result.success,
                    items_added=len(result.items_added),
                    duration=result.duration_seconds,
                )

                # Update run record with activity timestamp for stale detection
                now = datetime.utcnow()
                self._run.iterations_completed = self._iteration
                self._run.items_generated = self._items_generated
                self._run.last_activity_at = now
                self.db.update_run(
                    self._run.id,
                    iterations_completed=self._iteration,
                    items_generated=self._items_generated,
                    last_activity_at=now.isoformat(),
                )

                # Cooldown between iterations
                if not self._stopping:
                    cooldown = self.config.limits.cooldown_between_iterations
                    if cooldown > 0:
                        await asyncio.sleep(cooldown)

        except asyncio.CancelledError:
            self._run.status = RunStatus.ABORTED
            self._emit_event(ExecutorEvent.RUN_ABORTED, "Run cancelled")
            raise

        except Exception as e:
            self._run.status = RunStatus.ERROR
            self._run.error_message = str(e)
            self._emit_event(ExecutorEvent.ERROR, str(e))

        finally:
            # Restore signal handler
            signal.signal(signal.SIGINT, original_handler)

            # Finalize run
            self._run.completed_at = datetime.utcnow()
            self.db.update_run(
                self._run.id,
                status=self._run.status.value,
                completed_at=self._run.completed_at.isoformat(),
                iterations_completed=self._iteration,
                items_generated=self._items_generated,
                error_message=self._run.error_message,
            )

            # Auto-advance workflow step if run completed successfully
            if self._run.status == RunStatus.COMPLETED:
                self._handle_step_completion()

            # Stop adapter if running
            if self.adapter.is_running:
                await self.adapter.stop()

        return self._run

    async def stop(self) -> None:
        """Request graceful stop of the loop."""
        self._stopping = True
        if self.adapter.is_running:
            await self.adapter.stop()

    def pause(self) -> None:
        """Pause execution after current iteration."""
        if self._run and self._run.is_active:
            self._paused = True
            self._pause_event.clear()
            self._run.status = RunStatus.PAUSED
            self.db.update_run(self._run.id, status="paused")
            self._emit_event(ExecutorEvent.RUN_PAUSED, "Run paused")

    def resume(self) -> None:
        """Resume paused execution."""
        if self._run and self._run.status == RunStatus.PAUSED:
            self._paused = False
            self._pause_event.set()
            self._run.status = RunStatus.RUNNING
            self.db.update_run(self._run.id, status="running")
            self._emit_event(ExecutorEvent.RUN_RESUMED, "Run resumed")

    def _handle_step_completion(self) -> None:
        """Handle workflow step completion and auto-advance.

        When a run completes successfully, check if the step's target iterations
        have been met. If so, mark the step as completed and automatically start
        the next step in the workflow.

        This is called from the run() finally block when status is COMPLETED.
        """
        if not self.workflow_id or not self.step_id:
            return  # Not running as part of a workflow

        try:
            # Get current step info
            step = self.db.get_workflow_step(self.step_id)
            if not step:
                return

            # Only auto-advance if step is still active
            if step["status"] != "active":
                return

            # Check if step completion criteria are met
            step_config = step.get("config") or {}
            target_iterations = step_config.get("iterations", 0)

            # Get total iterations completed across all runs for this step
            step_runs = self.db.list_runs(workflow_id=self.workflow_id, step_id=self.step_id)
            total_iterations = sum(r.get("iterations_completed", 0) for r in step_runs)

            should_complete = False

            # For generator loops with explicit completion signal or no-items streak
            if not self._is_consumer_loop():
                # Generator completed if:
                # 1. Reached target iterations (target > 0 and total >= target)
                # 2. OR ran until done (target <= 0 and we broke out of loop)
                if target_iterations > 0:
                    should_complete = total_iterations >= target_iterations
                else:
                    # Unlimited mode - completed because generator signaled done
                    should_complete = True

            # For consumer loops, step completes when all items are processed
            else:
                all_done, _, _ = self._check_consumer_completion()
                should_complete = all_done

            if should_complete:
                self._emit_event(
                    ExecutorEvent.HEARTBEAT,
                    f"Step completed, checking for next step...",
                    step_id=self.step_id,
                    total_iterations=total_iterations,
                )

                # Get workflow and find next step
                workflow = self.db.get_workflow(self.workflow_id)
                if not workflow or workflow["status"] != "active":
                    return

                steps = self.db.list_workflow_steps(self.workflow_id)
                current_step_num = step["step_number"]

                # Find next step
                next_step = None
                for s in steps:
                    if s["step_number"] == current_step_num + 1:
                        next_step = s
                        break

                # Advance to next step atomically
                self.db.advance_workflow_step_atomic(
                    workflow_id=self.workflow_id,
                    current_step_id=step["id"],
                    next_step_id=next_step["id"] if next_step else None,
                    skip_current=False,
                    artifacts={"items_generated": self._items_generated},
                )

                if next_step:
                    self._emit_event(
                        ExecutorEvent.HEARTBEAT,
                        f"Auto-advanced to step {next_step['step_number']}: {next_step.get('name', 'Unknown')}",
                        next_step_id=next_step["id"],
                        next_step_name=next_step.get("name"),
                    )
                else:
                    self._emit_event(
                        ExecutorEvent.HEARTBEAT,
                        f"Workflow completed - no more steps",
                    )

        except Exception as e:
            # Don't fail the run if step completion handling fails
            self._emit_event(
                ExecutorEvent.WARNING,
                f"Failed to handle step completion: {e}",
            )

    # ========== Git Integration ==========

    async def _handle_git_commit(
        self,
        mode_name: str,
        result: "IterationResult",
        item: Optional[dict] = None,
    ) -> bool:
        """Commit changes after successful implementation.

        Args:
            mode_name: Name of the mode that was executed.
            result: Result of the iteration.
            item: The work item that was processed (for consumer loops).

        Returns:
            True if commit succeeded (or not enabled), False if commit failed.
        """
        if not self.config.git or not self.config.git.enabled:
            return True
        if not self.config.git.auto_commit or not result.success:
            return True

        # Check .git exists
        git_dir = Path(self.project.path) / ".git"
        if not git_dir.exists():
            self._emit_event(
                ExecutorEvent.WARNING,
                "Git enabled but no .git directory found",
            )
            return True  # Not a fatal error unless fail_on_error is True

        # Build commit message
        template = self.config.git.commit_template or "Implement {item_id}"
        item_id = item.get("id", "unknown") if item else "batch"
        item_title = item.get("title", "")[:50] if item else ""
        message = template.format(
            iteration=self._iteration,
            mode=mode_name,
            item_id=item_id,
            summary=item_title,
        )

        # Run git commit
        success = await self._run_git_commit(message)

        if not success and self.config.git.fail_on_error:
            return False

        return True

    async def _run_git_commit(self, message: str) -> bool:
        """Execute git add and commit.

        Args:
            message: Commit message.

        Returns:
            True if commit succeeded, False otherwise.
        """
        project_path = Path(self.project.path)

        try:
            # Run git add -A to stage all changes
            add_result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["git", "add", "-A"],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                ),
            )

            if add_result.returncode != 0:
                self._emit_event(
                    ExecutorEvent.WARNING,
                    f"git add failed: {add_result.stderr.strip()}",
                )
                return False

            # Check if there are changes to commit
            status_result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["git", "diff", "--cached", "--quiet"],
                    cwd=project_path,
                    capture_output=True,
                    timeout=30,
                ),
            )

            if status_result.returncode == 0:
                # No changes to commit
                self._emit_event(
                    ExecutorEvent.HEARTBEAT,
                    "No changes to commit",
                )
                return True

            # Run git commit
            commit_result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["git", "commit", "-m", message],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                ),
            )

            if commit_result.returncode != 0:
                # Check for pre-commit hook failure or merge conflict
                stderr = commit_result.stderr.strip()
                if "hook" in stderr.lower() or "pre-commit" in stderr.lower():
                    self._emit_event(
                        ExecutorEvent.WARNING,
                        f"Pre-commit hook rejected commit: {stderr}",
                    )
                elif "conflict" in stderr.lower():
                    self._emit_event(
                        ExecutorEvent.WARNING,
                        f"Merge conflict detected: {stderr}",
                    )
                else:
                    self._emit_event(
                        ExecutorEvent.WARNING,
                        f"git commit failed: {stderr}",
                    )
                return False

            # Parse commit hash from output (usually in first line)
            output = commit_result.stdout.strip()
            commit_hash = ""
            if output:
                # Try to extract short hash from output like "[main abc1234] message"
                import re
                match = re.search(r'\[[\w-]+\s+([a-f0-9]+)\]', output)
                if match:
                    commit_hash = match.group(1)

            self._emit_event(
                ExecutorEvent.GIT_COMMIT,
                f"Committed changes: {message[:50]}",
                commit_hash=commit_hash,
                message=message,
            )

            return True

        except subprocess.TimeoutExpired:
            self._emit_event(
                ExecutorEvent.WARNING,
                "Git operation timed out",
            )
            return False
        except Exception as e:
            self._emit_event(
                ExecutorEvent.WARNING,
                f"Git operation failed: {e}",
            )
            return False
