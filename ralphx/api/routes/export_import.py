"""Export/Import API routes for RalphX.

Provides endpoints for:
- Workflow export/import (single workflow)
- Project export/import (multiple workflows)
"""

from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ralphx.core.database import Database
from ralphx.core.project_db import ProjectDatabase
from ralphx.core.project_export import ProjectExporter, ProjectExportOptions
from ralphx.core.project_import import ProjectImporter, ProjectImportOptions
from ralphx.core.workflow_export import ExportOptions, WorkflowExporter
from ralphx.core.workflow_import import ConflictResolution, ImportOptions, WorkflowImporter, MAX_IMPORT_SIZE_MB


router = APIRouter()


# Maximum upload size in bytes (must match MAX_IMPORT_SIZE_MB from workflow_import)
MAX_UPLOAD_SIZE = MAX_IMPORT_SIZE_MB * 1024 * 1024


async def _read_upload_with_limit(file: UploadFile, max_size: int = MAX_UPLOAD_SIZE) -> bytes:
    """Read uploaded file with size limit to prevent memory exhaustion.

    Args:
        file: The uploaded file.
        max_size: Maximum allowed size in bytes.

    Returns:
        File content as bytes.

    Raises:
        HTTPException: If file exceeds size limit.
    """
    chunks = []
    total_size = 0

    # Read in chunks to avoid loading huge files all at once
    chunk_size = 1024 * 1024  # 1MB chunks

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break

        total_size += len(chunk)
        if total_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size exceeds maximum allowed size of {MAX_IMPORT_SIZE_MB}MB",
            )

        chunks.append(chunk)

    return b''.join(chunks)


# ============================================================================
# Request/Response Models
# ============================================================================


class ExportPreviewResponse(BaseModel):
    """Response for export preview."""
    workflow_name: str
    workflow_namespace: str
    steps_count: int
    items_total: int
    resources_count: int
    has_planning_session: bool
    runs_count: int
    estimated_size_bytes: int
    potential_secrets_detected: bool
    warnings: list[str] = []


class WorkflowExportRequest(BaseModel):
    """Request for workflow export."""
    include_runs: bool = False
    include_planning: bool = True
    include_planning_messages: bool = False
    strip_secrets: bool = False
    as_template: bool = False


class StepPreviewResponse(BaseModel):
    """Preview info for a single step."""
    step_number: int
    name: str
    step_type: str
    items_count: int


class ResourcePreviewResponse(BaseModel):
    """Preview info for a single resource."""
    id: int
    name: str
    resource_type: str


class ImportPreviewResponse(BaseModel):
    """Response for import preview."""
    workflow_name: str
    workflow_namespace: str
    exported_at: str
    ralphx_version: str
    schema_version: int
    steps_count: int
    items_count: int
    resources_count: int
    has_planning_session: bool
    has_runs: bool
    is_compatible: bool
    compatibility_notes: list[str]
    potential_secrets_detected: bool
    # Detailed breakdown for selective import
    steps: list[StepPreviewResponse] = []
    resources: list[ResourcePreviewResponse] = []


class ConflictInfo(BaseModel):
    """Information about a conflict."""
    conflict_type: str
    source_id: str
    source_name: str
    target_id: Optional[str] = None
    target_name: Optional[str] = None
    details: Optional[str] = None


class MergePreviewResponse(BaseModel):
    """Response for merge preview."""
    workflow_name: str
    workflow_namespace: str
    items_count: int
    resources_count: int
    conflicts: list[ConflictInfo]
    is_compatible: bool
    compatibility_notes: list[str]


class WorkflowImportRequest(BaseModel):
    """Request for workflow import."""
    conflict_resolution: str = Field(
        default="rename",
        pattern=r"^(skip|rename|overwrite)$",
    )
    import_items: bool = True
    import_resources: bool = True
    import_planning: bool = True
    import_runs: bool = False
    selected_step_ids: Optional[list[int]] = None
    selected_resource_ids: Optional[list[int]] = None


