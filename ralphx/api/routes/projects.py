"""Project CRUD API routes."""

import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ralphx.core.loop import LoopLoader
from ralphx.core.project import ProjectManager
from ralphx.core.project_db import ProjectDatabase
from ralphx.models.project import Project

router = APIRouter()


# Request/Response models
class ProjectCreate(BaseModel):
    """Request model for creating a project."""

    path: str = Field(..., description="Path to project directory")
    name: Optional[str] = Field(None, description="Human-readable name")
    design_doc: Optional[str] = Field(None, description="Path to design document")


class ProjectResponse(BaseModel):
    """Response model for a project."""

    id: str
    slug: str
    name: str
    path: str
    design_doc: Optional[str] = None
    created_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_project(cls, project: Project) -> "ProjectResponse":
        """Create from Project model."""
        return cls(
            id=project.id,
            slug=project.slug,
            name=project.name,
            path=str(project.path),
            design_doc=project.design_doc,
            created_at=project.created_at.isoformat() if project.created_at else "",
        )


class ProjectStats(BaseModel):
    """Project statistics."""

    total: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    # Frontend-friendly aliases
    total_items: int = 0
    pending_items: int = 0
    completed_items: int = 0
    loops: int = 0
    active_runs: int = 0


class ProjectWithStats(ProjectResponse):
    """Project response with statistics."""

    stats: ProjectStats = Field(default_factory=ProjectStats)


def get_manager() -> ProjectManager:
    """Get project manager instance."""
    return ProjectManager()


@router.get("", response_model=list[ProjectResponse])
async def list_projects():
    """List all registered projects."""
    manager = get_manager()
    projects = manager.list_projects()
    return [ProjectResponse.from_project(p) for p in projects]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(data: ProjectCreate):
    """Register a new project."""
    manager = get_manager()

    # Validate path exists
    path = Path(data.path)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path does not exist: {data.path}",
        )

    if not path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path is not a directory: {data.path}",
        )

    try:
        project = manager.add_project(
            path=path,
            name=data.name,
            design_doc=data.design_doc,
        )
        return ProjectResponse.from_project(project)
    except FileExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{slug}", response_model=ProjectWithStats)
async def get_project(slug: str):
    """Get a specific project by slug."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )

    # Get stats
    stats_data = manager.get_project_stats(slug) or {"total": 0, "by_status": {}}
    by_status = stats_data.get("by_status", {})

    # Get loops count using LoopLoader
    project_db = ProjectDatabase(project.path)
    loader = LoopLoader(db=project_db)
    loops = loader.list_loops()
    loops_count = len(loops)

    # Count active runs - check run status for each loop
    # For now, just set to 0 since we'd need to check the runs table
    active_runs = 0

    # Build stats with frontend-friendly fields
    stats = ProjectStats(
        total=stats_data.get("total", 0),
        by_status=by_status,
        total_items=stats_data.get("total", 0),
        pending_items=by_status.get("pending", 0),
        completed_items=by_status.get("completed", 0),
        loops=loops_count,
        active_runs=active_runs,
    )

    # Create base response first
    base = ProjectResponse.from_project(project)
    response = ProjectWithStats(
        id=base.id,
        slug=base.slug,
        name=base.name,
        path=base.path,
        design_doc=base.design_doc,
        created_at=base.created_at,
        stats=stats,
    )
    return response


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    slug: str,
    delete_workspace: bool = False,
):
    """Remove a project."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )

    result = manager.remove_project(slug, delete_local_data=delete_workspace)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove project",
        )

    return None


class CleanupRequest(BaseModel):
    """Request model for cleanup operation."""

    pattern: str = Field(
        default="^e2e-",
        description="Regex pattern to match project slugs for deletion"
    )
    dry_run: bool = Field(
        default=True,
        description="If True, only report what would be deleted"
    )


class CleanupResponse(BaseModel):
    """Response model for cleanup operation."""

    deleted: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list, description="Slugs that failed to delete")
    dry_run: bool


@router.post("/cleanup", response_model=CleanupResponse)
async def cleanup_projects(data: CleanupRequest):
    """Clean up projects matching a pattern.

    Used to remove orphaned test projects (e2e-test-*, e2e-loop-*, etc.).
    By default runs in dry_run mode to preview deletions.
    """
    import logging
    logger = logging.getLogger("ralphx.api.projects")

    manager = get_manager()
    projects = manager.list_projects()

    # Compile pattern
    try:
        pattern = re.compile(data.pattern)
    except re.error as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid regex pattern: {e}",
        )

    # Find matching projects
    matching = [p for p in projects if pattern.match(p.slug)]
    deleted_slugs = []
    failed_slugs = []

    if not data.dry_run:
        for project in matching:
            try:
                manager.remove_project(project.slug, delete_local_data=False)
                deleted_slugs.append(project.slug)
                logger.info(f"Cleanup: deleted project '{project.slug}'")
            except Exception as e:
                # Log the actual error instead of silently swallowing it
                logger.error(f"Cleanup: failed to delete '{project.slug}': {e}")
                failed_slugs.append(project.slug)
    else:
        deleted_slugs = [p.slug for p in matching]

    return CleanupResponse(deleted=deleted_slugs, failed=failed_slugs, dry_run=data.dry_run)
