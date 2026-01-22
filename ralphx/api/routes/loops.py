"""Loop control API routes."""

import asyncio
import re
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from ralphx.core.executor import ExecutorEvent, ExecutorEventData, LoopExecutor
from ralphx.core.import_manager import ImportManager
from ralphx.core.input_templates import get_required_tags, validate_loop_inputs
from ralphx.core.loop import LoopLoader
from ralphx.core.project import ProjectManager
from ralphx.core.project_db import ProjectDatabase
from ralphx.models.loop import LoopConfig, LoopType, ModeSelectionStrategy, ItemTypes
from ralphx.models.run import Run, RunStatus
from ralphx.core.logger import loop_log

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
    current_run_id: Optional[str] = None
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
            current_run_id=executor._run.id if executor._run else None,
            current_iteration=executor._iteration,
            current_mode=None,  # Mode is per-iteration, not tracked as state
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

    # Get loop's workflow context from database
    loop_record = project_db.get_loop(loop_name)
    if not loop_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Loop '{loop_name}' not registered in database. "
                   "Loops must be created via a workflow to run.",
        )
    workflow_id = loop_record.get("workflow_id")
    step_id = loop_record.get("step_id")
    if not workflow_id or step_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Loop '{loop_name}' missing workflow context. "
                   "Loops must be created via a workflow to run.",
        )

    # For consumer loops, determine which step to consume items from
    # By default, consume from the previous step in the workflow
    consume_from_step_id = None
    if config.type == LoopType.CONSUMER:
        # Get the current step to find its step_number
        current_step = project_db.get_workflow_step(step_id)
        step_number = current_step["step_number"] if current_step else 1

        if step_number > 1:
            # Get the previous step
            prev_step = project_db.get_workflow_step_by_number(workflow_id, step_number - 1)
            if prev_step:
                consume_from_step_id = prev_step["id"]
        else:
            # Single-step consumer: consume from own step ID (for imported items)
            consume_from_step_id = step_id

    # Check if ready check (Q&A) has been completed
    # Required for first run of consumer loops - CANNOT be bypassed with force
    if config.type == LoopType.CONSUMER:
        resources = project_db.list_loop_resources(loop_name)
        has_qa = any(r["resource_type"] == "qa_responses" for r in resources)
        if not has_qa:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "READY_CHECK_REQUIRED",
                    "message": "Please complete a Ready Check before starting this loop",
                    "redirect": f"/projects/{slug}/loops/{loop_name}",
                },
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

    # Create executor with workflow context and phase/category filtering
    executor = LoopExecutor(
        project=project,
        loop_config=config,
        db=project_db,
        workflow_id=workflow_id,
        step_id=step_id,
        dry_run=request.dry_run,
        phase=request.phase,
        category=request.category,
        respect_dependencies=request.respect_dependencies,
        batch_mode=request.batch_mode,
        batch_size=request.batch_size,
        consume_from_step_id=consume_from_step_id,
    )

    _running_loops[key] = executor

    # Run in background
    async def run_and_cleanup():
        try:
            await executor.run(max_iterations=request.iterations)
        finally:
            _running_loops.pop(key, None)

    background_tasks.add_task(run_and_cleanup)

    # Return initial run info
    # Wait briefly for run to be created
    await asyncio.sleep(0.1)

    if executor._run:
        return RunResponse.from_run(executor._run)

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

    await executor.stop()

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

    loop_log.info(
        "deleted",
        f"Loop deleted: {loop_name}",
        project_id=project.id,
        loop_name=loop_name,
    )

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

    loop_log.info(
        "created",
        f"Loop created: {request.name}",
        project_id=project.id,
        loop_name=request.name,
    )

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
    format_id: Optional[str] = Field("hank_prd", description="Import format ID for parsing JSONL")
    namespace: Optional[str] = Field(None, description="Namespace for imported items (defaults to loop_id)")


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

    DEPRECATED: This endpoint uses the legacy standalone loop model.
    In the workflow-first architecture, loops are created automatically
    by workflow steps. Use POST /workflows to create a new workflow instead.

    TODO(migration): This endpoint needs to be updated to either:
    1. Create a workflow implicitly (quick workflow for legacy compatibility)
    2. Be deprecated and removed in favor of workflow-based creation

    The loop ID is auto-generated as {type}-{YYYYMMDD}_{n}.
    Users only need to provide:
    - Planning: design doc + optional templates
    - Implementation: stories source + design context + optional templates

    WARNING: JSONL import in this endpoint is currently broken after the
    workflow-first migration - work items now require workflow_id and source_step_id.
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
        # ALWAYS set namespace for implementation loops (fix for broken loops)
        # Default to loop_id if no explicit source provided
        namespace = loop_id.replace("-", "_")

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
            source_loop_name = source_loop  # Use source loop name
        elif request.stories_source and request.stories_source.type == "content":
            # For JSONL uploads, derive source from request or loop_id
            source_loop_name = request.stories_source.namespace or loop_id.replace("-", "_")

        config_yaml = generate_simple_implementation_config(
            name=loop_id,
            source_loop=source_loop_name,
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

                # Also import JSONL into work_items table
                import tempfile
                from pathlib import Path as TmpPath

                # Use namespace already computed for config (or derive from loop_id if not set)
                import_namespace = namespace or loop_id.replace("-", "_")
                format_id = request.stories_source.format_id or "hank_prd"

                # Seed defaults if needed to ensure format exists
                project_db.seed_defaults_if_empty()

                # DEPRECATED: JSONL import in legacy simple loop creation is broken
                # after workflow-first migration. Work items now require workflow_id
                # and source_step_id. Skipping import until this endpoint is migrated.
                #
                # TODO(migration): Either:
                # 1. Create an implicit workflow/step for legacy loop creation
                # 2. Remove this code path and require workflow-based creation
                import logging
                logging.warning(
                    f"JSONL import skipped for {loop_id}: legacy simple loop creation "
                    "does not support workflow-scoped work items. Use workflow-based "
                    "creation instead."
                )
                # Original broken code:
                # with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
                # NOTE: JSONL import code was removed because it requires workflow context
                # (workflow_id, source_step_id) which standalone loop creation doesn't have.
                # See TODO at function docstring for migration plan.

    # Check for duplicate display names (warn but don't block)
    warnings = []
    duplicate_names = [
        loop.name for loop in existing_loops
        if loop.display_name == display_name and loop.name != loop_id
    ]
    if duplicate_names:
        warnings.append(
            f"Warning: Another loop already uses the display name '{display_name}'. "
            f"Consider using a unique name to avoid confusion. "
            f"Existing loops: {', '.join(duplicate_names)}"
        )

    return {
        "loop_id": loop_id,
        "display_name": display_name,
        "loop_dir": str(loops_dir / f"{loop_id}.yaml"),
        "inputs_created": inputs_created,
        "warnings": warnings,
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
    workflow_id: Optional[str] = None  # Workflow context
    source_step_id: Optional[int] = None  # Step to consume items from
    namespace: Optional[str] = None  # Deprecated: Source namespace for items
    source_loop: Optional[str] = None  # Backward compatibility
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

    # Get loop's DB record to find workflow context
    loop_record = project_db.get_loop(loop_name)
    workflow_id = loop_record.get("workflow_id") if loop_record else None
    step_id = loop_record.get("step_id") if loop_record else None

    # Check if this is a consumer loop with workflow context
    if not workflow_id or step_id is None or config.type != LoopType.CONSUMER:
        # Not a consumer loop or missing workflow context - return empty phase info
        return PhaseInfoResponse(
            loop_name=loop_name,
            workflow_id=workflow_id,
            source_step_id=None,
            namespace=None,
            source_loop=None,  # Backward compatibility
            total_items=0,
            phases=[],
            categories=[],
            has_dependencies=False,
            has_cycles=False,
            graph_stats={},
        )

    # For consumer loops, determine which step to consume items from
    # By default, consume from the previous step in the workflow
    consume_from_step_id = None
    current_step = project_db.get_workflow_step(step_id)
    step_number = current_step["step_number"] if current_step else 1

    if step_number > 1:
        # Get the previous step
        prev_step = project_db.get_workflow_step_by_number(workflow_id, step_number - 1)
        if prev_step:
            consume_from_step_id = prev_step["id"]
    else:
        # Single-step consumer: consume from own step ID (for imported items)
        consume_from_step_id = step_id

    # Get all items from the source step
    items, total = project_db.list_work_items(
        workflow_id=workflow_id,
        source_step_id=consume_from_step_id,
        limit=10000,
    )

    if not items:
        return PhaseInfoResponse(
            loop_name=loop_name,
            workflow_id=workflow_id,
            source_step_id=consume_from_step_id,
            namespace=None,
            source_loop=None,  # Backward compatibility
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
        workflow_id=workflow_id,
        source_step_id=consume_from_step_id,
        namespace=None,
        source_loop=None,  # Backward compatibility
        total_items=total,
        phases=phases,
        categories=categories,
        has_dependencies=has_deps,
        has_cycles=graph.has_cycle(),
        graph_stats=graph.get_stats(),
        warnings=warnings,
    )


# ========== Loop Resources (per-loop resources) ==========


class LoopResourceResponse(BaseModel):
    """Response model for a loop resource."""

    id: int
    loop_name: str
    resource_type: str
    name: str
    injection_position: str
    source_type: str
    source_path: Optional[str] = None
    source_loop: Optional[str] = None
    source_resource_id: Optional[int] = None
    enabled: bool
    priority: int
    created_at: Optional[str] = None
    # Optionally include resolved content
    content: Optional[str] = None


class CreateLoopResourceRequest(BaseModel):
    """Request to create a loop resource."""

    resource_type: str = Field(..., description="Type: loop_template, design_doc, guardrails, custom")
    name: str = Field(..., description="Display name for this resource")
    injection_position: str = Field("after_design_doc", description="Where to inject in prompt")
    source_type: str = Field(..., description="How to load: system, project_file, loop_ref, project_resource, inline")
    source_path: Optional[str] = Field(None, description="For project_file: path relative to project")
    source_loop: Optional[str] = Field(None, description="For loop_ref: source loop name")
    source_resource_id: Optional[int] = Field(None, description="For loop_ref or project_resource")
    inline_content: Optional[str] = Field(None, description="For inline: actual content")
    enabled: bool = Field(True, description="Whether this resource is active")
    priority: int = Field(0, description="Order priority (lower = earlier)")


class UpdateLoopResourceRequest(BaseModel):
    """Request to update a loop resource."""

    name: Optional[str] = None
    injection_position: Optional[str] = None
    source_type: Optional[str] = None
    source_path: Optional[str] = None
    source_loop: Optional[str] = None
    source_resource_id: Optional[int] = None
    inline_content: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None


@router.get("/{slug}/loops/{loop_name}/resources", response_model=list[LoopResourceResponse])
async def list_loop_resources(
    slug: str,
    loop_name: str,
    include_content: bool = False,
):
    """List all resources for a specific loop.

    These are per-loop resources stored in the loop_resources table,
    different from project-level resources in the resources table.

    Query params:
        include_content: If true, resolve and include content for each resource
    """
    # Security: Validate loop name
    if not LOOP_NAME_PATTERN.match(loop_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid loop name - use only letters, numbers, underscores, and dashes",
        )

    manager, project, project_db = get_managers(slug)

    # Check loop exists
    loader = LoopLoader(db=project_db)
    config = loader.get_loop(loop_name)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop not found: {loop_name}",
        )

    resources = project_db.list_loop_resources(loop_name=loop_name)

    result = []
    for r in resources:
        response = LoopResourceResponse(
            id=r["id"],
            loop_name=r["loop_name"],
            resource_type=r["resource_type"],
            name=r["name"],
            injection_position=r["injection_position"],
            source_type=r["source_type"],
            source_path=r.get("source_path"),
            source_loop=r.get("source_loop"),
            source_resource_id=r.get("source_resource_id"),
            enabled=r["enabled"],
            priority=r["priority"],
            created_at=r.get("created_at"),
        )

        if include_content:
            # Resolve content based on source_type
            response.content = _resolve_loop_resource_content(
                r, project.path, project_db
            )

        result.append(response)

    return result


@router.post("/{slug}/loops/{loop_name}/resources", response_model=LoopResourceResponse)
async def create_loop_resource(
    slug: str,
    loop_name: str,
    request: CreateLoopResourceRequest,
):
    """Create a new resource for a loop.

    Source types:
    - system: Use built-in default template
    - project_file: Import from a file in the project (provide source_path)
    - loop_ref: Reference another loop's resource (provide source_loop + source_resource_id)
    - project_resource: Use a project-level resource (provide source_resource_id)
    - inline: Store content directly (provide inline_content)
    """
    # Security: Validate loop name
    if not LOOP_NAME_PATTERN.match(loop_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid loop name - use only letters, numbers, underscores, and dashes",
        )

    manager, project, project_db = get_managers(slug)

    # Check loop exists
    loader = LoopLoader(db=project_db)
    config = loader.get_loop(loop_name)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop not found: {loop_name}",
        )

    # Validate source_type requirements
    if request.source_type == "project_file" and not request.source_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_path is required when source_type is 'project_file'",
        )
    if request.source_type == "loop_ref" and (not request.source_loop or not request.source_resource_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_loop and source_resource_id are required when source_type is 'loop_ref'",
        )
    if request.source_type == "project_resource" and not request.source_resource_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_resource_id is required when source_type is 'project_resource'",
        )
    if request.source_type == "inline" and not request.inline_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="inline_content is required when source_type is 'inline'",
        )

    # Check for duplicate
    existing = project_db.get_loop_resource_by_name(
        loop_name, request.resource_type, request.name
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Resource '{request.name}' of type '{request.resource_type}' already exists for this loop",
        )

    # Create the resource
    resource = project_db.create_loop_resource(
        loop_name=loop_name,
        resource_type=request.resource_type,
        name=request.name,
        injection_position=request.injection_position,
        source_type=request.source_type,
        source_path=request.source_path,
        source_loop=request.source_loop,
        source_resource_id=request.source_resource_id,
        inline_content=request.inline_content,
        enabled=request.enabled,
        priority=request.priority,
    )

    return LoopResourceResponse(
        id=resource["id"],
        loop_name=resource["loop_name"],
        resource_type=resource["resource_type"],
        name=resource["name"],
        injection_position=resource["injection_position"],
        source_type=resource["source_type"],
        source_path=resource.get("source_path"),
        source_loop=resource.get("source_loop"),
        source_resource_id=resource.get("source_resource_id"),
        enabled=resource["enabled"],
        priority=resource["priority"],
        created_at=resource.get("created_at"),
    )


