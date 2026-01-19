"""SSE streaming routes for live session tailing."""

import asyncio
import json
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from ralphx.core.project import ProjectManager
from ralphx.core.session import SessionEventType, SessionManager, SessionTailer
from ralphx.models.run import RunStatus

router = APIRouter()


def get_manager() -> ProjectManager:
    """Get project manager instance."""
    return ProjectManager()


def get_project(slug: str):
    """Get project by slug or raise 404.

    Returns:
        Tuple of (manager, project, project_db).
    """
    manager = get_manager()
    project = manager.get_project(slug)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )
    project_db = manager.get_project_db(project.path)
    return manager, project, project_db


async def format_sse(event: str, data: dict) -> str:
    """Format data as SSE event.

    Args:
        event: Event type name.
        data: Event data to JSON encode.

    Returns:
        SSE formatted string.
    """
    json_data = json.dumps(data)
    return f"event: {event}\ndata: {json_data}\n\n"


async def event_generator(
    project_db,
    project_id: str,
    project_path: str,
    loop_name: Optional[str] = None,
    session_id: Optional[str] = None,
    from_beginning: bool = True,
) -> AsyncGenerator[str, None]:
    """Generate SSE events from session or loop.

    Args:
        project_db: ProjectDatabase instance.
        project_id: Project ID (for client info).
        project_path: Path to project directory.
        loop_name: Optional loop name to watch.
        session_id: Optional specific session ID to tail.
        from_beginning: Start from file beginning.

    Yields:
        SSE formatted events.
    """
    session_manager = SessionManager(project_db)

    # Send initial connected event
    yield await format_sse("connected", {
        "project_id": project_id,
        "loop_name": loop_name,
        "session_id": session_id,
    })

    # If watching a specific session
    if session_id:
        async for sse_event in _tail_session(
            session_manager=session_manager,
            session_id=session_id,
            project_path=project_path,
            project_db=project_db,
            from_beginning=from_beginning,
        ):
            yield sse_event
        return

    # If watching a loop, get latest session
    if loop_name:
        # Check for active run
        runs = project_db.list_runs(
            loop_name=loop_name,
            limit=1,
        )

        if runs:
            run = runs[0]
            run_status = run.get("status", "")

            # Send status update
            yield await format_sse("status", {
                "loop_name": loop_name,
                "run_id": run.get("id"),
                "status": run_status,
                "iteration": run.get("current_iteration", 0),
                "mode": run.get("current_mode"),
            })

            # If running, try to tail latest session
            if run_status in [RunStatus.RUNNING.value, RunStatus.PAUSED.value]:
                session = session_manager.get_latest_session(
                    run_id=run.get("id"),
                )

                if session:
                    async for sse_event in _tail_session(
                        session_manager=session_manager,
                        session_id=session.session_id,
                        project_path=project_path,
                        project_db=project_db,
                        from_beginning=from_beginning,
                        run_id=run.get("id"),
                        iteration=session.iteration,
                    ):
                        yield sse_event
                    return
                else:
                    yield await format_sse("info", {"message": "No session found"})
            else:
                yield await format_sse("info", {
                    "message": f"Loop not running (status: {run_status})"
                })
        else:
            yield await format_sse("info", {"message": "No runs found for loop"})

    # Keep connection alive with heartbeats
    try:
        while True:
            await asyncio.sleep(15)
            yield await format_sse("heartbeat", {"timestamp": asyncio.get_event_loop().time()})
    except asyncio.CancelledError:
        yield await format_sse("disconnected", {})


