"""Loop control API routes."""

import asyncio
import re
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ralphx.core.executor import ExecutorEvent, ExecutorEventData, LoopExecutor
from ralphx.core.import_manager import ImportManager
from ralphx.core.input_templates import get_required_tags, validate_loop_inputs
from ralphx.core.loop import LoopLoader
from ralphx.core.project import ProjectManager
from ralphx.models.loop import LoopConfig, LoopType, ModeSelectionStrategy, ItemTypes
from ralphx.models.run import Run, RunStatus

router = APIRouter()


def detect_source_cycle(
    loop_name: str,
    source: str,
    loader: "LoopLoader",
) -> bool:
    """Detect cycles in loop source dependencies using DFS.

    Returns True if adding this source reference would create a cycle.
    """
    visited = set()

    def dfs(current: str) -> bool:
        if current in visited:
            return True  # Cycle detected
        if current == loop_name:
            return True  # Would create cycle back to original loop
        visited.add(current)

        config = loader.get_loop(current)
        if not config:
            return False  # Source doesn't exist (will be caught by validation)

        if config.item_types and config.item_types.input:
            next_source = config.item_types.input.source
            if next_source:
                return dfs(next_source)
        return False

    return dfs(source)

# Store for running loops
_running_loops: dict[str, LoopExecutor] = {}

# Security: Validate loop names to prevent path traversal
LOOP_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')


# Response models
class ModeResponse(BaseModel):
    """Response model for a mode."""

    name: str
    model: str
    timeout: int
    tools: list[str] = Field(default_factory=list)
    template: str


class ItemTypeResponse(BaseModel):
    """Response model for an item type configuration."""

    singular: str
    plural: str
    description: str = ""
    source: Optional[str] = None


class ItemTypesResponse(BaseModel):
    """Response model for loop item types."""

    input: Optional[ItemTypeResponse] = None
    output: ItemTypeResponse


class LoopResponse(BaseModel):
    """Response model for a loop configuration."""

    name: str
    display_name: str
    type: str
    strategy: str
    modes: list[ModeResponse]
    max_iterations: int
    max_runtime_seconds: int
    item_types: Optional[ItemTypesResponse] = None

    @classmethod
    def from_config(cls, config: LoopConfig) -> "LoopResponse":
        """Create from LoopConfig."""
        modes = [
            ModeResponse(
                name=name,
                model=mode.model,
                timeout=mode.timeout,
                tools=mode.tools or [],
                template=mode.prompt_template,
            )
            for name, mode in config.modes.items()
        ]

        # Build item_types response
        item_types_resp = None
        if config.item_types:
            output_resp = ItemTypeResponse(
                singular=config.item_types.output.singular,
                plural=config.item_types.output.plural,
                description=config.item_types.output.description,
                source=config.item_types.output.source,
            )
            input_resp = None
            if config.item_types.input:
                input_resp = ItemTypeResponse(
                    singular=config.item_types.input.singular,
                    plural=config.item_types.input.plural,
                    description=config.item_types.input.description,
                    source=config.item_types.input.source,
                )
            item_types_resp = ItemTypesResponse(input=input_resp, output=output_resp)

        return cls(
            name=config.name,
            display_name=config.display_name,
            type=config.type.value,
            strategy=config.mode_selection.strategy.value,
            modes=modes,
            max_iterations=config.limits.max_iterations,
            max_runtime_seconds=config.limits.max_runtime_seconds,
            item_types=item_types_resp,
        )


class LoopStatus(BaseModel):
    """Current status of a loop."""

    loop_name: str
    is_running: bool
    current_run_id: Optional[int] = None
    current_iteration: int = 0
    current_mode: Optional[str] = None
    items_generated: int = 0


class RunResponse(BaseModel):
    """Response model for a run."""

    id: int
    loop_name: str
    status: str
    iterations_completed: int
    items_generated: int
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None

    @classmethod
    def from_run(cls, run: Run) -> "RunResponse":
        """Create from Run model."""
        return cls(
            id=run.id,
            loop_name=run.loop_name,
            status=run.status.value,
            iterations_completed=run.iterations_completed,
            items_generated=run.items_generated,
            started_at=run.started_at.isoformat() if run.started_at else None,
            completed_at=run.completed_at.isoformat() if run.completed_at else None,
            duration_seconds=run.duration_seconds,
        )