class MergeRequest(BaseModel):
    """Request for merging into existing workflow."""
    conflict_resolution: str = Field(
        default="rename",
        pattern=r"^(skip|rename|overwrite)$",
    )
    import_items: bool = True
    import_resources: bool = True
    import_planning: bool = True


class ImportResultResponse(BaseModel):
    """Response for import result."""
    success: bool
    workflow_id: str
    workflow_name: str
    steps_created: int
    items_imported: int
    items_renamed: int
    items_skipped: int
    resources_created: int
    resources_renamed: int
    planning_sessions_imported: int
    runs_imported: int
    warnings: list[str]


# Project export/import models


class WorkflowSummaryResponse(BaseModel):
    """Summary of a workflow in project export."""
    id: str
    name: str
    namespace: str
    steps_count: int
    items_count: int
    resources_count: int


class ProjectExportPreviewResponse(BaseModel):
    """Response for project export preview."""
    project_name: str
    project_slug: str
    workflows: list[WorkflowSummaryResponse]
    total_items: int
    total_resources: int
    estimated_size_bytes: int
    potential_secrets_detected: bool


class ProjectExportRequest(BaseModel):
    """Request for project export."""
    workflow_ids: Optional[list[str]] = None
    include_runs: bool = False
    include_planning: bool = True
    include_planning_messages: bool = False
    strip_secrets: bool = False
    include_project_resources: bool = True


class ProjectImportPreviewResponse(BaseModel):
    """Response for project import preview."""
    is_project_export: bool
    project_name: Optional[str] = None
    project_slug: Optional[str] = None
    workflows: list[WorkflowSummaryResponse]
    total_items: int
    total_resources: int
    shared_resources_count: int
    is_compatible: bool
    compatibility_notes: list[str]
    exported_at: Optional[str] = None
    ralphx_version: Optional[str] = None
    schema_version: int


class ProjectImportRequest(BaseModel):
    """Request for project import."""
    selected_workflow_ids: Optional[list[str]] = None
    import_shared_resources: bool = True
    conflict_resolution: str = Field(
        default="rename",
        pattern=r"^(skip|rename|overwrite)$",
    )


class WorkflowImportResultResponse(BaseModel):
    """Result for a single workflow import."""
    success: bool
    workflow_id: str
    workflow_name: str
    steps_created: int
    items_imported: int
    items_renamed: int
    items_skipped: int
    resources_created: int
    warnings: list[str]


class ProjectImportResultResponse(BaseModel):
    """Response for project import result."""
    success: bool
    workflows_imported: int
    workflow_results: list[WorkflowImportResultResponse]
    shared_resources_imported: int
    warnings: list[str]


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


def _get_project_and_db(slug: str) -> tuple[dict, ProjectDatabase]:
    """Get project info and database."""
    db = Database()
    project = db.get_project(slug)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{slug}' not found",
        )
    return project, ProjectDatabase(project["path"])


# ============================================================================
# Workflow Export Endpoints
# ============================================================================


