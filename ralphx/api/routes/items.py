"""Work item CRUD API routes."""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from ralphx.core.project import ProjectManager
from ralphx.models.work_item import WorkItem, WorkItemStatus

router = APIRouter()


# Request/Response models
class ItemCreate(BaseModel):
    """Request model for creating a work item."""

    content: str = Field(..., min_length=1, description="Item content/description")
    title: Optional[str] = Field(None, description="Item title")
    workflow_id: str = Field(..., min_length=1, description="Parent workflow ID")
    source_step_id: int = Field(..., description="Workflow step that created this item")
    category: Optional[str] = Field(None, description="Category name")
    priority: int = Field(0, ge=0, le=10, description="Priority (0-10)")
    dependencies: Optional[list[str]] = Field(None, description="List of item IDs this depends on")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class ItemUpdate(BaseModel):
    """Request model for updating a work item."""

    content: Optional[str] = Field(None, description="Item content/description")
    title: Optional[str] = Field(None, description="Item title")
    status: Optional[str] = Field(None, description="Status (pending, in_progress, completed, rejected)")
    category: Optional[str] = Field(None, description="Category name")
    priority: Optional[int] = Field(None, ge=0, le=10, description="Priority (0-10)")
    dependencies: Optional[list[str]] = Field(None, description="List of item IDs this depends on")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class ItemResponse(BaseModel):
    """Response model for a work item."""

    id: str
    workflow_id: str
    source_step_id: int
    content: str
    title: Optional[str] = None
    status: str
    category: Optional[str] = None
    priority: Optional[int] = None
    tags: Optional[list[str]] = None
    item_type: Optional[str] = None
    claimed_by: Optional[str] = None
    claimed_at: Optional[str] = None
    processed_at: Optional[str] = None
    created_at: str
    updated_at: str
    metadata: Optional[dict] = None
    # Phase and dependency fields
    dependencies: Optional[list[str]] = None
    phase: Optional[int] = None
    duplicate_of: Optional[str] = None
    skip_reason: Optional[str] = None

    @classmethod
    def from_item(cls, item: WorkItem) -> "ItemResponse":
        """Create from WorkItem model."""
        return cls(
            id=item.id,
            workflow_id=item.workflow_id,
            source_step_id=item.source_step_id,
            content=item.content,
            title=item.title,
            status=item.status.value,
            category=item.category,
            priority=item.priority,
            tags=item.tags,
            item_type=item.item_type,
            claimed_by=item.claimed_by,
            claimed_at=item.claimed_at.isoformat() if item.claimed_at else None,
            processed_at=item.processed_at.isoformat() if item.processed_at else None,
            created_at=item.created_at.isoformat() if item.created_at else "",
            updated_at=item.updated_at.isoformat() if item.updated_at else "",
            metadata=item.metadata,
            dependencies=item.dependencies,
            phase=item.phase,
            duplicate_of=item.duplicate_of,
            skip_reason=item.skip_reason,
        )


class ItemsStats(BaseModel):
    """Statistics about work items."""

    total: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)
    by_priority: dict[int, int] = Field(default_factory=dict)


class ItemsPage(BaseModel):
    """Paginated list of items."""

    items: list[ItemResponse]
    total: int
    limit: int
    offset: int


def get_manager() -> ProjectManager:
    """Get project manager instance."""
    return ProjectManager()


def get_project(slug: str):
    """Get project by slug or raise 404.

    Returns:
        Tuple of (manager, project, project_db) for the requested project.
    """
    manager = get_manager()
    project = manager.get_project(slug)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )
    project_db = manager.get_project_db(project.path)
    return manager, project, project_db