# Pattern for validating category names (alphanumeric, underscore, hyphen, max 50 chars)
CATEGORY_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,50}$')


class StartRequest(BaseModel):
    """Request model for starting a loop."""

    iterations: Optional[int] = Field(None, description="Override max iterations")
    dry_run: bool = Field(False, description="Run without executing LLM calls")
    force: bool = Field(False, description="Skip input validation and start anyway")

    # Phase and category filtering (for consumer/implementation loops)
    phase: Optional[int] = Field(None, ge=1, description="Filter items by phase number (must be >= 1)")
    category: Optional[str] = Field(None, max_length=50, description="Filter items by category")
    respect_dependencies: bool = Field(True, description="Process items in dependency order")
    batch_mode: bool = Field(False, description="Implement multiple items together as a batch")
    batch_size: int = Field(10, ge=1, le=50, description="Max items per batch (when batch_mode=True)")

    @field_validator('category')
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        """Validate category format to prevent injection attacks."""
        if v is None:
            return v
        if not CATEGORY_PATTERN.match(v):
            raise ValueError(
                "Category must contain only letters, numbers, underscores, and hyphens (max 50 chars)"
            )
        return v.lower()  # Normalize to lowercase


def get_managers(slug: str) -> tuple[ProjectManager, Any, Any]:
    """Get project manager, project, and project database.

    Returns:
        Tuple of (manager, project, project_db).
    """
    manager = ProjectManager()
    project = manager.get_project(slug)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )
    project_db = manager.get_project_db(project.path)
    return manager, project, project_db


@router.get("/{slug}/loops", response_model=list[LoopResponse])
async def list_loops(slug: str):
    """List all loops for a project."""
    manager, project, project_db = get_managers(slug)

    loader = LoopLoader(db=project_db)
    loops = loader.list_loops()

    return [LoopResponse.from_config(loop) for loop in loops]


@router.get("/{slug}/loops/{loop_name}", response_model=LoopResponse)
async def get_loop(slug: str, loop_name: str):
    """Get details for a specific loop."""
    manager, project, project_db = get_managers(slug)

    loader = LoopLoader(db=project_db)
    config = loader.get_loop(loop_name)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop not found: {loop_name}",
        )

    return LoopResponse.from_config(config)


@router.get("/{slug}/loops/{loop_name}/status", response_model=LoopStatus)
async def get_loop_status(slug: str, loop_name: str):
    """Get current status of a loop."""
    manager, project, project_db = get_managers(slug)

    # Check if running
    key = f"{slug}:{loop_name}"
    executor = _running_loops.get(key)

    if executor:
        return LoopStatus(
            loop_name=loop_name,
            is_running=True,
            current_run_id=executor._current_run.id if executor._current_run else None,
            current_iteration=executor._iteration,
            current_mode=executor._current_mode,
            items_generated=executor._items_generated,
        )

    return LoopStatus(
        loop_name=loop_name,
        is_running=False,
    )