@router.get("/{slug}/loops/{loop_name}/resources/{resource_id}", response_model=LoopResourceResponse)
async def get_loop_resource(
    slug: str,
    loop_name: str,
    resource_id: int,
    include_content: bool = True,
):
    """Get a specific loop resource by ID."""
    manager, project, project_db = get_managers(slug)

    resource = project_db.get_loop_resource(resource_id)
    if not resource or resource["loop_name"] != loop_name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource not found: {resource_id}",
        )

    response = LoopResourceResponse(
        id=resource["id"],
        loop_name=resource["loop_name"],
        resource_type=resource["resource_type"],
        name=resource["name"],
        injection_position=resource["injection_position"],
        source_type=resource["source_type"],
        source_path=resource.get("source_path"),
        source_loop=resource.get("source_loop"),
        source_resource_id=resource.get("source_resource_id"),
        enabled=resource["enabled"],
        priority=resource["priority"],
        created_at=resource.get("created_at"),
    )

    if include_content:
        response.content = _resolve_loop_resource_content(
            resource, project.path, project_db
        )

    return response


@router.patch("/{slug}/loops/{loop_name}/resources/{resource_id}", response_model=LoopResourceResponse)
async def update_loop_resource(
    slug: str,
    loop_name: str,
    resource_id: int,
    request: UpdateLoopResourceRequest,
):
    """Update a loop resource."""
    manager, project, project_db = get_managers(slug)

    resource = project_db.get_loop_resource(resource_id)
    if not resource or resource["loop_name"] != loop_name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource not found: {resource_id}",
        )

    # Build update dict from non-None fields
    updates = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.injection_position is not None:
        updates["injection_position"] = request.injection_position
    if request.source_type is not None:
        updates["source_type"] = request.source_type
    if request.source_path is not None:
        updates["source_path"] = request.source_path
    if request.source_loop is not None:
        updates["source_loop"] = request.source_loop
    if request.source_resource_id is not None:
        updates["source_resource_id"] = request.source_resource_id
    if request.inline_content is not None:
        updates["inline_content"] = request.inline_content
    if request.enabled is not None:
        updates["enabled"] = request.enabled
    if request.priority is not None:
        updates["priority"] = request.priority

    if updates:
        project_db.update_loop_resource(resource_id, **updates)

    # Return updated resource
    updated = project_db.get_loop_resource(resource_id)
    return LoopResourceResponse(
        id=updated["id"],
        loop_name=updated["loop_name"],
        resource_type=updated["resource_type"],
        name=updated["name"],
        injection_position=updated["injection_position"],
        source_type=updated["source_type"],
        source_path=updated.get("source_path"),
        source_loop=updated.get("source_loop"),
        source_resource_id=updated.get("source_resource_id"),
        enabled=updated["enabled"],
        priority=updated["priority"],
        created_at=updated.get("created_at"),
    )


