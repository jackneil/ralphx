"""Configuration API routes for RalphX.

Provides endpoints for loop types, requirements, defaults, and import formats.
These are data-driven configurations stored in the project database.
"""

from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from ralphx.core.project import ProjectManager

router = APIRouter()


# ============================================================================
# Response Models
# ============================================================================


class LoopTypeResponse(BaseModel):
    """Loop type definition."""

    id: str
    label: str
    description: Optional[str] = None
    created_at: str


class LoopTypeRequirementResponse(BaseModel):
    """Requirement for a loop type."""

    id: int
    loop_type: str
    requirement_key: str
    category: str  # 'required' or 'recommended'
    label: str
    description: Optional[str] = None
    check_type: str  # 'resource', 'items_count', 'auth_status'
    check_config: Optional[dict] = None
    has_default: bool = False
    priority: int = 0


class LoopTypeDefaultResponse(BaseModel):
    """Default template/resource for a loop type."""

    id: int
    loop_type: str
    resource_type: str
    name: str
    content: str
    description: Optional[str] = None
    is_default: bool = True
    created_at: str


class ImportFormatResponse(BaseModel):
    """Import format definition."""

    id: str
    label: str
    description: Optional[str] = None
    field_mapping: dict
    category_mappings: Optional[dict] = None
    id_prefix_to_category: bool = False
    sample_content: Optional[str] = None
    created_at: str


class ImportJsonlRequest(BaseModel):
    """Request for JSONL import."""

    format_id: str = Field(..., description="Import format ID to use")
    namespace: str = Field(..., description="Namespace to assign to imported items")
    loop_name: Optional[str] = Field(None, description="Optional loop name for tracking")


class ImportJsonlResponse(BaseModel):
    """Response from JSONL import."""

    imported: int
    skipped: int
    errors: list[str]
    total_lines: int


class RequirementStatusResponse(BaseModel):
    """Status of a single requirement."""

    requirement_key: str
    label: str
    category: str
    check_type: str
    has_default: bool
    is_met: bool
    details: Optional[str] = None


class LoopRequirementsStatusResponse(BaseModel):
    """Combined status of all requirements for a loop type."""

    loop_type: str
    requirements: list[RequirementStatusResponse]
    all_required_met: bool
    all_recommended_met: bool


# ============================================================================
# Helper Functions
# ============================================================================


def get_project(slug: str):
    """Get project by slug or raise 404."""
    manager = ProjectManager()
    project = manager.get_project(slug)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )
    project_db = manager.get_project_db(project.path)
    return manager, project, project_db


# ============================================================================
# Loop Types Endpoints
# ============================================================================


@router.get("/{slug}/loop-types", response_model=list[LoopTypeResponse])
async def list_loop_types(slug: str):
    """List all available loop types."""
    manager, project, project_db = get_project(slug)

    # Seed defaults if needed
    project_db.seed_defaults_if_empty()

    loop_types = project_db.list_loop_types()
    return [LoopTypeResponse(**lt) for lt in loop_types]


@router.get("/{slug}/loop-types/{loop_type}", response_model=LoopTypeResponse)
async def get_loop_type(slug: str, loop_type: str):
    """Get a specific loop type."""
    manager, project, project_db = get_project(slug)

    lt = project_db.get_loop_type(loop_type)
    if not lt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop type not found: {loop_type}",
        )
    return LoopTypeResponse(**lt)


@router.get(
    "/{slug}/loop-types/{loop_type}/requirements",
    response_model=list[LoopTypeRequirementResponse],
)
async def get_loop_type_requirements(slug: str, loop_type: str):
    """Get requirements for a loop type."""
    manager, project, project_db = get_project(slug)

    requirements = project_db.get_loop_type_requirements(loop_type)
    return [LoopTypeRequirementResponse(**r) for r in requirements]


