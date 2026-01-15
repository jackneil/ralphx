"""Project file browsing API routes.

Allows browsing and reading files within a project folder for resource import.
"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from ralphx.core.project import ProjectManager

router = APIRouter()

# Allowed file extensions for browsing/reading
ALLOWED_EXTENSIONS = {
    # Documentation
    ".md", ".txt", ".rst", ".markdown",
    # Config
    ".yaml", ".yml", ".json", ".jsonl", ".toml", ".ini", ".cfg",
    # Source (for viewing context)
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp",
    ".rb", ".php", ".swift", ".kt", ".scala", ".sh", ".bash", ".zsh",
    # Web
    ".html", ".css", ".scss", ".less", ".vue", ".svelte",
    # Data
    ".csv", ".xml",
}

# Max file size for reading (10MB - allows larger JSONL files)
MAX_FILE_SIZE = 10 * 1024 * 1024


class ProjectFile(BaseModel):
    """A file in the project directory."""

    name: str
    size: int
    extension: str


class BrowseResponse(BaseModel):
    """Response for browsing project files."""

    path: str = Field(..., description="Current absolute path")
    relative_path: str = Field(..., description="Path relative to project root")
    directories: list[str] = Field(default_factory=list, description="Subdirectory names")
    files: list[ProjectFile] = Field(default_factory=list, description="Files in directory")
    canGoUp: bool = Field(..., description="Whether we can navigate to parent")
    parent: Optional[str] = Field(None, description="Parent relative path (if canGoUp)")
    hidden_count: int = Field(0, description="Number of hidden items filtered out")
    other_files_count: int = Field(0, description="Number of files with unsupported extensions")


class FileContentResponse(BaseModel):
    """Response for reading a file."""

    path: str = Field(..., description="Relative path to file")
    filename: str = Field(..., description="File name")
    content: str = Field(..., description="File content")
    size: int = Field(..., description="File size in bytes")


def get_manager() -> ProjectManager:
    """Get project manager instance."""
    return ProjectManager()


def get_project_path(slug: str) -> Path:
    """Get project path from slug or raise 404."""
    manager = get_manager()
    project = manager.get_project(slug)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )
    # Ensure absolute resolved path
    return Path(project.path).resolve()


def resolve_safe_path(project_path: Path, relative_path: Optional[str]) -> Path:
    """Resolve a path safely within the project directory.

    Args:
        project_path: The project root path.
        relative_path: Optional relative path within project.

    Returns:
        Resolved absolute path guaranteed to be within project.

    Raises:
        HTTPException: If path is outside project directory.
    """
    # Ensure project_path is resolved first
    project_path = project_path.resolve()

    if not relative_path:
        return project_path  # Now returns resolved path

    # Resolve the full path
    target = (project_path / relative_path).resolve()

    # Security: Ensure path is under project directory
    try:
        target.relative_to(project_path)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is outside project directory",
        )

    return target


@router.get("/{slug}/files/browse", response_model=BrowseResponse)
async def browse_project_files(
    slug: str,
    path: Optional[str] = Query(None, description="Relative path within project"),
):
    """Browse files and directories within a project folder.

    Security: Restricted to within the project path.

    Returns directories and text files (.md, .txt, .yaml, .yml, .json).
    Hidden files/directories (starting with .) are excluded.
    """
    project_path = get_project_path(slug)
    target = resolve_safe_path(project_path, path)

    # Ensure path exists and is a directory
    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Directory not found: {path}",
        )

    if not target.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path is not a directory: {path}",
        )

    # List directories and files
    directories = []
    files = []
    hidden_count = 0
    other_files_count = 0

    try:
        for item in sorted(target.iterdir()):
            # Skip hidden files/directories (but count them)
            if item.name.startswith("."):
                hidden_count += 1
                continue

            if item.is_dir():
                directories.append(item.name)
            elif item.is_file():
                # Only include allowed file types
                suffix = item.suffix.lower()
                if suffix in ALLOWED_EXTENSIONS:
                    files.append(
                        ProjectFile(
                            name=item.name,
                            size=item.stat().st_size,
                            extension=suffix,
                        )
                    )
                else:
                    other_files_count += 1
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied reading directory",
        )

    # Calculate relative path from project root
    try:
        rel_path = str(target.relative_to(project_path))
        if rel_path == ".":
            rel_path = ""
    except ValueError:
        rel_path = ""

    # Check if we can go up (but still within project)
    can_go_up = target != project_path

    # Calculate parent relative path
    parent_rel = None
    if can_go_up:
        parent = target.parent
        try:
            parent_rel = str(parent.relative_to(project_path))
            if parent_rel == ".":
                parent_rel = ""
        except ValueError:
            parent_rel = None

    return BrowseResponse(
        path=str(target),
        relative_path=rel_path,
        directories=directories,
        files=files,
        canGoUp=can_go_up,
        parent=parent_rel,
        hidden_count=hidden_count,
        other_files_count=other_files_count,
    )


@router.get("/{slug}/files/read", response_model=FileContentResponse)
async def read_project_file(
    slug: str,
    path: str = Query(..., description="Relative path to file within project"),
):
    """Read file content from within a project folder.

    Security: Restricted to within the project path.
    Max file size: 1MB.
    Only text files (.md, .txt, .yaml, .yml, .json) can be read.
    """
    project_path = get_project_path(slug)
    target = resolve_safe_path(project_path, path)

    # Ensure path exists and is a file
    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {path}",
        )

    if not target.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path is not a file: {path}",
        )

    # Check file extension
    suffix = target.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed: {suffix}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Check file size
    file_size = target.stat().st_size
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large: {file_size} bytes. Max: {MAX_FILE_SIZE} bytes (1MB)",
        )

    # Read file content
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not valid UTF-8 text",
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied reading file",
        )

    return FileContentResponse(
        path=path,
        filename=target.name,
        content=content,
        size=file_size,
    )
