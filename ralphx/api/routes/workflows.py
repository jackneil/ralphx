"""Workflow API routes for RalphX."""

import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from ralphx.core.database import Database
from ralphx.core.project_db import ProjectDatabase

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================


class ItemStatusBreakdown(BaseModel):
    """Breakdown of work items by status."""

    total: int = 0
    pending: int = 0
    in_progress: int = 0
    completed: int = 0
    skipped: int = 0
    failed: int = 0
    duplicate: int = 0
    rejected: int = 0


class WorkflowStepResponse(BaseModel):
    """Response model for a workflow step."""

    id: int
    workflow_id: str
    step_number: int
    name: str
    step_type: str
    status: str
    config: Optional[dict] = None
    loop_name: Optional[str] = None
    artifacts: Optional[dict] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    archived_at: Optional[str] = None  # NULL = active, non-NULL = archived (soft delete)
    has_active_run: bool = False  # True if there's a run in 'running' status
    # Progress tracking
    iterations_completed: int = 0  # Total iterations completed across all runs
    iterations_target: Optional[int] = None  # Target iterations (from config), None = unlimited
    current_run_iterations: int = 0  # Iterations in current/latest run
    items_generated: int = 0  # Total items generated (e.g., user stories)
    has_guardrails: bool = False  # Whether this step has guardrails configured
    # Input items (for consumer steps - items from previous step)
    input_items: Optional[ItemStatusBreakdown] = None


class WorkflowResponse(BaseModel):
    """Response model for a workflow."""

    id: str
    template_id: Optional[str] = None
    name: str
    namespace: str
    status: str
    current_step: int
    created_at: str
    updated_at: str
    archived_at: Optional[str] = None  # NULL = active, non-NULL = archived timestamp
    steps: list[WorkflowStepResponse] = []
    # Resource indicators
    has_design_doc: bool = False  # Whether workflow has a design document attached
    guardrails_count: int = 0  # Number of guardrails attached to workflow


class WorkflowTemplateStep(BaseModel):
    """A step definition in a workflow template."""

    number: int
    name: str
    type: str
    description: Optional[str] = None
    loopType: Optional[str] = None
    inputs: list[str] = []
    outputs: list[str] = []
    skippable: bool = False
    skipCondition: Optional[str] = None


class WorkflowTemplateResponse(BaseModel):
    """Response model for a workflow template."""

    id: str
    name: str
    description: Optional[str] = None
    steps: list[WorkflowTemplateStep]
    created_at: str


class CreateWorkflowRequest(BaseModel):
    """Request model for creating a workflow."""

    name: str = Field(..., min_length=1, max_length=200)
    template_id: Optional[str] = None


