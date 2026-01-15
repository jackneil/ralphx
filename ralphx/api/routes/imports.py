"""Import API routes for RalphX.

Handles importing content into loops via API.
"""

import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field, field_validator

from ralphx.core.import_manager import ImportManager
from ralphx.core.input_templates import (
    get_input_tags,
    get_input_template,
    get_required_tags,
    list_input_templates,
    validate_loop_inputs,
)
from ralphx.core.project import ProjectManager

router = APIRouter()

# Maximum file sizes for uploads (bytes)
MAX_MARKDOWN_SIZE = 10 * 1024 * 1024  # 10 MB for markdown files
MAX_JSONL_SIZE = 50 * 1024 * 1024  # 50 MB for JSONL (many items)
MAX_PASTE_SIZE = 1 * 1024 * 1024  # 1 MB for pasted content


# Request/Response models
class ImportPasteRequest(BaseModel):
    """Request to import pasted content."""

    content: str = Field(..., description="Content to import", max_length=MAX_PASTE_SIZE)
    filename: str = Field(..., description="Filename for the content", max_length=255)
    tag: Optional[str] = Field(None, description="Input tag (master_design, story_instructions, etc.)")

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Validate filename doesn't contain path traversal."""
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("Filename cannot contain path separators or '..'")
        return v


class ImportResult(BaseModel):
    """Result of an import operation."""

    success: bool
    files_imported: int = 0
    items_created: int = 0
    errors: list[str] = []
    paths: list[str] = []


class InputFileInfo(BaseModel):
    """Information about an input file."""

    name: str
    path: str
    size: int
    modified: str
    tag: Optional[str] = None


# Validate loop name
LOOP_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def get_project_and_manager(slug: str):
    """Get project and import manager."""
    pm = ProjectManager()
    project = pm.get_project(slug)

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )

    project_db = pm.get_project_db(project.path)
    import_manager = ImportManager(project.path, project_db)

    return project, import_manager


def validate_loop_name(loop_name: str):
    """Validate loop name to prevent path traversal."""
    if not LOOP_NAME_PATTERN.match(loop_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid loop name. Use only letters, numbers, underscores, and hyphens.",
        )


def validate_filename(filename: str):
    """Validate filename to prevent path traversal (defense in depth)."""
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename: path separators not allowed",
        )
    if len(filename) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename too long (max 255 characters)",
        )


@router.get("/{slug}/loops/{loop_name}/inputs", response_model=list[InputFileInfo])
async def list_loop_inputs(slug: str, loop_name: str):
    """List all input files for a loop."""
    validate_loop_name(loop_name)
    project, import_manager = get_project_and_manager(slug)

    files = import_manager.list_inputs(loop_name)
    return [InputFileInfo(**f) for f in files]


@router.post("/{slug}/loops/{loop_name}/inputs/paste", response_model=ImportResult)
async def import_paste(slug: str, loop_name: str, request: ImportPasteRequest):
    """Import pasted content as a new file."""
    validate_loop_name(loop_name)
    project, import_manager = get_project_and_manager(slug)

    result = import_manager.import_paste(
        content=request.content,
        loop_name=loop_name,
        filename=request.filename,
        tag=request.tag,
    )

    return ImportResult(
        success=result.success,
        files_imported=result.files_imported,
        items_created=result.items_created,
        errors=result.errors,
        paths=[str(p) for p in result.paths],
    )


@router.post("/{slug}/loops/{loop_name}/inputs/upload", response_model=ImportResult)
async def upload_file(slug: str, loop_name: str, file: UploadFile = File(...)):
    """Upload a file to the loop's inputs directory."""
    validate_loop_name(loop_name)
    project, import_manager = get_project_and_manager(slug)

    # Read file content with size limit
    content = await file.read()

    if len(content) > MAX_MARKDOWN_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_MARKDOWN_SIZE // (1024*1024)} MB",
        )

    try:
        content_str = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be UTF-8 encoded text",
        )

    # Validate and sanitize filename from upload
    filename = file.filename or "uploaded-file.md"
    # Prevent path traversal in uploaded filename
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename: path separators not allowed",
        )

    result = import_manager.import_paste(
        content=content_str,
        loop_name=loop_name,
        filename=filename,
    )

    return ImportResult(
        success=result.success,
        files_imported=result.files_imported,
        items_created=result.items_created,
        errors=result.errors,
        paths=[str(p) for p in result.paths],
    )


@router.post("/{slug}/loops/{loop_name}/inputs/jsonl", response_model=ImportResult)
async def import_jsonl(slug: str, loop_name: str, file: UploadFile = File(...)):
    """Import a JSONL file as work items.

    Each line should be a JSON object with:
    - id: Item identifier (optional, auto-generated if missing)
    - content: Item content (required)
    - priority: Priority 1-5 (optional)
    - category: Category string (optional)
    - tags: List of tags (optional)
    - metadata: Additional metadata dict (optional)
    """
    validate_loop_name(loop_name)

    pm = ProjectManager()
    project = pm.get_project(slug)

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )

    project_db = pm.get_project_db(project.path)
    import_manager = ImportManager(project.path, project_db)

    # Save uploaded file to temp location
    import tempfile

    content = await file.read()

    # Check file size limit
    if len(content) > MAX_JSONL_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_JSONL_SIZE // (1024*1024)} MB",
        )

    try:
        content_str = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be UTF-8 encoded",
        )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False
    ) as tmp:
        tmp.write(content_str)
        tmp_path = Path(tmp.name)

    try:
        result = import_manager.import_jsonl(
            source_path=tmp_path,
            loop_name=loop_name,
            project_id=project.id,
        )

        return ImportResult(
            success=result.success,
            files_imported=result.files_imported,
            items_created=result.items_created,
            errors=result.errors,
            paths=[str(p) for p in result.paths],
        )
    finally:
        # Clean up temp file
        tmp_path.unlink(missing_ok=True)


