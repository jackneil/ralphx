"""Workflow MCP tools.

Tools for managing workflows and workflow steps:
- ralphx_list_workflows: List workflows
- ralphx_get_workflow: Get workflow details
- ralphx_create_workflow: Create workflow from template
- ralphx_update_workflow: Update workflow properties
- ralphx_start_workflow: Start workflow execution
- ralphx_pause_workflow: Pause workflow
- ralphx_stop_workflow: Stop workflow
- ralphx_advance_workflow: Advance to next step
- ralphx_archive_workflow: Archive workflow
- ralphx_restore_workflow: Restore archived workflow
- ralphx_list_workflow_templates: List templates
- ralphx_create_workflow_step: Create step
- ralphx_update_workflow_step: Update step
- ralphx_archive_workflow_step: Archive step
- ralphx_restore_workflow_step: Restore step
- ralphx_reorder_workflow_steps: Reorder steps
- ralphx_run_workflow_step: Run current step
"""

import asyncio
import uuid
from typing import Any, Coroutine, Optional, TypeVar

from ralphx.mcp.base import (
    MCPError,
    PaginatedResult,
    ToolDefinition,
    ToolError,
    make_schema,
    prop_array,
    prop_bool,
    prop_enum,
    prop_int,
    prop_string,
    validate_pagination,
)
from ralphx.mcp.tools.projects import get_manager

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Safely run an async coroutine from synchronous code.

    Creates a new event loop, runs the coroutine, and ensures cleanup.
    This is safe to call from MCP tool handlers which run synchronously.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            asyncio.set_event_loop(None)
            loop.close()


def list_workflows(
    slug: str,
    status: Optional[str] = None,
    include_archived: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List workflows for a project with filtering and pagination."""
    limit, offset = validate_pagination(limit, offset)
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    workflows = project_db.list_workflows(
        status=status,
        include_archived=include_archived,
    )

    total = len(workflows)
    paginated = workflows[offset : offset + limit]

    return PaginatedResult(
        items=[
            {
                "id": w["id"],
                "name": w["name"],
                "status": w["status"],
                "current_step": w["current_step"],
                "template_id": w.get("template_id"),
                "archived_at": w.get("archived_at"),
                "created_at": w["created_at"],
            }
            for w in paginated
        ],
        total=total,
        limit=limit,
        offset=offset,
    ).to_dict()


def get_workflow(slug: str, workflow_id: str) -> dict:
    """Get detailed workflow information including steps."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    workflow = project_db.get_workflow(workflow_id)

    if not workflow:
        raise ToolError.workflow_not_found(workflow_id)

    steps = project_db.list_workflow_steps(workflow_id)

    # Get item counts per step
    item_counts = {}
    try:
        item_counts = project_db.get_workflow_item_counts(workflow_id)
    except Exception:
        pass

    return {
        "id": workflow["id"],
        "name": workflow["name"],
        "status": workflow["status"],
        "current_step": workflow["current_step"],
        "template_id": workflow.get("template_id"),
        "archived_at": workflow.get("archived_at"),
        "created_at": workflow["created_at"],
        "updated_at": workflow.get("updated_at"),
        "steps": [
            {
                "id": s["id"],
                "step_number": s["step_number"],
                "name": s["name"],
                "step_type": s["step_type"],
                "status": s["status"],
                "loop_name": s.get("loop_name"),
                "config": s.get("config"),
                "item_count": item_counts.get(s["id"], {}).get("total", 0),
            }
            for s in steps
        ],
    }


def create_workflow(
    slug: str,
    name: str,
    template_id: Optional[str] = None,
) -> dict:
    """Create a new workflow, optionally from a template."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    # Generate unique ID
    workflow_id = f"wf-{uuid.uuid4().hex[:12]}"

    # Get template steps if specified
    template_steps = []
    if template_id:
        project_db.seed_workflow_templates_if_empty()
        template = project_db.get_workflow_template(template_id)
        if not template:
            raise MCPError(
                error_code=ToolError.TEMPLATE_NOT_FOUND,
                message=f"Template not found: {template_id}",
                details={
                    "template_id": template_id,
                    "suggestion": "Run ralphx_list_workflow_templates to see available templates",
                },
            )
        template_steps = template.get("phases", [])

    try:
        project_db.create_workflow(
            id=workflow_id,
            name=name,
            template_id=template_id,
            status="draft",
        )

        # Create steps from template
        for step_def in template_steps:
            # Look up processing_type config if specified
            processing_type = step_def.get("processing_type")
            if processing_type and processing_type in PROCESSING_TYPES:
                type_config = PROCESSING_TYPES[processing_type]
                step_type = type_config["step_type"]
                config = {
                    **type_config["config"],
                    "description": step_def.get("description"),
                    "skippable": step_def.get("skippable", False),
                    "inputs": step_def.get("inputs", []),
                    "outputs": step_def.get("outputs", []),
                }
                if step_def.get("skipCondition"):
                    config["skipCondition"] = step_def["skipCondition"]
            else:
                # Fallback for legacy templates without processing_type
                step_type = step_def.get("type", "autonomous")
                config = {
                    "description": step_def.get("description"),
                    "loopType": step_def.get("loopType"),
                    "skippable": step_def.get("skippable", False),
                }

            project_db.create_workflow_step(
                workflow_id=workflow_id,
                step_number=step_def["number"],
                name=step_def["name"],
                step_type=step_type,
                config=config,
                status="pending",
            )
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to create workflow: {e}",
            details={"name": name},
        )

    return {
        "id": workflow_id,
        "name": name,
        "template_id": template_id,
        "step_count": len(template_steps),
        "message": "Workflow created",
    }


def update_workflow(
    slug: str,
    workflow_id: str,
    name: Optional[str] = None,
    status: Optional[str] = None,
    current_step: Optional[int] = None,
) -> dict:
    """Update workflow properties."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    workflow = project_db.get_workflow(workflow_id)

    if not workflow:
        raise ToolError.workflow_not_found(workflow_id)

    updates = {}
    if name is not None:
        updates["name"] = name
    if status is not None:
        valid_statuses = ["draft", "active", "paused", "completed", "failed"]
        if status not in valid_statuses:
            raise ToolError.validation_error(
                f"Invalid status: {status}. Must be one of: {valid_statuses}",
            )
        updates["status"] = status
    if current_step is not None:
        updates["current_step"] = current_step

    if not updates:
        return {
            "id": workflow_id,
            "message": "No changes specified",
        }

    try:
        project_db.update_workflow(workflow_id, **updates)
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to update workflow: {e}",
            details={"workflow_id": workflow_id},
        )

    return {
        "id": workflow_id,
        "updated_fields": list(updates.keys()),
        "message": "Workflow updated",
    }