class UpdateWorkflowRequest(BaseModel):
    """Request model for updating a workflow."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    status: Optional[str] = Field(None, pattern=r"^(draft|active|paused|completed)$")


class AdvanceStepRequest(BaseModel):
    """Request model for advancing to next step."""

    skip_current: bool = False
    artifacts: Optional[dict] = None


class CreateStepRequest(BaseModel):
    """Request model for creating a workflow step."""

    name: str = Field(..., min_length=1, max_length=200)
    step_type: str = Field(..., pattern=r"^(interactive|autonomous)$")
    description: Optional[str] = None
    loop_type: Optional[str] = None
    skippable: bool = False
    # Autonomous step execution settings (step config overrides template defaults)
    model: Optional[str] = Field(None, pattern=r"^(sonnet|sonnet-1m|opus|haiku)$")
    timeout: Optional[int] = Field(None, ge=60, le=7200)  # 1min to 2hr
    allowed_tools: Optional[list[str]] = None
    # Loop limits (autonomous steps only)
    max_iterations: Optional[int] = Field(None, ge=0, le=10000)  # 0 = unlimited
    cooldown_between_iterations: Optional[int] = Field(None, ge=0, le=300)  # seconds
    max_consecutive_errors: Optional[int] = Field(None, ge=1, le=100)


class UpdateStepRequest(BaseModel):
    """Request model for updating a workflow step.

    Note: To change step order, use the /steps/reorder endpoint instead.
    """

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    step_type: Optional[str] = Field(None, pattern=r"^(interactive|autonomous)$")
    description: Optional[str] = None
    loop_type: Optional[str] = None
    skippable: Optional[bool] = None
    # Autonomous step execution settings (step config overrides template defaults)
    model: Optional[str] = Field(None, pattern=r"^(sonnet|sonnet-1m|opus|haiku)$")
    timeout: Optional[int] = Field(None, ge=60, le=7200)  # 1min to 2hr
    allowed_tools: Optional[list[str]] = None
    # Loop limits (autonomous steps only)
    max_iterations: Optional[int] = Field(None, ge=0, le=10000)  # 0 = unlimited
    cooldown_between_iterations: Optional[int] = Field(None, ge=0, le=300)  # seconds
    max_consecutive_errors: Optional[int] = Field(None, ge=1, le=100)


# Valid tools for autonomous steps
# Full list of Claude Code tools that can be allowed/restricted
VALID_TOOLS = {
    "Read", "Write", "Edit", "MultiEdit",  # File operations
    "Bash", "Glob", "Grep", "LS",           # Shell and search
    "WebSearch", "WebFetch",                 # Web access
    "NotebookRead", "NotebookEdit",          # Jupyter notebooks
    "TodoRead", "TodoWrite",                 # Task management
    "Agent",                                 # Sub-agent spawning
}


def validate_allowed_tools(tools: Optional[list[str]]) -> list[str] | None:
    """Validate that all tools in the list are valid.

    Returns deduplicated list of tools, or None if input was None.
    """
    if tools is None:
        return None
    invalid = set(tools) - VALID_TOOLS
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tools: {sorted(invalid)}. Valid tools: {sorted(VALID_TOOLS)}",
        )
    # Deduplicate while preserving order
    seen = set()
    result = []
    for tool in tools:
        if tool not in seen:
            seen.add(tool)
            result.append(tool)
    return result


class ReorderStepsRequest(BaseModel):
    """Request model for reordering steps."""

    step_ids: list[int] = Field(..., min_length=1)


# ============================================================================
# Helper Functions
# ============================================================================


def _get_project_db(slug: str) -> ProjectDatabase:
    """Get project database for a project slug."""
    db = Database()
    project = db.get_project(slug)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{slug}' not found",
        )
    return ProjectDatabase(project["path"])


def _generate_namespace(name: str) -> str:
    """Generate a valid namespace from a workflow name."""
    import re

    # Convert to lowercase, replace spaces with dashes
    ns = name.lower().replace(" ", "-")
    # Remove invalid characters
    ns = re.sub(r"[^a-z0-9_-]", "", ns)
    # Ensure it starts with a letter
    if not ns or not ns[0].isalpha():
        ns = "w" + ns
    # Truncate to 64 chars and add unique suffix
    ns = ns[:56]
    suffix = uuid.uuid4().hex[:7]
    return f"{ns}-{suffix}"


def _workflow_to_response(
    workflow: dict, steps: list[dict], pdb: Optional[ProjectDatabase] = None
) -> WorkflowResponse:
    """Convert workflow and steps to response model.

    Args:
        workflow: Workflow dict from database.
        steps: List of step dicts from database.
        pdb: Optional ProjectDatabase to check for active runs and progress.
    """
    # Build step progress info if database is provided
    step_progress: dict[int, dict] = {}
    has_design_doc = False
    guardrails_count = 0

    if pdb:
        # Get workflow resources to check for design doc and guardrails
        try:
            workflow_resources = pdb.list_workflow_resources(
                workflow["id"], enabled_only=True
            )
            has_design_doc = any(
                r.get("resource_type") == "design_doc" for r in workflow_resources
            )
            guardrails_count = sum(
                1 for r in workflow_resources if r.get("resource_type") == "guardrails"
            )
        except Exception:
            # Don't fail if resources can't be fetched
            pass

        # Get all runs for this workflow to calculate progress
        all_runs = pdb.list_runs(workflow_id=workflow["id"], limit=1000)

        # Get item counts grouped by source step ID and status
        # Note: get_workflow_item_counts returns {step_id: {status: count}}
        item_counts_by_step_id: dict[int, dict[str, int]] = {}
        try:
            item_counts_by_step_id = pdb.get_workflow_item_counts(workflow["id"])
        except Exception:
            pass

        # Build mapping from step_number to step_id for looking up source items
        step_number_to_id = {s.get("step_number"): s.get("id") for s in steps}

        for step in steps:
            step_id = step["id"]
            step_runs = [r for r in all_runs if r.get("step_id") == step_id]

            # Calculate totals
            total_iterations = sum(
                r.get("iterations_completed", 0) or 0 for r in step_runs
            )
            total_items = sum(
                r.get("items_generated", 0) or 0 for r in step_runs
            )

            # Check for active run
            running_run = next(
                (r for r in step_runs if r.get("status") == "running"), None
            )

            # Get iterations target from config
            config = step.get("config") or {}
            iterations_target = config.get("max_iterations")

            # Check for step-level guardrails
            step_has_guardrails = False
            try:
                step_resources = pdb.list_step_resources(step_id)
                step_has_guardrails = any(
                    r.get("resource_type") == "guardrails" for r in step_resources
                )
            except Exception:
                pass

            # Build input items breakdown for consumer steps
            # Consumer steps consume items from the previous step (step_number - 1)
            input_items = None
            step_number = step.get("step_number", 0)
            loop_type = (step.get("config") or {}).get("loopType", "")

            # Check if this is a consumer step (implementation type)
            if step_number > 1 and loop_type in ("consumer", "implementation"):
                # Get items from the previous step (source)
                # We need to use the step_id (not step_number) to look up items
                source_step_number = step_number - 1
                source_step_id = step_number_to_id.get(source_step_number)
                if source_step_id:
                    item_stats = item_counts_by_step_id.get(source_step_id, {})
                    if item_stats:
                        total = sum(item_stats.values())
                        # Status mapping for display:
                        # - "completed" in DB = ready for consumer (display as "pending")
                        # - "processed" in DB = already done (display as "completed")
                        # - "pending" in DB = not yet ready (shouldn't happen much)
                        input_items = {
                            "total": total,
                            # "completed" in DB means ready-to-process, so count as pending for display
                            "pending": item_stats.get("pending", 0) + item_stats.get("completed", 0),
                            "in_progress": item_stats.get("in_progress", 0),
                            # "processed" in DB means actually done
                            "completed": item_stats.get("processed", 0),
                            "skipped": item_stats.get("skipped", 0),
                            "failed": item_stats.get("failed", 0),
                            "duplicate": item_stats.get("duplicate", 0),
                            "rejected": item_stats.get("rejected", 0),
                        }

            step_progress[step_id] = {
                "has_active_run": running_run is not None,
                "iterations_completed": total_iterations,
                "iterations_target": iterations_target,
                "current_run_iterations": (
                    running_run.get("iterations_completed", 0) or 0
                    if running_run
                    else 0
                ),
                "items_generated": total_items,
                "has_guardrails": step_has_guardrails or guardrails_count > 0,
                "input_items": input_items,
            }

    return WorkflowResponse(
        id=workflow["id"],
        template_id=workflow.get("template_id"),
        name=workflow["name"],
        namespace=workflow["namespace"],
        status=workflow["status"],
        current_step=workflow["current_step"],
        created_at=workflow["created_at"],
        updated_at=workflow["updated_at"],
        archived_at=workflow.get("archived_at"),
        steps=[
            WorkflowStepResponse(
                id=s["id"],
                workflow_id=s["workflow_id"],
                step_number=s["step_number"],
                name=s["name"],
                step_type=s["step_type"],
                status=s["status"],
                config=s.get("config"),
                loop_name=s.get("loop_name"),
                artifacts=s.get("artifacts"),
                started_at=s.get("started_at"),
                completed_at=s.get("completed_at"),
                has_active_run=step_progress.get(s["id"], {}).get("has_active_run", False),
                iterations_completed=step_progress.get(s["id"], {}).get("iterations_completed", 0),
                iterations_target=step_progress.get(s["id"], {}).get("iterations_target"),
                current_run_iterations=step_progress.get(s["id"], {}).get("current_run_iterations", 0),
                items_generated=step_progress.get(s["id"], {}).get("items_generated", 0),
                has_guardrails=step_progress.get(s["id"], {}).get("has_guardrails", False),
                input_items=step_progress.get(s["id"], {}).get("input_items"),
            )
            for s in steps
        ],
        has_design_doc=has_design_doc,
        guardrails_count=guardrails_count,
    )


def _step_to_response(step: dict, pdb: Optional[ProjectDatabase] = None) -> WorkflowStepResponse:
    """Convert a step dict to WorkflowStepResponse.

    Args:
        step: Step dictionary from database.
        pdb: Optional ProjectDatabase for fetching additional info like active runs.

    Returns:
        WorkflowStepResponse with basic step data.
    """
    return WorkflowStepResponse(
        id=step["id"],
        workflow_id=step["workflow_id"],
        step_number=step["step_number"],
        name=step["name"],
        step_type=step["step_type"],
        status=step["status"],
        config=step.get("config"),
        loop_name=step.get("loop_name"),
        artifacts=step.get("artifacts"),
        started_at=step.get("started_at"),
        completed_at=step.get("completed_at"),
        archived_at=step.get("archived_at"),
    )


# ============================================================================
# Workflow Template Endpoints
# ============================================================================


@router.get("/workflow-templates", response_model=list[WorkflowTemplateResponse])
async def list_workflow_templates(slug: str):
    """List all available workflow templates."""
    pdb = _get_project_db(slug)
    # Seed templates if empty
    pdb.seed_workflow_templates_if_empty()
    templates = pdb.list_workflow_templates()
    return [
        WorkflowTemplateResponse(
            id=t["id"],
            name=t["name"],
            description=t.get("description"),
            # Templates store phases but we expose as steps
            steps=[WorkflowTemplateStep(**p) for p in t.get("phases", [])],
            created_at=t["created_at"],
        )
        for t in templates
    ]


@router.get("/workflow-templates/{template_id}", response_model=WorkflowTemplateResponse)
async def get_workflow_template(slug: str, template_id: str):
    """Get a workflow template by ID."""
    pdb = _get_project_db(slug)
    pdb.seed_workflow_templates_if_empty()
    template = pdb.get_workflow_template(template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow template '{template_id}' not found",
        )
    return WorkflowTemplateResponse(
        id=template["id"],
        name=template["name"],
        description=template.get("description"),
        # Templates store phases but we expose as steps
        steps=[WorkflowTemplateStep(**p) for p in template.get("phases", [])],
        created_at=template["created_at"],
    )


# ============================================================================
# Workflow CRUD Endpoints
# ============================================================================


@router.get("/workflows", response_model=list[WorkflowResponse])
async def list_workflows(
    slug: str,
    status_filter: Optional[str] = None,
    include_archived: bool = Query(False, description="Include archived workflows"),
    archived_only: bool = Query(False, description="Only return archived workflows"),
):
    """List all workflows for a project.

    By default, archived workflows are excluded. Use include_archived=true
    to include them, or archived_only=true to only see archived workflows.
    """
    pdb = _get_project_db(slug)
    workflows = pdb.list_workflows(
        status=status_filter,
        include_archived=include_archived,
        archived_only=archived_only,
    )
    result = []
    for w in workflows:
        steps = pdb.list_workflow_steps(w["id"])
        result.append(_workflow_to_response(w, steps, pdb))
    return result


@router.post("/workflows", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(slug: str, request: CreateWorkflowRequest):
    """Create a new workflow.

    If template_id is provided, steps are created from the template.
    Otherwise, a blank workflow is created.
    """
    pdb = _get_project_db(slug)

    # Generate unique ID and namespace
    workflow_id = f"wf-{uuid.uuid4().hex[:12]}"
    namespace = _generate_namespace(request.name)

    # Get template steps if template specified (templates still use "phases" internally)
    template_steps = []
    if request.template_id:
        pdb.seed_workflow_templates_if_empty()
        template = pdb.get_workflow_template(request.template_id)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template '{request.template_id}' not found",
            )
        template_steps = template.get("phases", [])

    # Create workflow
    workflow = pdb.create_workflow(
        id=workflow_id,
        name=request.name,
        namespace=namespace,
        template_id=request.template_id,
        status="draft",
    )

    # Create steps from template
    created_steps = []
    for step_def in template_steps:
        step = pdb.create_workflow_step(
            workflow_id=workflow_id,
            step_number=step_def["number"],
            name=step_def["name"],
            step_type=step_def["type"],
            config={
                "description": step_def.get("description"),
                "loopType": step_def.get("loopType"),
                "inputs": step_def.get("inputs", []),
                "outputs": step_def.get("outputs", []),
                "skippable": step_def.get("skippable", False),
                "skipCondition": step_def.get("skipCondition"),
            },
            status="pending",
        )
        created_steps.append(step)

    # Inherit auto-inherit resources from project library
    pdb.inherit_project_resources_to_workflow(workflow_id)

    return _workflow_to_response(workflow, created_steps, pdb)


@router.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(slug: str, workflow_id: str):
    """Get a workflow by ID."""
    pdb = _get_project_db(slug)
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )
    steps = pdb.list_workflow_steps(workflow_id)
    return _workflow_to_response(workflow, steps, pdb)


@router.patch("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(slug: str, workflow_id: str, request: UpdateWorkflowRequest):
    """Update a workflow."""
    pdb = _get_project_db(slug)
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    updates = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.status is not None:
        updates["status"] = request.status

    if updates:
        pdb.update_workflow(workflow_id, **updates)
        workflow = pdb.get_workflow(workflow_id)

    steps = pdb.list_workflow_steps(workflow_id)
    return _workflow_to_response(workflow, steps, pdb)


@router.post("/workflows/{workflow_id}/archive", response_model=WorkflowResponse)
async def archive_workflow(slug: str, workflow_id: str):
    """Archive a workflow (soft delete).

    Archived workflows are hidden from the default list but can be restored.
    """
    pdb = _get_project_db(slug)
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    if workflow.get("archived_at"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workflow is already archived",
        )

    pdb.archive_workflow(workflow_id)

    # Return updated workflow
    workflow = pdb.get_workflow(workflow_id)
    steps = pdb.list_workflow_steps(workflow_id)
    return _workflow_to_response(workflow, steps, pdb)


@router.post("/workflows/{workflow_id}/restore", response_model=WorkflowResponse)
async def restore_workflow(slug: str, workflow_id: str):
    """Restore an archived workflow."""
    pdb = _get_project_db(slug)
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    if not workflow.get("archived_at"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workflow is not archived",
        )

    pdb.restore_workflow(workflow_id)

    # Return updated workflow
    workflow = pdb.get_workflow(workflow_id)
    steps = pdb.list_workflow_steps(workflow_id)
    return _workflow_to_response(workflow, steps, pdb)


@router.delete("/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(slug: str, workflow_id: str):
    """Permanently delete a workflow.

    IMPORTANT: Workflow must be archived first. This prevents accidental deletion.
    To delete a workflow:
    1. First archive it: POST /workflows/{id}/archive
    2. Then delete it: DELETE /workflows/{id}
    """
    pdb = _get_project_db(slug)
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    if not workflow.get("archived_at"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete active workflow. Archive it first using POST /workflows/{id}/archive",
        )

    pdb.delete_workflow(workflow_id)


# ============================================================================
# Step Management Endpoints
# ============================================================================


@router.post("/workflows/{workflow_id}/advance", response_model=WorkflowResponse)
async def advance_workflow_step(
    slug: str, workflow_id: str, request: AdvanceStepRequest
):
    """Advance workflow to the next step.

    If skip_current is True, marks the current step as skipped.
    Otherwise, marks the current step as completed with optional artifacts.
    """
    pdb = _get_project_db(slug)
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    # Validate workflow is active before allowing step advancement
    if workflow["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot advance steps of workflow in status '{workflow['status']}'. Workflow must be 'active'.",
        )

    steps = pdb.list_workflow_steps(workflow_id)
    current_step_num = workflow["current_step"]

    # Find current step
    current_step = None
    for s in steps:
        if s["step_number"] == current_step_num:
            current_step = s
            break

    if not current_step:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Current step {current_step_num} not found",
        )

    # Find next step (if any)
    next_step = None
    for s in steps:
        if s["step_number"] == current_step_num + 1:
            next_step = s
            break

    # Use atomic operation to prevent race conditions from concurrent requests
    pdb.advance_workflow_step_atomic(
        workflow_id=workflow_id,
        current_step_id=current_step["id"],
        next_step_id=next_step["id"] if next_step else None,
        skip_current=request.skip_current,
        artifacts=request.artifacts,
    )

    # Return updated workflow
    workflow = pdb.get_workflow(workflow_id)
    steps = pdb.list_workflow_steps(workflow_id)
    return _workflow_to_response(workflow, steps, pdb)


@router.post("/workflows/{workflow_id}/start", response_model=WorkflowResponse)
async def start_workflow(slug: str, workflow_id: str):
    """Start a workflow by activating the first step."""
    pdb = _get_project_db(slug)
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    if workflow["status"] not in ("draft", "paused"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Workflow is already {workflow['status']}",
        )

    # Find the first pending step
    steps = pdb.list_workflow_steps(workflow_id)
    first_pending = None
    for s in steps:
        if s["status"] == "pending":
            first_pending = s
            break

    if not first_pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending steps to start",
        )

    # Update workflow status and start first step
    pdb.update_workflow(
        workflow_id,
        status="active",
        current_step=first_pending["step_number"],
    )
    pdb.start_workflow_step(first_pending["id"])

    # If first step is autonomous, trigger the loop execution
    if first_pending["step_type"] == "autonomous":
        import asyncio
        from ralphx.core.project import Project
        from ralphx.core.workflow_executor import WorkflowExecutor

        db = Database()
        project = db.get_project(slug)
        if project:
            project_obj = Project.from_dict(project)
            executor = WorkflowExecutor(
                project=project_obj,
                db=pdb,
                workflow_id=workflow_id,
            )
            # Start autonomous step in background
            asyncio.create_task(executor._start_autonomous_step(first_pending))

    # Return updated workflow
    workflow = pdb.get_workflow(workflow_id)
    steps = pdb.list_workflow_steps(workflow_id)
    return _workflow_to_response(workflow, steps, pdb)


@router.post("/workflows/{workflow_id}/run-step", response_model=WorkflowResponse)
async def run_workflow_step(slug: str, workflow_id: str):
    """Start execution of the current autonomous step.

    This triggers the WorkflowExecutor to create and run a loop for the
    currently active autonomous step. For interactive steps, this is a no-op.
    """
    from ralphx.core.project import Project
    from ralphx.core.workflow_executor import WorkflowExecutor

    db = Database()
    project = db.get_project(slug)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )

    pdb = ProjectDatabase(project["path"])
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    if workflow["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Workflow must be active to run step. Current status: {workflow['status']}",
        )

    # Get current step
    steps = pdb.list_workflow_steps(workflow_id)
    current_step = None
    for s in steps:
        if s["step_number"] == workflow["current_step"]:
            current_step = s
            break

    if not current_step:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No current step found",
        )

    if current_step["step_type"] != "autonomous":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Current step is '{current_step['step_type']}', not autonomous",
        )

    if current_step["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Step must be active to run. Current status: {current_step['status']}",
        )

    # Create and use WorkflowExecutor to start the autonomous step
    project_obj = Project.from_dict(project)
    executor = WorkflowExecutor(
        project=project_obj,
        db=pdb,
        workflow_id=workflow_id,
    )

    # Start the autonomous step (creates loop and runs it)
    await executor._start_autonomous_step(current_step)

    # Return updated workflow
    workflow = pdb.get_workflow(workflow_id)
    steps = pdb.list_workflow_steps(workflow_id)
    return _workflow_to_response(workflow, steps, pdb)


@router.post("/workflows/{workflow_id}/run-specific-step/{step_number}", response_model=WorkflowResponse)
async def run_specific_step(slug: str, workflow_id: str, step_number: int):
    """Run a specific step out of order.

    This allows jumping to and running any step, not just the current one.
    The step will be activated and its execution started.
    For autonomous steps, this triggers the loop execution.
    """
    import asyncio
    from ralphx.core.project import Project
    from ralphx.core.workflow_executor import WorkflowExecutor

    db = Database()
    project = db.get_project(slug)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )

    pdb = ProjectDatabase(project["path"])
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    # Allow running steps when workflow is draft, active, or paused
    if workflow["status"] not in ("draft", "active", "paused"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot run steps on workflow in status '{workflow['status']}'",
        )

    # Find the target step
    steps = pdb.list_workflow_steps(workflow_id)
    target_step = None
    for s in steps:
        if s["step_number"] == step_number:
            target_step = s
            break

    if not target_step:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Step {step_number} not found in workflow",
        )

    # Update workflow to active status and set current step
    pdb.update_workflow(
        workflow_id,
        status="active",
        current_step=step_number,
    )

    # Start the target step if not already active
    if target_step["status"] != "active":
        pdb.start_workflow_step(target_step["id"])

    # If autonomous step, trigger the loop execution
    if target_step["step_type"] == "autonomous":
        project_obj = Project.from_dict(project)
        executor = WorkflowExecutor(
            project=project_obj,
            db=pdb,
            workflow_id=workflow_id,
        )
        # Refresh step data after starting
        target_step = pdb.get_workflow_step(target_step["id"])
        asyncio.create_task(executor._start_autonomous_step(target_step))

    # Return updated workflow
    workflow = pdb.get_workflow(workflow_id)
    steps = pdb.list_workflow_steps(workflow_id)
    return _workflow_to_response(workflow, steps, pdb)


@router.post("/workflows/{workflow_id}/pause", response_model=WorkflowResponse)
async def pause_workflow(slug: str, workflow_id: str):
    """Pause an active workflow."""
    pdb = _get_project_db(slug)
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    if workflow["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot pause workflow in status '{workflow['status']}'",
        )

    pdb.update_workflow(workflow_id, status="paused")

    workflow = pdb.get_workflow(workflow_id)
    steps = pdb.list_workflow_steps(workflow_id)
    return _workflow_to_response(workflow, steps, pdb)


@router.post("/workflows/{workflow_id}/stop", response_model=WorkflowResponse)
async def stop_workflow(slug: str, workflow_id: str):
    """Stop an active or paused workflow completely.

    This will:
    - Mark all running runs as aborted
    - Stop the workflow entirely
    """
    from datetime import datetime

    pdb = _get_project_db(slug)
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    if workflow["status"] not in ["active", "paused"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot stop workflow in status '{workflow['status']}'",
        )

    # Mark all running/paused runs as aborted
    runs = pdb.list_runs(status=["running", "paused"])
    for run in runs:
        # Only abort runs belonging to this workflow
        if run.get("workflow_id") == workflow_id:
            pdb.update_run(
                run["id"],
                status="aborted",
                completed_at=datetime.utcnow().isoformat(),
                error_message="Workflow stopped by user",
            )

    # Mark workflow as paused (can be restarted later)
    # Using 'paused' instead of 'completed' so user can resume if needed
    pdb.update_workflow(workflow_id, status="paused")

    workflow = pdb.get_workflow(workflow_id)
    steps = pdb.list_workflow_steps(workflow_id)
    return _workflow_to_response(workflow, steps, pdb)


# ============================================================================
# Step CRUD Endpoints
# ============================================================================


@router.post("/workflows/{workflow_id}/steps", response_model=WorkflowStepResponse, status_code=status.HTTP_201_CREATED)
async def create_step(slug: str, workflow_id: str, request: CreateStepRequest):
    """Add a new step to a workflow."""
    pdb = _get_project_db(slug)
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    # Validate allowed_tools if provided (returns deduplicated list)
    validated_tools = validate_allowed_tools(request.allowed_tools)

    # Reject autonomous config fields when creating an interactive step
    if request.step_type == "interactive":
        autonomous_fields_sent = []
        if request.model is not None:
            autonomous_fields_sent.append("model")
        if request.timeout is not None:
            autonomous_fields_sent.append("timeout")
        if request.allowed_tools is not None:
            autonomous_fields_sent.append("allowed_tools")
        if request.max_iterations is not None:
            autonomous_fields_sent.append("max_iterations")
        if request.cooldown_between_iterations is not None:
            autonomous_fields_sent.append("cooldown_between_iterations")
        if request.max_consecutive_errors is not None:
            autonomous_fields_sent.append("max_consecutive_errors")
        if autonomous_fields_sent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot set {autonomous_fields_sent} on interactive step. "
                       f"Use step_type='autonomous' instead.",
            )

    # Build config - include autonomous settings only for autonomous steps
    config: dict[str, Any] = {
        "description": request.description,
        "loopType": request.loop_type,
        "skippable": request.skippable,
    }

    if request.step_type == "autonomous":
        if request.model is not None:
            config["model"] = request.model
        if request.timeout is not None:
            config["timeout"] = request.timeout
        if validated_tools is not None:
            config["allowedTools"] = validated_tools
        # Loop limits
        if request.max_iterations is not None:
            config["max_iterations"] = request.max_iterations
        if request.cooldown_between_iterations is not None:
            config["cooldown_between_iterations"] = request.cooldown_between_iterations
        if request.max_consecutive_errors is not None:
            config["max_consecutive_errors"] = request.max_consecutive_errors

    # Create step atomically (step_number calculated inside transaction)
    step = pdb.create_workflow_step_atomic(
        workflow_id=workflow_id,
        name=request.name,
        step_type=request.step_type,
        config=config,
        status="pending",
    )

    return WorkflowStepResponse(
        id=step["id"],
        workflow_id=step["workflow_id"],
        step_number=step["step_number"],
        name=step["name"],
        step_type=step["step_type"],
        status=step["status"],
        config=step.get("config"),
        loop_name=step.get("loop_name"),
        artifacts=step.get("artifacts"),
        started_at=step.get("started_at"),
        completed_at=step.get("completed_at"),
    )


@router.patch("/workflows/{workflow_id}/steps/{step_id}", response_model=WorkflowStepResponse)
async def update_step(slug: str, workflow_id: str, step_id: int, request: UpdateStepRequest):
    """Update a workflow step."""
    pdb = _get_project_db(slug)
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    step = pdb.get_workflow_step(step_id)
    if not step or step["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Step '{step_id}' not found in workflow '{workflow_id}'",
        )

    # Validate allowed_tools if provided (returns deduplicated list)
    validated_tools = validate_allowed_tools(request.allowed_tools)

    # Determine the effective step_type (may be changing)
    effective_step_type = request.step_type if request.step_type is not None else step["step_type"]

    # Reject autonomous config fields when step is/will be interactive
    if effective_step_type == "interactive":
        autonomous_fields_sent = []
        if request.model is not None:
            autonomous_fields_sent.append("model")
        if request.timeout is not None:
            autonomous_fields_sent.append("timeout")
        if request.allowed_tools is not None:
            autonomous_fields_sent.append("allowed_tools")
        if request.max_iterations is not None:
            autonomous_fields_sent.append("max_iterations")
        if request.cooldown_between_iterations is not None:
            autonomous_fields_sent.append("cooldown_between_iterations")
        if request.max_consecutive_errors is not None:
            autonomous_fields_sent.append("max_consecutive_errors")
        if autonomous_fields_sent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot set {autonomous_fields_sent} on interactive step. "
                       f"Set step_type='autonomous' first or include it in the same request.",
            )

    # Build update kwargs
    updates: dict[str, Any] = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.step_type is not None:
        updates["step_type"] = request.step_type

    # Handle config updates (merge with existing config)
    config_updates: dict[str, Any] = {}
    if request.description is not None:
        config_updates["description"] = request.description
    if request.loop_type is not None:
        config_updates["loopType"] = request.loop_type
    if request.skippable is not None:
        config_updates["skippable"] = request.skippable

    # Include autonomous settings only for autonomous steps
    if effective_step_type == "autonomous":
        if request.model is not None:
            config_updates["model"] = request.model
        if request.timeout is not None:
            config_updates["timeout"] = request.timeout
        if validated_tools is not None:
            config_updates["allowedTools"] = validated_tools
        # Loop limits
        if request.max_iterations is not None:
            config_updates["max_iterations"] = request.max_iterations
        if request.cooldown_between_iterations is not None:
            config_updates["cooldown_between_iterations"] = request.cooldown_between_iterations
        if request.max_consecutive_errors is not None:
            config_updates["max_consecutive_errors"] = request.max_consecutive_errors
    elif request.step_type == "interactive":
        # Changing from autonomous to interactive: clear autonomous-only config
        config_updates["model"] = None
        config_updates["timeout"] = None
        config_updates["allowedTools"] = None
        config_updates["max_iterations"] = None
        config_updates["cooldown_between_iterations"] = None
        config_updates["max_consecutive_errors"] = None

    if config_updates:
        current_config = step.get("config") or {}
        current_config.update(config_updates)
        # Remove None values to keep config clean
        updates["config"] = {k: v for k, v in current_config.items() if v is not None}

    if updates:
        pdb.update_workflow_step(step_id, **updates)

    # Return updated step
    step = pdb.get_workflow_step(step_id)
    return WorkflowStepResponse(
        id=step["id"],
        workflow_id=step["workflow_id"],
        step_number=step["step_number"],
        name=step["name"],
        step_type=step["step_type"],
        status=step["status"],
        config=step.get("config"),
        loop_name=step.get("loop_name"),
        artifacts=step.get("artifacts"),
        started_at=step.get("started_at"),
        completed_at=step.get("completed_at"),
    )


@router.post("/workflows/{workflow_id}/steps/{step_id}/archive", response_model=WorkflowStepResponse)
async def archive_step(slug: str, workflow_id: str, step_id: int):
    """Archive a workflow step (soft delete). Step can be restored later.

    The step keeps its original step_number so it can be restored to
    its original position. Remaining active steps are NOT renumbered.
    """
    pdb = _get_project_db(slug)

    # Validate workflow exists
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    # Validate step exists AND belongs to this workflow (prevents cross-workflow manipulation)
    step = pdb.get_workflow_step(step_id)
    if not step or step["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Step '{step_id}' not found in workflow '{workflow_id}'",
        )

    # Check not already archived
    if step.get("archived_at"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Step is already archived",
        )

    # Archive (does NOT renumber - preserves original position for restore)
    pdb.archive_workflow_step(step_id)

    # Return updated step
    step = pdb.get_workflow_step(step_id)
    return _step_to_response(step, pdb)


@router.post("/workflows/{workflow_id}/steps/{step_id}/restore", response_model=WorkflowStepResponse)
async def restore_step(slug: str, workflow_id: str, step_id: int):
    """Restore an archived step to its original position.

    Returns 409 Conflict if the original position is now occupied by another step.
    """
    pdb = _get_project_db(slug)

    # Validate workflow exists
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    # Validate step exists AND belongs to this workflow
    step = pdb.get_workflow_step(step_id)
    if not step or step["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Step '{step_id}' not found in workflow '{workflow_id}'",
        )

    # Check is archived
    if not step.get("archived_at"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Step is not archived",
        )

    # Restore to original position (raises ValueError if position occupied)
    try:
        restored = pdb.restore_workflow_step(step_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    return _step_to_response(restored, pdb)


@router.get("/workflows/{workflow_id}/steps/archived", response_model=list[WorkflowStepResponse])
async def list_archived_steps(slug: str, workflow_id: str):
    """List archived steps for a workflow (recycle bin view)."""
    pdb = _get_project_db(slug)

    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    archived = pdb.list_archived_steps(workflow_id)
    return [_step_to_response(s, pdb) for s in archived]


@router.delete("/workflows/{workflow_id}/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_step(slug: str, workflow_id: str, step_id: int):
    """Permanently delete a workflow step.

    IMPORTANT: Step must be archived first. This prevents accidental permanent deletion.
    To delete a step:
    1. First archive it: POST /workflows/{workflow_id}/steps/{step_id}/archive
    2. Then delete it: DELETE /workflows/{workflow_id}/steps/{step_id}
    """
    pdb = _get_project_db(slug)
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    step = pdb.get_workflow_step(step_id)
    if not step or step["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Step '{step_id}' not found in workflow '{workflow_id}'",
        )

    # MUST be archived first (safety: prevents accidental permanent deletion)
    if not step.get("archived_at"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot permanently delete active step. Archive it first using POST /workflows/{workflow_id}/steps/{step_id}/archive",
        )

    # Delete step (no renumbering - step number gaps are acceptable to avoid
    # UNIQUE constraint collisions with archived steps)
    pdb.delete_workflow_step_atomic(step_id, workflow_id)


@router.post("/workflows/{workflow_id}/steps/reorder", response_model=WorkflowResponse)
async def reorder_steps(slug: str, workflow_id: str, request: ReorderStepsRequest):
    """Reorder workflow steps."""
    pdb = _get_project_db(slug)
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    # Verify all step IDs belong to this workflow
    existing_steps = pdb.list_workflow_steps(workflow_id)
    existing_ids = {s["id"] for s in existing_steps}

    if set(request.step_ids) != existing_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="step_ids must contain all and only the step IDs in this workflow",
        )

    # Update step numbers atomically to avoid unique constraint violations
    pdb.reorder_workflow_steps_atomic(workflow_id, request.step_ids)

    # Return updated workflow
    workflow = pdb.get_workflow(workflow_id)
    steps = pdb.list_workflow_steps(workflow_id)
    return _workflow_to_response(workflow, steps, pdb)


# ============================================================================
# Workflow Resources Endpoints
# ============================================================================


class WorkflowResourceResponse(BaseModel):
    """Response model for a workflow resource."""

    id: int
    workflow_id: str
    resource_type: str
    name: str
    content: Optional[str] = None
    file_path: Optional[str] = None
    source: Optional[str] = None
    source_id: Optional[int] = None
    enabled: bool
    created_at: str
    updated_at: str


class CreateWorkflowResourceRequest(BaseModel):
    """Request model for creating a workflow resource."""

    resource_type: str = Field(..., pattern=r"^(design_doc|guardrail|input_file|prompt)$")
    name: str = Field(..., min_length=1, max_length=200)
    content: Optional[str] = None
    file_path: Optional[str] = None
    source: Optional[str] = Field(None, pattern=r"^(manual|upload|planning_phase|imported|inherited)$")
    enabled: bool = True


class UpdateWorkflowResourceRequest(BaseModel):
    """Request model for updating a workflow resource."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = None
    file_path: Optional[str] = None
    enabled: Optional[bool] = None
    expected_updated_at: Optional[str] = None  # For optimistic locking