async def _tail_session(
    session_manager: SessionManager,
    session_id: str,
    project_path: str,
    project_db,
    from_beginning: bool = True,
    run_id: Optional[str] = None,
    iteration: Optional[int] = None,
) -> AsyncGenerator[str, None]:
    """Tail a specific session file, storing events to DB for history.

    Args:
        session_manager: Session manager instance.
        session_id: Session UUID.
        project_path: Project directory path.
        project_db: ProjectDatabase for storing events.
        from_beginning: Start from file beginning.
        run_id: Run ID for this session.
        iteration: Iteration number for this session.

    Yields:
        SSE formatted events.
    """
    from pathlib import Path

    session_file = session_manager.find_session_file(
        session_id=session_id,
        project_path=Path(project_path),
    )

    if not session_file:
        yield await format_sse("error", {
            "message": f"Session file not found: {session_id}"
        })
        return

    # Get session info if not provided
    if run_id is None or iteration is None:
        session_info = session_manager.get_session(session_id)
        if session_info:
            run_id = run_id or session_info.run_id
            iteration = iteration if iteration is not None else session_info.iteration

    # Metadata to include in each event
    event_meta = {
        "run_id": run_id,
        "iteration": iteration,
        "session_id": session_id,
    }

    # First, send any historical events from DB
    existing_events = project_db.get_session_events(session_id)
    last_db_event_id = 0

    for db_event in existing_events:
        last_db_event_id = db_event.get("id", 0)
        event_type = db_event.get("event_type", "unknown")

        if event_type == "text":
            yield await format_sse("text", {
                "content": db_event.get("content", ""),
                **event_meta,
            })
        elif event_type == "tool_call":
            yield await format_sse("tool_call", {
                "name": db_event.get("tool_name"),
                "input": db_event.get("tool_input"),
                **event_meta,
            })
        elif event_type == "tool_result":
            yield await format_sse("tool_result", {
                "name": db_event.get("tool_name"),
                "result": db_event.get("tool_result"),
                **event_meta,
            })
        elif event_type == "error":
            yield await format_sse("error", {
                "message": db_event.get("error_message"),
                **event_meta,
            })
        elif event_type == "init":
            yield await format_sse("init", {
                "data": db_event.get("raw_data"),
                **event_meta,
            })
        elif event_type == "complete":
            yield await format_sse("complete", event_meta)
            return  # Session already complete

    yield await format_sse("session_start", {
        "session_id": session_id,
        "file": str(session_file),
        "history_events": len(existing_events),
        "run_id": run_id,
        "iteration": iteration,
    })

    # Now tail the file for new events, starting from where DB left off
    # If we have history, start from end of file to avoid duplicates
    tailer = SessionTailer(
        session_path=session_file,
        from_beginning=from_beginning and len(existing_events) == 0,
    )

    try:
        async for event in tailer.tail():
            # Skip UNKNOWN events (like queue-operation, user messages)
            if event.type == SessionEventType.UNKNOWN:
                continue

            # Store event to DB for history
            if event.type == SessionEventType.TEXT:
                project_db.add_session_event(
                    session_id=session_id,
                    event_type="text",
                    content=event.text,
                )
                yield await format_sse("text", {
                    "content": event.text,
                    **event_meta,
                })

            elif event.type == SessionEventType.TOOL_CALL:
                project_db.add_session_event(
                    session_id=session_id,
                    event_type="tool_call",
                    tool_name=event.tool_name,
                    tool_input=event.tool_input,
                )
                yield await format_sse("tool_call", {
                    "name": event.tool_name,
                    "input": event.tool_input,
                    **event_meta,
                })

            elif event.type == SessionEventType.TOOL_RESULT:
                project_db.add_session_event(
                    session_id=session_id,
                    event_type="tool_result",
                    tool_name=event.tool_name,
                    tool_result=event.tool_result[:1000] if event.tool_result else None,
                )
                yield await format_sse("tool_result", {
                    "name": event.tool_name,
                    "result": event.tool_result[:1000] if event.tool_result else None,
                    **event_meta,
                })

            elif event.type == SessionEventType.ERROR:
                project_db.add_session_event(
                    session_id=session_id,
                    event_type="error",
                    error_message=event.error_message,
                )
                yield await format_sse("error", {
                    "message": event.error_message,
                    **event_meta,
                })

            elif event.type == SessionEventType.COMPLETE:
                project_db.add_session_event(
                    session_id=session_id,
                    event_type="complete",
                )
                yield await format_sse("complete", event_meta)
                break

            elif event.type == SessionEventType.INIT:
                project_db.add_session_event(
                    session_id=session_id,
                    event_type="init",
                    raw_data=event.raw_data,
                )
                yield await format_sse("init", {
                    "data": event.raw_data,
                    **event_meta,
                })

    except asyncio.CancelledError:
        tailer.stop()
        yield await format_sse("disconnected", {})


