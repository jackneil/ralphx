"""Resource management MCP tools.

Tools for managing project and workflow resources:
- ralphx_list_project_resources: List project resources
- ralphx_sync_project_resources: Sync resources from filesystem
- ralphx_list_workflow_resources: List workflow resources
- ralphx_create_workflow_resource: Create workflow resource
- ralphx_update_workflow_resource: Update workflow resource
"""

from typing import Optional

from ralphx.mcp.base import (
    MCPError,
    PaginatedResult,
    ToolDefinition,
    ToolError,
    make_schema,
    prop_bool,
    prop_enum,
    prop_int,
    prop_string,
    validate_pagination,
)
from ralphx.mcp.tools.projects import get_manager


def list_project_resources(
    slug: str,
    resource_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List resources attached to a project.

    Resources are shared content that can be inherited by workflows
    (design docs, coding standards, domain knowledge, etc.)
    """
    limit, offset = validate_pagination(limit, offset)
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    try:
        resources = project_db.list_project_resources(resource_type=resource_type)
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to list resources: {e}",
            details={"slug": slug},
        )

    total = len(resources)
    paginated = resources[offset : offset + limit]

    return PaginatedResult(
        items=[
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "resource_type": r.get("resource_type"),
                "path": r.get("path"),
                "enabled": r.get("enabled", True),
                "content_preview": r.get("content", "")[:200] if r.get("content") else None,
                "created_at": r.get("created_at"),
            }
            for r in paginated
        ],
        total=total,
        limit=limit,
        offset=offset,
    ).to_dict()


def sync_project_resources(
    slug: str,
    resource_type: Optional[str] = None,
) -> dict:
    """Sync project resources from filesystem.

    Scans project directories for resource files and updates database.
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    try:
        from ralphx.core.resources import ResourceManager

        rm = ResourceManager(project.path, project_db)
        result = rm.sync_project_resources(resource_type=resource_type)

        return {
            "synced": result.get("synced", []),
            "added": result.get("added", 0),
            "updated": result.get("updated", 0),
            "removed": result.get("removed", 0),
            "errors": result.get("errors", []),
            "message": f"Synced {result.get('added', 0) + result.get('updated', 0)} resources",
        }
    except ImportError:
        # Fallback: basic filesystem scan
        from pathlib import Path

        resources_dir = Path(project.path) / ".ralphx" / "resources"
        synced = []
        errors = []

        # Also check for design doc
        design_doc_path = Path(project.path) / "DESIGN.md"
        if design_doc_path.exists():
            synced.append({
                "name": "Design Document",
                "type": "design_doc",
                "path": "DESIGN.md",
            })

        if resources_dir.exists():
            for f in resources_dir.iterdir():
                if f.is_file():
                    synced.append({
                        "name": f.stem,
                        "type": "custom",
                        "path": str(f.relative_to(project.path)),
                    })

        return {
            "synced": synced,
            "added": len(synced),
            "updated": 0,
            "removed": 0,
            "errors": errors,
        }
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Sync failed: {e}",
            details={"slug": slug},
        )


def list_workflow_resources(
    slug: str,
    workflow_id: str,
    resource_type: Optional[str] = None,
    include_inherited: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List resources attached to a workflow.

    Resources can be workflow-specific or inherited from project level.
    """
    limit, offset = validate_pagination(limit, offset)
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    # Verify workflow exists
    workflow = project_db.get_workflow(workflow_id)
    if not workflow:
        raise ToolError.workflow_not_found(workflow_id)

    try:
        resources = project_db.list_workflow_resources(
            workflow_id=workflow_id,
            resource_type=resource_type,
            include_inherited=include_inherited,
        )
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to list resources: {e}",
            details={"workflow_id": workflow_id},
        )

    total = len(resources)
    paginated = resources[offset : offset + limit]

    return PaginatedResult(
        items=[
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "resource_type": r.get("resource_type"),
                "source": r.get("source", "workflow"),  # workflow or project
                "enabled": r.get("enabled", True),
                "content_preview": r.get("content", "")[:200] if r.get("content") else None,
                "created_at": r.get("created_at"),
            }
            for r in paginated
        ],
        total=total,
        limit=limit,
        offset=offset,
    ).to_dict()


def create_workflow_resource(
    slug: str,
    workflow_id: str,
    name: str,
    resource_type: str,
    content: str,
    enabled: bool = True,
) -> dict:
    """Create a new resource for a workflow.

    Args:
        slug: Project slug
        workflow_id: Workflow ID
        name: Resource name
        resource_type: Type (design_doc, architecture, coding_standards, domain_knowledge, custom)
        content: Resource content
        enabled: Whether resource is active (default: True)
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    # Verify workflow exists
    workflow = project_db.get_workflow(workflow_id)
    if not workflow:
        raise ToolError.workflow_not_found(workflow_id)

    valid_types = ["design_doc", "architecture", "coding_standards", "domain_knowledge", "custom", "guardrails", "prompt_template"]
    if resource_type not in valid_types:
        raise ToolError.validation_error(
            f"Invalid resource_type: {resource_type}. Must be one of: {valid_types}",
        )

    try:
        resource = project_db.create_workflow_resource(
            workflow_id=workflow_id,
            resource_type=resource_type,
            name=name,
            content=content,
            enabled=enabled,
        )
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to create resource: {e}",
            details={"workflow_id": workflow_id},
        )

    return {
        "id": resource.get("id"),
        "name": name,
        "resource_type": resource_type,
        "message": "Resource created",
    }