@router.post("/{slug}/loops/{loop_name}/start", response_model=RunResponse)
async def start_loop(
    slug: str,
    loop_name: str,
    request: StartRequest,
    background_tasks: BackgroundTasks,
):
    """Start a loop execution."""
    manager, project, project_db = get_managers(slug)

    # Check if already running
    key = f"{slug}:{loop_name}"
    if key in _running_loops:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Loop {loop_name} is already running",
        )

    # Get loop config
    loader = LoopLoader(db=project_db)
    config = loader.get_loop(loop_name)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop not found: {loop_name}",
        )

    # Validate required inputs (unless force=True)
    if not request.force:
        # Determine loop type for validation
        loop_type = "planning" if config.type == LoopType.GENERATOR else "implementation"

        # Get current inputs
        import_manager = ImportManager(project.path, project_db)
        inputs = import_manager.list_inputs(loop_name)

        # Validate inputs
        validation = validate_loop_inputs(inputs, loop_type)

        if not validation["valid"]:
            missing_tags = validation["missing_tags"]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "MISSING_REQUIRED_INPUTS",
                    "message": f"Missing required inputs: {', '.join(missing_tags)}",
                    "missing_tags": missing_tags,
                    "recommendation": "Add required inputs or use force=true to skip validation",
                },
            )

    # Create executor with phase/category filtering
    executor = LoopExecutor(
        project=project,
        loop_config=config,
        db=project_db,
        dry_run=request.dry_run,
        phase=request.phase,
        category=request.category,
        respect_dependencies=request.respect_dependencies,
        batch_mode=request.batch_mode,
        batch_size=request.batch_size,
    )

    _running_loops[key] = executor

    # Run in background
    async def run_and_cleanup():
        try:
            await executor.run(max_iterations=request.iterations)
        finally:
            _running_loops.pop(key, None)

    background_tasks.add_task(asyncio.create_task, run_and_cleanup())

    # Return initial run info
    # Wait briefly for run to be created
    await asyncio.sleep(0.1)

    if executor._current_run:
        return RunResponse.from_run(executor._current_run)

    # Return placeholder
    return RunResponse(
        id=0,
        loop_name=loop_name,
        status="starting",
        iterations_completed=0,
        items_generated=0,
    )


@router.post("/{slug}/loops/{loop_name}/stop")
async def stop_loop(slug: str, loop_name: str):
    """Stop a running loop."""
    # Validate project exists first
    get_managers(slug)

    key = f"{slug}:{loop_name}"
    executor = _running_loops.get(key)

    if not executor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop {loop_name} is not running",
        )

    executor.stop()

    return {"message": f"Stop signal sent to {loop_name}"}


@router.post("/{slug}/loops/{loop_name}/pause")
async def pause_loop(slug: str, loop_name: str):
    """Pause a running loop."""
    # Validate project exists first
    get_managers(slug)

    key = f"{slug}:{loop_name}"
    executor = _running_loops.get(key)

    if not executor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop {loop_name} is not running",
        )

    executor.pause()

    return {"message": f"Pause signal sent to {loop_name}"}


@router.post("/{slug}/loops/{loop_name}/resume")
async def resume_loop(slug: str, loop_name: str):
    """Resume a paused loop."""
    # Validate project exists first
    get_managers(slug)

    key = f"{slug}:{loop_name}"
    executor = _running_loops.get(key)

    if not executor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop {loop_name} is not running",
        )

    executor.resume()

    return {"message": f"Resume signal sent to {loop_name}"}


@router.delete("/{slug}/loops/{loop_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_loop(slug: str, loop_name: str):
    """Delete a loop configuration.

    Checks for dependent loops (loops that source from this one) before deletion.
    """
    from pathlib import Path

    # Security: Validate loop name to prevent path traversal
    if not LOOP_NAME_PATTERN.match(loop_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid loop name",
        )

    # Check if loop is running
    key = f"{slug}:{loop_name}"
    if key in _running_loops:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete loop while it is running",
        )

    manager, project, project_db = get_managers(slug)
    loader = LoopLoader(db=project_db)

    # Check if loop exists
    config = loader.get_loop(loop_name)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop not found: {loop_name}",
        )

    # Check for dependent loops (loops that source from this one)
    all_loops = loader.list_loops()
    dependents = []

    for loop in all_loops:
        if loop.name != loop_name and loop.item_types and loop.item_types.input:
            if loop.item_types.input.source == loop_name:
                dependents.append(loop.name)

    if dependents:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete loop '{loop_name}': referenced by {dependents}. "
                   f"Remove source references first.",
        )

    # Release any claims this loop is holding (prevents orphaned locked items)
    project_db.release_claims_by_loop(loop_name)

    # Delete the config file
    loops_dir = Path(project.path) / ".ralphx" / "loops"
    config_path = loops_dir / f"{loop_name}.yaml"

    if not config_path.exists():
        config_path = loops_dir / f"{loop_name}.yml"

    if config_path.exists():
        config_path.unlink()

    # Remove from database
    project_db.delete_loop(loop_name)

    return None


@router.post("/{slug}/loops/sync")
async def sync_loops(slug: str):
    """Sync loops from project files to database."""
    manager, project, project_db = get_managers(slug)

    loader = LoopLoader(db=project_db)
    result = loader.sync_loops(project)

    return result


