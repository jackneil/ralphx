"""Resource management API routes."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from ralphx.core.project import ProjectManager
from ralphx.core.resources import InjectionPosition, ResourceManager, ResourceType

router = APIRouter()


# Request/Response models
class ResourceCreate(BaseModel):
    """Request model for creating a resource."""

    name: str = Field(..., min_length=1, max_length=100, description="Resource name (without type prefix)")
    resource_type: str = Field(..., description="Resource type (design_doc, architecture, coding_standards, domain_knowledge, custom)")
    content: str = Field(..., min_length=1, description="Markdown content")
    injection_position: Optional[str] = Field(None, description="Where to inject (before_prompt, after_design_doc, before_task, after_task)")


class ResourceUpdate(BaseModel):
    """Request model for updating a resource."""

    content: Optional[str] = Field(None, description="New markdown content")
    injection_position: Optional[str] = Field(None, description="Where to inject")
    enabled: Optional[bool] = Field(None, description="Enable/disable resource")
    inherit_default: Optional[bool] = Field(None, description="Whether loops inherit by default")
    priority: Optional[int] = Field(None, ge=0, le=1000, description="Ordering priority (lower = earlier)")


class ResourceResponse(BaseModel):
    """Response model for a resource."""

    id: int
    name: str
    resource_type: str
    file_path: str
    injection_position: str
    enabled: bool
    inherit_default: bool
    priority: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    content: Optional[str] = None


class ResourceSyncResult(BaseModel):
    """Result of syncing resources from filesystem."""

    added: int
    updated: int
    removed: int


def get_manager() -> ProjectManager:
    """Get project manager instance."""
    return ProjectManager()


def get_project_and_resources(slug: str):
    """Get project and resource manager or raise 404.

    Returns:
        Tuple of (project_manager, project, resource_manager).
    """
    manager = get_manager()
    project = manager.get_project(slug)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )
    project_db = manager.get_project_db(project.path)
    resource_manager = ResourceManager(project.path, db=project_db)
    return manager, project, resource_manager


def validate_resource_type(resource_type: str) -> ResourceType:
    """Validate and convert resource type string."""
    try:
        return ResourceType(resource_type)
    except ValueError:
        valid_types = [t.value for t in ResourceType]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid resource_type: {resource_type}. Must be one of: {valid_types}",
        )


def validate_injection_position(position: Optional[str]) -> Optional[InjectionPosition]:
    """Validate and convert injection position string."""
    if position is None:
        return None
    try:
        return InjectionPosition(position)
    except ValueError:
        valid_positions = [p.value for p in InjectionPosition]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid injection_position: {position}. Must be one of: {valid_positions}",
        )


@router.get("/{slug}/resources", response_model=list[ResourceResponse])
async def list_resources(
    slug: str,
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    include_content: bool = Query(False, description="Include file content in response"),
):
    """List all resources for a project."""
    manager, project, resource_manager = get_project_and_resources(slug)

    # Validate resource_type if provided
    rt = None
    if resource_type:
        rt = validate_resource_type(resource_type)

    resources = resource_manager.list_resources(
        resource_type=rt,
        enabled=enabled,
    )

    results = []
    for r in resources:
        response = ResourceResponse(
            id=r["id"],
            name=r["name"],
            resource_type=r["resource_type"],
            file_path=r["file_path"],
            injection_position=r["injection_position"],
            enabled=r["enabled"],
            inherit_default=r["inherit_default"],
            priority=r["priority"],
            created_at=r.get("created_at"),
            updated_at=r.get("updated_at"),
        )

        # Optionally load content
        if include_content:
            loaded = resource_manager.load_resource(r)
            if loaded:
                response.content = loaded.content

        results.append(response)

    return results


@router.get("/{slug}/resources/{resource_id}", response_model=ResourceResponse)
async def get_resource(
    slug: str,
    resource_id: int,
    include_content: bool = Query(True, description="Include file content"),
):
    """Get a specific resource by ID."""
    manager, project, resource_manager = get_project_and_resources(slug)

    resource = resource_manager.get_resource(resource_id)
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource not found: {resource_id}",
        )

    response = ResourceResponse(
        id=resource["id"],
        name=resource["name"],
        resource_type=resource["resource_type"],
        file_path=resource["file_path"],
        injection_position=resource["injection_position"],
        enabled=resource["enabled"],
        inherit_default=resource["inherit_default"],
        priority=resource["priority"],
        created_at=resource.get("created_at"),
        updated_at=resource.get("updated_at"),
    )

    if include_content:
        loaded = resource_manager.load_resource(resource)
        if loaded:
            response.content = loaded.content

    return response


@router.post("/{slug}/resources", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(slug: str, data: ResourceCreate):
    """Create a new resource."""
    manager, project, resource_manager = get_project_and_resources(slug)

    # Validate types
    rt = validate_resource_type(data.resource_type)
    ip = validate_injection_position(data.injection_position)

    # Create resource (creates file and db entry)
    resource = resource_manager.create_resource(
        name=data.name,
        resource_type=rt,
        content=data.content,
        injection_position=ip,
    )

    return ResourceResponse(
        id=resource["id"],
        name=resource["name"],
        resource_type=resource["resource_type"],
        file_path=resource["file_path"],
        injection_position=resource["injection_position"],
        enabled=resource["enabled"],
        inherit_default=resource["inherit_default"],
        priority=resource["priority"],
        created_at=resource.get("created_at"),
        updated_at=resource.get("updated_at"),
        content=data.content,
    )


@router.patch("/{slug}/resources/{resource_id}", response_model=ResourceResponse)
async def update_resource(slug: str, resource_id: int, data: ResourceUpdate):
    """Update a resource."""
    manager, project, resource_manager = get_project_and_resources(slug)

    # Verify resource exists
    resource = resource_manager.get_resource(resource_id)
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource not found: {resource_id}",
        )

    # Validate injection position if provided
    ip = validate_injection_position(data.injection_position)

    # Update
    resource_manager.update_resource(
        resource_id=resource_id,
        content=data.content,
        injection_position=ip,
        enabled=data.enabled,
        inherit_default=data.inherit_default,
        priority=data.priority,
    )

    # Get updated resource
    updated = resource_manager.get_resource(resource_id)
    response = ResourceResponse(
        id=updated["id"],
        name=updated["name"],
        resource_type=updated["resource_type"],
        file_path=updated["file_path"],
        injection_position=updated["injection_position"],
        enabled=updated["enabled"],
        inherit_default=updated["inherit_default"],
        priority=updated["priority"],
        created_at=updated.get("created_at"),
        updated_at=updated.get("updated_at"),
    )

    # Include content if it was updated
    if data.content is not None:
        response.content = data.content
    else:
        loaded = resource_manager.load_resource(updated)
        if loaded:
            response.content = loaded.content

    return response


@router.delete("/{slug}/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(
    slug: str,
    resource_id: int,
    delete_file: bool = Query(True, description="Also delete the file from disk"),
):
    """Delete a resource."""
    manager, project, resource_manager = get_project_and_resources(slug)

    # Verify resource exists
    resource = resource_manager.get_resource(resource_id)
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource not found: {resource_id}",
        )

    resource_manager.delete_resource(resource_id, delete_file=delete_file)
    return None


@router.post("/{slug}/resources/sync", response_model=ResourceSyncResult)
async def sync_resources(slug: str):
    """Sync resources from filesystem to database.

    Discovers markdown files in .ralphx/resources/ subdirectories
    and creates/updates database entries to match.
    """
    manager, project, resource_manager = get_project_and_resources(slug)

    result = resource_manager.sync_from_filesystem()

    return ResourceSyncResult(
        added=result["added"],
        updated=result["updated"],
        removed=result["removed"],
    )


@router.get("/{slug}/resources/types")
async def list_resource_types():
    """List available resource types."""
    return {
        "types": [
            {
                "value": t.value,
                "label": t.value.replace("_", " ").title(),
            }
            for t in ResourceType
        ],
        "positions": [
            {
                "value": p.value,
                "label": p.value.replace("_", " ").title(),
            }
            for p in InjectionPosition
        ],
    }
