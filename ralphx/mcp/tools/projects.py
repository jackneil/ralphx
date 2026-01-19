"""Project management MCP tools.

Tools for managing RalphX projects:
- ralphx_list_projects: List all projects
- ralphx_get_project: Get project details
- ralphx_add_project: Register a new project
- ralphx_remove_project: Unregister a project
- ralphx_update_project: Update project settings
"""

from typing import Optional

from ralphx.core.project import ProjectManager
from ralphx.mcp.base import (
    MCPError,
    PaginatedResult,
    ToolDefinition,
    ToolError,
    make_schema,
    prop_bool,
    prop_int,
    prop_string,
    validate_pagination,
)


# Shared project manager instance
_manager: Optional[ProjectManager] = None


def get_manager() -> ProjectManager:
    """Get or create the project manager instance."""
    global _manager
    if _manager is None:
        _manager = ProjectManager()
    return _manager


def reset_manager() -> None:
    """Reset the project manager (for testing)."""
    global _manager
    _manager = None


def list_projects(
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List all RalphX projects with pagination."""
    limit, offset = validate_pagination(limit, offset)
    manager = get_manager()

    all_projects = manager.list_projects()
    total = len(all_projects)

    # Apply pagination
    paginated = all_projects[offset : offset + limit]

    items = [
        {
            "slug": p.slug,
            "name": p.name,
            "path": str(p.path),
        }
        for p in paginated
    ]

    return PaginatedResult(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    ).to_dict()


def get_project(slug: str) -> dict:
    """Get detailed information about a project."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    stats = manager.get_project_stats(slug)

    return {
        "slug": project.slug,
        "name": project.name,
        "path": str(project.path),
        "design_doc": str(project.design_doc) if project.design_doc else None,
        "stats": stats,
    }


def add_project(
    path: str,
    name: Optional[str] = None,
    design_doc: Optional[str] = None,
) -> dict:
    """Register a new project with RalphX.

    Args:
        path: Absolute path to the project directory
        name: Optional display name (defaults to directory name)
        design_doc: Optional path to design document
    """
    manager = get_manager()

    try:
        project = manager.add_project(
            path=path,
            name=name,
            design_doc=design_doc,
        )
    except ValueError as e:
        raise ToolError.validation_error(str(e))
    except FileNotFoundError as e:
        raise ToolError.validation_error(
            f"Path does not exist: {path}",
            {"path": path},
        )
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to add project: {e}",
            details={"path": path},
        )

    return {
        "slug": project.slug,
        "name": project.name,
        "path": str(project.path),
        "message": "Project registered successfully",
    }


def remove_project(
    slug: str,
    delete_data: bool = False,
) -> dict:
    """Remove a project from RalphX.

    Args:
        slug: Project slug to remove
        delete_data: If True, also delete .ralphx directory (default: False)
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    try:
        manager.remove_project(slug, delete_data=delete_data)
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to remove project: {e}",
            details={"slug": slug},
        )

    return {
        "slug": slug,
        "deleted_data": delete_data,
        "message": "Project removed successfully",
    }


def update_project(
    slug: str,
    name: Optional[str] = None,
    design_doc: Optional[str] = None,
) -> dict:
    """Update project settings.

    Args:
        slug: Project slug to update
        name: New display name (optional)
        design_doc: New design document path (optional)
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    updates = {}
    if name is not None:
        updates["name"] = name
    if design_doc is not None:
        updates["design_doc"] = design_doc

    if not updates:
        return {
            "slug": slug,
            "message": "No changes specified",
        }

    try:
        manager.update_project(slug, **updates)
        # Get updated project
        project = manager.get_project(slug)
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to update project: {e}",
            details={"slug": slug},
        )

    return {
        "slug": project.slug,
        "name": project.name,
        "path": str(project.path),
        "design_doc": str(project.design_doc) if project.design_doc else None,
        "message": "Project updated successfully",
    }


def get_project_tools() -> list[ToolDefinition]:
    """Get all project management tool definitions."""
    return [
        ToolDefinition(
            name="ralphx_list_projects",
            description="List all registered RalphX projects with pagination",
            handler=list_projects,
            input_schema=make_schema(
                properties={
                    "limit": prop_int("Max projects to return (1-500)", minimum=1, maximum=500),
                    "offset": prop_int("Number of projects to skip", minimum=0),
                },
                required=[],
            ),
        ),
        ToolDefinition(
            name="ralphx_get_project",
            description="Get detailed information about a specific project including stats",
            handler=get_project,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug identifier"),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_add_project",
            description="Register a new project with RalphX. Creates .ralphx directory if needed.",
            handler=add_project,
            input_schema=make_schema(
                properties={
                    "path": prop_string("Absolute path to the project directory"),
                    "name": prop_string("Display name for the project (optional, defaults to directory name)"),
                    "design_doc": prop_string("Path to design document (optional)"),
                },
                required=["path"],
            ),
        ),
        ToolDefinition(
            name="ralphx_remove_project",
            description="Unregister a project from RalphX. Optionally delete .ralphx data.",
            handler=remove_project,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug to remove"),
                    "delete_data": prop_bool("Delete .ralphx directory (default: false)"),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_update_project",
            description="Update project settings like name or design document path",
            handler=update_project,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug to update"),
                    "name": prop_string("New display name"),
                    "design_doc": prop_string("New design document path"),
                },
                required=["slug"],
            ),
        ),
    ]