@router.get("/workflows/{workflow_id}/export/preview", response_model=ExportPreviewResponse)
async def preview_workflow_export(slug: str, workflow_id: str):
    """Preview what will be exported from a workflow.

    Returns counts of steps, items, resources, and estimated size.
    Also scans for potential secrets and warns if found.
    """
    pdb = _get_project_db(slug)

    exporter = WorkflowExporter(pdb)
    try:
        preview = exporter.get_preview(workflow_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    return ExportPreviewResponse(
        workflow_name=preview.workflow_name,
        workflow_namespace=preview.workflow_namespace,
        steps_count=preview.steps_count,
        items_total=preview.items_total,
        resources_count=preview.resources_count,
        has_planning_session=preview.has_planning_session,
        runs_count=preview.runs_count,
        estimated_size_bytes=preview.estimated_size_bytes,
        potential_secrets_detected=len(preview.potential_secrets) > 0,
        warnings=preview.warnings,
    )


@router.post("/workflows/{workflow_id}/export")
async def export_workflow(
    slug: str,
    workflow_id: str,
    request: WorkflowExportRequest,
):
    """Export a workflow to a ZIP file.

    Returns the ZIP file as a download.
    """
    pdb = _get_project_db(slug)

    exporter = WorkflowExporter(pdb)

    options = ExportOptions(
        include_runs=request.include_runs,
        include_planning=request.include_planning,
        include_planning_messages=request.include_planning_messages,
        strip_secrets=request.strip_secrets,
        as_template=request.as_template,
    )

    try:
        zip_bytes, filename = exporter.export_workflow(workflow_id, options)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# ============================================================================
# Workflow Import Endpoints
# ============================================================================


@router.post("/workflows/import/preview", response_model=ImportPreviewResponse)
async def preview_workflow_import(
    slug: str,
    file: UploadFile = File(...),
):
    """Preview what will be imported from a ZIP file.

    Upload the ZIP file to see its contents and compatibility.
    """
    pdb = _get_project_db(slug)

    # Read file content with size limit
    zip_data = await _read_upload_with_limit(file)

    importer = WorkflowImporter(pdb)
    try:
        preview = importer.get_preview(zip_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return ImportPreviewResponse(
        workflow_name=preview.workflow_name,
        workflow_namespace=preview.workflow_namespace,
        exported_at=preview.exported_at,
        ralphx_version=preview.ralphx_version,
        schema_version=preview.schema_version,
        steps_count=preview.steps_count,
        items_count=preview.items_count,
        resources_count=preview.resources_count,
        has_planning_session=preview.has_planning_session,
        has_runs=preview.has_runs,
        is_compatible=preview.is_compatible,
        compatibility_notes=preview.compatibility_notes,
        potential_secrets_detected=preview.potential_secrets_detected,
        steps=[
            StepPreviewResponse(
                step_number=s.step_number,
                name=s.name,
                step_type=s.step_type,
                items_count=s.items_count,
            )
            for s in preview.steps
        ],
        resources=[
            ResourcePreviewResponse(
                id=r.id,
                name=r.name,
                resource_type=r.resource_type,
            )
            for r in preview.resources
        ],
    )


@router.post("/workflows/import", response_model=ImportResultResponse)
async def import_workflow(
    slug: str,
    file: UploadFile = File(...),
    conflict_resolution: str = Query(default="rename", pattern=r"^(skip|rename|overwrite)$"),
    import_items: bool = Query(default=True),
    import_resources: bool = Query(default=True),
    import_planning: bool = Query(default=True),
    import_runs: bool = Query(default=False),
    selected_steps: Optional[str] = Query(default=None, description="Comma-separated step numbers to import"),
    selected_resource_ids: Optional[str] = Query(default=None, description="Comma-separated resource IDs to import"),
):
    """Import a workflow from a ZIP file.

    Creates a new workflow with all IDs regenerated.
    Optionally filter to specific steps and resources.
    """
    pdb = _get_project_db(slug)

    zip_data = await _read_upload_with_limit(file)

    importer = WorkflowImporter(pdb)

    # Parse comma-separated values if provided
    step_ids = None
    if selected_steps:
        try:
            step_ids = [int(s.strip()) for s in selected_steps.split(',') if s.strip()]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="selected_steps must be comma-separated integers",
            )

    resource_ids = None
    if selected_resource_ids:
        try:
            resource_ids = [int(r.strip()) for r in selected_resource_ids.split(',') if r.strip()]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="selected_resource_ids must be comma-separated integers",
            )

    options = ImportOptions(
        conflict_resolution=ConflictResolution(conflict_resolution),
        import_items=import_items,
        import_resources=import_resources,
        import_planning=import_planning,
        import_runs=import_runs,
        selected_step_ids=step_ids,
        selected_resource_ids=resource_ids,
    )

    try:
        result = importer.import_workflow(zip_data, options)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return ImportResultResponse(
        success=result.success,
        workflow_id=result.workflow_id,
        workflow_name=result.workflow_name,
        steps_created=result.steps_created,
        items_imported=result.items_imported,
        items_renamed=result.items_renamed,
        items_skipped=result.items_skipped,
        resources_created=result.resources_created,
        resources_renamed=result.resources_renamed,
        planning_sessions_imported=result.planning_sessions_imported,
        runs_imported=result.runs_imported,
        warnings=result.warnings,
    )