def update_workflow_resource(
    slug: str,
    resource_id: int,
    name: Optional[str] = None,
    content: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> dict:
    """Update a workflow resource.

    Args:
        slug: Project slug
        resource_id: Resource ID
        name: New name
        content: New content
        enabled: Enable/disable resource
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    # Verify resource exists
    resource = project_db.get_workflow_resource(resource_id)
    if not resource:
        raise MCPError(
            error_code=ToolError.RESOURCE_NOT_FOUND,
            message=f"Resource not found: {resource_id}",
            details={"resource_id": resource_id},
        )

    updates = {}
    if name is not None:
        updates["name"] = name
    if content is not None:
        updates["content"] = content
    if enabled is not None:
        updates["enabled"] = enabled

    if not updates:
        return {
            "id": resource_id,
            "message": "No changes specified",
        }

    try:
        project_db.update_workflow_resource(resource_id, **updates)
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to update resource: {e}",
            details={"resource_id": resource_id},
        )

    return {
        "id": resource_id,
        "updated_fields": list(updates.keys()),
        "message": "Resource updated",
    }


def get_resource_tools() -> list[ToolDefinition]:
    """Get all resource management tool definitions."""
    return [
        ToolDefinition(
            name="ralphx_list_project_resources",
            description="List resources attached to a project (shared across workflows)",
            handler=list_project_resources,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "resource_type": prop_enum(
                        "Filter by type",
                        ["design_doc", "architecture", "coding_standards", "domain_knowledge", "custom"],
                    ),
                    "limit": prop_int("Max resources to return (1-500)", minimum=1, maximum=500),
                    "offset": prop_int("Number of resources to skip", minimum=0),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_sync_project_resources",
            description="Sync project resources from filesystem to database",
            handler=sync_project_resources,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "resource_type": prop_enum(
                        "Only sync specific type",
                        ["design_doc", "architecture", "coding_standards", "domain_knowledge", "custom"],
                    ),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_list_workflow_resources",
            description="List resources attached to a workflow (including inherited from project)",
            handler=list_workflow_resources,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "workflow_id": prop_string("Workflow ID"),
                    "resource_type": prop_enum(
                        "Filter by type",
                        ["design_doc", "architecture", "coding_standards", "domain_knowledge", "custom", "guardrails"],
                    ),
                    "include_inherited": prop_bool("Include resources inherited from project (default: true)"),
                    "limit": prop_int("Max resources to return (1-500)", minimum=1, maximum=500),
                    "offset": prop_int("Number of resources to skip", minimum=0),
                },
                required=["slug", "workflow_id"],
            ),
        ),
        ToolDefinition(
            name="ralphx_create_workflow_resource",
            description="Create a new resource for a workflow",
            handler=create_workflow_resource,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "workflow_id": prop_string("Workflow ID"),
                    "name": prop_string("Resource name"),
                    "resource_type": prop_enum(
                        "Resource type",
                        ["design_doc", "architecture", "coding_standards", "domain_knowledge", "custom", "guardrails", "prompt_template"],
                    ),
                    "content": prop_string("Resource content"),
                    "enabled": prop_bool("Whether resource is active (default: true)"),
                },
                required=["slug", "workflow_id", "name", "resource_type", "content"],
            ),
        ),
        ToolDefinition(
            name="ralphx_update_workflow_resource",
            description="Update a workflow resource's name, content, or enabled status",
            handler=update_workflow_resource,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "resource_id": prop_int("Resource ID"),
                    "name": prop_string("New name"),
                    "content": prop_string("New content"),
                    "enabled": prop_bool("Enable/disable resource"),
                },
                required=["slug", "resource_id"],
            ),
        ),
    ]