@router.delete("/{slug}/loops/{loop_name}/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_loop_resource(
    slug: str,
    loop_name: str,
    resource_id: int,
):
    """Delete a loop resource."""
    manager, project, project_db = get_managers(slug)

    resource = project_db.get_loop_resource(resource_id)
    if not resource or resource["loop_name"] != loop_name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource not found: {resource_id}",
        )

    project_db.delete_loop_resource(resource_id)
    return None


def _resolve_loop_resource_content(
    resource: dict,
    project_path: str,
    db,
) -> Optional[str]:
    """Resolve content for a loop resource based on its source_type.

    This is a helper function for API routes - the executor has its own version.
    """
    from pathlib import Path

    source_type = resource.get("source_type", "")

    if source_type == "system":
        # Load from system default templates
        resource_type = resource.get("resource_type", "")
        default_path = (
            Path(__file__).parent.parent.parent / "templates" / "loop_templates" / f"{resource_type}.md"
        )
        if default_path.exists():
            return default_path.read_text()
        return None

    elif source_type == "project_file":
        # Load from project file path
        source_path = resource.get("source_path")
        if source_path:
            file_path = Path(project_path) / source_path
            if file_path.exists():
                return file_path.read_text()
        return None

    elif source_type == "loop_ref":
        # Load from another loop's resource (recursively)
        source_resource_id = resource.get("source_resource_id")
        if source_resource_id:
            source_resource = db.get_loop_resource(source_resource_id)
            if source_resource:
                return _resolve_loop_resource_content(source_resource, project_path, db)
        return None

    elif source_type == "project_resource":
        # Load from project-level resource
        from ralphx.core.resources import ResourceManager
        source_resource_id = resource.get("source_resource_id")
        if source_resource_id:
            resource_manager = ResourceManager(project_path, db=db)
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


