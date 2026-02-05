"""Resource management API routes."""

import os
import shutil
from datetime import datetime
from pathlib import Path
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

    # Auto-sync from filesystem to ensure files on disk are reflected
    resource_manager.sync_from_filesystem()

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
    try:
        resource = resource_manager.create_resource(
            name=data.name,
            resource_type=rt,
            content=data.content,
            injection_position=ip,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
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


# =============================================================================
# Design Doc File Operations (for interactive design_doc steps)
# These work directly with files, not database resources
# =============================================================================


class DesignDocFileInfo(BaseModel):
    """Info about a design doc file."""

    path: str  # Relative path like "design_doc/RCM_DESIGN.md"
    name: str  # Just the filename
    size: int  # Bytes
    modified: str  # ISO timestamp


class DesignDocFileContent(BaseModel):
    """Design doc file with content."""

    path: str
    name: str
    size: int
    modified: str
    content: str


class DesignDocBackup(BaseModel):
    """Info about a backup file."""

    path: str
    name: str
    size: int
    created: str  # ISO timestamp


class SaveDesignDocRequest(BaseModel):
    """Request to save design doc content."""

    content: str


class SaveDesignDocResponse(BaseModel):
    """Response after saving design doc."""

    path: str
    backup_path: Optional[str] = None
    size: int


def get_project_path(slug: str) -> Path:
    """Get project path or raise 404."""
    manager = get_manager()
    project = manager.get_project(slug)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )
    return Path(project.path)


def _validate_safe_filename(name: str, label: str = "file name") -> None:
    """Validate that a filename is safe (no path traversal, null bytes, etc.).

    Args:
        name: The filename to validate.
        label: Human-readable label for error messages.

    Raises:
        HTTPException: If the filename is unsafe.
    """
    if not name or ".." in name or "/" in name or "\\" in name or "\0" in name or name.startswith("."):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {label}",
        )


def _validate_path_containment(file_path: Path, allowed_root: Path) -> None:
    """Verify that a resolved path stays within the allowed root directory.

    Args:
        file_path: The path to validate.
        allowed_root: The directory the path must stay within.

    Raises:
        HTTPException: If the path escapes the allowed root.
    """
    resolved = file_path.resolve()
    root_resolved = allowed_root.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path",
        )


def get_design_doc_folder(project_path: Path) -> Path:
    """Get the design_doc resources folder."""
    return project_path / ".ralphx" / "resources" / "design_doc"


def get_backups_folder(project_path: Path) -> Path:
    """Get the backups folder, creating if needed."""
    backups = project_path / ".ralphx" / "resources" / "design_doc" / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    return backups


@router.get("/{slug}/design-doc-files", response_model=list[DesignDocFileInfo])
async def list_design_doc_files(slug: str):
    """List all .md files in the design_doc resources folder."""
    project_path = get_project_path(slug)
    design_doc_folder = get_design_doc_folder(project_path)

    if not design_doc_folder.exists():
        return []

    files = []
    for file_path in design_doc_folder.glob("*.md"):
        if file_path.is_file():
            stat = file_path.stat()
            files.append(
                DesignDocFileInfo(
                    path=f"design_doc/{file_path.name}",
                    name=file_path.name,
                    size=stat.st_size,
                    modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                )
            )

    # Sort by modified time, newest first
    files.sort(key=lambda f: f.modified, reverse=True)
    return files


@router.get("/{slug}/design-doc-files/{file_name}", response_model=DesignDocFileContent)
async def get_design_doc_file(slug: str, file_name: str):
    """Read a design doc file's content."""
    project_path = get_project_path(slug)
    design_doc_folder = get_design_doc_folder(project_path)

    # Security: prevent path traversal and null bytes
    _validate_safe_filename(file_name, "file name")

    file_path = design_doc_folder / file_name
    _validate_path_containment(file_path, design_doc_folder)

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {file_name}",
        )

    stat = file_path.stat()
    content = file_path.read_text(encoding="utf-8")

    return DesignDocFileContent(
        path=f"design_doc/{file_name}",
        name=file_name,
        size=stat.st_size,
        modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
        content=content,
    )