@router.get(
    "/{slug}/loop-types/{loop_type}/requirements/status",
    response_model=LoopRequirementsStatusResponse,
)
async def check_loop_type_requirements_status(slug: str, loop_type: str):
    """Check the status of requirements for a loop type.

    Returns which requirements are met based on current project state.
    """
    manager, project, project_db = get_project(slug)

    requirements = project_db.get_loop_type_requirements(loop_type)
    if not requirements:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No requirements found for loop type: {loop_type}",
        )

    # Check credentials for auth requirement
    from ralphx.core.database import Database

    global_db = Database()
    credentials = global_db.get_credentials()
    has_auth = credentials is not None

    # Get resource counts by type
    resources = project_db.list_resources(enabled=True)
    resource_counts = {}
    for r in resources:
        rt = r.get("resource_type", "custom")
        resource_counts[rt] = resource_counts.get(rt, 0) + 1

    # Get work item count
    stats = project_db.get_work_item_stats()
    item_count = stats.get("total", 0)

    statuses = []
    all_required_met = True
    all_recommended_met = True

    for req in requirements:
        is_met = False
        details = None
        check_type = req["check_type"]
        check_config = req.get("check_config") or {}

        if check_type == "auth_status":
            is_met = has_auth
            details = "Authenticated" if has_auth else "Not authenticated"

        elif check_type == "resource":
            resource_type = check_config.get("resource_type", "")
            count = resource_counts.get(resource_type, 0)
            has_default = req.get("has_default", False)
            is_met = count > 0 or has_default
            if count > 0:
                details = f"{count} resource(s) imported"
            elif has_default:
                details = "Using default"
            else:
                details = "No resources"

        elif check_type == "items_count":
            min_items = check_config.get("min", 1)
            is_met = item_count >= min_items
            details = f"{item_count} item(s)"

        # Track overall status
        if req["category"] == "required" and not is_met:
            all_required_met = False
        if req["category"] == "recommended" and not is_met:
            all_recommended_met = False

        statuses.append(
            RequirementStatusResponse(
                requirement_key=req["requirement_key"],
                label=req["label"],
                category=req["category"],
                check_type=check_type,
                has_default=req.get("has_default", False),
                is_met=is_met,
                details=details,
            )
        )

    return LoopRequirementsStatusResponse(
        loop_type=loop_type,
        requirements=statuses,
        all_required_met=all_required_met,
        all_recommended_met=all_recommended_met,
    )


@router.get(
    "/{slug}/loop-types/{loop_type}/defaults",
    response_model=list[LoopTypeDefaultResponse],
)
async def get_loop_type_defaults(
    slug: str,
    loop_type: str,
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
):
    """Get default templates/resources for a loop type."""
    manager, project, project_db = get_project(slug)

    defaults = project_db.list_loop_type_defaults(
        loop_type=loop_type,
        resource_type=resource_type,
    )
    return [LoopTypeDefaultResponse(**d) for d in defaults]


@router.get(
    "/{slug}/loop-types/{loop_type}/defaults/{resource_type}",
    response_model=LoopTypeDefaultResponse,
)
async def get_loop_type_default(
    slug: str,
    loop_type: str,
    resource_type: str,
    name: str = Query("default", description="Default name"),
):
    """Get a specific default template/resource."""
    manager, project, project_db = get_project(slug)

    default = project_db.get_loop_type_default(loop_type, resource_type, name)
    if not default:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Default not found: {loop_type}/{resource_type}/{name}",
        )
    return LoopTypeDefaultResponse(**default)


# ============================================================================
# Import Formats Endpoints
# ============================================================================


@router.get("/{slug}/import-formats", response_model=list[ImportFormatResponse])
async def list_import_formats(slug: str):
    """List all available import formats."""
    manager, project, project_db = get_project(slug)

    # Seed defaults if needed
    project_db.seed_defaults_if_empty()

    formats = project_db.list_import_formats()
    return [ImportFormatResponse(**f) for f in formats]


@router.get("/{slug}/import-formats/{format_id}", response_model=ImportFormatResponse)
async def get_import_format(slug: str, format_id: str):
    """Get a specific import format."""
    manager, project, project_db = get_project(slug)

    fmt = project_db.get_import_format(format_id)
    if not fmt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import format not found: {format_id}",
        )
    return ImportFormatResponse(**fmt)


@router.post("/{slug}/import-jsonl", response_model=ImportJsonlResponse)
async def import_jsonl_with_format(
    slug: str,
    format_id: str = Query(..., description="Import format ID"),
    workflow_id: str = Query(..., description="Parent workflow ID for imported items"),
    source_step_id: int = Query(..., description="Workflow step ID that is importing items"),
    loop_name: Optional[str] = Query(None, description="Optional loop name for tracking"),
    file: UploadFile = File(...),
):
    """Import work items from a JSONL file using a specified format.

    The format determines how fields in the JSONL are mapped to work item fields.
    Categories can be auto-detected from item ID prefixes if the format supports it.

    Work items are scoped to the specified workflow and step.
    """
    import tempfile
    from pathlib import Path

    manager, project, project_db = get_project(slug)

    # Verify workflow exists
    workflow = project_db.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow not found: {workflow_id}",
        )

    # Verify step exists and belongs to this workflow
    step = project_db.get_workflow_step(source_step_id)
    if not step or step["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Step {source_step_id} not found or does not belong to workflow {workflow_id}",
        )

    # Read and validate file
    content = await file.read()

    # Check file size (50 MB limit)
    max_size = 50 * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {max_size // (1024*1024)} MB",
        )

    try:
        content_str = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be UTF-8 encoded",
        )

    # Save to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
        tmp.write(content_str)
        tmp_path = Path(tmp.name)

    try:
        result = project_db.import_jsonl(
            file_path=str(tmp_path),
            format_id=format_id,
            workflow_id=workflow_id,
            source_step_id=source_step_id,
            loop_name=loop_name,
        )

        return ImportJsonlResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    finally:
        tmp_path.unlink(missing_ok=True)