def start_workflow(slug: str, workflow_id: str) -> dict:
    """Start a workflow execution."""
    from ralphx.core.workflow_executor import WorkflowExecutor

    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    workflow = project_db.get_workflow(workflow_id)

    if not workflow:
        raise ToolError.workflow_not_found(workflow_id)

    if workflow["status"] == "active":
        raise ToolError.concurrency_error(
            "Workflow is already active",
            {"workflow_id": workflow_id, "status": workflow["status"]},
        )

    executor = WorkflowExecutor(
        project=project,
        db=project_db,
        workflow_id=workflow_id,
    )

    try:
        result = run_async(executor.start_workflow())
    except MCPError:
        raise
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to start workflow: {e}",
            details={"workflow_id": workflow_id},
        )

    return {
        "id": result["id"],
        "status": result["status"],
        "current_step": result["current_step"],
        "message": "Workflow started",
    }


def pause_workflow(slug: str, workflow_id: str) -> dict:
    """Pause a running workflow."""
    from ralphx.core.workflow_executor import WorkflowExecutor

    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    workflow = project_db.get_workflow(workflow_id)

    if not workflow:
        raise ToolError.workflow_not_found(workflow_id)

    if workflow["status"] != "active":
        raise ToolError.validation_error(
            f"Cannot pause workflow with status: {workflow['status']}",
            {"workflow_id": workflow_id, "status": workflow["status"]},
        )

    executor = WorkflowExecutor(
        project=project,
        db=project_db,
        workflow_id=workflow_id,
    )

    try:
        result = run_async(executor.pause_workflow())
    except MCPError:
        raise
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to pause workflow: {e}",
            details={"workflow_id": workflow_id},
        )

    return {
        "id": result["id"],
        "status": result["status"],
        "message": "Workflow paused",
    }