@router.post("/{slug}/design-doc-files/{file_name}/save", response_model=SaveDesignDocResponse)
async def save_design_doc_file(slug: str, file_name: str, data: SaveDesignDocRequest):
    """Save design doc file with automatic backup.

    If the file exists, creates a timestamped backup in the backups/ folder
    before overwriting.
    """
    project_path = get_project_path(slug)
    design_doc_folder = get_design_doc_folder(project_path)

    # Security: prevent path traversal and null bytes
    _validate_safe_filename(file_name, "file name")

    # Ensure folder exists
    design_doc_folder.mkdir(parents=True, exist_ok=True)

    file_path = design_doc_folder / file_name
    _validate_path_containment(file_path, design_doc_folder)
    backup_path_str = None

    # Create backup if file exists
    if file_path.exists():
        backups_folder = get_backups_folder(project_path)
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        backup_name = f"{file_path.stem}.{timestamp}{file_path.suffix}"
        backup_path = backups_folder / backup_name

        shutil.copy2(file_path, backup_path)
        backup_path_str = f"design_doc/backups/{backup_name}"

        # Keep only last 10 backups for this file
        _cleanup_old_backups(backups_folder, file_path.stem, max_backups=10)

    # Write new content
    file_path.write_text(data.content, encoding="utf-8")

    return SaveDesignDocResponse(
        path=f"design_doc/{file_name}",
        backup_path=backup_path_str,
        size=len(data.content.encode("utf-8")),
    )


@router.post("/{slug}/design-doc-files/create", response_model=DesignDocFileInfo)
async def create_design_doc_file(slug: str, name: str = Query(..., description="File name without .md extension")):
    """Create a new empty design doc file."""
    project_path = get_project_path(slug)
    design_doc_folder = get_design_doc_folder(project_path)

    # Sanitize name
    safe_name = "".join(c for c in name if c.isalnum() or c in "-_").strip()
    if not safe_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file name",
        )

    file_name = f"{safe_name}.md"
    file_path = design_doc_folder / file_name

    if file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"File already exists: {file_name}",
        )

    # Create folder and file
    design_doc_folder.mkdir(parents=True, exist_ok=True)
    file_path.write_text(f"# {name}\n\n", encoding="utf-8")

    stat = file_path.stat()
    return DesignDocFileInfo(
        path=f"design_doc/{file_name}",
        name=file_name,
        size=stat.st_size,
        modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
    )


@router.get("/{slug}/design-doc-files/{file_name}/backups", response_model=list[DesignDocBackup])
async def list_design_doc_backups(slug: str, file_name: str):
    """List backups for a design doc file."""
    # Security: prevent path traversal and null bytes
    _validate_safe_filename(file_name, "file name")

    project_path = get_project_path(slug)
    backups_folder = get_backups_folder(project_path)

    # Get the stem (filename without extension)
    # Sanitize stem to prevent glob injection (only allow alphanumeric, hyphens, underscores)
    stem = Path(file_name).stem
    safe_stem = "".join(c for c in stem if c.isalnum() or c in "-_")
    if not safe_stem:
        return []

    backups = []
    for backup_path in backups_folder.glob(f"{safe_stem}.*.md"):
        if backup_path.is_file():
            stat = backup_path.stat()
            backups.append(
                DesignDocBackup(
                    path=f"design_doc/backups/{backup_path.name}",
                    name=backup_path.name,
                    size=stat.st_size,
                    created=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                )
            )

    # Sort by created time, newest first
    backups.sort(key=lambda b: b.created, reverse=True)
    return backups


@router.get("/{slug}/design-doc-files/backups/{backup_name}", response_model=DesignDocFileContent)
async def get_design_doc_backup(slug: str, backup_name: str):
    """Read a backup file's content."""
    project_path = get_project_path(slug)
    backups_folder = get_backups_folder(project_path)

    # Security: prevent path traversal and null bytes
    _validate_safe_filename(backup_name, "backup name")

    backup_path = backups_folder / backup_name
    _validate_path_containment(backup_path, backups_folder)

    if not backup_path.exists() or not backup_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup not found: {backup_name}",
        )

    stat = backup_path.stat()
    content = backup_path.read_text(encoding="utf-8")

    return DesignDocFileContent(
        path=f"design_doc/backups/{backup_name}",
        name=backup_name,
        size=stat.st_size,
        modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
        content=content,
    )


def _cleanup_old_backups(backups_folder: Path, stem: str, max_backups: int = 10):
    """Remove old backups, keeping only the most recent max_backups."""
    backups = list(backups_folder.glob(f"{stem}.*.md"))
    if len(backups) <= max_backups:
        return

    # Sort by modification time, oldest first
    backups.sort(key=lambda p: p.stat().st_mtime)

    # Remove oldest backups
    for backup in backups[: len(backups) - max_backups]:
        backup.unlink()


# =============================================================================
# Design Doc Diff and Restore Operations
# =============================================================================


class DiffLine(BaseModel):
    """A single line in a diff."""

    line: str
    type: str  # 'add', 'remove', 'context'