@router.get("/{slug}/items", response_model=ItemsPage)
async def list_items(
    slug: str,
    item_status: Optional[str] = Query(None, alias="status", description="Filter by status"),
    category: Optional[str] = Query(None, description="Filter by category"),
    workflow_id: Optional[str] = Query(None, description="Filter by workflow"),
    source_step_id: Optional[int] = Query(None, description="Filter by source step"),
    limit: int = Query(50, ge=1, le=1000, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    sort_by: str = Query("created_at", description="Column to sort by"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
):
    """List work items with optional filtering."""
    manager, project, project_db = get_project(slug)

    # Get items from database (returns tuple of items and total)
    items_data, total = project_db.list_work_items(
        status=item_status,
        category=category,
        workflow_id=workflow_id,
        source_step_id=source_step_id,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    # Convert to response models
    items = []
    for row in items_data:
        item = WorkItem.from_dict(row)
        items.append(ItemResponse.from_item(item))

    return ItemsPage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{slug}/items/stats", response_model=ItemsStats)
async def get_items_stats(slug: str):
    """Get statistics about work items."""
    manager, project, project_db = get_project(slug)

    stats = project_db.get_work_item_stats()

    return ItemsStats(
        total=stats.get("total", 0),
        by_status=stats.get("by_status", {}),
        by_category=stats.get("by_category", {}),
        by_priority=stats.get("by_priority", {}),
    )


@router.get("/{slug}/items/{item_id}", response_model=ItemResponse)
async def get_item(slug: str, item_id: str):
    """Get a specific work item."""
    manager, project, project_db = get_project(slug)

    row = project_db.get_work_item(item_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Work item not found: {item_id}",
        )

    item = WorkItem.from_dict(row, project_id=project.id)
    return ItemResponse.from_item(item)


@router.post("/{slug}/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(slug: str, data: ItemCreate):
    """Create a new work item.

    Work items must belong to a workflow and must specify which step created them.
    """
    manager, project, project_db = get_project(slug)

    # Verify workflow exists
    workflow = project_db.get_workflow(data.workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow not found: {data.workflow_id}",
        )

    # Verify step exists and belongs to this workflow
    step = project_db.get_workflow_step(data.source_step_id)
    if not step or step["workflow_id"] != data.workflow_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Step {data.source_step_id} not found or does not belong to workflow {data.workflow_id}",
        )

    item_id = str(uuid.uuid4())
    project_db.create_work_item(
        id=item_id,
        workflow_id=data.workflow_id,
        source_step_id=data.source_step_id,
        content=data.content,
        title=data.title,
        category=data.category,
        priority=data.priority,
        dependencies=data.dependencies,
        metadata=data.metadata,
    )

    row = project_db.get_work_item(item_id)
    item = WorkItem.from_dict(row, project_id=project.id)
    return ItemResponse.from_item(item)


@router.patch("/{slug}/items/{item_id}", response_model=ItemResponse)
async def update_item(slug: str, item_id: str, data: ItemUpdate):
    """Update a work item."""
    manager, project, project_db = get_project(slug)

    # Verify item exists
    row = project_db.get_work_item(item_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Work item not found: {item_id}",
        )

    # Build update dict
    updates = {}
    if data.content is not None:
        updates["content"] = data.content
    if data.title is not None:
        updates["title"] = data.title
    if data.status is not None:
        # Validate status
        try:
            WorkItemStatus(data.status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {data.status}",
            )
        updates["status"] = data.status
    if data.category is not None:
        updates["category"] = data.category
    if data.priority is not None:
        updates["priority"] = data.priority
    if data.dependencies is not None:
        updates["dependencies"] = data.dependencies
    if data.metadata is not None:
        updates["metadata"] = data.metadata

    if updates:
        project_db.update_work_item(item_id, **updates)

    row = project_db.get_work_item(item_id)
    item = WorkItem.from_dict(row, project_id=project.id)
    return ItemResponse.from_item(item)


@router.delete("/{slug}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(slug: str, item_id: str):
    """Delete a work item."""
    manager, project, project_db = get_project(slug)

    # Verify item exists
    row = project_db.get_work_item(item_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Work item not found: {item_id}",
        )

    project_db.delete_work_item(item_id)
    return None


@router.post("/{slug}/items/{item_id}/duplicate", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_item(slug: str, item_id: str):
    """Duplicate a work item."""
    manager, project, project_db = get_project(slug)

    # Get original item
    row = project_db.get_work_item(item_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Work item not found: {item_id}",
        )

    # Create duplicate
    new_id = str(uuid.uuid4())
    project_db.create_work_item(
        id=new_id,
        content=row["content"],
        category=row.get("category"),
        priority=row.get("priority", 0),
        metadata=row.get("metadata"),
    )

    new_row = project_db.get_work_item(new_id)
    item = WorkItem.from_dict(new_row)
    return ItemResponse.from_item(item)


@router.post("/{slug}/items/{item_id}/external")
async def mark_external(
    slug: str,
    item_id: str,
    external_id: str = Query(..., description="External system ID"),
    external_url: Optional[str] = Query(None, description="External URL"),
):
    """Mark work item as linked to external system."""
    manager, project, project_db = get_project(slug)

    # Verify item exists
    row = project_db.get_work_item(item_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Work item not found: {item_id}",
        )

    # Update metadata with external link
    metadata = row.get("metadata") or {}
    metadata["external_id"] = external_id
    if external_url:
        metadata["external_url"] = external_url

    project_db.update_work_item(item_id, metadata=metadata)

    return {"message": f"Linked to external: {external_id}"}


# =========================================================================
# Consumer Loop Item Operations
# =========================================================================

class ClaimRequest(BaseModel):
    """Request model for claiming an item."""

    consumer_loop: str = Field(..., description="Name of the consumer loop claiming this item")


class ClaimResponse(BaseModel):
    """Response model for a claimed item."""

    id: str
    workflow_id: str
    source_step_id: int
    content: str
    status: str
    item_type: Optional[str] = None
    claimed_by: str
    claimed_at: str
    metadata: Optional[dict] = None


@router.post("/{slug}/items/{item_id}/claim", response_model=ClaimResponse)
async def claim_item(slug: str, item_id: str, data: ClaimRequest):
    """Claim an item for processing by a consumer loop.

    Uses atomic UPDATE...WHERE to prevent race conditions.
    Returns 409 Conflict if the item is already claimed.
    """
    from ralphx.core.loop import LoopLoader

    manager, project, project_db = get_project(slug)

    # Validate consumer_loop exists in this project
    loader = LoopLoader(db=project_db)
    loop_config = loader.get_loop(data.consumer_loop)
    if not loop_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Consumer loop '{data.consumer_loop}' not found in project",
        )

    # Attempt atomic claim
    success = project_db.claim_work_item(item_id, data.consumer_loop)

    if not success:
        # Check if item exists or is already claimed
        row = project_db.get_work_item(item_id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Work item not found: {item_id}",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Item already claimed by {row.get('claimed_by', 'unknown')}",
        )

    # Return the claimed item
    row = project_db.get_work_item(item_id)
    return ClaimResponse(
        id=row["id"],
        workflow_id=row["workflow_id"],
        source_step_id=row["source_step_id"],
        content=row["content"],
        status=row["status"],
        item_type=row.get("item_type"),
        claimed_by=row["claimed_by"],
        claimed_at=row["claimed_at"],
        metadata=row.get("metadata"),
    )


@router.post("/{slug}/items/{item_id}/release")
async def release_item_claim(slug: str, item_id: str, data: ClaimRequest):
    """Release a claim on an item so it can be retried.

    Authorization: Only the loop that claimed the item can release it.
    """
    manager, project, project_db = get_project(slug)

    # Verify item exists and check claim ownership
    row = project_db.get_work_item(item_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Work item not found: {item_id}",
        )

    if row.get("claimed_by") is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item is not claimed",
        )

    if row.get("claimed_by") != data.consumer_loop:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Item is claimed by '{row['claimed_by']}', not '{data.consumer_loop}'. Cannot release.",
        )

    # Release the claim atomically with ownership check (prevents TOCTOU race)
    released = project_db.release_work_item_claim(item_id, claimed_by=data.consumer_loop)
    if not released:
        # Claim state changed between check and release
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Item claim state changed - retry the operation",
        )

    return {"message": f"Claim released for item {item_id}"}


@router.post("/{slug}/items/{item_id}/complete")
async def mark_item_processed(slug: str, item_id: str, data: ClaimRequest):
    """Mark an item as processed after successful consumer iteration.

    Authorization: Only the loop that claimed the item can mark it complete.
    """
    manager, project, project_db = get_project(slug)

    # Verify item exists and check claim ownership
    row = project_db.get_work_item(item_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Work item not found: {item_id}",
        )

    if row.get("claimed_by") != data.consumer_loop:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Item not claimed by '{data.consumer_loop}'",
        )

    # Mark as processed
    project_db.mark_work_item_processed(item_id, data.consumer_loop)

    return {"message": f"Item {item_id} marked as processed by {data.consumer_loop}"}