def stop_workflow(slug: str, workflow_id: str) -> dict:
    """Stop a workflow (different from pause - terminates all running loops)."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    workflow = project_db.get_workflow(workflow_id)

    if not workflow:
        raise ToolError.workflow_not_found(workflow_id)

    try:
        # Stop any running loops for this workflow
        runs = project_db.list_runs(workflow_id=workflow_id, status="running")
        stopped_runs = []
        for run in runs:
            project_db.update_run(run["id"], status="aborted")
            stopped_runs.append(run["id"])

        # Update workflow status
        project_db.update_workflow(workflow_id, status="paused")
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to stop workflow: {e}",
            details={"workflow_id": workflow_id},
        )

    return {
        "id": workflow_id,
        "status": "paused",
        "stopped_runs": stopped_runs,
        "message": "Workflow stopped",
    }


def advance_workflow(slug: str, workflow_id: str) -> dict:
    """Advance a workflow to the next step by completing the current step."""
    from ralphx.core.workflow_executor import WorkflowExecutor

    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    workflow = project_db.get_workflow(workflow_id)

    if not workflow:
        raise ToolError.workflow_not_found(workflow_id)

    current_step = project_db.get_workflow_step_by_number(
        workflow_id, workflow["current_step"]
    )
    if not current_step:
        raise ToolError.step_not_found(f"step {workflow['current_step']}")

    executor = WorkflowExecutor(
        project=project,
        db=project_db,
        workflow_id=workflow_id,
    )

    try:
        run_async(executor.complete_step(current_step["id"]))
    except MCPError:
        raise
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to advance workflow: {e}",
            details={"workflow_id": workflow_id},
        )

    # Get updated workflow
    workflow = project_db.get_workflow(workflow_id)
    return {
        "id": workflow["id"],
        "current_step": workflow["current_step"],
        "status": workflow["status"],
        "message": f"Advanced to step {workflow['current_step']}",
    }


def archive_workflow(slug: str, workflow_id: str) -> dict:
    """Archive a workflow (soft delete)."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    workflow = project_db.get_workflow(workflow_id)

    if not workflow:
        raise ToolError.workflow_not_found(workflow_id)

    if workflow.get("archived_at"):
        return {
            "id": workflow_id,
            "message": "Workflow is already archived",
        }

    try:
        project_db.archive_workflow(workflow_id)
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to archive workflow: {e}",
            details={"workflow_id": workflow_id},
        )

    return {
        "id": workflow_id,
        "message": "Workflow archived",
    }


def restore_workflow(slug: str, workflow_id: str) -> dict:
    """Restore an archived workflow."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    workflow = project_db.get_workflow(workflow_id)

    if not workflow:
        raise ToolError.workflow_not_found(workflow_id)

    if not workflow.get("archived_at"):
        return {
            "id": workflow_id,
            "message": "Workflow is not archived",
        }

    try:
        project_db.restore_workflow(workflow_id)
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to restore workflow: {e}",
            details={"workflow_id": workflow_id},
        )

    return {
        "id": workflow_id,
        "message": "Workflow restored",
    }


def list_workflow_templates(slug: str) -> dict:
    """List available workflow templates."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    project_db.seed_workflow_templates_if_empty()
    templates = project_db.list_workflow_templates()

    return {
        "templates": [
            {
                "id": t["id"],
                "name": t["name"],
                "description": t.get("description", ""),
                "step_count": len(t.get("phases", [])),
            }
            for t in templates
        ]
    }


# Workflow Step tools