@router.get("/{slug}/loops/{loop_name}/config")
async def get_loop_config(slug: str, loop_name: str):
    """Get the raw YAML configuration for a loop."""
    from pathlib import Path

    # Security: Validate loop name to prevent path traversal
    if not LOOP_NAME_PATTERN.match(loop_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid loop name",
        )

    manager, project, project_db = get_managers(slug)

    # Find loop config file
    loops_dir = Path(project.path) / ".ralphx" / "loops"
    config_path = loops_dir / f"{loop_name}.yaml"

    if not config_path.exists():
        config_path = loops_dir / f"{loop_name}.yml"

    if not config_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop config file not found: {loop_name}",
        )

    return {"content": config_path.read_text(), "path": str(config_path)}


class UpdateConfigRequest(BaseModel):
    """Request model for updating loop config."""

    content: str = Field(..., description="YAML content")


class CreateLoopRequest(BaseModel):
    """Request model for creating a new loop."""

    name: str = Field(..., description="Loop name (slug-style, e.g., 'research-loop')")
    content: str = Field(..., description="YAML content for the loop configuration")


@router.post("/{slug}/loops")
async def create_loop(slug: str, request: CreateLoopRequest):
    """Create a new loop configuration.

    Creates the YAML file in .ralphx/loops/ and syncs to database.
    """
    import yaml
    from pathlib import Path
    from pydantic import ValidationError

    # Security: Validate loop name to prevent path traversal
    if not LOOP_NAME_PATTERN.match(request.name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid loop name. Use only letters, numbers, underscores, and hyphens.",
        )

    manager, project, project_db = get_managers(slug)

    # Check if loop already exists
    loops_dir = Path(project.path) / ".ralphx" / "loops"
    config_path = loops_dir / f"{request.name}.yaml"

    if config_path.exists() or (loops_dir / f"{request.name}.yml").exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Loop '{request.name}' already exists",
        )

    # Validate YAML syntax
    try:
        yaml_data = yaml.safe_load(request.content)
    except yaml.YAMLError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid YAML: {e}",
        )

    # Validate against LoopConfig schema
    try:
        config = LoopConfig.model_validate(yaml_data)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid loop configuration: {e}",
        )

    # Validate source loop reference (if present)
    loader = LoopLoader(db=project_db)
    if config.item_types and config.item_types.input and config.item_types.input.source:
        source = config.item_types.input.source

        # Check source loop exists in same project
        source_config = loader.get_loop(source)
        if not source_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Source loop '{source}' not found in this project",
            )

        # Check for circular dependencies
        if detect_source_cycle(request.name, source, loader):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Circular dependency detected: adding source '{source}' would create a cycle",
            )

    # Create the loops directory if it doesn't exist
    loops_dir.mkdir(parents=True, exist_ok=True)

    # Write the config file
    config_path.write_text(request.content)

    # Sync to reload into database
    loader.sync_loops(project)

    return {
        "message": f"Loop '{request.name}' created successfully",
        "path": str(config_path),
        "loop": LoopResponse.from_config(config).model_dump(),
    }


# ============================================================================
# Simple Loop Creation (Simplified Wizard)
# ============================================================================


class DesignDocInput(BaseModel):
    """Design document input."""

    content: str = Field(..., description="File content")
    filename: str = Field(..., description="Filename")


class StoriesSourceInput(BaseModel):
    """Stories source configuration."""

    type: str = Field(..., description="'loop' or 'content'")
    loop_name: Optional[str] = Field(None, description="Source loop name if type='loop'")
    content: Optional[str] = Field(None, description="JSONL content if type='content'")
    filename: Optional[str] = Field(None, description="Filename if type='content'")