# ============================================================================
# Ready Check (Pre-Flight Clarification) Endpoints
# ============================================================================


class ReadyCheckStatusResponse(BaseModel):
    """Response model for ready check status."""

    has_qa: bool = False
    qa_count: int = 0
    last_updated: Optional[str] = None
    qa_summary: list[str] = Field(default_factory=list)
    resource_id: Optional[int] = None


class ReadyCheckQuestion(BaseModel):
    """A question from Claude during ready check."""

    id: str
    category: str
    question: str
    context: Optional[str] = None


class ReadyCheckTriggerResponse(BaseModel):
    """Response model for triggering a ready check."""

    status: str  # "analyzing", "questions", "ready"
    questions: list[ReadyCheckQuestion] = Field(default_factory=list)
    assessment: Optional[str] = None
    session_id: Optional[str] = None


class ReadyCheckAnswer(BaseModel):
    """An answer to a ready check question."""

    question_id: str
    answer: str


class ReadyCheckAnswersRequest(BaseModel):
    """Request model for submitting ready check answers."""

    session_id: Optional[str] = None
    questions: list[ReadyCheckQuestion] = Field(default_factory=list)
    answers: list[ReadyCheckAnswer] = Field(default_factory=list)


class ReadyCheckAnswersResponse(BaseModel):
    """Response model for submitting ready check answers."""

    saved: bool
    resource_id: Optional[int] = None
    can_start: bool = False


