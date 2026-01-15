"""Filesystem browsing routes for directory selection."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/browse")
async def browse_directory(path: Optional[str] = Query(None)):
    """Browse a directory and list its subdirectories.

    Security: Limits browsing to user's home directory and below.
    """
    home = Path.home()

    # Default to home directory
    if not path:
        target = home
    else:
        target = Path(path).resolve()

    # Security: Ensure path is under home directory
    try:
        target.relative_to(home)
    except ValueError:
        # Path is outside home directory, redirect to home
        target = home

    # Ensure path exists and is a directory
    if not target.exists() or not target.is_dir():
        target = home

    # List subdirectories only (no files for cleaner UI)
    directories = []
    try:
        for item in sorted(target.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                directories.append(item.name)
    except PermissionError:
        # Can't read directory, return empty list
        pass

    # Check if we can go up (but still within home)
    can_go_up = target != home

    return {
        "path": str(target),
        "directories": directories,
        "canGoUp": can_go_up,
        "parent": str(target.parent) if can_go_up else None,
    }
