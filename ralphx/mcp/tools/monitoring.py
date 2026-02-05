"""Monitoring MCP tools.

Tools for monitoring runs, logs, and sessions:
- ralphx_list_runs: List run history
- ralphx_get_run: Get run details with sessions
- ralphx_get_logs: Query logs with filters
- ralphx_get_log_stats: Get log counts by level/category
- ralphx_cleanup_logs: Delete old logs
- ralphx_list_sessions: List Claude sessions
- ralphx_get_session_events: Get session events with scrubbing
"""

from typing import Optional

from ralphx.mcp.base import (
    MCPError,
    PaginatedResult,
    ToolDefinition,
    ToolError,
    make_schema,
    prop_bool,
    prop_enum,
    prop_int,
    prop_string,
    sanitize_event,
    scrub_sensitive_data,
    validate_pagination,
)
from ralphx.mcp.tools.projects import get_manager


def list_runs(
    slug: str,
    workflow_id: Optional[str] = None,
    step_id: Optional[int] = None,
    loop_name: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List run history with filtering and pagination."""
    limit, offset = validate_pagination(limit, offset)
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    try:
        runs = project_db.list_runs(
            workflow_id=workflow_id,
            step_id=step_id,
            loop_name=loop_name,
            status=status,
        )
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to list runs: {e}",
            details={"slug": slug},
        )

    total = len(runs)
    paginated = runs[offset : offset + limit]

    return PaginatedResult(
        items=[
            {
                "id": r["id"],
                "loop_name": r.get("loop_name"),
                "workflow_id": r.get("workflow_id"),
                "step_id": r.get("step_id"),
                "status": r["status"],
                "iterations_completed": r.get("iterations_completed", 0),
                "items_generated": r.get("items_generated", 0),
                "executor_pid": r.get("executor_pid"),
                "started_at": r.get("started_at"),
                "completed_at": r.get("completed_at"),
                "last_activity_at": r.get("last_activity_at"),
            }
            for r in paginated
        ],
        total=total,
        limit=limit,
        offset=offset,
    ).to_dict()


def get_run(
    slug: str,
    run_id: str,
    include_sessions: bool = True,
) -> dict:
    """Get detailed run information including sessions."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)
    run = project_db.get_run(run_id)

    if not run:
        raise ToolError.run_not_found(run_id)

    # Scrub error_message to prevent leaking sensitive data
    error_msg = run.get("error_message")
    if error_msg:
        error_msg = scrub_sensitive_data(error_msg)

    result = {
        "id": run["id"],
        "loop_name": run.get("loop_name"),
        "workflow_id": run.get("workflow_id"),
        "step_id": run.get("step_id"),
        "status": run["status"],
        "iterations_completed": run.get("iterations_completed", 0),
        "items_generated": run.get("items_generated", 0),
        "executor_pid": run.get("executor_pid"),
        "started_at": run.get("started_at"),
        "completed_at": run.get("completed_at"),
        "last_activity_at": run.get("last_activity_at"),
        "error_message": error_msg,
    }

    if include_sessions:
        sessions = project_db.list_sessions(run_id=run_id)
        result["sessions"] = [
            {
                "id": s.get("session_id", s.get("id")),
                "iteration": s.get("iteration"),
                "status": s.get("status"),
                "started_at": s.get("started_at"),
                "duration_seconds": s.get("duration_seconds"),
            }
            for s in sessions
        ]
        result["session_count"] = len(sessions)

    return result


def get_logs(
    slug: str,
    level: Optional[str] = None,
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Query logs with filters. Max 500 results per query."""
    limit, offset = validate_pagination(limit, offset)
    # Cap at 500 for safety
    if limit > 500:
        limit = 500

    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    try:
        logs, total = project_db.get_logs(
            level=level,
            run_id=run_id,
            session_id=session_id,
            search=search,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to get logs: {e}",
            details={"slug": slug},
        )

    return PaginatedResult(
        items=[
            {
                "id": log.get("id"),
                "timestamp": log.get("timestamp"),
                "level": log.get("level"),
                "message": scrub_sensitive_data(log.get("message", "")),
                "run_id": log.get("run_id"),
            }
            for log in logs
        ],
        total=total,
        limit=limit,
        offset=offset,
    ).to_dict()


def get_log_stats(
    slug: str,
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """Get log statistics (counts by level and category)."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    try:
        stats = project_db.get_log_stats(
            run_id=run_id,
            session_id=session_id,
        )
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to get log stats: {e}",
            details={"slug": slug},
        )

    return {
        "by_level": stats.get("by_level", {}),
        "by_category": stats.get("by_category", {}),
        "total": stats.get("total", 0),
    }


def cleanup_logs(
    slug: str,
    days: int = 30,
    dry_run: bool = True,
) -> dict:
    """Delete logs older than specified days.

    Args:
        slug: Project slug
        days: Delete logs older than this many days
        dry_run: If True, only report what would be deleted
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    if days < 1:
        raise ToolError.validation_error("days must be at least 1")

    project_db = manager.get_project_db(project.path)

    try:
        result = project_db.cleanup_logs(days=days, dry_run=dry_run)
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to cleanup logs: {e}",
            details={"slug": slug},
        )

    return {
        "deleted_count": result.get("deleted_count", 0),
        "dry_run": dry_run,
        "days": days,
        "message": f"{'Would delete' if dry_run else 'Deleted'} {result.get('deleted_count', 0)} logs older than {days} days",
    }


def list_sessions(
    slug: str,
    run_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List Claude sessions with filtering and pagination."""
    limit, offset = validate_pagination(limit, offset)
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    try:
        sessions = project_db.list_sessions(
            run_id=run_id,
            status=status,
        )
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to list sessions: {e}",
            details={"slug": slug},
        )

    total = len(sessions)
    paginated = sessions[offset : offset + limit]

    return PaginatedResult(
        items=[
            {
                "id": s.get("session_id", s.get("id")),
                "run_id": s.get("run_id"),
                "iteration": s.get("iteration"),
                "status": s.get("status"),
                "started_at": s.get("started_at"),
                "duration_seconds": s.get("duration_seconds"),
            }
            for s in paginated
        ],
        total=total,
        limit=limit,
        offset=offset,
    ).to_dict()