@router.get("/{slug}/loops/{loop_name}/ready-check", response_model=ReadyCheckStatusResponse)
async def get_ready_check_status(slug: str, loop_name: str):
    """Get the ready check status for a loop."""
    from ralphx.core.loop import LoopLoader
    from ralphx.core.project import ProjectManager

    manager = ProjectManager()
    project = manager.get_project(slug)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )

    project_db = ProjectDatabase(project.path)

    # Validate the loop exists
    loader = LoopLoader(db=project_db)
    loop_config = loader.get_loop(loop_name)
    if not loop_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop not found: {loop_name}",
        )

    # Look for qa_responses resource
    resources = project_db.list_loop_resources(loop_name)
    qa_resource = next(
        (r for r in resources if r["resource_type"] == "qa_responses"),
        None,
    )

    if not qa_resource:
        return ReadyCheckStatusResponse(has_qa=False)

    # Parse the Q&A content to get summary
    content = qa_resource.get("inline_content", "")
    qa_count = content.count("## ")  # Count section headers
    qa_summary = []

    # Extract first line of each answer for summary
    import re
    sections = re.split(r"\n## ", content)
    for section in sections[1:]:  # Skip the header
        lines = section.split("\n")
        if lines:
            title = lines[0].strip()
            # Find the answer line
            for line in lines:
                if line.startswith("**Answer:**"):
                    answer = line.replace("**Answer:**", "").strip()[:50]
                    qa_summary.append(f"{title}: {answer}...")
                    break

    return ReadyCheckStatusResponse(
        has_qa=True,
        qa_count=qa_count,
        last_updated=qa_resource.get("updated_at") or qa_resource.get("created_at"),
        qa_summary=qa_summary[:5],  # First 5 for summary
        resource_id=qa_resource.get("id"),
    )


@router.post("/{slug}/loops/{loop_name}/ready-check", response_model=ReadyCheckTriggerResponse)
async def trigger_ready_check(slug: str, loop_name: str):
    """Trigger a ready check analysis for a loop.

    This sends the loop configuration and resources to Claude to identify
    any clarifying questions before starting the loop.
    """
    import json
    import uuid

    from ralphx.core.loop import LoopLoader
    from ralphx.core.project import ProjectManager

    manager = ProjectManager()
    project = manager.get_project(slug)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )

    project_db = ProjectDatabase(project.path)
    loader = LoopLoader(db=project_db)
    loop_config = loader.get_loop(loop_name)

    if not loop_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop not found: {loop_name}",
        )

    # Get loop's workflow context from database
    loop_record = project_db.get_loop(loop_name)
    workflow_id = loop_record.get("workflow_id") if loop_record else None
    step_id = loop_record.get("step_id") if loop_record else None

    # For consumer loops, determine which step to consume items from
    consume_from_step_id = None
    if loop_config.type == LoopType.CONSUMER and workflow_id and step_id is not None:
        if step_id > 1:
            # Get the previous step
            prev_step = project_db.get_workflow_step_by_number(workflow_id, step_id - 1)
            if prev_step:
                consume_from_step_id = prev_step["id"]
        else:
            # Single-step consumer: consume from own step ID (for imported items)
            step = project_db.get_workflow_step_by_number(workflow_id, step_id)
            if step:
                consume_from_step_id = step["id"]

    # Get pending items for this loop
    pending_count = 0
    sample_item = None
    if consume_from_step_id:
        items, total = project_db.list_work_items(
            source_step_id=consume_from_step_id,
            status="pending",
            limit=1,
        )
        pending_count = total
        if items:
            sample_item = items[0]

    # Get loop resources
    resources = project_db.list_loop_resources(loop_name)
    resource_contents = {}
    for res in resources:
        if res["resource_type"] != "qa_responses":  # Skip existing Q&A
            content = _resolve_loop_resource_content(res, str(project.path), project_db)
            if content:
                resource_contents[res["name"]] = {
                    "type": res["resource_type"],
                    "content": content[:5000],  # Limit size
                }

    # Build the ready check prompt
    prompt = _build_ready_check_prompt(
        loop_config=loop_config,
        resources=resource_contents,
        sample_item=sample_item,
        pending_count=pending_count,
        namespace=loop_name,  # Use loop name as identifier
    )

    # Call Claude via the CLI adapter
    from ralphx.adapters.claude_cli import ClaudeCLIAdapter

    # Create adapter with project context (handles auth internally)
    adapter = ClaudeCLIAdapter(
        project_path=project.path,
        project_id=project.id,
    )

    try:
        # Run Claude analysis with sonnet model
        result = await adapter.execute(
            prompt=prompt,
            model="sonnet",
            tools=[],  # No tools needed for Q&A analysis
            timeout=120,
        )

        # Check for execution failures
        if not result.success:
            if result.error_message:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Ready check analysis failed: {result.error_message}",
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ready check analysis failed with unknown error",
            )

        # Parse the response
        response_text = result.text_output

        if not response_text.strip():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ready check analysis returned empty response",
            )

        # Try to extract JSON from response
        json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
        if json_match:
            response_data = json.loads(json_match.group(1))
        else:
            # Try direct JSON parse
            response_data = json.loads(response_text)

        questions = response_data.get("questions", [])
        assessment = response_data.get("assessment", "")

        if not questions:
            return ReadyCheckTriggerResponse(
                status="ready",
                questions=[],
                assessment=assessment or "Ready to start - no clarifications needed",
            )

        return ReadyCheckTriggerResponse(
            status="questions",
            questions=[
                ReadyCheckQuestion(
                    id=q.get("id", f"q-{i}"),
                    category=q.get("category", "General"),
                    question=q.get("question", ""),
                    context=q.get("context"),
                )
                for i, q in enumerate(questions)
            ],
            assessment=assessment,
            session_id=str(uuid.uuid4()),
        )

    except json.JSONDecodeError as e:
        # Claude returned non-JSON response - this is unexpected, report it
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ready check analysis returned invalid JSON: {str(e)}. "
                   "Claude may not have followed the expected response format.",
        )
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ready check failed: {str(e)}",
        )