class CreateSimpleLoopRequest(BaseModel):
    """Request model for creating a simple loop via wizard."""

    type: str = Field(..., description="'planning' or 'implementation'")

    # User-facing name and description (ID is auto-generated)
    display_name: Optional[str] = Field(
        None,
        description="User-facing name (defaults to 'Planning' or 'Implementation')",
    )
    description: Optional[str] = Field(
        None,
        description="Optional description of what this loop is for",
    )

    # Planning fields
    design_doc: Optional[DesignDocInput] = Field(None, description="Design document")
    use_default_instructions: bool = Field(True, description="Apply default story instructions")
    use_default_guardrails: bool = Field(True, description="Apply default guardrails")

    # Implementation fields
    stories_source: Optional[StoriesSourceInput] = Field(None, description="Stories source")
    design_context: Optional[DesignDocInput] = Field(None, description="Design context for reference")
    use_code_guardrails: bool = Field(True, description="Apply default code guardrails")


@router.post("/{slug}/loops/simple")
async def create_simple_loop(slug: str, request: CreateSimpleLoopRequest):
    """Create a loop using the simplified wizard flow.

    This endpoint handles the simple loop creation with sensible defaults.
    The loop ID is auto-generated as {type}-{YYYYMMDD}_{n}.
    Users only need to provide:
    - Planning: design doc + optional templates
    - Implementation: stories source + design context + optional templates
    """
    from pathlib import Path

    from ralphx.core.loop_templates import (
        generate_loop_id,
        generate_simple_planning_config,
        generate_simple_implementation_config,
    )
    from ralphx.core.input_templates import get_input_template

    # Validate loop type
    if request.type not in ("planning", "implementation"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Loop type must be 'planning' or 'implementation'",
        )

    manager, project, project_db = get_managers(slug)
    loader = LoopLoader(db=project_db)

    # Get existing loop names for ID generation
    existing_loops = loader.list_loops()
    existing_names = [loop.name for loop in existing_loops]

    # Auto-generate unique loop ID
    loop_id = generate_loop_id(request.type, existing_names)

    # Set display_name with sensible default
    display_name = request.display_name
    if not display_name:
        display_name = "Planning" if request.type == "planning" else "Implementation"

    description = request.description or ""

    # Generate config YAML based on type
    loops_dir = Path(project.path) / ".ralphx" / "loops"

    if request.type == "planning":
        config_yaml = generate_simple_planning_config(
            name=loop_id,
            display_name=display_name,
            description=description,
        )
    else:
        source_loop = None
        # Validate stories_source.type if provided
        if request.stories_source and request.stories_source.type not in ("loop", "content"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="stories_source.type must be 'loop' or 'content'.",
            )
        if request.stories_source and request.stories_source.type == "loop":
            source_loop = request.stories_source.loop_name
            # Validate: if type is "loop", loop_name must be provided
            if not source_loop:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Source loop name is required when stories_source.type is 'loop'.",
                )
            # Security: Validate source loop name to prevent YAML injection
            if not LOOP_NAME_PATTERN.match(source_loop):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid source loop name. Use only letters, numbers, underscores, and hyphens.",
                )
            # Validate: source loop must exist in project
            source_config = loader.get_loop(source_loop)
            if not source_config:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Source loop '{source_loop}' not found in this project.",
                )
        config_yaml = generate_simple_implementation_config(
            name=loop_id,
            source_loop=source_loop,
            display_name=display_name,
            description=description,
        )

    # Create loops directory and write config
    loops_dir.mkdir(parents=True, exist_ok=True)
    config_path = loops_dir / f"{loop_id}.yaml"
    config_path.write_text(config_yaml)

    # Create prompts directory with default prompt
    prompts_dir = Path(project.path) / ".ralphx" / "loops" / loop_id / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    if request.type == "planning":
        prompt_file = prompts_dir / "planning.md"
        prompt_file.write_text("# Planning Prompt\n\nGenerate user stories from the design documents in inputs/.\n")
    else:
        prompt_file = prompts_dir / "implement.md"
        prompt_file.write_text("# Implementation Prompt\n\nImplement the provided story according to the design context.\n")

    # Sync to load into database
    loader.sync_loops(project)

    # Create inputs from provided content
    import_manager = ImportManager(project.path, project_db)
    inputs_created = []

    # Add design doc (for planning) or design context (for implementation)
    doc_input = request.design_doc if request.type == "planning" else request.design_context
    if doc_input:
        result = import_manager.import_paste(
            content=doc_input.content,
            loop_name=loop_id,
            filename=doc_input.filename,
            tag="master_design",
        )
        if result.success:
            inputs_created.append(doc_input.filename)

    # Apply default templates
    if request.type == "planning":
        if request.use_default_instructions:
            template = get_input_template("planning/story-instructions")
            if template:
                result = import_manager.import_paste(
                    content=template["content"],
                    loop_name=loop_id,
                    filename=template["filename"],
                    tag=template["tag"],
                    applied_from_template="planning/story-instructions",
                )
                if result.success:
                    inputs_created.append(template["filename"])

        if request.use_default_guardrails:
            template = get_input_template("planning/story-guardrails")
            if template:
                result = import_manager.import_paste(
                    content=template["content"],
                    loop_name=loop_id,
                    filename=template["filename"],
                    tag=template["tag"],
                    applied_from_template="planning/story-guardrails",
                )
                if result.success:
                    inputs_created.append(template["filename"])
    else:
        # Implementation loop
        if request.use_code_guardrails:
            template = get_input_template("implementation/code-guardrails")
            if template:
                result = import_manager.import_paste(
                    content=template["content"],
                    loop_name=loop_id,
                    filename=template["filename"],
                    tag=template["tag"],
                    applied_from_template="implementation/code-guardrails",
                )
                if result.success:
                    inputs_created.append(template["filename"])

        # Handle stories source if content provided
        if request.stories_source and request.stories_source.type == "content":
            if request.stories_source.content:
                filename = request.stories_source.filename or "stories.jsonl"
                result = import_manager.import_paste(
                    content=request.stories_source.content,
                    loop_name=loop_id,
                    filename=filename,
                    tag="stories",
                )
                if result.success:
                    inputs_created.append(filename)

    return {
        "loop_id": loop_id,
        "display_name": display_name,
        "loop_dir": str(loops_dir / f"{loop_id}.yaml"),
        "inputs_created": inputs_created,
        "message": f"Created {request.type} loop '{display_name}' (ID: {loop_id}) with {len(inputs_created)} inputs",
    }


