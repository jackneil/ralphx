"""Loop preview engine for RalphX.

Generates previews of fully rendered prompts for loops, showing exactly
what Claude will see when the loop runs. Includes all resources, guardrails,
and sample item substitution.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ralphx.core.project_db import ProjectDatabase
from ralphx.core.resources import InjectionPosition, ResourceManager
from ralphx.models.loop import LoopConfig, Mode, ModeSelectionStrategy


@dataclass
class PromptSection:
    """A section of the rendered prompt with source attribution."""

    position: str  # before_prompt, after_design_doc, template, before_task, after_task
    source: str  # template, resource, guardrail, item
    source_name: Optional[str] = None
    content: str = ""
    start_line: int = 0
    end_line: int = 0


@dataclass
class ModePreview:
    """Preview of a single mode's rendered prompt."""

    mode_name: str
    model: str
    timeout: int
    tools: list[str]
    total_length: int
    token_estimate: int  # chars / 4 rough estimate
    sections: list[PromptSection]
    rendered_prompt: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class PreviewResponse:
    """Complete preview response for a loop."""

    loop_name: str
    loop_type: str
    mode_selection_strategy: str
    strategy_explanation: str
    sample_item: Optional[dict]
    modes: list[ModePreview]
    resources_used: list[str]
    guardrails_used: list[str]
    template_variables: dict[str, str]
    warnings: list[str] = field(default_factory=list)