@router.get("/{slug}/loops/{loop_name}/inputs/{filename}")
async def get_input_content(slug: str, loop_name: str, filename: str):
    """Get the content of an input file."""
    validate_loop_name(loop_name)
    validate_filename(filename)
    project, import_manager = get_project_and_manager(slug)

    content = import_manager.get_input_content(loop_name, filename)

    if content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Input file not found: {filename}",
        )

    return {"filename": filename, "content": content}


@router.delete("/{slug}/loops/{loop_name}/inputs/{filename}")
async def delete_input(slug: str, loop_name: str, filename: str):
    """Delete an input file."""
    validate_loop_name(loop_name)
    validate_filename(filename)
    project, import_manager = get_project_and_manager(slug)

    success = import_manager.delete_input(loop_name, filename)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Input file not found: {filename}",
        )

    return {"message": f"Deleted {filename}"}


# ============================================================================
# Input Templates API
# ============================================================================


class InputTemplateInfo(BaseModel):
    """Information about an input template."""

    id: str
    name: str
    description: str
    loop_type: str
    tag: str
    filename: str


class InputTemplateDetail(InputTemplateInfo):
    """Full input template including content."""

    content: str


class ApplyTemplateRequest(BaseModel):
    """Request to apply a template to a loop."""

    template_id: str = Field(..., description="Template ID to apply")
    custom_filename: Optional[str] = Field(None, description="Optional custom filename")


class UpdateInputTagRequest(BaseModel):
    """Request to update an input file's tag."""

    tag: Optional[str] = Field(None, description="New tag for the input file")


class ValidationResult(BaseModel):
    """Result of input validation."""

    valid: bool
    missing_tags: list[str]
    warnings: list[str]


@router.get("/input-templates", response_model=list[InputTemplateInfo])
async def list_templates(loop_type: Optional[str] = None):
    """List available input templates.

    Args:
        loop_type: Optional filter by loop type ('planning' or 'implementation').
    """
    templates = list_input_templates(loop_type)
    return [InputTemplateInfo(**t) for t in templates]


@router.get("/input-templates/{template_id:path}", response_model=InputTemplateDetail)
async def get_template(template_id: str):
    """Get a specific input template with content."""
    template = get_input_template(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template not found: {template_id}",
        )

    return InputTemplateDetail(**template)


@router.get("/input-tags")
async def list_input_tags():
    """Get all available input tags with descriptions."""
    return get_input_tags()


@router.post("/{slug}/loops/{loop_name}/inputs/apply-template", response_model=ImportResult)
async def apply_template(slug: str, loop_name: str, request: ApplyTemplateRequest):
    """Apply an input template to a loop.

    Copies the template content to the loop's inputs directory.
    """
    validate_loop_name(loop_name)
    project, import_manager = get_project_and_manager(slug)

    template = get_input_template(request.template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template not found: {request.template_id}",
        )

    # Determine filename (with versioning if needed)
    base_filename = request.custom_filename or template["filename"]

    # Get existing files to check for duplicates
    existing_files = import_manager.list_inputs(loop_name)
    existing_names = {f["name"] for f in existing_files}

    # Version the filename if it already exists
    filename = base_filename
    counter = 2
    while filename in existing_names:
        # Split name and extension
        if "." in base_filename:
            name_part = base_filename.rsplit(".", 1)[0]
            ext_part = "." + base_filename.rsplit(".", 1)[1]
        else:
            name_part = base_filename
            ext_part = ""
        filename = f"{name_part}-{counter}{ext_part}"
        counter += 1

    # Import the template content with tag
    result = import_manager.import_paste(
        content=template["content"],
        loop_name=loop_name,
        filename=filename,
        tag=template["tag"],
        applied_from_template=request.template_id,
    )

    return ImportResult(
        success=result.success,
        files_imported=result.files_imported,
        items_created=result.items_created,
        errors=result.errors,
        paths=[str(p) for p in result.paths],
    )


@router.get("/{slug}/loops/{loop_name}/inputs/validate", response_model=ValidationResult)
async def validate_inputs(slug: str, loop_name: str, loop_type: str):
    """Validate that a loop has required inputs for its type.

    Args:
        loop_type: Loop type ('planning' or 'implementation').
    """
    validate_loop_name(loop_name)
    project, import_manager = get_project_and_manager(slug)

    inputs = import_manager.list_inputs(loop_name)
    result = validate_loop_inputs(inputs, loop_type)

    return ValidationResult(**result)


@router.patch("/{slug}/loops/{loop_name}/inputs/{filename}")
async def update_input_tag(
    slug: str, loop_name: str, filename: str, request: UpdateInputTagRequest
):
    """Update the tag of an input file."""
    validate_loop_name(loop_name)
    validate_filename(filename)
    project, import_manager = get_project_and_manager(slug)

    # Verify file exists
    content = import_manager.get_input_content(loop_name, filename)
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Input file not found: {filename}",
        )

    # Update the tag
    success = import_manager.update_input_tag(loop_name, filename, request.tag)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update tag",
        )

    return {"filename": filename, "tag": request.tag}