@router.post("/{slug}/loops/{loop_name}/ready-check/answers", response_model=ReadyCheckAnswersResponse)
async def submit_ready_check_answers(
    slug: str,
    loop_name: str,
    request: ReadyCheckAnswersRequest,
):
    """Submit answers to ready check questions.

    This saves the Q&A as a loop resource that will be injected into
    the executor prompt for all future iterations.
    """
    from ralphx.core.loop import LoopLoader
    from ralphx.core.project import ProjectManager

    manager = ProjectManager()
    project = manager.get_project(slug)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )

    project_db = ProjectDatabase(project.path)

    # Validate the loop exists
    loader = LoopLoader(db=project_db, project_path=str(project.path))
    loop_config = loader.get_loop(loop_name)
    if not loop_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop not found: {loop_name}",
        )

    # Build the Q&A markdown content
    content_lines = [
        "# Pre-Flight Clarifications",
        "",
        "The following clarifications were provided by the user before starting this loop:",
        "",
    ]

    # Match questions to answers - track how many were matched
    questions_by_id = {q.id: q for q in request.questions}
    matched_count = 0
    for answer in request.answers:
        question = questions_by_id.get(answer.question_id)
        if question:
            # Validate answer is not empty
            if not answer.answer.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Answer for question '{question.question[:50]}...' cannot be empty",
                )
            matched_count += 1
            content_lines.extend([
                f"## {question.category}",
                f"**Question:** {question.question}",
                f"**Answer:** {answer.answer}",
                "",
            ])

    # Require at least one valid Q&A pair
    if matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid question-answer pairs provided. "
                   "Please answer at least one question.",
        )

    content = "\n".join(content_lines)

    # Check if Q&A resource already exists
    resources = project_db.list_loop_resources(loop_name)
    existing_qa = next(
        (r for r in resources if r["resource_type"] == "qa_responses"),
        None,
    )

    if existing_qa:
        # Update existing resource
        project_db.update_loop_resource(
            existing_qa["id"],
            inline_content=content,
        )
        resource_id = existing_qa["id"]
    else:
        # Create new resource - returns dict, extract ID
        new_resource = project_db.create_loop_resource(
            loop_name=loop_name,
            resource_type="qa_responses",
            name="Pre-Flight Clarifications",
            injection_position="after_design_doc",
            source_type="inline",
            inline_content=content,
            enabled=True,
            priority=50,  # After design doc
        )
        resource_id = new_resource["id"]

    return ReadyCheckAnswersResponse(
        saved=True,
        resource_id=resource_id,
        can_start=True,
    )


def _build_ready_check_prompt(
    loop_config,
    resources: dict,
    sample_item: Optional[dict],
    pending_count: int,
    namespace: Optional[str],
) -> str:
    """Build the prompt for ready check analysis."""
    import json

    lines = [
        "# Pre-Flight Analysis Request",
        "",
        "You are about to run an implementation loop. Before starting, analyze the configuration and ask any clarifying questions.",
        "",
        "## Loop Configuration",
        f"- Name: {loop_config.name}",
        f"- Type: {loop_config.type.value if hasattr(loop_config.type, 'value') else loop_config.type}",
        f"- Description: {loop_config.description or 'N/A'}",
    ]

    # Add mode info
    if loop_config.modes:
        mode_names = list(loop_config.modes.keys())
        first_mode = loop_config.modes.get(mode_names[0])
        if first_mode:
            lines.append(f"- Model: {first_mode.model}")
            lines.append(f"- Timeout: {first_mode.timeout}s per iteration")

    if loop_config.limits:
        lines.append(f"- Max iterations: {loop_config.limits.max_iterations}")

    if namespace:
        lines.append(f"- Namespace: {namespace} ({pending_count} pending items)")

    lines.append("")
    lines.append("## Resources That Will Be Used")
    lines.append("")

    for name, info in resources.items():
        lines.append(f"### {name} ({info['type']})")
        lines.append("```")
        lines.append(info["content"])
        lines.append("```")
        lines.append("")

    if sample_item:
        lines.append("## Sample Work Item")
        lines.append("Here's an example of the items you'll be implementing:")
        lines.append("```json")
        lines.append(json.dumps(sample_item, indent=2, default=str))
        lines.append("```")
        lines.append("")

    lines.extend([
        "## Your Task",
        "",
        "Analyze the above and identify any clarifying questions you need answered before implementing stories. Focus on:",
        "",
        "1. **Ambiguities** - Where requirements could be interpreted multiple ways",
        "2. **Missing information** - What context would help you implement correctly",
        "3. **Decisions** - Where you'd have to make assumptions otherwise",
        "4. **Technical choices** - Where best practices could vary",
        "",
        "If everything is clear and you have no questions, respond with:",
        "```json",
        '{"questions": [], "assessment": "Ready to start"}',
        "```",
        "",
        "Otherwise, respond with:",
        "```json",
        "{",
        '  "questions": [',
        "    {",
        '      "id": "unique-id",',
        '      "category": "Testing|Architecture|Style|Dependencies|etc",',
        '      "question": "Your question here",',
        '      "context": "Why you\'re asking / what you found"',
        "    }",
        "  ],",
        '  "assessment": "Brief assessment of overall readiness"',
        "}",
        "```",
    ])

    return "\n".join(lines)


