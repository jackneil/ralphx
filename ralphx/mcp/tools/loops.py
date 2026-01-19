"""Loop management MCP tools.

Tools for managing RalphX loops:
- ralphx_list_loops: List configured loops
- ralphx_get_loop_status: Get loop status
- ralphx_start_loop: Start loop execution
- ralphx_stop_loop: Stop running loop
- ralphx_get_loop_config: Get detailed loop configuration
- ralphx_validate_loop: Validate loop YAML configuration
- ralphx_sync_loops: Sync loops to database
"""

from typing import Optional

from ralphx.mcp.base import (
    MCPError,
    ToolDefinition,
    ToolError,
    make_schema,
    prop_bool,
    prop_int,
    prop_string,
)
from ralphx.mcp.tools.projects import get_manager


def list_loops(slug: str) -> dict:
    """List all configured loops for a project."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    # Use LoopLoader with project database to list loops
    from ralphx.core.loop import LoopLoader

    project_db = manager.get_project_db(project.path)
    loader = LoopLoader(db=project_db)
    loops = loader.list_loops()

    return {
        "loops": [
            {
                "name": loop.name,
                "display_name": loop.display_name,
                "type": loop.type,
                "modes": list(loop.modes.keys()),
            }
            for loop in loops
        ],
    }


def get_loop_status(slug: str, loop_name: str) -> dict:
    """Get the current status of a loop."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    # Get loop record from database
    loop_record = project_db.get_loop(loop_name)
    if not loop_record:
        raise ToolError.loop_not_found(loop_name)

    # Check for active runs
    runs = project_db.list_runs(loop_name=loop_name, status="running", limit=1)
    if runs:
        run = runs[0]
        return {
            "loop_name": loop_name,
            "is_running": True,
            "run_id": run.get("id"),
            "current_iteration": run.get("current_iteration"),
            "current_mode": run.get("current_mode"),
            "status": run.get("status"),
            "executor_pid": run.get("executor_pid"),
            "last_activity_at": run.get("last_activity_at"),
        }

    return {
        "loop_name": loop_name,
        "is_running": False,
        "run_id": None,
        "current_iteration": None,
        "current_mode": None,
        "status": None,
        "executor_pid": None,
        "last_activity_at": None,
    }


def start_loop(
    slug: str,
    loop_name: str,
    mode: Optional[str] = None,
    iterations: Optional[int] = None,
    force: bool = False,
) -> dict:
    """Start a loop execution.

    Args:
        slug: Project slug
        loop_name: Name of the loop to start
        mode: Optional mode to use (defaults to loop default)
        iterations: Number of iterations to run
        force: If True, stop existing run and start new one
    """
    import uuid
    from ralphx.core.loop import LoopLoader

    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    # Get loop record from database
    loop_record = project_db.get_loop(loop_name)
    if not loop_record:
        raise ToolError.loop_not_found(loop_name)

    # Check if already running
    runs = project_db.list_runs(loop_name=loop_name, status="running", limit=1)
    if runs and not force:
        raise ToolError.already_running(loop_name, runs[0].get("id"))

    # Stop existing if force
    if runs and force:
        for run in runs:
            project_db.update_run(run["id"], status="aborted")

    # Verify loop configuration exists
    loader = LoopLoader(db=project_db)
    config = loader.get_loop(loop_name)
    if not config:
        raise ToolError.loop_not_found(loop_name)

    # Get workflow context
    workflow_id = loop_record.get("workflow_id")
    step_id = loop_record.get("step_id")
    if not workflow_id or step_id is None:
        raise ToolError.validation_error(
            f"Loop '{loop_name}' missing workflow context. "
            "Loops must be created via a workflow to run.",
            {"loop_name": loop_name},
        )

    try:
        # Create run record
        run_id = str(uuid.uuid4())[:12]
        project_db.create_run(
            id=run_id,
            loop_name=loop_name,
            workflow_id=workflow_id,
            step_id=step_id,
        )
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to start loop: {e}",
            details={"loop_name": loop_name},
        )

    return {
        "message": f"Loop {loop_name} started",
        "run_id": run_id,
        "mode": mode,
        "iterations": iterations,
    }


