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
import random
import re
import signal
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
from ralphx.core.workspace import get_loop_settings_path
from ralphx.models.loop import LoopConfig, Mode, ModeSelectionStrategy
from ralphx.models.project import Project
from ralphx.models.run import Run, RunStatus


class ExecutorEvent(str, Enum):
    """Events emitted by the executor."""

    RUN_STARTED = "run_started"
    ITERATION_STARTED = "iteration_started"
    ITERATION_COMPLETED = "iteration_completed"
    ITEM_ADDED = "item_added"
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
        adapter: Optional[LLMAdapter] = None,
        dry_run: bool = False,
        phase: Optional[int] = None,
        category: Optional[str] = None,
        respect_dependencies: bool = True,
        batch_mode: bool = False,
        batch_size: int = 10,
    ):
        """Initialize the executor.

        Args:
            project: Project to run loop against.
            loop_config: Loop configuration.
            db: Project-local database instance for persistence.
            adapter: LLM adapter (defaults to ClaudeCLIAdapter).
            dry_run: If True, simulate execution without calling LLM.
            phase: Optional phase number to filter items (consumer loops only).
            category: Optional category to filter items (consumer loops only).
            respect_dependencies: If True, process items in dependency order.
            batch_mode: If True, claim multiple items for batch implementation.
            batch_size: Maximum items to claim for batch mode.
        """
        self.project = project
        self.config = loop_config
        self.db = db
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

        # Dependency graph for ordering (built on first claim)
        self._dependency_graph: Optional[DependencyGraph] = None
        self._detected_phases: Optional[dict[int, list[str]]] = None
        self._completed_item_ids: set[str] = set()

        # Run state
        self._run: Optional[Run] = None
        self._iteration = 0
        self._consecutive_errors = 0
        self._items_generated = 0
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

    def _load_prompt_template(self, mode: Mode) -> str:
        """Load prompt template for a mode.

        Args:
            mode: Mode configuration.

        Returns:
            Prompt template content.
        """
        template_path = self.project.path / mode.prompt_template
        if template_path.exists():
            return template_path.read_text()
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
        1. BEFORE_PROMPT position resources (coding standards, system guardrails)
        2. AFTER_DESIGN_DOC position resources (design docs, architecture)
        3. Template content
        4. BEFORE_TASK position resources (output guardrails)
        5. AFTER_TASK position resources (custom resources)
        6. Variable substitution (consumer loop variables)
        7. Batch items context (if batch mode)
        8. Run tracking marker

        Args:
            mode: Mode configuration.
            mode_name: Name of the mode.
            claimed_item: For consumer loops, the item being processed (first item in batch mode).
            batch_items: For batch mode, all items to process together.

        Returns:
            Complete prompt with all resources and tracking marker.
        """
        template = self._load_prompt_template(mode)

        # Load project resources
        resource_manager = ResourceManager(self.project.path, db=self.db)
        resource_set = resource_manager.load_for_loop(self.config, mode_name)

        # Build sections for each injection position
        before_prompt = resource_manager.build_prompt_section(
            resource_set, InjectionPosition.BEFORE_PROMPT
        )
        after_design_doc = resource_manager.build_prompt_section(
            resource_set, InjectionPosition.AFTER_DESIGN_DOC
        )
        before_task = resource_manager.build_prompt_section(
            resource_set, InjectionPosition.BEFORE_TASK
        )
        after_task = resource_manager.build_prompt_section(
            resource_set, InjectionPosition.AFTER_TASK
        )

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
            metadata = claimed_item.get("metadata")
            # json.dumps does NOT escape {{ }} so we must escape the result
            metadata_json = self._escape_template_vars(
                json.dumps(metadata) if metadata else "{}"
            )
            source = claimed_item.get("source_loop", "unknown")
            # source comes from our DB, not user input, but escape anyway for defense in depth
            source = self._escape_template_vars(source)

            # Substitution order: most specific first to avoid partial matches
            template = template.replace("{{input_item.metadata}}", metadata_json)
            template = template.replace("{{input_item.content}}", content)
            template = template.replace("{{input_item.title}}", title)
            template = template.replace("{{input_item}}", content)  # Alias
            template = template.replace("{{source_loop}}", source)

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
        """Check if this loop consumes items from another loop."""
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

        # 1. Get all items generated by this loop
        existing_items, _ = self.db.list_work_items(
            source_loop=self.config.name,
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

    def _get_source_loop_name(self) -> Optional[str]:
        """Get the name of the source loop for consumer loops."""
        if not self._is_consumer_loop():
            return None
        return self.config.item_types.input.source

    def _build_dependency_graph(self) -> None:
        """Build/rebuild the dependency graph from source items.

        Called on first claim or when needed for phase detection.
        """
        source_loop = self._get_source_loop_name()
        if not source_loop:
            return

        # Get ALL items from source loop (not just unclaimed)
        # Using limit of 10000 - warn if there are more items
        all_items, total_count = self.db.list_work_items(
            source_loop=source_loop,
            limit=10000,
        )

        if not all_items:
            return

        # Warn if items were truncated (dependency graph may be incomplete)
        if total_count > 10000:
            self._emit_event(
                ExecutorEvent.WARNING,
                f"Source loop has {total_count} items but only loaded 10000. "
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
        """Claim an item from the source loop for processing.

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

        source_loop = self._get_source_loop_name()
        if not source_loop:
            return None

        # Build dependency graph on first call
        if self._dependency_graph is None and self._respect_dependencies:
            self._build_dependency_graph()

        # Query for available items with optional category filter
        items, _ = self.db.list_work_items(
            source_loop=source_loop,
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
                        source_loop=source_loop,
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

        try:
            # Look for JSON array
            json_match = re.search(r'\[[\s\S]*?\]', output)
            if json_match:
                parsed = json.loads(json_match.group())
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict) and 'id' in item and 'content' in item:
                            # Extract known fields explicitly
                            known_fields = {
                                'id', 'content', 'title', 'priority', 'category',
                                'tags', 'dependencies', 'acceptance_criteria', 'complexity'
                            }
                            items.append({
                                'id': str(item['id']),
                                'content': str(item['content']),
                                'title': item.get('title'),
                                'priority': item.get('priority'),
                                'category': item.get('category'),
                                'tags': item.get('tags'),
                                'dependencies': item.get('dependencies'),
                                'metadata': {k: v for k, v in item.items()
                                             if k not in known_fields},
                            })
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

        # Determine source_loop and item_type from loop config
        source_loop = self.config.name
        item_type = "item"
        if self.config.item_types and self.config.item_types.output:
            item_type = self.config.item_types.output.singular

        for item in items:
            try:
                item_id = item.get('id', str(uuid.uuid4())[:8])
                self.db.create_work_item(
                    id=item_id,
                    content=item.get('content', ''),
                    title=item.get('title'),
                    priority=item.get('priority'),
                    status='completed',  # Items from loops are ready for consumption
                    category=item.get('category'),
                    metadata=item.get('metadata'),
                    dependencies=item.get('dependencies'),
                    source_loop=source_loop,
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
            exec_result = await self.adapter.execute(
                prompt=prompt,
                model=mode.model,
                tools=mode.tools if mode.tools else None,
                timeout=mode.timeout,
            )

            result.session_id = exec_result.session_id
            result.success = exec_result.success
            result.timeout = exec_result.timeout

            if exec_result.error_message:
                result.error_message = exec_result.error_message

            # Extract work items from output
            if exec_result.text_output:
                items = self.extract_work_items(exec_result.text_output)
                if items:
                    saved = self._save_work_items(items)
                    result.items_added = items
                    self._items_generated += saved

            # Register session
            if exec_result.session_id and self._run:
                self.db.create_session(
                    session_id=exec_result.session_id,
                    run_id=self._run.id,
                    iteration=self._iteration,
                    mode=mode_name,
                    status="completed" if exec_result.success else "error",
                )

            # Mark claimed item(s) as processed on success
            if result.success:
                items_to_mark = claimed_items if self._batch_mode else ([claimed_item] if claimed_item else [])
                for item in items_to_mark:
                    if not self._mark_item_processed(item["id"]):
                        # Failed to mark as processed - log warning but don't fail iteration
                        # Item may have been processed by another consumer or released
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

        # Create run record
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        self._run = Run(
            id=run_id,
            project_id=self.project.id,
            loop_name=self.config.name,
            status=RunStatus.ACTIVE,
            started_at=datetime.utcnow(),
        )
        self._start_time = self._run.started_at
        self._iteration = 0
        self._consecutive_errors = 0
        self._items_generated = 0

        # Save run to database (ProjectDatabase.create_run starts as active by default)
        self.db.create_run(
            id=run_id,
            loop_name=self.config.name,
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
                    self._emit_event(
                        ExecutorEvent.HEARTBEAT,
                        f"Consumer loop waiting for items from source",
                        mode=mode_name,
                    )
                    # Use longer back-off when no items available (5s or configured cooldown, whichever is longer)
                    wait_time = max(5.0, self.config.limits.cooldown_between_iterations)
                    if not self._stopping:
                        await asyncio.sleep(wait_time)
                    continue

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
                else:
                    self._consecutive_errors += 1
                    self._emit_event(
                        ExecutorEvent.ERROR,
                        result.error_message or "Iteration failed",
                        mode=mode_name,
                    )

                self._emit_event(
                    ExecutorEvent.ITERATION_COMPLETED,
                    f"Iteration {self._iteration} completed",
                    mode=mode_name,
                    success=result.success,
                    items_added=len(result.items_added),
                    duration=result.duration_seconds,
                )

                # Update run record
                self._run.iterations_completed = self._iteration
                self._run.items_generated = self._items_generated
                self.db.update_run(
                    self._run.id,
                    iterations_completed=self._iteration,
                    items_generated=self._items_generated,
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
            self._run.status = RunStatus.ACTIVE
            self.db.update_run(self._run.id, status="active")
            self._emit_event(ExecutorEvent.RUN_RESUMED, "Run resumed")