@router.put("/{slug}/loops/{loop_name}/config")
async def update_loop_config(slug: str, loop_name: str, request: UpdateConfigRequest):
    """Update the YAML configuration for a loop."""
    import yaml
    from pathlib import Path
    from pydantic import ValidationError

    # Security: Validate loop name to prevent path traversal
    if not LOOP_NAME_PATTERN.match(loop_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid loop name",
        )

    # Check if loop is running (cannot edit config while running)
    key = f"{slug}:{loop_name}"
    if key in _running_loops:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot edit config while loop is running",
        )

    manager, project, project_db = get_managers(slug)

    # Find loop config file
    loops_dir = Path(project.path) / ".ralphx" / "loops"
    config_path = loops_dir / f"{loop_name}.yaml"

    if not config_path.exists():
        config_path = loops_dir / f"{loop_name}.yml"

    if not config_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop config file not found: {loop_name}",
        )

    # Validate YAML syntax
    try:
        yaml_data = yaml.safe_load(request.content)
    except yaml.YAMLError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid YAML: {e}",
        )

    # Validate against LoopConfig schema
    try:
        config = LoopConfig.model_validate(yaml_data)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid loop configuration: {e}",
        )

    # Validate source loop reference (if present)
    loader = LoopLoader(db=project_db)
    if config.item_types and config.item_types.input and config.item_types.input.source:
        source = config.item_types.input.source

        # Check source loop exists in same project
        source_config = loader.get_loop(source)
        if not source_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Source loop '{source}' not found in this project",
            )

        # Check for circular dependencies
        if detect_source_cycle(loop_name, source, loader):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Circular dependency detected: adding source '{source}' would create a cycle",
            )

    # Write the config
    config_path.write_text(request.content)

    # Sync to reload into database
    loader.sync_loops(project)

    return {"message": "Config updated and synced", "path": str(config_path)}


# ========== Preview Endpoint ==========


class PreviewRequest(BaseModel):
    """Request model for previewing a loop prompt."""

    mode: Optional[str] = Field(None, description="Specific mode to preview (None = all modes)")
    sample_item_id: Optional[str] = Field(None, description="Item ID to use as sample (for consumer loops)")
    use_first_pending: bool = Field(True, description="If no sample_item, use first pending item")
    include_annotations: bool = Field(True, description="Include section markers in rendered prompt")