# ============================================================================
# Loop Permissions Endpoints
# ============================================================================


class LoopPermissionsResponse(BaseModel):
    """Response model for loop permissions."""

    has_custom: bool = Field(..., description="Whether the loop has custom permissions")
    source: str = Field(..., description="Source of permissions: 'custom', 'template', or 'default'")
    permissions: dict = Field(..., description="The permissions object with allow/deny lists")
    settings_path: str = Field(..., description="Path to the settings.json file")
    template_id: Optional[str] = Field(None, description="Template ID if using a template")


class UpdateLoopPermissionsRequest(BaseModel):
    """Request model for updating loop permissions."""

    permissions: dict = Field(..., description="The permissions object with allow/deny lists")
    template_id: Optional[str] = Field(None, description="Optional: apply a template instead of custom permissions")


@router.get("/{slug}/loops/{loop_name}/permissions", response_model=LoopPermissionsResponse)
async def get_loop_permissions(slug: str, loop_name: str):
    """Get the permissions configuration for a loop.

    Returns the current permissions from the loop's settings.json file,
    or indicates if no custom permissions are set (using defaults).
    """
    from pathlib import Path
    from ralphx.core.workspace import get_loop_settings_path
    from ralphx.core.permission_templates import (
        read_settings_file,
        TEMPLATES,
        DEFAULT_LOOP_TEMPLATE,
    )

    # Security: Validate loop name
    if not LOOP_NAME_PATTERN.match(loop_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid loop name",
        )

    manager, project, project_db = get_managers(slug)

    # Get loop config to verify it exists
    loader = LoopLoader(db=project_db)
    config = loader.get_loop(loop_name)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop not found: {loop_name}",
        )

    # Get settings path
    settings_path = get_loop_settings_path(project.path, loop_name)

    # Check if custom settings exist
    if settings_path.exists():
        settings = read_settings_file(settings_path)
        permissions = settings.get("permissions", {"allow": [], "deny": []}) if settings else {"allow": [], "deny": []}

        # Try to detect if it matches a template
        template_id = None
        for tid, template in TEMPLATES.items():
            template_perms = template["settings"].get("permissions", {})
            if permissions == template_perms:
                template_id = tid
                break

        return LoopPermissionsResponse(
            has_custom=True,
            source="template" if template_id else "custom",
            permissions=permissions,
            settings_path=str(settings_path),
            template_id=template_id,
        )

    # No custom settings - return default template info
    default_template = TEMPLATES.get(DEFAULT_LOOP_TEMPLATE, {})
    default_permissions = default_template.get("settings", {}).get("permissions", {"allow": [], "deny": []})

    return LoopPermissionsResponse(
        has_custom=False,
        source="default",
        permissions=default_permissions,
        settings_path=str(settings_path),
        template_id=DEFAULT_LOOP_TEMPLATE,
    )


@router.put("/{slug}/loops/{loop_name}/permissions", response_model=LoopPermissionsResponse)
async def update_loop_permissions(
    slug: str,
    loop_name: str,
    request: UpdateLoopPermissionsRequest,
):
    """Update the permissions configuration for a loop.

    Can either:
    1. Apply a template by providing template_id
    2. Set custom permissions by providing permissions object

    This writes to <project>/.ralphx/loops/{loop_name}/settings.json
    """
    from pathlib import Path
    from ralphx.core.workspace import get_loop_settings_path, ensure_loop_directory
    from ralphx.core.permission_templates import (
        write_settings_file,
        read_settings_file,
        TEMPLATES,
    )

    # Security: Validate loop name
    if not LOOP_NAME_PATTERN.match(loop_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid loop name",
        )

    manager, project, project_db = get_managers(slug)

    # Verify loop exists
    loader = LoopLoader(db=project_db)
    config = loader.get_loop(loop_name)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop not found: {loop_name}",
        )

    # Check if loop is running
    key = f"{slug}:{loop_name}"
    if key in _running_loops:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot update permissions while loop is running",
        )

    # Ensure loop directory exists
    ensure_loop_directory(project.path, loop_name)
    settings_path = get_loop_settings_path(project.path, loop_name)

    # Apply template or custom permissions
    if request.template_id:
        if request.template_id not in TEMPLATES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown template: {request.template_id}. "
                       f"Available: {list(TEMPLATES.keys())}",
            )
        write_settings_file(settings_path, template_id=request.template_id)
        template = TEMPLATES[request.template_id]
        permissions = template["settings"]["permissions"]
        source = "template"
    else:
        # Validate permissions structure
        if not isinstance(request.permissions, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Permissions must be an object",
            )
        if "allow" not in request.permissions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Permissions must have an 'allow' list",
            )
        # Validate allow is a list of strings
        if not isinstance(request.permissions["allow"], list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Permissions 'allow' must be a list",
            )
        for item in request.permissions["allow"]:
            if not isinstance(item, str):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="All items in 'allow' must be strings",
                )
        # Validate deny if present
        if "deny" in request.permissions:
            if not isinstance(request.permissions["deny"], list):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Permissions 'deny' must be a list",
                )
            for item in request.permissions["deny"]:
                if not isinstance(item, str):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="All items in 'deny' must be strings",
                    )

        # Write custom permissions
        settings = {"permissions": request.permissions}
        write_settings_file(settings_path, custom_settings=settings)
        permissions = request.permissions
        source = "custom"

    loop_log.info(
        "permissions_updated",
        f"Loop permissions updated: {loop_name}",
        project_id=project.id,
        loop_name=loop_name,
        extra={"source": source, "template_id": request.template_id},
    )

    return LoopPermissionsResponse(
        has_custom=True,
        source=source,
        permissions=permissions,
        settings_path=str(settings_path),
        template_id=request.template_id if source == "template" else None,
    )