# Processing type configurations - matches frontend StepSettings.tsx
PROCESSING_TYPES = {
    "design_doc": {
        "label": "Build Design Doc",
        "description": "Interactive chat with web research to create a design document",
        "step_type": "interactive",
        "config": {
            "loopType": "design_doc",
            "allowedTools": ["WebSearch", "WebFetch", "Bash", "Read", "Glob", "Grep"],
            "model": "opus",
            "timeout": 300,
        },
    },
    "extractgen_requirements": {
        "label": "Generate Stories (Extract)",
        "description": "Extract user stories from design documents",
        "step_type": "autonomous",
        "config": {
            "loopType": "generator",
            "template": "extractgen_requirements",
            "allowedTools": ["WebSearch", "WebFetch"],
            "model": "opus",
            "timeout": 600,
            "max_iterations": 100,
            "cooldown_between_iterations": 5,
            "max_consecutive_errors": 5,
        },
    },
    "webgen_requirements": {
        "label": "Generate Stories (WebSearch)",
        "description": "Discover missing requirements via web research",
        "step_type": "autonomous",
        "config": {
            "loopType": "generator",
            "template": "webgen_requirements",
            "allowedTools": ["WebSearch", "WebFetch"],
            "model": "opus",
            "timeout": 900,
            "max_iterations": 15,
            "cooldown_between_iterations": 15,
            "max_consecutive_errors": 3,
        },
    },
    "implementation": {
        "label": "Implementation",
        "description": "Consumes stories and commits code to git",
        "step_type": "autonomous",
        "config": {
            "loopType": "consumer",
            "template": "implementation",
            "allowedTools": ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
            "model": "opus",
            "timeout": 1800,
            "max_iterations": 50,
            "cooldown_between_iterations": 5,
            "max_consecutive_errors": 3,
        },
    },
}


def create_workflow_step(
    slug: str,
    workflow_id: str,
    step_name: str,
    processing_type: str,
    step_number: Optional[int] = None,
    loop_name: Optional[str] = None,
) -> dict:
    """Create a new step in a workflow from a processing type.

    Processing types:
    - design_doc: Interactive chat to build a design document (with web search)
    - extractgen_requirements: Extract user stories from design documents
    - webgen_requirements: Discover requirements via web research
    - implementation: Implement stories and commit code

    If step_number is not provided, appends to end.
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    workflow = project_db.get_workflow(workflow_id)

    if not workflow:
        raise ToolError.workflow_not_found(workflow_id)

    if processing_type not in PROCESSING_TYPES:
        raise ToolError.validation_error(
            f"Invalid processing_type: {processing_type}. "
            f"Must be one of: {list(PROCESSING_TYPES.keys())}",
        )

    # Get the processing type configuration
    type_config = PROCESSING_TYPES[processing_type]
    step_type = type_config["step_type"]
    config = {**type_config["config"]}  # Copy to avoid mutation

    try:
        if step_number is None:
            # Use atomic creation that auto-calculates step number
            step = project_db.create_workflow_step_atomic(
                workflow_id=workflow_id,
                name=step_name,
                step_type=step_type,
                config=config,
                loop_name=loop_name,
            )
        else:
            step = project_db.create_workflow_step(
                workflow_id=workflow_id,
                step_number=step_number,
                name=step_name,
                step_type=step_type,
                config=config,
                loop_name=loop_name,
                status="pending",
            )
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to create step: {e}",
            details={"workflow_id": workflow_id},
        )

    return {
        "id": step["id"],
        "step_number": step["step_number"],
        "name": step["name"],
        "step_type": step["step_type"],
        "processing_type": processing_type,
        "config": config,
        "message": f"Step created with {type_config['label']} configuration",
    }


def update_workflow_step(
    slug: str,
    step_id: int,
    name: Optional[str] = None,
    status: Optional[str] = None,
    config: Optional[dict] = None,
    loop_name: Optional[str] = None,
) -> dict:
    """Update a workflow step's properties."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    step = project_db.get_workflow_step(step_id)

    if not step:
        raise ToolError.step_not_found(step_id)

    updates = {}
    if name is not None:
        updates["name"] = name
    if status is not None:
        valid_statuses = ["pending", "active", "completed", "skipped", "failed"]
        if status not in valid_statuses:
            raise ToolError.validation_error(
                f"Invalid status: {status}. Must be one of: {valid_statuses}",
            )
        updates["status"] = status
    if config is not None:
        updates["config"] = config
    if loop_name is not None:
        updates["loop_name"] = loop_name

    if not updates:
        return {
            "id": step_id,
            "message": "No changes specified",
        }

    try:
        project_db.update_workflow_step(step_id, **updates)
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to update step: {e}",
            details={"step_id": step_id},
        )

    return {
        "id": step_id,
        "updated_fields": list(updates.keys()),
        "message": "Step updated",
    }