# ============================================================================
# Namespace Endpoints
# ============================================================================


class NamespaceInfo(BaseModel):
    """Information about a namespace."""

    namespace: str
    item_count: int
    pending_count: int
    completed_count: int
    processed_count: int


@router.get("/{slug}/namespaces", response_model=list[NamespaceInfo])
async def list_namespaces(slug: str):
    """List all namespaces with item counts.

    Returns namespaces that have work items, along with counts by status.
    """
    manager, project, project_db = get_project(slug)

    # Get all items grouped by namespace
    items, _ = project_db.list_work_items(limit=10000)

    namespace_stats = {}
    for item in items:
        ns = item.get("namespace")
        if not ns:
            continue

        if ns not in namespace_stats:
            namespace_stats[ns] = {
                "namespace": ns,
                "item_count": 0,
                "pending_count": 0,
                "completed_count": 0,
                "processed_count": 0,
            }

        namespace_stats[ns]["item_count"] += 1
        status = item.get("status", "pending")
        if status == "pending":
            namespace_stats[ns]["pending_count"] += 1
        elif status == "completed":
            namespace_stats[ns]["completed_count"] += 1
        elif status == "processed":
            namespace_stats[ns]["processed_count"] += 1

    return [NamespaceInfo(**ns) for ns in namespace_stats.values()]


# ============================================================================
# Project Resources (Shared Library) Endpoints
# ============================================================================


class ProjectResourceResponse(BaseModel):
    """Project-level shared resource."""

    id: int
    resource_type: str
    name: str
    content: Optional[str] = None
    description: Optional[str] = None
    auto_inherit: bool = True
    created_at: str
    updated_at: str


class CreateProjectResourceRequest(BaseModel):
    """Request to create a project resource."""

    resource_type: str = Field(..., description="Type: design_doc, guardrail, prompt, etc.")
    name: str = Field(..., description="Display name for the resource")
    content: str = Field(..., description="Resource content")
    description: Optional[str] = Field(None, description="Optional description")
    auto_inherit: bool = Field(True, description="Auto-add to new workflows")


class UpdateProjectResourceRequest(BaseModel):
    """Request to update a project resource."""

    name: Optional[str] = None
    content: Optional[str] = None
    description: Optional[str] = None
    auto_inherit: Optional[bool] = None


@router.get("/{slug}/project-resources", response_model=list[ProjectResourceResponse])
async def list_project_resources(
    slug: str,
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
):
    """List all project-level shared resources.

    These are template resources that can be inherited by workflows.
    """
    manager, project, project_db = get_project(slug)

    resources = project_db.list_project_resources(resource_type=resource_type)
    return [ProjectResourceResponse(**r) for r in resources]


@router.post(
    "/{slug}/project-resources",
    response_model=ProjectResourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_resource(slug: str, request: CreateProjectResourceRequest):
    """Create a new project-level shared resource."""
    manager, project, project_db = get_project(slug)

    resource_id = project_db.create_project_resource(
        resource_type=request.resource_type,
        name=request.name,
        content=request.content,
        description=request.description,
        auto_inherit=request.auto_inherit,
    )

    resource = project_db.get_project_resource(resource_id)
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create resource",
        )
    return ProjectResourceResponse(**resource)


@router.get(
    "/{slug}/project-resources/{resource_id}",
    response_model=ProjectResourceResponse,
)
async def get_project_resource(slug: str, resource_id: int):
    """Get a specific project resource."""
    manager, project, project_db = get_project(slug)

    resource = project_db.get_project_resource(resource_id)
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project resource not found: {resource_id}",
        )
    return ProjectResourceResponse(**resource)


@router.patch(
    "/{slug}/project-resources/{resource_id}",
    response_model=ProjectResourceResponse,
)
async def update_project_resource(
    slug: str,
    resource_id: int,
    request: UpdateProjectResourceRequest,
):
    """Update a project resource."""
    manager, project, project_db = get_project(slug)

    # Check exists
    existing = project_db.get_project_resource(resource_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project resource not found: {resource_id}",
        )

    # Build update dict
    updates = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.content is not None:
        updates["content"] = request.content
    if request.description is not None:
        updates["description"] = request.description
    if request.auto_inherit is not None:
        updates["auto_inherit"] = request.auto_inherit

    if updates:
        project_db.update_project_resource(resource_id, **updates)

    resource = project_db.get_project_resource(resource_id)
    return ProjectResourceResponse(**resource)


@router.delete(
    "/{slug}/project-resources/{resource_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_project_resource(slug: str, resource_id: int):
    """Delete a project resource."""
    manager, project, project_db = get_project(slug)

    existing = project_db.get_project_resource(resource_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project resource not found: {resource_id}",
        )

    project_db.delete_project_resource(resource_id)
    return None