class PromptPreviewEngine:
    """Generates previews of fully rendered prompts.

    Shows exactly what Claude will see when a loop runs, including:
    - Base prompt template
    - Injected resources (by type and position)
    - Injected guardrails
    - Sample item substitution (for consumer loops)
    - Token count estimates
    - Section breakdown for debugging

    Usage:
        engine = PromptPreviewEngine(project, loop_config, db)
        preview = engine.generate_preview(
            mode_name="turbo",
            sample_item={"content": "..."},
            include_annotations=True,
        )
    """

    def __init__(
        self,
        project_path: str | Path,
        loop_config: LoopConfig,
        db: ProjectDatabase,
    ):
        """Initialize the preview engine.

        Args:
            project_path: Path to the project directory.
            loop_config: Loop configuration to preview.
            db: Project database instance.
        """
        self.project_path = Path(project_path)
        self.config = loop_config
        self.db = db
        self.resource_manager = ResourceManager(project_path, db=db)

    def generate_preview(
        self,
        mode_name: Optional[str] = None,
        sample_item: Optional[dict] = None,
        use_first_pending: bool = True,
        include_annotations: bool = True,
    ) -> PreviewResponse:
        """Generate a preview of the loop's rendered prompts.

        Args:
            mode_name: Specific mode to preview (None = all modes).
            sample_item: Sample item for consumer loop substitution.
            use_first_pending: If no sample_item, use first pending item.
            include_annotations: Add section markers to rendered prompt.

        Returns:
            PreviewResponse with all mode previews.
        """
        # Determine which modes to preview
        if mode_name:
            modes_to_preview = {mode_name: self.config.modes[mode_name]}
        else:
            modes_to_preview = self.config.modes

        # Get sample item for consumer loops
        actual_sample_item = sample_item
        if not actual_sample_item and use_first_pending and self._is_consumer_loop():
            actual_sample_item = self._get_sample_item()

        # Load resources once
        resource_set = self.resource_manager.load_for_loop(self.config, mode_name)
        resources_used = resource_set.all_names()

        # Generate mode previews
        mode_previews = []
        all_warnings = []

        for name, mode in modes_to_preview.items():
            preview = self._render_mode(
                mode_name=name,
                mode=mode,
                sample_item=actual_sample_item,
                include_annotations=include_annotations,
            )
            mode_previews.append(preview)
            all_warnings.extend(preview.warnings)

        # Build response
        return PreviewResponse(
            loop_name=self.config.name,
            loop_type=self.config.type.value,
            mode_selection_strategy=self.config.mode_selection.strategy.value,
            strategy_explanation=self._explain_strategy(),
            sample_item=actual_sample_item,
            modes=mode_previews,
            resources_used=resources_used,
            guardrails_used=[],  # TODO: Add guardrails when implemented
            template_variables=self._get_template_variables(actual_sample_item),
            warnings=all_warnings,
        )

    def _render_mode(
        self,
        mode_name: str,
        mode: Mode,
        sample_item: Optional[dict],
        include_annotations: bool,
    ) -> ModePreview:
        """Render a single mode's prompt with section tracking.

        Args:
            mode_name: Name of the mode.
            mode: Mode configuration.
            sample_item: Sample item for substitution.
            include_annotations: Add section markers.

        Returns:
            ModePreview with sections and rendered prompt.
        """
        sections: list[PromptSection] = []
        warnings: list[str] = []
        current_line = 1

        # Load resources
        resource_set = self.resource_manager.load_for_loop(self.config, mode_name)

        # 1. BEFORE_PROMPT resources
        before_prompt = self.resource_manager.build_prompt_section(
            resource_set, InjectionPosition.BEFORE_PROMPT, include_headers=True
        )
        if before_prompt:
            lines = before_prompt.count("\n") + 1
            sections.append(PromptSection(
                position="before_prompt",
                source="resource",
                source_name="coding_standards",
                content=before_prompt,
                start_line=current_line,
                end_line=current_line + lines - 1,
            ))
            current_line += lines + 1  # +1 for separator

        # 2. AFTER_DESIGN_DOC resources
        after_design_doc = self.resource_manager.build_prompt_section(
            resource_set, InjectionPosition.AFTER_DESIGN_DOC, include_headers=True
        )
        if after_design_doc:
            lines = after_design_doc.count("\n") + 1
            sections.append(PromptSection(
                position="after_design_doc",
                source="resource",
                source_name="design_doc/architecture",
                content=after_design_doc,
                start_line=current_line,
                end_line=current_line + lines - 1,
            ))
            current_line += lines + 1

        # 3. Template content
        template = self._load_prompt_template(mode)
        if not template or template.startswith("Prompt template not found"):
            warnings.append(f"Template not found: {mode.prompt_template}")
            template = f"[MISSING TEMPLATE: {mode.prompt_template}]"

        template_lines = template.count("\n") + 1
        sections.append(PromptSection(
            position="template",
            source="template",
            source_name=mode.prompt_template,
            content=template,
            start_line=current_line,
            end_line=current_line + template_lines - 1,
        ))
        current_line += template_lines + 1

        # 4. BEFORE_TASK resources
        before_task = self.resource_manager.build_prompt_section(
            resource_set, InjectionPosition.BEFORE_TASK, include_headers=True
        )
        if before_task:
            lines = before_task.count("\n") + 1
            sections.append(PromptSection(
                position="before_task",
                source="resource",
                source_name="output_guardrails",
                content=before_task,
                start_line=current_line,
                end_line=current_line + lines - 1,
            ))
            current_line += lines + 1

        # 5. AFTER_TASK resources
        after_task = self.resource_manager.build_prompt_section(
            resource_set, InjectionPosition.AFTER_TASK, include_headers=True
        )
        if after_task:
            lines = after_task.count("\n") + 1
            sections.append(PromptSection(
                position="after_task",
                source="resource",
                source_name="custom",
                content=after_task,
                start_line=current_line,
                end_line=current_line + lines - 1,
            ))

        # Build the final rendered prompt
        rendered = self._assemble_prompt(sections, sample_item, include_annotations)

        # Token estimate (rough: chars / 4)
        token_estimate = len(rendered) // 4

        return ModePreview(
            mode_name=mode_name,
            model=mode.model,
            timeout=mode.timeout,
            tools=mode.tools or [],
            total_length=len(rendered),
            token_estimate=token_estimate,
            sections=sections,
            rendered_prompt=rendered,
            warnings=warnings,
        )

    def _assemble_prompt(
        self,
        sections: list[PromptSection],
        sample_item: Optional[dict],
        include_annotations: bool,
    ) -> str:
        """Assemble sections into final prompt with optional annotations.

        Args:
            sections: List of prompt sections.
            sample_item: Sample item for variable substitution.
            include_annotations: Add section markers.

        Returns:
            Assembled prompt string.
        """
        parts = []

        for section in sections:
            content = section.content

            if include_annotations:
                # Add section marker
                marker = f"<!-- [{section.position.upper()}] Source: {section.source}"
                if section.source_name:
                    marker += f" ({section.source_name})"
                marker += f" Lines: {section.start_line}-{section.end_line} -->"

                parts.append(marker)
                parts.append(content)
                parts.append(f"<!-- [/{section.position.upper()}] -->")
            else:
                parts.append(content)

        rendered = "\n\n".join(parts)

        # Substitute consumer loop variables
        if sample_item:
            rendered = self._substitute_variables(rendered, sample_item)

        return rendered

    def _substitute_variables(self, template: str, item: dict) -> str:
        """Substitute template variables with item values.

        Args:
            template: Template string with {{var}} placeholders.
            item: Item dict with values.

        Returns:
            Template with variables substituted.
        """
        import json

        content = item.get("content") or "[No content]"
        title = item.get("title") or ""
        metadata = item.get("metadata")
        metadata_json = json.dumps(metadata) if metadata else "{}"
        workflow_id = item.get("workflow_id", "unknown")

        # Substitution order: most specific first
        result = template.replace("{{input_item.metadata}}", metadata_json)
        result = result.replace("{{input_item.content}}", content)
        result = result.replace("{{input_item.title}}", title)
        result = result.replace("{{input_item}}", content)
        result = result.replace("{{workflow_id}}", workflow_id)

        return result

    def _load_prompt_template(self, mode: Mode) -> str:
        """Load prompt template for a mode.

        Args:
            mode: Mode configuration.

        Returns:
            Template content or error message.
        """
        template_path = self.project_path / mode.prompt_template
        if template_path.exists():
            return template_path.read_text()
        return f"Prompt template not found: {mode.prompt_template}"

    def _is_consumer_loop(self) -> bool:
        """Check if this is a consumer loop."""
        if not self.config.item_types:
            return False
        if not self.config.item_types.input:
            return False
        return bool(self.config.item_types.input.source)

    def _get_sample_item(self) -> Optional[dict]:
        """Get a sample item for preview (for consumer loops).

        Returns:
            Sample item dict or None.
        """
        if not self._is_consumer_loop():
            return None

        # Get first completed item
        items, _ = self.db.list_work_items(
            status="completed",
            limit=1,
        )

        if items:
            return items[0]

        # Fallback: get any pending item
        items, _ = self.db.list_work_items(
            status="pending",
            limit=1,
        )

        if items:
            return items[0]

        # Return a placeholder
        return {
            "id": "sample-001",
            "content": "[Sample item content - no items available]",
            "source": source_name,
        }

    def _explain_strategy(self) -> str:
        """Generate human-readable explanation of mode selection strategy.

        Returns:
            Explanation string.
        """
        strategy = self.config.mode_selection.strategy

        if strategy == ModeSelectionStrategy.FIXED:
            return (
                f"Fixed: Always uses '{self.config.mode_selection.fixed_mode}' mode"
            )

        elif strategy == ModeSelectionStrategy.RANDOM:
            modes = list(self.config.modes.keys())
            return f"Random: Randomly selects from modes: {', '.join(modes)}"

        elif strategy == ModeSelectionStrategy.WEIGHTED_RANDOM:
            weights = self.config.mode_selection.weights
            weight_str = ", ".join(f"{k}: {v}%" for k, v in weights.items())
            return f"Weighted Random: {weight_str}"

        elif strategy == ModeSelectionStrategy.PHASE_AWARE:
            phase1_modes = [
                name for name, mode in self.config.modes.items()
                if mode.phase == "phase_1"
            ]
            return (
                f"Phase Aware: First runs Phase 1 modes ({', '.join(phase1_modes)}), "
                f"then switches to '{self.config.mode_selection.fixed_mode}'"
            )

        elif strategy == ModeSelectionStrategy.ADAPTIVE:
            return "Adaptive: Dynamically adjusts mode selection based on performance"

        return f"Unknown strategy: {strategy.value}"

    def _get_template_variables(self, sample_item: Optional[dict]) -> dict[str, str]:
        """Get available template variables and their values.

        Args:
            sample_item: Sample item for consumer loop variables.

        Returns:
            Dict of variable name to value/description.
        """
        variables = {}

        if self._is_consumer_loop():
            if sample_item:
                variables["{{input_item}}"] = sample_item.get("content", "")[:50] + "..."
                variables["{{input_item.content}}"] = sample_item.get("content", "")[:50] + "..."
                variables["{{input_item.title}}"] = sample_item.get("title", "")
                variables["{{input_item.metadata}}"] = "{...}"
                variables["{{workflow_id}}"] = sample_item.get("workflow_id", "")
            else:
                variables["{{input_item}}"] = "[Claimed item content]"
                variables["{{input_item.content}}"] = "[Claimed item content]"
                variables["{{input_item.title}}"] = "[Claimed item title]"
                variables["{{input_item.metadata}}"] = "[Claimed item metadata as JSON]"
                variables["{{workflow_id}}"] = "[Workflow ID]"

        # Design doc variable (if configured)
        if self.config.context and self.config.context.design_doc:
            variables["{{design_doc}}"] = f"[Contents of {self.config.context.design_doc}]"

        # Task variable (common in templates)
        variables["{{task}}"] = "[Task instructions marker]"

        return variables

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Uses rough approximation of chars/4 for English text.

        Args:
            text: Text to estimate.

        Returns:
            Estimated token count.
        """
        return len(text) // 4