@router.get("/{slug}/loops/{loop_name}/stream")
async def stream_loop(
    slug: str,
    loop_name: str,
    from_beginning: bool = Query(True, description="Start from beginning of session"),
):
    """Stream SSE events from a loop's current session.

    Provides real-time updates on loop execution including:
    - Status changes
    - Text output from Claude
    - Tool calls and results
    - Progress updates
    """
    manager, project, project_db = get_project(slug)

    return StreamingResponse(
        event_generator(
            project_db=project_db,
            project_id=project.id,
            project_path=project.path,
            loop_name=loop_name,
            from_beginning=from_beginning,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{slug}/loops/{loop_name}/tail")
async def tail_loop(
    slug: str,
    loop_name: str,
):
    """Tail the latest session for a loop (from end of file).

    Similar to `tail -f` - starts from current position
    and streams new events as they appear.
    """
    manager, project, project_db = get_project(slug)

    return StreamingResponse(
        event_generator(
            project_db=project_db,
            project_id=project.id,
            project_path=project.path,
            loop_name=loop_name,
            from_beginning=False,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{slug}/sessions/{session_id}/tail")
async def tail_session(
    slug: str,
    session_id: str,
    from_beginning: bool = Query(True, description="Start from beginning"),
):
    """Tail a specific session by ID.

    Streams events from the session JSONL file as they appear.
    Validates that the session belongs to the specified project.
    """
    manager, project, project_db = get_project(slug)

    # Verify session exists (it's in this project's database so it belongs here)
    session_manager = SessionManager(project_db)
    session = session_manager.get_session(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )

    return StreamingResponse(
        event_generator(
            project_db=project_db,
            project_id=project.id,
            project_path=project.path,
            session_id=session_id,
            from_beginning=from_beginning,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{slug}/sessions")
async def list_sessions(
    slug: str,
    run_id: Optional[str] = Query(None, description="Filter by run ID"),
    limit: int = Query(50, ge=1, le=200, description="Max sessions to return"),
):
    """List sessions for a project.

    Returns session metadata without streaming content.
    """
    manager, project, project_db = get_project(slug)

    session_manager = SessionManager(project_db)
    sessions = session_manager.list_sessions(
        run_id=run_id,
        limit=limit,
    )

    return [
        {
            "session_id": s.session_id,
            "project_id": project.id,
            "run_id": s.run_id,
            "iteration": s.iteration,
            "mode": s.mode,
            "status": s.status,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "duration_seconds": s.duration_seconds,
        }
        for s in sessions
    ]


@router.get("/{slug}/sessions/{session_id}")
async def get_session(
    slug: str,
    session_id: str,
):
    """Get session details by ID."""
    manager, project, project_db = get_project(slug)

    session_manager = SessionManager(project_db)
    session = session_manager.get_session(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )

    return {
        "session_id": session.session_id,
        "project_id": project.id,
        "run_id": session.run_id,
        "iteration": session.iteration,
        "mode": session.mode,
        "status": session.status,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "duration_seconds": session.duration_seconds,
        "items_added": session.items_added,
    }


@router.get("/{slug}/sessions/{session_id}/events")
async def get_session_events(
    slug: str,
    session_id: str,
    after_id: Optional[int] = Query(None, description="Only return events after this ID"),
    limit: int = Query(500, ge=1, le=1000, description="Max events to return"),
):
    """Get events for a session (for history/replay).

    Use `after_id` for polling: pass the last received event ID to get only newer events.
    """
    manager, project, project_db = get_project(slug)

    # Verify session exists
    session_manager = SessionManager(project_db)
    session = session_manager.get_session(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )

    events = project_db.get_session_events(
        session_id=session_id,
        after_id=after_id,
        limit=limit,
    )

    return {
        "session_id": session_id,
        "events": events,
        "count": len(events),
    }


@router.get("/{slug}/loops/{loop_name}/events/grouped")
async def get_grouped_events(
    slug: str,
    loop_name: str,
    limit_runs: int = Query(5, ge=1, le=50, description="Max runs to return"),
):
    """Get events grouped by run and iteration.

    Returns events organized in a tree structure:
    - runs: { run_id: { status, iterations: { iteration: { events, session_id, is_live } } } }
    """
    manager, project, project_db = get_project(slug)
    session_manager = SessionManager(project_db)

    # Get recent runs for this loop
    runs = project_db.list_runs(loop_name=loop_name, limit=limit_runs)

    result = {
        "loop_name": loop_name,
        "runs": {},
    }

    for run in runs:
        run_id = run.get("id")
        run_status = run.get("status", "unknown")

        # Get all sessions for this run
        sessions = session_manager.list_sessions(run_id=run_id, limit=100)

        iterations = {}
        for session in sessions:
            iter_num = session.iteration

            # Get events for this session
            events = project_db.get_session_events(session.session_id)

            # Determine if this is the live session
            is_live = (
                run_status in [RunStatus.RUNNING.value, RunStatus.PAUSED.value]
                and session == sessions[-1]  # Most recent session
            )

            iterations[iter_num] = {
                "session_id": session.session_id,
                "mode": session.mode,
                "status": session.status,
                "is_live": is_live,
                "events": events,
            }

        result["runs"][run_id] = {
            "status": run_status,
            "loop_name": run.get("loop_name", loop_name),
            "started_at": run.get("started_at"),
            "completed_at": run.get("completed_at"),
            "iterations_completed": run.get("iterations_completed", 0),
            "iterations": iterations,
        }

    return result