def stop_loop(slug: str, loop_name: str) -> dict:
    """Stop a running loop."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    # Get loop record from database
    loop_record = project_db.get_loop(loop_name)
    if not loop_record:
        raise ToolError.loop_not_found(loop_name)

    # Check if running
    runs = project_db.list_runs(loop_name=loop_name, status="running")
    if not runs:
        raise ToolError.not_running(loop_name)

    try:
        # Mark all running runs as aborted
        stopped_count = 0
        for run in runs:
            project_db.update_run(run["id"], status="aborted")
            stopped_count += 1
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to stop loop: {e}",
            details={"loop_name": loop_name},
        )

    return {
        "message": f"Loop {loop_name} stopped",
        "loop_name": loop_name,
        "stopped_runs": stopped_count,
    }


def get_loop_config(slug: str, loop_name: str) -> dict:
    """Get detailed configuration for a loop.

    Returns the full loop configuration including modes,
    guardrails, and execution settings.
    """
    from ralphx.core.loop import LoopLoader

    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    loader = LoopLoader(db=project_db)
    loop = loader.get_loop(loop_name)

    if not loop:
        raise ToolError.loop_not_found(loop_name)

    # Get detailed config
    config = {
        "name": loop.name,
        "display_name": loop.display_name,
        "type": loop.type,
        "modes": {},
    }

    for mode_name, mode_config in loop.modes.items():
        mode_info = {
            "name": mode_name,
        }
        # Add mode-specific fields if available
        if hasattr(mode_config, "prompt"):
            mode_info["prompt"] = mode_config.prompt
        if hasattr(mode_config, "guardrails"):
            mode_info["guardrails"] = mode_config.guardrails
        if hasattr(mode_config, "max_iterations"):
            mode_info["max_iterations"] = mode_config.max_iterations
        config["modes"][mode_name] = mode_info

    return config


def validate_loop(slug: str, loop_name: str) -> dict:
    """Validate a loop's YAML configuration.

    Checks for:
    - Valid YAML syntax
    - Required fields present
    - Valid mode configurations
    - Valid guardrail references
    """
    from ralphx.core.loop import LoopLoader

    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    loader = LoopLoader(db=project_db)
    errors = []
    warnings = []

    # Try to load the loop
    try:
        loop = loader.get_loop(loop_name)
        if not loop:
            raise ToolError.loop_not_found(loop_name)
    except Exception as e:
        errors.append(f"Failed to parse loop configuration: {e}")
        return {
            "valid": False,
            "loop_name": loop_name,
            "errors": errors,
            "warnings": warnings,
        }

    # Validate modes
    if not loop.modes:
        warnings.append("No modes defined in loop")

    # Check for default mode
    if loop.modes and not any(m == "default" for m in loop.modes):
        warnings.append("No 'default' mode defined")

    return {
        "valid": len(errors) == 0,
        "loop_name": loop_name,
        "errors": errors,
        "warnings": warnings,
        "mode_count": len(loop.modes) if loop.modes else 0,
    }


def sync_loops(slug: str) -> dict:
    """Sync loop configurations from filesystem to database.

    Reads loop YAML files and updates database records.
    """
    from ralphx.core.loop import LoopLoader

    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    try:
        project_db = manager.get_project_db(project.path)
        loader = LoopLoader(db=project_db)

        # Get all loops from database
        loops = loader.list_loops()
        synced = []
        errors = []

        for loop in loops:
            try:
                synced.append(loop.name)
            except Exception as e:
                errors.append({"loop": loop.name, "error": str(e)})

        return {
            "synced": synced,
            "errors": errors,
            "total": len(loops),
            "success_count": len(synced),
            "error_count": len(errors),
        }

    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Sync failed: {e}",
            details={"slug": slug},
        )


def get_loop_tools() -> list[ToolDefinition]:
    """Get all loop management tool definitions."""
    return [
        ToolDefinition(
            name="ralphx_list_loops",
            description="List all configured loops for a project",
            handler=list_loops,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_get_loop_status",
            description="Get the current execution status of a loop",
            handler=get_loop_status,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "loop_name": prop_string("Loop name"),
                },
                required=["slug", "loop_name"],
            ),
        ),
        ToolDefinition(
            name="ralphx_start_loop",
            description="Start a loop execution. Use force=true to restart if already running.",
            handler=start_loop,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "loop_name": prop_string("Loop name to start"),
                    "mode": prop_string("Mode to use (optional)"),
                    "iterations": prop_int("Number of iterations"),
                    "force": prop_bool("Stop existing run and start new one"),
                },
                required=["slug", "loop_name"],
            ),
        ),
        ToolDefinition(
            name="ralphx_stop_loop",
            description="Stop a running loop execution",
            handler=stop_loop,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "loop_name": prop_string("Loop name to stop"),
                },
                required=["slug", "loop_name"],
            ),
        ),
        ToolDefinition(
            name="ralphx_get_loop_config",
            description="Get detailed configuration for a loop including all modes and settings",
            handler=get_loop_config,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "loop_name": prop_string("Loop name"),
                },
                required=["slug", "loop_name"],
            ),
        ),
        ToolDefinition(
            name="ralphx_validate_loop",
            description="Validate a loop's YAML configuration for errors and warnings",
            handler=validate_loop,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "loop_name": prop_string("Loop name to validate"),
                },
                required=["slug", "loop_name"],
            ),
        ),
        ToolDefinition(
            name="ralphx_sync_loops",
            description="Sync loop configurations from YAML files to database",
            handler=sync_loops,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                },
                required=["slug"],
            ),
        ),
    ]