def get_session_events(
    slug: str,
    session_id: str,
    after_id: Optional[int] = None,
    event_type: Optional[str] = None,
    include_sensitive: bool = False,
    limit: int = 100,
) -> dict:
    """Get session events with sensitive data scrubbing.

    Args:
        slug: Project slug
        session_id: Session ID
        after_id: Only return events after this ID (for polling)
        event_type: Filter by event type
        include_sensitive: If True, don't scrub sensitive data
        limit: Max events to return
    """
    limit = min(limit, 500)  # Cap at 500
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    # Verify session exists
    session = project_db.get_session(session_id)
    if not session:
        raise ToolError.session_not_found(session_id)

    try:
        events = project_db.get_session_events(
            session_id=session_id,
            after_id=after_id,
            event_type=event_type,
            limit=limit,
        )
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to get session events: {e}",
            details={"session_id": session_id},
        )

    # Sanitize events
    sanitized_events = [
        sanitize_event(e, include_sensitive=include_sensitive)
        for e in events
    ]

    # Get last event ID for polling
    last_id = sanitized_events[-1].get("id") if sanitized_events else after_id

    return {
        "session_id": session_id,
        "events": sanitized_events,
        "count": len(sanitized_events),
        "last_id": last_id,
        "has_more": len(events) == limit,
    }


def get_monitoring_tools() -> list[ToolDefinition]:
    """Get all monitoring tool definitions."""
    return [
        ToolDefinition(
            name="ralphx_list_runs",
            description="List run history with filtering and pagination",
            handler=list_runs,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "workflow_id": prop_string("Filter by workflow ID"),
                    "step_id": prop_int("Filter by step ID"),
                    "loop_name": prop_string("Filter by loop name"),
                    "status": prop_enum("Filter by status", ["running", "paused", "completed", "error", "aborted"]),
                    "limit": prop_int("Max runs to return (1-500)", minimum=1, maximum=500),
                    "offset": prop_int("Number of runs to skip", minimum=0),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_get_run",
            description="Get detailed run information including sessions",
            handler=get_run,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "run_id": prop_string("Run ID"),
                    "include_sessions": prop_bool("Include session list (default: true)"),
                },
                required=["slug", "run_id"],
            ),
        ),
        ToolDefinition(
            name="ralphx_get_logs",
            description="Query logs with filters (max 500 results per query)",
            handler=get_logs,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "level": prop_enum("Filter by log level", ["debug", "info", "warning", "error"]),
                    "run_id": prop_string("Filter by run ID"),
                    "session_id": prop_string("Filter by session ID"),
                    "search": prop_string("Search text in messages"),
                    "limit": prop_int("Max logs to return (1-500)", minimum=1, maximum=500),
                    "offset": prop_int("Number of logs to skip", minimum=0),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_get_log_stats",
            description="Get log statistics (counts by level and category)",
            handler=get_log_stats,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "run_id": prop_string("Filter by run ID"),
                    "session_id": prop_string("Filter by session ID"),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_cleanup_logs",
            description="Delete logs older than specified days (use dry_run to preview)",
            handler=cleanup_logs,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "days": prop_int("Delete logs older than this many days", minimum=1),
                    "dry_run": prop_bool("Only report what would be deleted (default: true)"),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_list_sessions",
            description="List Claude sessions with filtering and pagination",
            handler=list_sessions,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "run_id": prop_string("Filter by run ID"),
                    "status": prop_enum("Filter by status", ["active", "completed", "error"]),
                    "limit": prop_int("Max sessions to return (1-500)", minimum=1, maximum=500),
                    "offset": prop_int("Number of sessions to skip", minimum=0),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_get_session_events",
            description="Get session events with automatic sensitive data scrubbing. Use after_id for polling.",
            handler=get_session_events,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "session_id": prop_string("Session ID"),
                    "after_id": prop_int("Only return events after this ID (for polling)"),
                    "event_type": prop_enum("Filter by event type", ["text", "tool_call", "tool_result", "error"]),
                    "include_sensitive": prop_bool("Don't scrub sensitive data (default: false)"),
                    "limit": prop_int("Max events to return (1-500)", minimum=1, maximum=500),
                },
                required=["slug", "session_id"],
            ),
        ),
    ]
