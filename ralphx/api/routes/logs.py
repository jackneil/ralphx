"""Log viewing routes for RalphX.

Provides:
- DB-based log querying with filters
- File-based log tailing (MCP-style)
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ralphx.core.database import Database
from ralphx.core.logger import get_log_file_path

# Maximum allowed regex pattern length to prevent ReDoS attacks
MAX_PATTERN_LENGTH = 200

# Patterns that indicate potential ReDoS (nested quantifiers, etc.)
# These are simplified checks - not exhaustive but catch common cases
DANGEROUS_REGEX_PATTERNS = [
    r'\([^)]*\+[^)]*\)\+',    # (x+)+  - nested + quantifiers
    r'\([^)]*\*[^)]*\)\+',    # (x*)+  - * inside, + outside
    r'\([^)]*\+[^)]*\)\*',    # (x+)*  - + inside, * outside
    r'\([^)]*\*[^)]*\)\*',    # (x*)*  - nested * quantifiers
    r'\([^)]+\|[^)]+\)\+',    # (a|b)+ where a and b might overlap
    r'\([^)]+\|[^)]+\)\*',    # (a|b)* where a and b might overlap
]


def _validate_regex_pattern(pattern: str) -> None:
    """Validate regex pattern to prevent ReDoS attacks.

    Args:
        pattern: The regex pattern to validate.

    Raises:
        HTTPException: If the pattern is potentially dangerous.
    """
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Pattern too long (max {MAX_PATTERN_LENGTH} characters)",
        )

    # Check for obviously dangerous patterns
    for dangerous in DANGEROUS_REGEX_PATTERNS:
        if re.search(dangerous, pattern):
            raise HTTPException(
                status_code=400,
                detail="Pattern contains potentially dangerous nested quantifiers",
            )

    # Try to compile with a timeout-like check (compile is fast, but we verify it's valid)
    try:
        re.compile(pattern)
    except re.error as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid regex pattern: {e}",
        )

router = APIRouter(prefix="/logs", tags=["logs"])


class LogEntry(BaseModel):
    """A single log entry."""

    id: int
    level: str
    category: Optional[str]
    event: Optional[str]
    message: str
    project_id: Optional[str]
    run_id: Optional[str]
    metadata: Optional[dict]
    timestamp: str


class LogsResponse(BaseModel):
    """Response containing log entries."""

    logs: list[LogEntry]
    total: int
    limit: int
    offset: int


class LogStats(BaseModel):
    """Log statistics."""

    total: int
    by_level: dict[str, int]
    by_category: dict[str, int]
    recent_errors_24h: int


@router.get("", response_model=LogsResponse)
async def get_logs(
    level: Optional[str] = Query(None, description="Filter by level (DEBUG, INFO, WARNING, ERROR)"),
    category: Optional[str] = Query(None, description="Filter by category (auth, loop, run, iteration, system)"),
    event: Optional[str] = Query(None, description="Filter by event type"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    run_id: Optional[str] = Query(None, description="Filter by run ID"),
    since: Optional[datetime] = Query(None, description="Only logs after this timestamp"),
    until: Optional[datetime] = Query(None, description="Only logs before this timestamp"),
    limit: int = Query(100, ge=1, le=1000, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Rows to skip for pagination"),
) -> LogsResponse:
    """Get logs with optional filters.

    Returns logs in reverse chronological order (newest first).
    """
    db = Database()
    logs = db.get_logs(
        level=level,
        category=category,
        event=event,
        project_id=project_id,
        run_id=run_id,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )

    # Get filtered count for pagination (matching the same filters)
    total = db.count_logs(
        level=level,
        category=category,
        event=event,
        project_id=project_id,
        run_id=run_id,
        since=since,
        until=until,
    )

    return LogsResponse(
        logs=[LogEntry(**log) for log in logs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", response_model=LogStats)
async def get_log_stats() -> LogStats:
    """Get log statistics.

    Returns counts by level, category, and recent errors.
    """
    db = Database()
    stats = db.get_log_stats()
    return LogStats(**stats)


@router.delete("")
async def cleanup_logs(
    days: int = Query(30, ge=1, le=365, description="Delete logs older than this many days"),
) -> dict:
    """Delete old logs.

    Args:
        days: Delete logs older than this many days (default 30)

    Returns:
        Count of deleted log entries
    """
    db = Database()
    deleted = db.cleanup_old_logs(days=days)
    return {"deleted": deleted, "days": days}


# ==============================================================================
# File-based Log Tailing (MCP-style)
# ==============================================================================


class TailLogEntry(BaseModel):
    """A single log entry from the file."""

    timestamp: str
    level: str
    category: Optional[str] = None
    event: Optional[str] = None
    message: str
    project_id: Optional[str] = None
    run_id: Optional[str] = None
    metadata: Optional[dict] = None


class TailResponse(BaseModel):
    """Response from the tail endpoint."""

    entries: list[TailLogEntry]
    file_size: int
    offset: int  # Byte offset for "follow" style polling
    has_more: bool


class LogFileInfo(BaseModel):
    """Information about the log file."""

    path: str
    size: int
    modified: str
    exists: bool


def _tail_file(
    path: Path,
    lines: int = 100,
    offset: int = 0,
    pattern: Optional[str] = None,
    level: Optional[str] = None,
    category: Optional[str] = None,
) -> tuple[list[dict], int, bool]:
    """Read the last N lines from a file, with optional filtering.

    Args:
        path: Path to the log file.
        lines: Number of lines to return.
        offset: Byte offset to start from (0 = read from end, >0 = follow mode).
        pattern: Optional regex pattern to filter messages.
        level: Optional level filter (INFO, WARNING, ERROR).
        category: Optional category filter.

    Returns:
        Tuple of (entries, new_offset, has_more).
        Entries are returned in reverse chronological order (newest first).
    """
    if not path.exists():
        return [], 0, False

    file_size = path.stat().st_size
    if file_size == 0:
        return [], 0, False

    # Compile pattern if provided (validation already done in endpoint)
    regex = re.compile(pattern, re.IGNORECASE) if pattern else None

    def parse_and_filter(line: str) -> Optional[dict]:
        """Parse a line and return entry if it passes filters."""
        if not line.strip():
            return None
        try:
            entry = json.loads(line)
            # Apply filters
            if level and entry.get("level") != level:
                return None
            if category and entry.get("category") != category:
                return None
            if regex and not regex.search(entry.get("message", "")):
                return None
            return entry
        except json.JSONDecodeError:
            return None

    entries = []
    has_more = False

    if offset <= 0:
        # Read last N lines (tail mode)
        # Read file backwards efficiently
        with open(path, "rb") as f:
            f.seek(0, 2)
            end_pos = f.tell()

            # Read in chunks from the end
            chunk_size = 8192
            remaining = b""
            pos = end_pos
            all_lines = []

            while pos > 0 and len(all_lines) < lines * 3:  # Read extra for filtering
                read_size = min(chunk_size, pos)
                pos -= read_size
                f.seek(pos)
                chunk = f.read(read_size)

                # Prepend to remaining and split
                data = chunk + remaining
                parts = data.split(b"\n")

                # First part might be incomplete (split mid-line)
                remaining = parts[0]

                # Add complete lines (in reverse order, newest first)
                for line_bytes in reversed(parts[1:]):
                    if line_bytes:
                        all_lines.append(line_bytes.decode("utf-8", errors="replace"))

            # Handle any remaining data at start of file
            if remaining:
                all_lines.append(remaining.decode("utf-8", errors="replace"))

            # all_lines is now newest-first, process and filter
            for line in all_lines:
                entry = parse_and_filter(line)
                if entry:
                    entries.append(entry)
                    if len(entries) >= lines:
                        has_more = len(all_lines) > len(entries)
                        break

        return entries, end_pos, has_more

    else:
        # Follow mode - read forward from offset
        with open(path, "r", encoding="utf-8") as f:
            f.seek(offset)
            for line in f:
                entry = parse_and_filter(line)
                if entry:
                    entries.append(entry)
                    if len(entries) >= lines:
                        has_more = True
                        break
            new_offset = f.tell()

        # In follow mode, entries are oldest-first (chronological for streaming)
        return entries, new_offset, has_more


@router.get("/tail", response_model=TailResponse)
async def tail_logs(
    lines: int = Query(100, ge=1, le=1000, description="Number of lines to return"),
    offset: int = Query(0, ge=0, description="Byte offset for follow mode (0 = read from end)"),
    pattern: Optional[str] = Query(None, description="Regex pattern to filter messages"),
    level: Optional[str] = Query(None, description="Filter by level (INFO, WARNING, ERROR)"),
    category: Optional[str] = Query(None, description="Filter by category"),
) -> TailResponse:
    """Tail the log file (MCP-style).

    This endpoint reads from the rotating log file and supports:
    - Reading the last N lines (offset=0)
    - Following new entries (offset=previous_offset)
    - Filtering by pattern, level, or category

    For "follow" mode, save the returned offset and pass it in the next request.

    Example usage:
    ```
    # Get last 50 lines
    GET /api/logs/tail?lines=50

    # Get last 50 ERROR lines
    GET /api/logs/tail?lines=50&level=ERROR

    # Follow mode: get new entries since last call
    GET /api/logs/tail?offset=12345&lines=100

    # Search for pattern
    GET /api/logs/tail?pattern=foreign.*key&lines=100
    ```
    """
    # Validate pattern to prevent ReDoS attacks
    if pattern:
        _validate_regex_pattern(pattern)

    log_path = get_log_file_path()
    file_size = log_path.stat().st_size if log_path.exists() else 0

    entries, new_offset, has_more = _tail_file(
        log_path,
        lines=lines,
        offset=offset,
        pattern=pattern,
        level=level,
        category=category,
    )

    return TailResponse(
        entries=[TailLogEntry(**e) for e in entries],
        file_size=file_size,
        offset=new_offset,
        has_more=has_more,
    )


@router.get("/file", response_model=LogFileInfo)
async def get_log_file_info() -> LogFileInfo:
    """Get information about the log file.

    Returns file name (not full path), size, and modification time.
    Useful for checking if there are new logs to tail.
    """
    log_path = get_log_file_path()

    if log_path.exists():
        stat = log_path.stat()
        return LogFileInfo(
            path=log_path.name,  # Only expose filename, not full path
            size=stat.st_size,
            modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
            exists=True,
        )
    else:
        return LogFileInfo(
            path=log_path.name,  # Only expose filename, not full path
            size=0,
            modified="",
            exists=False,
        )