class DiffResult(BaseModel):
    """Result of comparing two versions."""

    left_path: str
    right_path: str
    left_size: int
    right_size: int
    chars_added: int
    chars_removed: int
    diff_html: str  # Unified diff with syntax highlighting
    diff_lines: list[DiffLine]  # Structured diff for custom rendering


class RestoreBackupRequest(BaseModel):
    """Request to restore a backup."""

    backup_name: str


class RestoreBackupResponse(BaseModel):
    """Response after restoring a backup."""

    success: bool
    backup_created: Optional[str] = None  # New backup of current state


@router.get("/{slug}/design-doc-files/{file_name}/diff", response_model=DiffResult)
async def diff_design_doc_versions(
    slug: str,
    file_name: str,
    left: str = Query(..., description="Left version: 'current' or backup filename"),
    right: str = Query(..., description="Right version: 'current' or backup filename"),
):
    """Compare two versions of a design document.

    Returns a unified diff with change statistics.
    """
    import difflib

    project_path = get_project_path(slug)
    design_doc_folder = get_design_doc_folder(project_path)
    backups_folder = get_backups_folder(project_path)

    # Security: prevent path traversal and null bytes
    _validate_safe_filename(file_name, "file name")
    if left != "current":
        _validate_safe_filename(left, "left version")
    if right != "current":
        _validate_safe_filename(right, "right version")

    # Resolve left version
    if left == "current":
        left_path = design_doc_folder / file_name
        left_label = "current"
    else:
        left_path = backups_folder / left
        _validate_path_containment(left_path, backups_folder)
        left_label = left

    # Resolve right version
    if right == "current":
        right_path = design_doc_folder / file_name
        right_label = "current"
    else:
        right_path = backups_folder / right
        _validate_path_containment(right_path, backups_folder)
        right_label = right

    if not left_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Left version not found: {left}",
        )
    if not right_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Right version not found: {right}",
        )

    left_content = left_path.read_text(encoding="utf-8")
    right_content = right_path.read_text(encoding="utf-8")

    # Generate unified diff
    diff = list(
        difflib.unified_diff(
            left_content.splitlines(keepends=True),
            right_content.splitlines(keepends=True),
            fromfile=left_label,
            tofile=right_label,
        )
    )

    # Calculate stats
    chars_added = sum(
        len(line) - 1
        for line in diff
        if line.startswith("+") and not line.startswith("+++")
    )
    chars_removed = sum(
        len(line) - 1
        for line in diff
        if line.startswith("-") and not line.startswith("---")
    )

    # Build structured diff lines
    diff_lines = []
    for line in diff:
        if line.startswith("+") and not line.startswith("+++"):
            diff_lines.append(DiffLine(line=line.rstrip("\n"), type="add"))
        elif line.startswith("-") and not line.startswith("---"):
            diff_lines.append(DiffLine(line=line.rstrip("\n"), type="remove"))
        elif line.startswith("@@"):
            diff_lines.append(DiffLine(line=line.rstrip("\n"), type="hunk"))
        elif not line.startswith("+++") and not line.startswith("---"):
            diff_lines.append(DiffLine(line=line.rstrip("\n"), type="context"))

    return DiffResult(
        left_path=left_label,
        right_path=right_label,
        left_size=len(left_content),
        right_size=len(right_content),
        chars_added=chars_added,
        chars_removed=chars_removed,
        diff_html="".join(diff),
        diff_lines=diff_lines,
    )


@router.post(
    "/{slug}/design-doc-files/{file_name}/restore",
    response_model=RestoreBackupResponse,
)
async def restore_design_doc_backup(
    slug: str,
    file_name: str,
    request: RestoreBackupRequest,
):
    """Restore a design doc from a backup.

    Creates a backup of current state before restoring.
    """
    project_path = get_project_path(slug)
    design_doc_folder = get_design_doc_folder(project_path)
    backups_folder = get_backups_folder(project_path)

    # Security: prevent path traversal and null bytes
    _validate_safe_filename(file_name, "file name")
    _validate_safe_filename(request.backup_name, "backup name")

    backup_path = backups_folder / request.backup_name
    current_path = design_doc_folder / file_name
    _validate_path_containment(backup_path, backups_folder)
    _validate_path_containment(current_path, design_doc_folder)

    if not backup_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup not found: {request.backup_name}",
        )

    # Backup current if it exists
    new_backup = None
    if current_path.exists():
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        new_backup = f"{Path(file_name).stem}.{timestamp}.md"
        backups_folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current_path, backups_folder / new_backup)

    # Restore from backup
    design_doc_folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_path, current_path)

    return RestoreBackupResponse(success=True, backup_created=new_backup)