class PromptSectionResponse(BaseModel):
    """Response model for a prompt section."""

    position: str
    source: str
    source_name: Optional[str] = None
    content: str
    start_line: int
    end_line: int


class ModePreviewResponse(BaseModel):
    """Response model for a mode preview."""

    mode_name: str
    model: str
    timeout: int
    tools: list[str]
    total_length: int
    token_estimate: int
    sections: list[PromptSectionResponse]
    rendered_prompt: str
    warnings: list[str]


class PreviewResponse(BaseModel):
    """Response model for a loop preview."""

    loop_name: str
    loop_type: str
    mode_selection_strategy: str
    strategy_explanation: str
    sample_item: Optional[dict] = None
    modes: list[ModePreviewResponse]
    resources_used: list[str]
    guardrails_used: list[str]
    template_variables: dict[str, str]
    warnings: list[str]


@router.post("/{slug}/loops/{loop_name}/preview", response_model=PreviewResponse)
async def preview_loop_prompt(slug: str, loop_name: str, request: PreviewRequest):
    """Preview fully rendered prompt for a loop.

    Shows exactly what Claude will see when the loop runs, including:
    - Base prompt template
    - Injected resources (by type and position)
    - Sample item substitution (for consumer loops)
    - Token count estimates
    - Section breakdown for debugging

    This is useful for:
    - Debugging prompt construction
    - Verifying resource injection
    - Testing consumer loop variable substitution
    - Understanding the full context Claude receives
    """
    from ralphx.core.preview import PromptPreviewEngine

    # Security: Validate loop name
    if not LOOP_NAME_PATTERN.match(loop_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid loop name",
        )

    manager, project, project_db = get_managers(slug)

    # Get loop config
    loader = LoopLoader(db=project_db)
    config = loader.get_loop(loop_name)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop not found: {loop_name}",
        )

    # Validate mode name if specified
    if request.mode and request.mode not in config.modes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mode '{request.mode}' not found in loop. Available: {list(config.modes.keys())}",
        )

    # Get sample item if specified by ID
    sample_item = None
    if request.sample_item_id:
        sample_item = project_db.get_work_item(request.sample_item_id)
        if not sample_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sample item not found: {request.sample_item_id}",
            )

    # Generate preview
    engine = PromptPreviewEngine(
        project_path=project.path,
        loop_config=config,
        db=project_db,
    )

    preview = engine.generate_preview(
        mode_name=request.mode,
        sample_item=sample_item,
        use_first_pending=request.use_first_pending,
        include_annotations=request.include_annotations,
    )

    # Convert to response model
    mode_responses = [
        ModePreviewResponse(
            mode_name=m.mode_name,
            model=m.model,
            timeout=m.timeout,
            tools=m.tools,
            total_length=m.total_length,
            token_estimate=m.token_estimate,
            sections=[
                PromptSectionResponse(
                    position=s.position,
                    source=s.source,
                    source_name=s.source_name,
                    content=s.content,
                    start_line=s.start_line,
                    end_line=s.end_line,
                )
                for s in m.sections
            ],
            rendered_prompt=m.rendered_prompt,
            warnings=m.warnings,
        )
        for m in preview.modes
    ]

    return PreviewResponse(
        loop_name=preview.loop_name,
        loop_type=preview.loop_type,
        mode_selection_strategy=preview.mode_selection_strategy,
        strategy_explanation=preview.strategy_explanation,
        sample_item=preview.sample_item,
        modes=mode_responses,
        resources_used=preview.resources_used,
        guardrails_used=preview.guardrails_used,
        template_variables=preview.template_variables,
        warnings=preview.warnings,
    )


# ========== Phase Info Endpoint ==========


class PhaseInfo(BaseModel):
    """Information about a detected phase."""

    phase_number: int
    item_count: int
    item_ids: list[str]
    categories: list[str]
    pending_count: int
    completed_count: int


class CategoryInfo(BaseModel):
    """Information about a category."""

    name: str
    item_count: int
    pending_count: int
    completed_count: int


