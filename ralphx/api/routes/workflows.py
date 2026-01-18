"""Workflow API routes for RalphX."""

import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ralphx.core.database import Database
from ralphx.core.project_db import ProjectDatabase

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================


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
    steps: list[WorkflowStepResponse] = []


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
    model: Optional[str] = Field(None, pattern=r"^(sonnet|opus|haiku)$")
    timeout: Optional[int] = Field(None, ge=60, le=7200)  # 1min to 2hr
    allowed_tools: Optional[list[str]] = None


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
    model: Optional[str] = Field(None, pattern=r"^(sonnet|opus|haiku)$")
    timeout: Optional[int] = Field(None, ge=60, le=7200)  # 1min to 2hr
    allowed_tools: Optional[list[str]] = None


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
    workflow: dict, steps: list[dict]
) -> WorkflowResponse:
    """Convert workflow and steps to response model."""
    return WorkflowResponse(
        id=workflow["id"],
        template_id=workflow.get("template_id"),
        name=workflow["name"],
        namespace=workflow["namespace"],
        status=workflow["status"],
        current_step=workflow["current_step"],
        created_at=workflow["created_at"],
        updated_at=workflow["updated_at"],
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
            )
            for s in steps
        ],
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
async def list_workflows(slug: str, status_filter: Optional[str] = None):
    """List all workflows for a project."""
    pdb = _get_project_db(slug)
    workflows = pdb.list_workflows(status=status_filter)
    result = []
    for w in workflows:
        steps = pdb.list_workflow_steps(w["id"])
        result.append(_workflow_to_response(w, steps))
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

    return _workflow_to_response(workflow, created_steps)


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
    return _workflow_to_response(workflow, steps)


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
    return _workflow_to_response(workflow, steps)


@router.delete("/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(slug: str, workflow_id: str):
    """Delete a workflow."""
    pdb = _get_project_db(slug)
    if not pdb.get_workflow(workflow_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
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
    return _workflow_to_response(workflow, steps)


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
    return _workflow_to_response(workflow, steps)


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
    return _workflow_to_response(workflow, steps)


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
    return _workflow_to_response(workflow, steps)


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
    elif request.step_type == "interactive":
        # Changing from autonomous to interactive: clear autonomous-only config
        config_updates["model"] = None
        config_updates["timeout"] = None
        config_updates["allowedTools"] = None

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


@router.delete("/workflows/{workflow_id}/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_step(slug: str, workflow_id: str, step_id: int):
    """Delete a workflow step."""
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

    # Delete step and renumber atomically in a single transaction
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
    return _workflow_to_response(workflow, steps)


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
    """Update a workflow resource."""
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