class ResourceVersionResponse(BaseModel):
    """Response model for a single resource version."""

    id: int
    workflow_resource_id: int
    version_number: int
    content: Optional[str] = None
    name: Optional[str] = None
    created_at: str


class VersionListResponse(BaseModel):
    """Paginated response for version list."""

    versions: list[ResourceVersionResponse]
    total: int
    limit: int
    offset: int


@router.get("/workflows/{workflow_id}/resources", response_model=list[WorkflowResourceResponse])
async def list_workflow_resources(
    slug: str,
    workflow_id: str,
    resource_type: Optional[str] = None,
    enabled_only: bool = False,
):
    """List resources for a workflow."""
    pdb = _get_project_db(slug)

    # Verify workflow exists
    if not pdb.get_workflow(workflow_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    resources = pdb.list_workflow_resources(
        workflow_id, resource_type=resource_type, enabled_only=enabled_only
    )
    return [WorkflowResourceResponse(**r) for r in resources]


@router.post(
    "/workflows/{workflow_id}/resources",
    response_model=WorkflowResourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow_resource(
    slug: str, workflow_id: str, request: CreateWorkflowResourceRequest
):
    """Create a new resource for a workflow."""
    pdb = _get_project_db(slug)

    # Verify workflow exists
    if not pdb.get_workflow(workflow_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    resource = pdb.create_workflow_resource(
        workflow_id=workflow_id,
        resource_type=request.resource_type,
        name=request.name,
        content=request.content,
        file_path=request.file_path,
        source=request.source or "manual",
        enabled=request.enabled,
    )
    return WorkflowResourceResponse(**resource)


@router.get("/workflows/{workflow_id}/resources/{resource_id}", response_model=WorkflowResourceResponse)
async def get_workflow_resource(slug: str, workflow_id: str, resource_id: int):
    """Get a specific workflow resource."""
    pdb = _get_project_db(slug)

    resource = pdb.get_workflow_resource(resource_id)
    if not resource or resource["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{resource_id}' not found in workflow '{workflow_id}'",
        )
    return WorkflowResourceResponse(**resource)


@router.patch("/workflows/{workflow_id}/resources/{resource_id}", response_model=WorkflowResourceResponse)
async def update_workflow_resource(
    slug: str, workflow_id: str, resource_id: int, request: UpdateWorkflowResourceRequest
):
    """Update a workflow resource.

    Supports optimistic locking via expected_updated_at. If provided and the
    resource has been modified since that timestamp, returns 409 Conflict.
    """
    pdb = _get_project_db(slug)

    resource = pdb.get_workflow_resource(resource_id)
    if not resource or resource["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{resource_id}' not found in workflow '{workflow_id}'",
        )

    updated = pdb.update_workflow_resource(
        resource_id,
        name=request.name,
        content=request.content,
        file_path=request.file_path,
        enabled=request.enabled,
        expected_updated_at=request.expected_updated_at,
    )

    # Check for optimistic locking conflict
    if updated.get("conflict"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resource was modified in another session. Reload to see the latest version.",
        )

    return WorkflowResourceResponse(**updated)


@router.delete("/workflows/{workflow_id}/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow_resource(slug: str, workflow_id: str, resource_id: int):
    """Delete a workflow resource."""
    pdb = _get_project_db(slug)

    resource = pdb.get_workflow_resource(resource_id)
    if not resource or resource["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{resource_id}' not found in workflow '{workflow_id}'",
        )

    pdb.delete_workflow_resource(resource_id)


@router.get(
    "/workflows/{workflow_id}/resources/{resource_id}/versions",
    response_model=VersionListResponse,
)
async def list_resource_versions(
    slug: str,
    workflow_id: str,
    resource_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List version history for a workflow resource.

    Returns paginated list of previous versions, newest first.
    """
    pdb = _get_project_db(slug)

    # Verify resource exists and belongs to workflow
    resource = pdb.get_workflow_resource(resource_id)
    if not resource or resource["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{resource_id}' not found in workflow '{workflow_id}'",
        )

    versions, total = pdb.list_resource_versions(resource_id, limit=limit, offset=offset)

    return VersionListResponse(
        versions=[ResourceVersionResponse(**v) for v in versions],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/workflows/{workflow_id}/resources/{resource_id}/versions/{version_id}/restore",
    response_model=WorkflowResourceResponse,
)
async def restore_resource_version(
    slug: str, workflow_id: str, resource_id: int, version_id: int
):
    """Restore a workflow resource to a previous version.

    Creates a new version snapshot of the current state, then overwrites
    the resource with the old version's content and name.
    """
    pdb = _get_project_db(slug)

    # Verify resource exists and belongs to workflow
    resource = pdb.get_workflow_resource(resource_id)
    if not resource or resource["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{resource_id}' not found in workflow '{workflow_id}'",
        )

    # Verify version exists
    version = pdb.get_resource_version(version_id)
    if not version or version["workflow_resource_id"] != resource_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version '{version_id}' not found for resource '{resource_id}'",
        )

    # Restore the version
    restored = pdb.restore_resource_version(resource_id, version_id)
    if not restored:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to restore version",
        )

    return WorkflowResourceResponse(**restored)


@router.post("/workflows/{workflow_id}/resources/import/{project_resource_id}", response_model=WorkflowResourceResponse)
async def import_project_resource_to_workflow(
    slug: str, workflow_id: str, project_resource_id: int
):
    """Import a project resource into a workflow.

    Creates a copy of the project resource as a workflow resource.
    """
    pdb = _get_project_db(slug)

    # Verify workflow exists
    if not pdb.get_workflow(workflow_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    # Get project resource
    project_resource = pdb.get_project_resource(project_resource_id)
    if not project_resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project resource '{project_resource_id}' not found",
        )

    # Create workflow resource from project resource
    resource = pdb.create_workflow_resource(
        workflow_id=workflow_id,
        resource_type=project_resource["resource_type"],
        name=project_resource["name"],
        content=project_resource.get("content"),
        file_path=project_resource.get("file_path"),
        source="imported",
        source_id=project_resource_id,
    )
    return WorkflowResourceResponse(**resource)


# ============================================================================
# Step Resources Endpoints (Per-Step Resource Overrides)
# ============================================================================


class StepResourceResponse(BaseModel):
    """Response model for a step resource."""

    id: int
    step_id: int
    workflow_resource_id: Optional[int] = None
    resource_type: Optional[str] = None
    name: Optional[str] = None
    content: Optional[str] = None
    file_path: Optional[str] = None
    mode: str
    enabled: bool
    priority: int
    created_at: str
    updated_at: str


class EffectiveResourceResponse(BaseModel):
    """Response model for an effective resource (after merge)."""

    id: int
    resource_type: str
    name: str
    content: Optional[str] = None
    file_path: Optional[str] = None
    source: str  # 'workflow', 'step_override', 'step_add'
    priority: Optional[int] = None


class CreateStepResourceRequest(BaseModel):
    """Request model for creating a step resource."""

    mode: str = Field(..., pattern=r"^(override|disable|add)$")
    workflow_resource_id: Optional[int] = None
    resource_type: Optional[str] = Field(None, pattern=r"^(design_doc|guardrail|input_file|prompt)$")
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = None
    file_path: Optional[str] = None
    enabled: bool = True
    priority: int = 0


class UpdateStepResourceRequest(BaseModel):
    """Request model for updating a step resource."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = None
    file_path: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None


class PromptSectionResponse(BaseModel):
    """Response model for a prompt section."""

    position: str
    content: str
    resource_name: Optional[str] = None
    resource_type: Optional[str] = None


class PreviewPromptResponse(BaseModel):
    """Response model for step prompt preview."""

    prompt_sections: list[PromptSectionResponse]
    resources_used: list[str]
    total_chars: int
    total_tokens_estimate: int


@router.get(
    "/workflows/{workflow_id}/steps/{step_id}/resources",
    response_model=list[StepResourceResponse],
)
async def list_step_resources(slug: str, workflow_id: str, step_id: int):
    """List step resource configurations for a step."""
    pdb = _get_project_db(slug)

    # Verify workflow and step exist
    if not pdb.get_workflow(workflow_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    step = pdb.get_workflow_step(step_id)
    if not step or step["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Step '{step_id}' not found in workflow '{workflow_id}'",
        )

    resources = pdb.list_step_resources(step_id)
    return [StepResourceResponse(**r) for r in resources]


@router.get(
    "/workflows/{workflow_id}/steps/{step_id}/resources/effective",
    response_model=list[EffectiveResourceResponse],
)
async def get_effective_resources(slug: str, workflow_id: str, step_id: int):
    """Get effective resources for a step after merging workflow and step configs."""
    pdb = _get_project_db(slug)

    # Verify workflow and step exist
    if not pdb.get_workflow(workflow_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    step = pdb.get_workflow_step(step_id)
    if not step or step["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Step '{step_id}' not found in workflow '{workflow_id}'",
        )

    effective = pdb.get_effective_resources_for_step(step_id, workflow_id)
    return [EffectiveResourceResponse(**r) for r in effective]


@router.post(
    "/workflows/{workflow_id}/steps/{step_id}/resources",
    response_model=StepResourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_step_resource(
    slug: str, workflow_id: str, step_id: int, request: CreateStepResourceRequest
):
    """Create a step resource configuration."""
    pdb = _get_project_db(slug)

    # Verify workflow and step exist
    if not pdb.get_workflow(workflow_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    step = pdb.get_workflow_step(step_id)
    if not step or step["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Step '{step_id}' not found in workflow '{workflow_id}'",
        )

    # Validate workflow_resource_id if provided
    if request.workflow_resource_id:
        wr = pdb.get_workflow_resource(request.workflow_resource_id)
        if not wr or wr["workflow_id"] != workflow_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow resource '{request.workflow_resource_id}' not found",
            )

    try:
        resource = pdb.create_step_resource(
            step_id=step_id,
            mode=request.mode,
            workflow_resource_id=request.workflow_resource_id,
            resource_type=request.resource_type,
            name=request.name,
            content=request.content,
            file_path=request.file_path,
            enabled=request.enabled,
            priority=request.priority,
        )
        return StepResourceResponse(**resource)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.patch(
    "/workflows/{workflow_id}/steps/{step_id}/resources/{resource_id}",
    response_model=StepResourceResponse,
)
async def update_step_resource(
    slug: str,
    workflow_id: str,
    step_id: int,
    resource_id: int,
    request: UpdateStepResourceRequest,
):
    """Update a step resource configuration."""
    pdb = _get_project_db(slug)

    # Verify workflow and step exist
    if not pdb.get_workflow(workflow_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    step = pdb.get_workflow_step(step_id)
    if not step or step["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Step '{step_id}' not found in workflow '{workflow_id}'",
        )

    resource = pdb.get_step_resource(resource_id)
    if not resource or resource["step_id"] != step_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Step resource '{resource_id}' not found",
        )

    updated = pdb.update_step_resource(
        resource_id,
        name=request.name,
        content=request.content,
        file_path=request.file_path,
        enabled=request.enabled,
        priority=request.priority,
    )
    return StepResourceResponse(**updated)


@router.delete(
    "/workflows/{workflow_id}/steps/{step_id}/resources/{resource_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_step_resource(
    slug: str, workflow_id: str, step_id: int, resource_id: int
):
    """Delete a step resource configuration."""
    pdb = _get_project_db(slug)

    # Verify workflow and step exist
    if not pdb.get_workflow(workflow_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    step = pdb.get_workflow_step(step_id)
    if not step or step["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Step '{step_id}' not found in workflow '{workflow_id}'",
        )

    resource = pdb.get_step_resource(resource_id)
    if not resource or resource["step_id"] != step_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Step resource '{resource_id}' not found",
        )

    pdb.delete_step_resource(resource_id)


@router.post(
    "/workflows/{workflow_id}/steps/{step_id}/resources/disable/{workflow_resource_id}",
    response_model=StepResourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def disable_inherited_resource(
    slug: str, workflow_id: str, step_id: int, workflow_resource_id: int
):
    """Disable an inherited workflow resource for this step."""
    pdb = _get_project_db(slug)

    # Verify workflow and step exist
    if not pdb.get_workflow(workflow_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    step = pdb.get_workflow_step(step_id)
    if not step or step["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Step '{step_id}' not found in workflow '{workflow_id}'",
        )

    # Verify workflow resource exists
    wr = pdb.get_workflow_resource(workflow_resource_id)
    if not wr or wr["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow resource '{workflow_resource_id}' not found",
        )

    # Check if already disabled
    existing = pdb.get_step_resource_by_workflow_resource(step_id, workflow_resource_id)
    if existing:
        if existing["mode"] == "disable":
            return StepResourceResponse(**existing)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resource already has a step override. Delete it first.",
        )

    resource = pdb.create_step_resource(
        step_id=step_id,
        mode="disable",
        workflow_resource_id=workflow_resource_id,
    )
    return StepResourceResponse(**resource)


@router.delete(
    "/workflows/{workflow_id}/steps/{step_id}/resources/disable/{workflow_resource_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def enable_inherited_resource(
    slug: str, workflow_id: str, step_id: int, workflow_resource_id: int
):
    """Re-enable an inherited workflow resource for this step (remove disable)."""
    pdb = _get_project_db(slug)

    # Verify workflow and step exist
    if not pdb.get_workflow(workflow_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    step = pdb.get_workflow_step(step_id)
    if not step or step["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Step '{step_id}' not found in workflow '{workflow_id}'",
        )

    # Find and delete the disable record
    existing = pdb.get_step_resource_by_workflow_resource(step_id, workflow_resource_id)
    if not existing or existing["mode"] != "disable":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource is not disabled for this step",
        )

    pdb.delete_step_resource(existing["id"])


@router.get(
    "/workflows/{workflow_id}/steps/{step_id}/preview-prompt",
    response_model=PreviewPromptResponse,
)
async def preview_step_prompt(slug: str, workflow_id: str, step_id: int):
    """Preview what Claude will receive for this step.

    Shows the assembled prompt sections from effective resources.
    """
    pdb = _get_project_db(slug)

    # Verify workflow and step exist
    if not pdb.get_workflow(workflow_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    step = pdb.get_workflow_step(step_id)
    if not step or step["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Step '{step_id}' not found in workflow '{workflow_id}'",
        )

    # Only autonomous steps have prompts to preview
    if step["step_type"] != "autonomous":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only autonomous steps have prompt previews",
        )

    # Get effective resources
    effective = pdb.get_effective_resources_for_step(step_id, workflow_id)

    # Build prompt sections
    sections: list[PromptSectionResponse] = []
    resources_used: list[str] = []
    total_chars = 0

    for res in effective:
        content = res.get("content") or ""
        if not content and res.get("file_path"):
            # TODO: Read file content if file_path is set
            content = f"[Content from file: {res['file_path']}]"

        if content:
            resource_type = res.get("resource_type", "unknown")
            # Determine injection position based on type
            if resource_type == "design_doc":
                position = "after_design_doc"
            elif resource_type == "guardrail":
                position = "before_task"
            elif resource_type == "prompt":
                position = "before_prompt"
            else:
                position = "after_design_doc"

            sections.append(PromptSectionResponse(
                position=position,
                content=content,
                resource_name=res.get("name"),
                resource_type=resource_type,
            ))
            resources_used.append(res.get("name", "Unknown"))
            total_chars += len(content)

    # Rough token estimate (4 chars per token on average)
    total_tokens_estimate = total_chars // 4

    return PreviewPromptResponse(
        prompt_sections=sections,
        resources_used=resources_used,
        total_chars=total_chars,
        total_tokens_estimate=total_tokens_estimate,
    )