@router.delete("/{slug}/loops/{loop_name}/permissions", status_code=status.HTTP_204_NO_CONTENT)
async def delete_loop_permissions(slug: str, loop_name: str):
    """Delete custom permissions for a loop.

    This removes the settings.json file, causing the loop to use defaults.
    """
    from pathlib import Path
    from ralphx.core.workspace import get_loop_settings_path

    # Security: Validate loop name
    if not LOOP_NAME_PATTERN.match(loop_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid loop name",
        )

    manager, project, project_db = get_managers(slug)

    # Verify loop exists
    loader = LoopLoader(db=project_db)
    config = loader.get_loop(loop_name)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop not found: {loop_name}",
        )

    # Check if loop is running
    key = f"{slug}:{loop_name}"
    if key in _running_loops:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete permissions while loop is running",
        )

    # Delete settings file if it exists
    settings_path = get_loop_settings_path(project.path, loop_name)
    if settings_path.exists():
        settings_path.unlink()

        loop_log.info(
            "permissions_deleted",
            f"Loop permissions deleted: {loop_name}",
            project_id=project.id,
            loop_name=loop_name,
        )

    return None


# ============================================================================
# Permission Templates List Endpoint
# ============================================================================


class PermissionTemplateInfoResponse(BaseModel):
    """Response model for a permission template."""

    id: str
    name: str
    description: str


class PermissionTemplateDetailResponse(PermissionTemplateInfoResponse):
    """Response model for permission template details."""

    settings: dict


@router.get("/permission-templates", response_model=list[PermissionTemplateInfoResponse])
async def list_permission_templates():
    """List all available permission templates."""
    from ralphx.core.permission_templates import list_templates

    templates = list_templates()
    return [
        PermissionTemplateInfoResponse(
            id=t["id"],
            name=t["name"],
            description=t["description"],
        )
        for t in templates
    ]


@router.get("/permission-templates/{template_id}", response_model=PermissionTemplateDetailResponse)
async def get_permission_template(template_id: str):
    """Get details of a specific permission template."""
    from ralphx.core.permission_templates import get_template

    template = get_template(template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template not found: {template_id}",
        )

    return PermissionTemplateDetailResponse(
        id=template_id,
        name=template["name"],
        description=template["description"],
        settings=template["settings"],
    )


@router.post("/{slug}/cleanup-stale-runs")
async def cleanup_stale_runs_endpoint(
    slug: str,
    max_inactivity_minutes: int = Query(15, ge=1, le=120),
    dry_run: bool = Query(False),
):
    """Clean up stale runs for a project.

    A run is considered stale if:
    - Status is RUNNING or PAUSED
    - AND one of:
      - executor_pid is set and process is not running (definitive stale)
      - last_activity_at is older than max_inactivity_minutes and PID not running
      - last_activity_at is older than 2x max_inactivity_minutes even if PID appears
        running (handles PID reuse by OS)
      - No executor_pid/activity tracking and started > 1 hour ago (legacy runs)

    Args:
        slug: Project slug.
        max_inactivity_minutes: Max minutes without activity before considering stale.
            Default is 15. The 2x threshold for PID reuse detection means runs
            with an apparently-running PID won't be marked stale until activity
            is 2x this value old.
        dry_run: If True, don't actually update, just report what would be cleaned.

    Returns:
        Dictionary with:
        - cleaned: Number of runs cleaned (or would be cleaned if dry_run)
        - dry_run: Whether this was a dry run
        - runs: List of stale run details
        - errors: List of any errors during cleanup (if not dry_run)
    """
    manager = ProjectManager()
    project = manager.get_project(slug)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )

    project_db = ProjectDatabase(project.path)

    from ralphx.core.doctor import detect_stale_runs

    stale = detect_stale_runs(project_db, max_inactivity_minutes)
    errors = []

    if not dry_run:
        for run in stale:
            try:
                project_db.update_run(
                    run["run_id"],
                    status="aborted",
                    completed_at=datetime.utcnow().isoformat(),
                    error_message=f"Marked stale: {run['reason']}",
                )
            except Exception as e:
                errors.append({
                    "run_id": run["run_id"],
                    "error": str(e),
                })

    return {
        "cleaned": len(stale) - len(errors),
        "dry_run": dry_run,
        "runs": stale,
        "errors": errors if errors else None,
    }