@router.get("/{slug}/items/workflow/{workflow_id}/step/{step_id}")
async def list_step_items(
    slug: str,
    workflow_id: str,
    step_id: int,
    unclaimed: bool = Query(True, description="Only return unclaimed items"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List items from a workflow step that are available for consumption.

    Returns completed items from the step that haven't been claimed yet.
    """
    manager, project, project_db = get_project(slug)

    # Get items from the workflow step (returns tuple of items and total)
    items_data, total = project_db.list_work_items(
        workflow_id=workflow_id,
        source_step_id=step_id,
        status="completed",
        unclaimed_only=unclaimed,
        limit=limit,
        offset=offset,
    )

    items = []
    for row in items_data:
        item = WorkItem.from_dict(row)
        items.append(ItemResponse.from_item(item))

    return ItemsPage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{slug}/items/workflow-counts/{workflow_id}")
async def get_workflow_item_counts(slug: str, workflow_id: str):
    """Get item counts grouped by step and status for a workflow.

    Useful for dashboard displays showing item progress per workflow step.
    """
    manager, project, project_db = get_project(slug)

    counts = project_db.get_workflow_item_counts(workflow_id)

    return {"counts": counts, "workflow_id": workflow_id}


@router.post("/{slug}/items/release-stale")
async def release_stale_claims(
    slug: str,
    max_age_minutes: int = Query(30, ge=1, le=1440, description="Release claims older than this"),
):
    """Release claims that have been held too long (likely from crashed consumers)."""
    manager, project, project_db = get_project(slug)

    released = project_db.release_stale_claims(max_age_minutes)

    return {"released_count": released, "max_age_minutes": max_age_minutes}