class PhaseInfoResponse(BaseModel):
    """Response with phase and category information for a consumer loop."""

    loop_name: str
    source_loop: Optional[str]
    total_items: int
    phases: list[PhaseInfo]
    categories: list[CategoryInfo]
    has_dependencies: bool
    has_cycles: bool
    graph_stats: dict
    warnings: list[str] = Field(default_factory=list)


@router.get("/{slug}/loops/{loop_name}/phases", response_model=PhaseInfoResponse)
async def get_loop_phases(slug: str, loop_name: str):
    """Get phase and category information for a consumer loop.

    Returns:
    - Detected phases with item counts
    - Available categories
    - Dependency graph statistics

    This information is used by the UI to populate phase/category dropdowns
    when starting a loop.
    """
    from ralphx.core.dependencies import DependencyGraph

    # Security: Validate loop name
    if not LOOP_NAME_PATTERN.match(loop_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid loop name",
        )

    manager, project, project_db = get_managers(slug)

    # Get loop config
    loader = LoopLoader(db=project_db)
    config = loader.get_loop(loop_name)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop not found: {loop_name}",
        )

    # Check if this is a consumer loop
    source_loop = None
    if config.item_types and config.item_types.input:
        source_loop = config.item_types.input.source

    if not source_loop:
        # Not a consumer loop - return empty phase info
        return PhaseInfoResponse(
            loop_name=loop_name,
            source_loop=None,
            total_items=0,
            phases=[],
            categories=[],
            has_dependencies=False,
            has_cycles=False,
            graph_stats={},
        )

    # Get all items from source loop
    items, total = project_db.list_work_items(
        source_loop=source_loop,
        limit=10000,
    )

    if not items:
        return PhaseInfoResponse(
            loop_name=loop_name,
            source_loop=source_loop,
            total_items=0,
            phases=[],
            categories=[],
            has_dependencies=False,
            has_cycles=False,
            graph_stats={},
        )

    # Build dependency graph
    graph = DependencyGraph(items)

    # Detect phases
    max_batch = 10
    if config.multi_phase and config.multi_phase.max_batch_size:
        max_batch = config.multi_phase.max_batch_size

    detected_phases = graph.detect_phases(max_batch_size=max_batch)

    # Build phase info
    phases = []
    for phase_num, item_ids in sorted(detected_phases.items()):
        phase_items = [item for item in items if item["id"] in item_ids]
        categories = list(set((item.get("category") or "").lower() for item in phase_items if item.get("category")))
        pending = sum(1 for item in phase_items if item.get("status") in ("pending", "completed"))
        completed = sum(1 for item in phase_items if item.get("status") in ("processed", "failed", "skipped", "duplicate"))

        phases.append(PhaseInfo(
            phase_number=phase_num,
            item_count=len(item_ids),
            item_ids=item_ids,
            categories=sorted(categories),
            pending_count=pending,
            completed_count=completed,
        ))

    # Build category info
    category_counts: dict[str, dict] = {}
    for item in items:
        cat = (item.get("category") or "").lower()
        if not cat:
            continue
        if cat not in category_counts:
            category_counts[cat] = {"total": 0, "pending": 0, "completed": 0}
        category_counts[cat]["total"] += 1
        if item.get("status") in ("pending", "completed"):
            category_counts[cat]["pending"] += 1
        else:
            category_counts[cat]["completed"] += 1

    categories = [
        CategoryInfo(
            name=cat,
            item_count=counts["total"],
            pending_count=counts["pending"],
            completed_count=counts["completed"],
        )
        for cat, counts in sorted(category_counts.items())
    ]

    # Check for dependencies
    has_deps = any(item.get("dependencies") for item in items)

    # Build warnings list
    warnings = []
    if total > 10000:
        warnings.append(
            f"Only showing first 10000 of {total} items. "
            "Dependency graph may be incomplete."
        )
    if graph.has_cycle():
        warnings.append(
            "Dependency cycles detected. Some items may be processed out of order."
        )

    return PhaseInfoResponse(
        loop_name=loop_name,
        source_loop=source_loop,
        total_items=total,
        phases=phases,
        categories=categories,
        has_dependencies=has_deps,
        has_cycles=graph.has_cycle(),
        graph_stats=graph.get_stats(),
        warnings=warnings,
    )
