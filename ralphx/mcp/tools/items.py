"""Work item MCP tools.

Tools for managing work items:
- ralphx_list_items: List work items with filtering
- ralphx_get_item: Get item details
- ralphx_add_item: Create new work item
- ralphx_update_item: Update item properties
- ralphx_claim_item: Claim item for processing
- ralphx_complete_item: Mark item as completed
"""

import uuid
from typing import Optional

from ralphx.mcp.base import (
    MCPError,
    PaginatedResult,
    ToolDefinition,
    ToolError,
    make_schema,
    prop_enum,
    prop_int,
    prop_string,
    validate_pagination,
)
from ralphx.mcp.tools.projects import get_manager


def list_items(
    slug: str,
    workflow_id: Optional[str] = None,
    source_step_id: Optional[int] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List work items with filtering and pagination."""
    limit, offset = validate_pagination(limit, offset)
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    # Build filters
    items, total = project_db.list_work_items(
        workflow_id=workflow_id,
        source_step_id=source_step_id,
        status=status,
        category=category,
        limit=limit,
        offset=offset,
    )

    return PaginatedResult(
        items=[
            {
                "id": item["id"],
                "workflow_id": item.get("workflow_id"),
                "source_step_id": item.get("source_step_id"),
                "content": item["content"],
                "title": item.get("title"),
                "status": item["status"],
                "category": item.get("category"),
                "priority": item.get("priority"),
                "phase": item.get("phase"),
                "claimed_by": item.get("claimed_by"),
                "created_at": item.get("created_at"),
            }
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    ).to_dict()


def get_item(slug: str, item_id: str) -> dict:
    """Get detailed information about a work item."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    item = project_db.get_work_item(item_id)

    if not item:
        raise ToolError.item_not_found(item_id)

    return {
        "id": item["id"],
        "workflow_id": item.get("workflow_id"),
        "source_step_id": item.get("source_step_id"),
        "content": item["content"],
        "title": item.get("title"),
        "status": item["status"],
        "category": item.get("category"),
        "priority": item.get("priority"),
        "phase": item.get("phase"),
        "tags": item.get("tags"),
        "metadata": item.get("metadata"),
        "claimed_by": item.get("claimed_by"),
        "claimed_at": item.get("claimed_at"),
        "processed_at": item.get("processed_at"),
        "dependencies": item.get("dependencies"),
        "duplicate_of": item.get("duplicate_of"),
        "skip_reason": item.get("skip_reason"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def add_item(
    slug: str,
    content: str,
    workflow_id: str,
    source_step_id: int,
    title: Optional[str] = None,
    category: Optional[str] = None,
    priority: int = 0,
    phase: int = 1,
    metadata: Optional[dict] = None,
) -> dict:
    """Create a new work item in a workflow step."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    # Verify workflow exists
    workflow = project_db.get_workflow(workflow_id)
    if not workflow:
        raise ToolError.workflow_not_found(workflow_id)

    # Verify step exists
    step = project_db.get_workflow_step(source_step_id)
    if not step:
        raise ToolError.step_not_found(source_step_id)

    item_id = str(uuid.uuid4())[:8]

    try:
        project_db.create_work_item(
            id=item_id,
            workflow_id=workflow_id,
            source_step_id=source_step_id,
            content=content,
            title=title,
            category=category,
            priority=priority,
            phase=phase,
            metadata=metadata,
        )
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to create work item: {e}",
            details={"workflow_id": workflow_id},
        )

    return {
        "id": item_id,
        "workflow_id": workflow_id,
        "source_step_id": source_step_id,
        "message": "Work item created",
    }


def update_item(
    slug: str,
    item_id: str,
    content: Optional[str] = None,
    title: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[int] = None,
    phase: Optional[int] = None,
    tags: Optional[list[str]] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Update a work item's properties."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    # Verify item exists
    item = project_db.get_work_item(item_id)
    if not item:
        raise ToolError.item_not_found(item_id)

    updates = {}
    if content is not None:
        updates["content"] = content
    if title is not None:
        updates["title"] = title
    if status is not None:
        updates["status"] = status
    if category is not None:
        updates["category"] = category
    if priority is not None:
        updates["priority"] = priority
    if phase is not None:
        updates["phase"] = phase
    if tags is not None:
        updates["tags"] = tags
    if metadata is not None:
        updates["metadata"] = metadata

    if not updates:
        return {
            "id": item_id,
            "message": "No changes specified",
        }

    try:
        project_db.update_work_item(item_id, **updates)
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to update work item: {e}",
            details={"item_id": item_id},
        )

    return {
        "id": item_id,
        "message": "Work item updated",
        "updated_fields": list(updates.keys()),
    }


def claim_item(
    slug: str,
    item_id: str,
    claimed_by: str,
) -> dict:
    """Claim a work item for processing."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    # Verify item exists
    item = project_db.get_work_item(item_id)
    if not item:
        raise ToolError.item_not_found(item_id)

    # Check if already claimed
    if item.get("claimed_by") and item.get("claimed_by") != claimed_by:
        raise ToolError.concurrency_error(
            f"Item already claimed by {item.get('claimed_by')}",
            {"item_id": item_id, "claimed_by": item.get("claimed_by")},
        )

    try:
        success = project_db.claim_work_item(item_id, claimed_by)
        if not success:
            raise ToolError.concurrency_error(
                "Failed to claim item (concurrent modification)",
                {"item_id": item_id},
            )
    except MCPError:
        raise
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to claim work item: {e}",
            details={"item_id": item_id},
        )

    return {
        "id": item_id,
        "claimed_by": claimed_by,
        "message": "Work item claimed",
    }


def complete_item(
    slug: str,
    item_id: str,
    status: str = "completed",
    result: Optional[dict] = None,
) -> dict:
    """Mark a work item as completed.

    Args:
        slug: Project slug
        item_id: Work item ID
        status: Final status (completed, failed, skipped)
        result: Optional result metadata
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    # Verify item exists
    item = project_db.get_work_item(item_id)
    if not item:
        raise ToolError.item_not_found(item_id)

    valid_statuses = ["completed", "failed", "skipped", "processed"]
    if status not in valid_statuses:
        raise ToolError.validation_error(
            f"Invalid status: {status}. Must be one of: {valid_statuses}",
            {"status": status},
        )

    try:
        project_db.complete_work_item(item_id)
        if status != "completed":
            project_db.update_work_item(item_id, status=status)
        if result:
            project_db.update_work_item(item_id, metadata=result)
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to complete work item: {e}",
            details={"item_id": item_id},
        )

    return {
        "id": item_id,
        "status": status,
        "message": "Work item completed",
    }


def get_item_tools() -> list[ToolDefinition]:
    """Get all work item tool definitions."""
    return [
        ToolDefinition(
            name="ralphx_list_items",
            description="List work items with filtering and pagination",
            handler=list_items,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "workflow_id": prop_string("Filter by workflow ID"),
                    "source_step_id": prop_int("Filter by source step ID"),
                    "status": prop_enum(
                        "Filter by status",
                        ["pending", "in_progress", "completed", "processed", "failed", "skipped", "duplicate"],
                    ),
                    "category": prop_string("Filter by category"),
                    "limit": prop_int("Max items to return (1-500)", minimum=1, maximum=500),
                    "offset": prop_int("Number of items to skip", minimum=0),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_get_item",
            description="Get detailed information about a specific work item",
            handler=get_item,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "item_id": prop_string("Work item ID"),
                },
                required=["slug", "item_id"],
            ),
        ),
        ToolDefinition(
            name="ralphx_add_item",
            description="Create a new work item in a workflow step",
            handler=add_item,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "content": prop_string("Item content/description"),
                    "workflow_id": prop_string("Workflow ID the item belongs to"),
                    "source_step_id": prop_int("Step ID that creates/owns this item"),
                    "title": prop_string("Short title for the item"),
                    "category": prop_string("Item category"),
                    "priority": prop_int("Priority (0-10)", minimum=0, maximum=10),
                    "phase": prop_int("Phase number", minimum=1),
                },
                required=["slug", "content", "workflow_id", "source_step_id"],
            ),
        ),
        ToolDefinition(
            name="ralphx_update_item",
            description="Update a work item's properties",
            handler=update_item,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "item_id": prop_string("Work item ID"),
                    "content": prop_string("New content"),
                    "title": prop_string("New title"),
                    "status": prop_enum(
                        "New status",
                        ["pending", "in_progress", "completed", "processed", "failed", "skipped"],
                    ),
                    "category": prop_string("New category"),
                    "priority": prop_int("New priority (0-10)", minimum=0, maximum=10),
                    "phase": prop_int("New phase number", minimum=1),
                },
                required=["slug", "item_id"],
            ),
        ),
        ToolDefinition(
            name="ralphx_claim_item",
            description="Claim a work item for processing (prevents concurrent processing)",
            handler=claim_item,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "item_id": prop_string("Work item ID to claim"),
                    "claimed_by": prop_string("Identifier of the claimer (e.g., run ID)"),
                },
                required=["slug", "item_id", "claimed_by"],
            ),
        ),
        ToolDefinition(
            name="ralphx_complete_item",
            description="Mark a work item as completed with optional result",
            handler=complete_item,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "item_id": prop_string("Work item ID"),
                    "status": prop_enum(
                        "Final status",
                        ["completed", "failed", "skipped", "processed"],
                    ),
                },
                required=["slug", "item_id"],
            ),
        ),
    ]