def archive_workflow_step(slug: str, step_id: int) -> dict:
    """Archive a workflow step (soft delete)."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    step = project_db.get_workflow_step(step_id)

    if not step:
        raise ToolError.step_not_found(step_id)

    try:
        project_db.archive_workflow_step(step_id)
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to archive step: {e}",
            details={"step_id": step_id},
        )

    return {
        "id": step_id,
        "message": "Step archived",
    }


def restore_workflow_step(slug: str, step_id: int) -> dict:
    """Restore an archived workflow step."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    # Verify step exists before attempting restore
    step = project_db.get_workflow_step(step_id)
    if not step:
        raise ToolError.step_not_found(step_id)

    try:
        project_db.restore_workflow_step(step_id)
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to restore step: {e}",
            details={"step_id": step_id},
        )

    return {
        "id": step_id,
        "message": "Step restored",
    }


def reorder_workflow_steps(
    slug: str,
    workflow_id: str,
    step_order: list[int],
) -> dict:
    """Reorder workflow steps.

    Args:
        slug: Project slug
        workflow_id: Workflow ID
        step_order: List of step IDs in desired order
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    workflow = project_db.get_workflow(workflow_id)

    if not workflow:
        raise ToolError.workflow_not_found(workflow_id)

    try:
        # Update step numbers according to new order
        for idx, step_id in enumerate(step_order, start=1):
            project_db.update_workflow_step(step_id, step_number=idx)
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to reorder steps: {e}",
            details={"workflow_id": workflow_id},
        )

    return {
        "workflow_id": workflow_id,
        "step_order": step_order,
        "message": "Steps reordered",
    }


def run_workflow_step(slug: str, workflow_id: str) -> dict:
    """Run the current step of a workflow."""
    from ralphx.core.workflow_executor import WorkflowExecutor

    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    workflow = project_db.get_workflow(workflow_id)

    if not workflow:
        raise ToolError.workflow_not_found(workflow_id)

    current_step = project_db.get_workflow_step_by_number(
        workflow_id, workflow["current_step"]
    )
    if not current_step:
        raise ToolError.step_not_found(f"step {workflow['current_step']}")

    executor = WorkflowExecutor(
        project=project,
        db=project_db,
        workflow_id=workflow_id,
    )

    try:
        run_async(executor._run_step(current_step["id"]))
    except MCPError:
        raise
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to run step: {e}",
            details={"workflow_id": workflow_id, "step_id": current_step["id"]},
        )

    return {
        "workflow_id": workflow_id,
        "step_id": current_step["id"],
        "step_name": current_step["name"],
        "message": "Step execution started",
    }


def get_workflow_tools() -> list[ToolDefinition]:
    """Get all workflow tool definitions."""
    return [
        # Workflow CRUD
        ToolDefinition(
            name="ralphx_list_workflows",
            description="List all workflows for a project with pagination",
            handler=list_workflows,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "status": prop_enum("Filter by status", ["draft", "active", "paused", "completed", "failed"]),
                    "include_archived": prop_bool("Include archived workflows"),
                    "limit": prop_int("Max workflows to return (1-500)", minimum=1, maximum=500),
                    "offset": prop_int("Number of workflows to skip", minimum=0),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_get_workflow",
            description="Get detailed workflow information including all steps",
            handler=get_workflow,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "workflow_id": prop_string("Workflow ID"),
                },
                required=["slug", "workflow_id"],
            ),
        ),
        ToolDefinition(
            name="ralphx_create_workflow",
            description="Create a new workflow, optionally from a template",
            handler=create_workflow,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "name": prop_string("Workflow name"),
                    "template_id": prop_string("Template ID (optional)"),
                },
                required=["slug", "name"],
            ),
        ),
        ToolDefinition(
            name="ralphx_update_workflow",
            description="Update workflow properties like name or status",
            handler=update_workflow,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "workflow_id": prop_string("Workflow ID"),
                    "name": prop_string("New name"),
                    "status": prop_enum("New status", ["draft", "active", "paused", "completed", "failed"]),
                    "current_step": prop_int("New current step number"),
                },
                required=["slug", "workflow_id"],
            ),
        ),
        # Workflow lifecycle
        ToolDefinition(
            name="ralphx_start_workflow",
            description="Start a workflow execution",
            handler=start_workflow,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "workflow_id": prop_string("Workflow ID"),
                },
                required=["slug", "workflow_id"],
            ),
        ),
        ToolDefinition(
            name="ralphx_pause_workflow",
            description="Pause a running workflow",
            handler=pause_workflow,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "workflow_id": prop_string("Workflow ID"),
                },
                required=["slug", "workflow_id"],
            ),
        ),
        ToolDefinition(
            name="ralphx_stop_workflow",
            description="Stop a workflow and terminate all running loops",
            handler=stop_workflow,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "workflow_id": prop_string("Workflow ID"),
                },
                required=["slug", "workflow_id"],
            ),
        ),
        ToolDefinition(
            name="ralphx_advance_workflow",
            description="Complete current step and advance to next step",
            handler=advance_workflow,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "workflow_id": prop_string("Workflow ID"),
                },
                required=["slug", "workflow_id"],
            ),
        ),
        ToolDefinition(
            name="ralphx_archive_workflow",
            description="Archive a workflow (soft delete)",
            handler=archive_workflow,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "workflow_id": prop_string("Workflow ID"),
                },
                required=["slug", "workflow_id"],
            ),
        ),
        ToolDefinition(
            name="ralphx_restore_workflow",
            description="Restore an archived workflow",
            handler=restore_workflow,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "workflow_id": prop_string("Workflow ID"),
                },
                required=["slug", "workflow_id"],
            ),
        ),
        ToolDefinition(
            name="ralphx_list_workflow_templates",
            description="List available workflow templates",
            handler=list_workflow_templates,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                },
                required=["slug"],
            ),
        ),
        # Step management
        ToolDefinition(
            name="ralphx_create_workflow_step",
            description="Create a new step in a workflow. Processing types: design_doc (interactive chat with web research), extractgen_requirements (extract stories from docs), webgen_requirements (web research for requirements), implementation (implement stories)",
            handler=create_workflow_step,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "workflow_id": prop_string("Workflow ID"),
                    "step_name": prop_string("Step name (e.g., 'Design Document', 'Story Generation')"),
                    "processing_type": prop_enum("Processing type", ["design_doc", "extractgen_requirements", "webgen_requirements", "implementation"]),
                    "step_number": prop_int("Step number (optional, defaults to append)"),
                    "loop_name": prop_string("Loop name for autonomous steps"),
                },
                required=["slug", "workflow_id", "step_name", "processing_type"],
            ),
        ),
        ToolDefinition(
            name="ralphx_update_workflow_step",
            description="Update a workflow step's properties",
            handler=update_workflow_step,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "step_id": prop_int("Step ID"),
                    "name": prop_string("New name"),
                    "status": prop_enum("New status", ["pending", "active", "completed", "skipped", "failed"]),
                    "loop_name": prop_string("New loop name"),
                },
                required=["slug", "step_id"],
            ),
        ),
        ToolDefinition(
            name="ralphx_archive_workflow_step",
            description="Archive a workflow step (soft delete)",
            handler=archive_workflow_step,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "step_id": prop_int("Step ID"),
                },
                required=["slug", "step_id"],
            ),
        ),
        ToolDefinition(
            name="ralphx_restore_workflow_step",
            description="Restore an archived workflow step",
            handler=restore_workflow_step,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "step_id": prop_int("Step ID"),
                },
                required=["slug", "step_id"],
            ),
        ),
        ToolDefinition(
            name="ralphx_reorder_workflow_steps",
            description="Reorder workflow steps",
            handler=reorder_workflow_steps,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "workflow_id": prop_string("Workflow ID"),
                    "step_order": prop_array("List of step IDs in desired order", {"type": "integer"}),
                },
                required=["slug", "workflow_id", "step_order"],
            ),
        ),
        ToolDefinition(
            name="ralphx_run_workflow_step",
            description="Run the current step of a workflow",
            handler=run_workflow_step,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "workflow_id": prop_string("Workflow ID"),
                },
                required=["slug", "workflow_id"],
            ),
        ),
    ]