@router.post("/workflows/{workflow_id}/merge/preview", response_model=MergePreviewResponse)
async def preview_workflow_merge(
    slug: str,
    workflow_id: str,
    file: UploadFile = File(...),
):
    """Preview merging imported content into an existing workflow.

    Shows detected conflicts and resolution options.
    """
    pdb = _get_project_db(slug)

    zip_data = await _read_upload_with_limit(file)

    importer = WorkflowImporter(pdb)
    try:
        preview = importer.get_merge_preview(zip_data, workflow_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    conflicts = [
        ConflictInfo(
            conflict_type=c.conflict_type.value,
            source_id=c.source_id,
            source_name=c.source_name,
            target_id=c.target_id,
            target_name=c.target_name,
            details=c.details,
        )
        for c in preview.conflicts
    ]

    return MergePreviewResponse(
        workflow_name=preview.workflow_name,
        workflow_namespace=preview.workflow_namespace,
        items_count=preview.items_count,
        resources_count=preview.resources_count,
        conflicts=conflicts,
        is_compatible=preview.is_compatible,
        compatibility_notes=preview.compatibility_notes,
    )


@router.post("/workflows/{workflow_id}/merge", response_model=ImportResultResponse)
async def merge_into_workflow(
    slug: str,
    workflow_id: str,
    file: UploadFile = File(...),
    conflict_resolution: str = Query(default="rename", pattern=r"^(skip|rename|overwrite)$"),
    import_items: bool = Query(default=True),
    import_resources: bool = Query(default=True),
    import_planning: bool = Query(default=True),
):
    """Merge imported content into an existing workflow.

    Uses specified conflict resolution strategy for conflicts.
    """
    pdb = _get_project_db(slug)

    zip_data = await _read_upload_with_limit(file)

    importer = WorkflowImporter(pdb)

    options = ImportOptions(
        conflict_resolution=ConflictResolution(conflict_resolution),
        import_items=import_items,
        import_resources=import_resources,
        import_planning=import_planning,
    )

    try:
        result = importer.merge_into_workflow(zip_data, workflow_id, options)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return ImportResultResponse(
        success=result.success,
        workflow_id=result.workflow_id,
        workflow_name=result.workflow_name,
        steps_created=result.steps_created,
        items_imported=result.items_imported,
        items_renamed=result.items_renamed,
        items_skipped=result.items_skipped,
        resources_created=result.resources_created,
        resources_renamed=result.resources_renamed,
        planning_sessions_imported=result.planning_sessions_imported,
        runs_imported=result.runs_imported,
        warnings=result.warnings,
    )


# ============================================================================
# Project Export Endpoints
# ============================================================================


@router.get("/export/preview", response_model=ProjectExportPreviewResponse)
async def preview_project_export(
    slug: str,
    workflow_ids: Optional[list[str]] = Query(default=None),
):
    """Preview what will be exported from the project.

    Returns list of workflows with their counts.
    """
    project, pdb = _get_project_and_db(slug)

    options = ProjectExportOptions(workflow_ids=workflow_ids)
    exporter = ProjectExporter(pdb, project)

    preview = exporter.get_preview(options)

    return ProjectExportPreviewResponse(
        project_name=preview.project_name,
        project_slug=preview.project_slug,
        workflows=[
            WorkflowSummaryResponse(
                id=w.id,
                name=w.name,
                namespace=w.namespace,
                steps_count=w.steps_count,
                items_count=w.items_count,
                resources_count=w.resources_count,
            )
            for w in preview.workflows
        ],
        total_items=preview.total_items,
        total_resources=preview.total_resources,
        estimated_size_bytes=preview.estimated_size_bytes,
        potential_secrets_detected=len(preview.potential_secrets) > 0,
    )


@router.post("/export")
async def export_project(
    slug: str,
    request: ProjectExportRequest,
):
    """Export the project (or selected workflows) to a ZIP file.

    Returns the ZIP file as a download.
    """
    project, pdb = _get_project_and_db(slug)

    options = ProjectExportOptions(
        workflow_ids=request.workflow_ids,
        include_runs=request.include_runs,
        include_planning=request.include_planning,
        include_planning_messages=request.include_planning_messages,
        strip_secrets=request.strip_secrets,
        include_project_resources=request.include_project_resources,
    )

    exporter = ProjectExporter(pdb, project)

    try:
        zip_bytes, filename = exporter.export_project(options)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# ============================================================================
# Project Import Endpoints
# ============================================================================


@router.post("/import/preview", response_model=ProjectImportPreviewResponse)
async def preview_project_import(
    slug: str,
    file: UploadFile = File(...),
):
    """Preview what will be imported from a ZIP file.

    Auto-detects whether this is a project export or workflow export.
    """
    pdb = _get_project_db(slug)

    zip_data = await _read_upload_with_limit(file)

    importer = ProjectImporter(pdb)
    try:
        preview = importer.get_preview(zip_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return ProjectImportPreviewResponse(
        is_project_export=preview.is_project_export,
        project_name=preview.project_name,
        project_slug=preview.project_slug,
        workflows=[
            WorkflowSummaryResponse(
                id=w.id,
                name=w.name,
                namespace=w.namespace,
                steps_count=w.steps_count,
                items_count=w.items_count,
                resources_count=w.resources_count,
            )
            for w in preview.workflows
        ],
        total_items=preview.total_items,
        total_resources=preview.total_resources,
        shared_resources_count=preview.shared_resources_count,
        is_compatible=preview.is_compatible,
        compatibility_notes=preview.compatibility_notes,
        exported_at=preview.exported_at,
        ralphx_version=preview.ralphx_version,
        schema_version=preview.schema_version,
    )


@router.post("/import", response_model=ProjectImportResultResponse)
async def import_project(
    slug: str,
    file: UploadFile = File(...),
    selected_workflow_ids: Optional[list[str]] = Query(default=None),
    import_shared_resources: bool = Query(default=True),
    conflict_resolution: str = Query(default="rename", pattern=r"^(skip|rename|overwrite)$"),
):
    """Import workflows from a ZIP file.

    Supports both project exports (multiple workflows) and single workflow exports.
    """
    pdb = _get_project_db(slug)

    zip_data = await _read_upload_with_limit(file)

    options = ProjectImportOptions(
        selected_workflow_ids=selected_workflow_ids,
        import_shared_resources=import_shared_resources,
        conflict_resolution=ConflictResolution(conflict_resolution),
    )

    importer = ProjectImporter(pdb)
    try:
        result = importer.import_project(zip_data, options)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return ProjectImportResultResponse(
        success=result.success,
        workflows_imported=result.workflows_imported,
        workflow_results=[
            WorkflowImportResultResponse(
                success=r.success,
                workflow_id=r.workflow_id,
                workflow_name=r.workflow_name,
                steps_created=r.steps_created,
                items_imported=r.items_imported,
                items_renamed=r.items_renamed,
                items_skipped=r.items_skipped,
                resources_created=r.resources_created,
                warnings=r.warnings,
            )
            for r in result.workflow_results
        ],
        shared_resources_imported=result.shared_resources_imported,
        warnings=result.warnings,
    )
