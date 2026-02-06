"""Planning session API routes for RalphX.

Planning sessions are interactive chat-based conversations with Claude
for the planning step of workflows.
"""

import asyncio
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ralphx.core.database import Database
from ralphx.core.project_db import ProjectDatabase

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================


class PlanningMessage(BaseModel):
    """A message in a planning session."""

    role: str
    content: str
    timestamp: str
    metadata: Optional[dict] = None


class PlanningSessionResponse(BaseModel):
    """Response model for a planning session."""

    id: str
    workflow_id: str
    step_id: int
    messages: list[PlanningMessage]
    artifacts: Optional[dict] = None
    status: str
    created_at: str
    updated_at: str


class PlanningSessionSummary(BaseModel):
    """Summary of a planning session for list display."""

    id: str
    step_id: int
    status: str  # 'active', 'completed', 'interrupted'
    message_count: int
    first_user_message: Optional[str] = None  # Truncated to 100 chars
    created_at: str
    updated_at: str
    # Diff stats (if we have before/after snapshots)
    chars_added: Optional[int] = None
    chars_removed: Optional[int] = None
    backup_created: Optional[str] = None  # Backup filename if one was created


class PlanningSessionDetail(BaseModel):
    """Full planning session with messages."""

    id: str
    workflow_id: str
    step_id: int
    status: str
    messages: list[PlanningMessage]
    artifacts: Optional[dict] = None
    created_at: str
    updated_at: str
    # Snapshot info
    initial_content_size: Optional[int] = None  # Size when session started
    final_content_size: Optional[int] = None  # Size when session ended


class SendMessageRequest(BaseModel):
    """Request model for sending a message to Claude."""

    content: str = Field(..., min_length=1)


class CompleteSessionRequest(BaseModel):
    """Request model for completing a planning session."""

    design_doc: Optional[str] = None
    guardrails: Optional[str] = None


class ArtifactUpdate(BaseModel):
    """Request model for updating artifacts."""

    design_doc: Optional[str] = None
    guardrails: Optional[str] = None


# ============================================================================
# Iteration-Based Planning Models (v17)
# ============================================================================


class StartIterationRequest(BaseModel):
    """Request model for starting an iteration session."""

    prompt: str = Field(..., min_length=1, description="User's guidance for the iterations")
    iterations: int = Field(default=3, ge=1, le=10, description="Number of iterations (1-10)")
    model: str = Field(default="opus", description="Model to use")


class CancelIterationRequest(BaseModel):
    """Request model for cancelling an iteration session."""

    session_id: str = Field(..., description="Session ID to cancel")


class IterationResponse(BaseModel):
    """Response model for iteration session."""

    id: str
    workflow_id: str
    step_id: int
    prompt: Optional[str] = None
    iterations_requested: int
    iterations_completed: int
    current_iteration: int
    run_status: str
    is_legacy: bool
    error_message: Optional[str] = None
    artifacts: Optional[dict] = None
    status: str
    created_at: str
    updated_at: str


class PlanningIterationSummary(BaseModel):
    """Summary of a planning iteration."""

    id: int
    iteration_number: int
    status: str
    chars_added: int
    chars_removed: int
    summary: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class DiffLine(BaseModel):
    """A single line in a unified diff."""

    line: str
    type: str  # 'add', 'remove', 'context', 'hunk'


class IterationDiffResponse(BaseModel):
    """Response model for iteration diff."""

    iteration_id: int
    iteration_number: int
    diff_text: Optional[str] = None
    chars_added: int = 0
    chars_removed: int = 0
    diff_lines: list[DiffLine] = []


class IterationSessionSummary(BaseModel):
    """Summary of an iteration session for list display."""

    id: str
    step_id: int
    status: str
    run_status: str
    is_legacy: bool
    prompt: Optional[str] = None  # Full for iteration sessions, truncated for legacy
    iterations_requested: int
    iterations_completed: int
    current_iteration: int = 0
    created_at: str
    updated_at: str
    # Aggregate stats from iterations
    total_chars_added: int = 0
    total_chars_removed: int = 0
    iterations: list[PlanningIterationSummary] = []


# ============================================================================
# Helper Functions
# ============================================================================


def _sanitize_error_message(message: str) -> str:
    """Sanitize error messages before sending to client.

    Removes sensitive information like file paths, database details,
    and internal state that could aid attackers or confuse users.

    Args:
        message: Raw error message.

    Returns:
        Sanitized message safe for client display.
    """
    import re

    # Remove file paths (Unix and Windows)
    sanitized = re.sub(r'/[\w./-]+\.py', '[path]', message)
    sanitized = re.sub(r'[A-Za-z]:\\[\w\\./-]+', '[path]', sanitized)

    # Remove line numbers from tracebacks
    sanitized = re.sub(r'line \d+', 'line [N]', sanitized)

    # Remove database connection strings
    sanitized = re.sub(r'sqlite:///[\w./-]+', '[database]', sanitized)
    sanitized = re.sub(r'postgresql://[^\s]+', '[database]', sanitized)

    # Remove credential-like patterns
    sanitized = re.sub(r'(access_token|refresh_token|api_key)[=:]\s*\S+', r'\1=[REDACTED]', sanitized, flags=re.IGNORECASE)

    # Truncate very long messages that might contain stack traces
    if len(sanitized) > 200:
        sanitized = sanitized[:200] + "... [truncated]"

    # If after sanitization the message is still too technical, provide generic fallback
    technical_patterns = ['Traceback', 'Exception', 'Error:', 'at 0x', '__']
    if any(pattern in sanitized for pattern in technical_patterns):
        return "An error occurred while processing your request. Please try again."

    return sanitized


def _get_project_db(slug: str) -> tuple[ProjectDatabase, dict]:
    """Get project database for a project slug."""
    db = Database()
    project = db.get_project(slug)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{slug}' not found",
        )
    return ProjectDatabase(project["path"]), project


def _session_to_response(session: dict) -> PlanningSessionResponse:
    """Convert planning session to response model."""
    return PlanningSessionResponse(
        id=session["id"],
        workflow_id=session["workflow_id"],
        step_id=session["step_id"],
        messages=[
            PlanningMessage(
                role=m["role"],
                content=m["content"],
                timestamp=m.get("timestamp", ""),
                metadata=m.get("metadata"),
            )
            for m in session.get("messages", [])
        ],
        artifacts=session.get("artifacts"),
        status=session["status"],
        created_at=session["created_at"],
        updated_at=session["updated_at"],
    )


# ============================================================================
# Planning Session Endpoints
# ============================================================================


@router.get(
    "/workflows/{workflow_id}/planning",
    response_model=PlanningSessionResponse,
)
async def get_planning_session(slug: str, workflow_id: str):
    """Get or create the planning session for a workflow.

    If no session exists for the current interactive step, one is created.
    """
    pdb, project = _get_project_db(slug)

    # Verify workflow exists
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    # Find the current interactive step
    steps = pdb.list_workflow_steps(workflow_id)
    current_step = None
    for s in steps:
        if s["step_number"] == workflow["current_step"]:
            current_step = s
            break

    if not current_step:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No current step found",
        )

    if current_step["step_type"] != "interactive":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Current step '{current_step['name']}' is not interactive",
        )

    # Get or create planning session
    session = pdb.get_planning_session_by_step(current_step["id"])
    if not session:
        session_id = f"ps-{uuid.uuid4().hex[:12]}"

        # Check if step has a design_doc_path configured - load existing content
        initial_artifacts = None
        step_config = current_step.get("config") or {}
        design_doc_path = step_config.get("design_doc_path")
        if design_doc_path:
            from pathlib import Path
            doc_dir = Path(project["path"]) / ".ralphx" / "resources" / "design_doc"
            doc_file = doc_dir / design_doc_path
            # Security: verify path stays within design_doc directory
            if (".." not in design_doc_path and "\0" not in design_doc_path
                    and doc_file.resolve().is_relative_to(doc_dir.resolve())
                    and doc_file.exists()):
                try:
                    initial_artifacts = {"design_doc": doc_file.read_text()}
                    logger.info(f"Loaded existing design doc from {doc_file}")
                except Exception as e:
                    logger.warning(f"Failed to load design doc {doc_file}: {e}")
            elif ".." in design_doc_path or "\0" in design_doc_path:
                logger.warning(f"Path traversal blocked in design_doc_path: {design_doc_path!r}")

        session = pdb.create_planning_session(
            id=session_id,
            workflow_id=workflow_id,
            step_id=current_step["id"],
            messages=[],
            artifacts=initial_artifacts,
        )

    return _session_to_response(session)


@router.post(
    "/workflows/{workflow_id}/planning/message",
    response_model=PlanningSessionResponse,
)
async def send_planning_message(
    slug: str, workflow_id: str, request: SendMessageRequest
):
    """Send a message in the planning session.

    This adds the user message to the session. The frontend will separately
    call the streaming endpoint to get Claude's response.
    """
    pdb, project = _get_project_db(slug)

    # Get the active planning session
    session = pdb.get_planning_session_by_workflow(workflow_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active planning session found",
        )

    if session["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Planning session is not active",
        )

    # Add user message
    pdb.add_planning_message(
        session_id=session["id"],
        role="user",
        content=request.content,
    )

    # Get updated session
    session = pdb.get_planning_session(session["id"])
    return _session_to_response(session)


@router.get("/workflows/{workflow_id}/planning/stream")
async def stream_planning_response(slug: str, workflow_id: str):
    """Stream Claude's response to the latest message.

    Returns a Server-Sent Events stream with Claude's response.
    Note: Uses GET for EventSource compatibility in browsers.
    Authorization is via project slug verification (each project has isolated DB).
    """
    pdb, project = _get_project_db(slug)

    # Get the active planning session
    session = pdb.get_planning_session_by_workflow(workflow_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active planning session found",
        )

    if session["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Planning session is not active",
        )

    # Get workflow and current step for context
    workflow = pdb.get_workflow(workflow_id)

    # Get the step to access its config (tools, model, timeout)
    step = pdb.get_workflow_step(session["step_id"])
    step_config = step.get("config", {}) if step else {}

    # Default tools for design_doc steps (matches PROCESSING_TYPES in workflows.py)
    DEFAULT_DESIGN_DOC_TOOLS = ["WebSearch", "WebFetch", "Bash", "Read", "Glob", "Grep", "Edit", "Write"]

    # Extract configuration from step, with defaults for design_doc
    loop_type = step_config.get("loopType", "design_doc")
    allowed_tools = step_config.get("allowedTools")
    if allowed_tools is None and loop_type == "design_doc":
        allowed_tools = DEFAULT_DESIGN_DOC_TOOLS
    elif allowed_tools is None:
        allowed_tools = []
    model = step_config.get("model", "opus")  # Default to opus for design docs
    timeout = step_config.get("timeout", 180)

    async def generate_response():
        """Generate streaming response from Claude."""
        import json

        from ralphx.core.project import Project
        from ralphx.core.planning_service import PlanningService
        from ralphx.adapters.base import AdapterEvent

        project_obj = Project.from_dict(project)
        service = PlanningService(
            project=project_obj,
            project_id=project.get("id"),
        )

        messages = session.get("messages", [])
        accumulated = ""

        error_occurred = False
        error_message = None

        try:
            async for event in service.stream_response(
                messages,
                model=model,
                tools=allowed_tools,
                timeout=timeout,
            ):
                if event.type == AdapterEvent.TEXT:
                    text = event.text or ""
                    accumulated += text
                    yield f"data: {json.dumps({'type': 'content', 'content': text})}\n\n"
                elif event.type == AdapterEvent.TOOL_USE:
                    # Forward tool use events so frontend can show activity
                    yield f"data: {json.dumps({'type': 'tool_use', 'tool': event.tool_name, 'input': event.tool_input})}\n\n"
                elif event.type == AdapterEvent.TOOL_RESULT:
                    # Forward tool result (truncated for display)
                    result_preview = str(event.tool_result or "")[:200]
                    if len(str(event.tool_result or "")) > 200:
                        result_preview += "..."
                    yield f"data: {json.dumps({'type': 'tool_result', 'tool': event.tool_name, 'result': result_preview})}\n\n"
                elif event.type == AdapterEvent.ERROR:
                    logger.warning(f"Claude error: {event.error_message}")
                    error_occurred = True
                    error_message = _sanitize_error_message(event.error_message or "Claude error")
                    # Don't return early - save accumulated content first
                    break
                elif event.type == AdapterEvent.COMPLETE:
                    break

        except Exception as e:
            # Log full error for debugging but sanitize for client
            logger.warning(f"Error during streaming response: {e}", exc_info=True)
            error_occurred = True
            error_message = _sanitize_error_message(str(e))

        # Always save accumulated content, even on error
        # This preserves partial responses from Claude
        if accumulated:
            try:
                pdb.add_planning_message(
                    session_id=session["id"],
                    role="assistant",
                    content=accumulated,
                )
            except Exception as save_err:
                logger.warning(f"Failed to save accumulated message: {save_err}")

        # Send error if one occurred (after saving content)
        if error_occurred:
            try:
                yield f"data: {json.dumps({'type': 'error', 'message': error_message})}\n\n"
            except Exception:
                pass  # Client disconnected

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.patch(
    "/workflows/{workflow_id}/planning/artifacts",
    response_model=PlanningSessionResponse,
)
async def update_planning_artifacts(
    slug: str, workflow_id: str, request: ArtifactUpdate
):
    """Update the artifacts in a planning session.

    This allows users to edit the generated design doc or guardrails.
    """
    pdb, project = _get_project_db(slug)

    session = pdb.get_planning_session_by_workflow(workflow_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active planning session found",
        )

    # Merge with existing artifacts
    artifacts = session.get("artifacts") or {}
    if request.design_doc is not None:
        artifacts["design_doc"] = request.design_doc
    if request.guardrails is not None:
        artifacts["guardrails"] = request.guardrails

    pdb.update_planning_session(session["id"], artifacts=artifacts)

    session = pdb.get_planning_session(session["id"])
    return _session_to_response(session)


@router.post(
    "/workflows/{workflow_id}/planning/complete",
    response_model=PlanningSessionResponse,
)
async def complete_planning_session(
    slug: str, workflow_id: str, request: CompleteSessionRequest
):
    """Complete the planning session and save artifacts as resources.

    This marks the planning step as complete and creates loop resources
    from the generated artifacts.
    """
    pdb, project = _get_project_db(slug)

    session = pdb.get_planning_session_by_workflow(workflow_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active planning session found",
        )

    if session["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Planning session is not active",
        )

    # Build final artifacts
    artifacts = session.get("artifacts") or {}
    if request.design_doc:
        artifacts["design_doc"] = request.design_doc
    if request.guardrails:
        artifacts["guardrails"] = request.guardrails

    # Complete the planning session
    pdb.complete_planning_session(session["id"], artifacts=artifacts)

    # Get workflow info
    workflow = pdb.get_workflow(workflow_id)

    # Save artifacts as project resources
    # Use workflow_id for unique filenames (namespace was removed in schema v16)
    from pathlib import Path
    from datetime import datetime

    if artifacts.get("design_doc"):
        # Save design doc
        resource_path = Path(project["path"]) / ".ralphx" / "resources"
        resource_path.mkdir(parents=True, exist_ok=True)

        doc_filename = f"design-doc-{workflow_id}.md"
        doc_path = resource_path / doc_filename
        doc_path.write_text(artifacts["design_doc"])

        # Create resource entry (may already exist if re-completing session)
        try:
            pdb.create_resource(
                name=f"Design Doc ({workflow['name']})",
                resource_type="design_doc",
                file_path=str(doc_path.relative_to(project["path"])),
                injection_position="after_design_doc",
                enabled=True,
                inherit_default=True,
            )
        except sqlite3.IntegrityError:
            # Resource with this name already exists - this is expected
            # on re-completion of a session, file was already updated above
            logger.debug(f"Design doc resource already exists for workflow '{workflow['name']}'")
        except Exception as e:
            # Unexpected error - log but don't fail the operation
            logger.warning(f"Failed to create design doc resource: {e}")

    if artifacts.get("guardrails"):
        resource_path = Path(project["path"]) / ".ralphx" / "resources"
        resource_path.mkdir(parents=True, exist_ok=True)

        guardrails_filename = f"guardrails-{workflow_id}.md"
        guardrails_path = resource_path / guardrails_filename
        guardrails_path.write_text(artifacts["guardrails"])

        try:
            pdb.create_resource(
                name=f"Guardrails ({workflow['name']})",
                resource_type="guardrails",
                file_path=str(guardrails_path.relative_to(project["path"])),
                injection_position="after_design_doc",
                enabled=True,
                inherit_default=True,
            )
        except sqlite3.IntegrityError:
            # Resource with this name already exists
            logger.debug(f"Guardrails resource already exists for workflow '{workflow['name']}'")
        except Exception as e:
            logger.warning(f"Failed to create guardrails resource: {e}")

    # Advance workflow to next step via WorkflowExecutor
    from ralphx.core.project import Project
    from ralphx.core.workflow_executor import WorkflowExecutor

    project_obj = Project.from_dict(project)
    workflow_executor = WorkflowExecutor(
        project=project_obj,
        db=pdb,
        workflow_id=workflow_id,
    )

    # Complete the current step (planning) which advances to the next step
    current_step = pdb.get_workflow_step_by_number(workflow_id, workflow["current_step"])
    if current_step and current_step["status"] == "active":
        await workflow_executor.complete_step(current_step["id"], artifacts=artifacts)

    # Get updated session
    session = pdb.get_planning_session(session["id"])
    return _session_to_response(session)


@router.get("/workflows/{workflow_id}/planning/generate-artifacts")
async def generate_artifacts(slug: str, workflow_id: str):
    """Ask Claude to generate design doc and guardrails from conversation.

    Returns a streaming response with the generated artifacts.
    Note: Uses GET for EventSource compatibility in browsers.
    Authorization is via project slug verification (each project has isolated DB).
    """
    pdb, project = _get_project_db(slug)

    session = pdb.get_planning_session_by_workflow(workflow_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active planning session found",
        )

    async def generate():
        """Generate artifacts from conversation."""
        import json

        from ralphx.core.project import Project
        from ralphx.core.planning_service import PlanningService
        from ralphx.adapters.base import AdapterEvent

        messages = session.get("messages", [])

        project_obj = Project.from_dict(project)
        service = PlanningService(
            project=project_obj,
            project_id=project.get("id"),
        )

        accumulated = ""

        try:
            # Stream the generation (we'll parse artifacts at the end)
            async for event in service.generate_artifacts(messages):
                if event.type == AdapterEvent.TEXT:
                    text = event.text or ""
                    accumulated += text
                    # Stream progress indicator (not the full text to avoid noise)
                    yield f"data: {json.dumps({'type': 'progress', 'length': len(accumulated)})}\n\n"
                elif event.type == AdapterEvent.ERROR:
                    logger.warning(f"Claude error during artifact generation: {event.error_message}")
                    safe_message = _sanitize_error_message(event.error_message or "Claude error")
                    yield f"data: {json.dumps({'type': 'error', 'message': safe_message})}\n\n"
                    return
                elif event.type == AdapterEvent.COMPLETE:
                    break

            # Parse the generated text to extract artifacts
            parsed = PlanningService.parse_artifacts(accumulated)

            # Fall back to full text if parsing failed
            if not parsed["design_doc"] and accumulated:
                logger.warning("Failed to parse design doc markers, using full text")
                parsed["design_doc"] = accumulated

            if not parsed["guardrails"]:
                # Generate default guardrails if not included
                parsed["guardrails"] = """# Project Guardrails

## Code Quality
- All code must pass linting and type checking
- Functions should have docstrings
- Keep functions focused and under 50 lines

## Testing
- Unit tests required for all business logic
- Integration tests for API endpoints

## Security
- No hardcoded secrets
- Input validation on all user inputs
- Proper error handling without leaking internals

## Git Practices
- Descriptive commit messages
- One logical change per commit
"""

            # Update session artifacts
            artifacts = {
                "design_doc": parsed["design_doc"],
                "guardrails": parsed["guardrails"],
            }
            pdb.update_planning_session(session["id"], artifacts=artifacts)

            # Send the final artifacts
            yield f"data: {json.dumps({'type': 'artifacts', 'artifacts': artifacts})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            # Log full error for debugging but sanitize for client
            logger.warning(f"Error during artifact generation: {e}", exc_info=True)
            try:
                safe_message = _sanitize_error_message(str(e))
                yield f"data: {json.dumps({'type': 'error', 'message': safe_message})}\n\n"
            except Exception:
                pass  # Client disconnected

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ============================================================================
# Iteration-Based Planning Endpoints (v17)
# ============================================================================


def _session_to_iteration_response(session: dict) -> IterationResponse:
    """Convert planning session to iteration response model."""
    return IterationResponse(
        id=session["id"],
        workflow_id=session["workflow_id"],
        step_id=session["step_id"],
        prompt=session.get("prompt"),
        iterations_requested=session.get("iterations_requested", 1),
        iterations_completed=session.get("iterations_completed", 0),
        current_iteration=session.get("current_iteration", 0),
        run_status=session.get("run_status", "pending"),
        is_legacy=session.get("is_legacy", False),
        error_message=session.get("error_message"),
        artifacts=session.get("artifacts"),
        status=session["status"],
        created_at=session["created_at"],
        updated_at=session["updated_at"],
    )


@router.post(
    "/workflows/{workflow_id}/planning/iterate",
    response_model=IterationResponse,
)
async def start_iteration_session(
    slug: str, workflow_id: str, request: StartIterationRequest
):
    """Start a new iteration-based planning session.

    Creates a new session and returns immediately. Use the stream endpoint
    to receive progress events as iterations run.
    """
    pdb, project = _get_project_db(slug)

    # Verify workflow exists
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    # Find the current interactive step
    steps = pdb.list_workflow_steps(workflow_id)
    current_step = None
    for s in steps:
        if s["step_number"] == workflow["current_step"]:
            current_step = s
            break

    if not current_step:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No current step found",
        )

    if current_step["step_type"] != "interactive":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Current step '{current_step['name']}' is not interactive",
        )

    # Check for already running session (concurrency protection) with stale recovery
    existing = pdb.get_running_planning_session(workflow_id)
    if existing:
        updated = datetime.fromisoformat(existing["updated_at"])
        if datetime.utcnow() - updated > timedelta(minutes=10):
            logger.warning(f"Auto-recovering stale session '{existing['id']}' (last updated: {existing['updated_at']})")
            pdb.update_planning_session(
                existing["id"], run_status="error", error_message="Session timed out (stale recovery)"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Session '{existing['id']}' is already running. Cancel it first.",
            )

    # Check if there's an existing active session to build upon
    existing_session = pdb.get_planning_session_by_step(current_step["id"])
    initial_artifacts = None

    if existing_session:
        # Preserve existing artifacts (design doc)
        initial_artifacts = existing_session.get("artifacts")
        # Mark old session as completed if it's active
        if existing_session["status"] == "active":
            pdb.update_planning_session(
                existing_session["id"],
                status="completed",
                run_status="completed" if existing_session.get("run_status") == "running" else existing_session.get("run_status", "completed"),
            )

    # Also check step config for design_doc_path to load existing content
    if not initial_artifacts:
        step_config = current_step.get("config") or {}
        design_doc_path = step_config.get("design_doc_path")
        if design_doc_path:
            from pathlib import Path
            doc_dir = Path(project["path"]) / ".ralphx" / "resources" / "design_doc"
            doc_file = doc_dir / design_doc_path
            # Security: verify path stays within design_doc directory
            if (".." not in design_doc_path and "\0" not in design_doc_path
                    and doc_file.resolve().is_relative_to(doc_dir.resolve())
                    and doc_file.exists()):
                try:
                    initial_artifacts = {"design_doc": doc_file.read_text()}
                    logger.info(f"Loaded existing design doc from {doc_file}")
                except Exception as e:
                    logger.warning(f"Failed to load design doc {doc_file}: {e}")
            elif ".." in design_doc_path or "\0" in design_doc_path:
                logger.warning(f"Path traversal blocked in design_doc_path: {design_doc_path!r}")

    # Create new iteration session
    session_id = f"ps-{uuid.uuid4().hex[:12]}"
    session = pdb.create_planning_session(
        id=session_id,
        workflow_id=workflow_id,
        step_id=current_step["id"],
        messages=[],  # Not used in iteration mode
        artifacts=initial_artifacts,
        status="active",
        prompt=request.prompt,
        iterations_requested=request.iterations,
        run_status="pending",
        is_legacy=False,
    )

    # Get step configuration for tools/model
    step_config = current_step.get("config", {}) or {}
    DEFAULT_DESIGN_DOC_TOOLS = ["WebSearch", "WebFetch", "Bash", "Read", "Glob", "Grep", "Edit", "Write"]
    allowed_tools = step_config.get("allowedTools") or DEFAULT_DESIGN_DOC_TOOLS
    model = step_config.get("model", "opus")

    # Launch executor as background task
    async def run_executor_background():
        from ralphx.core.project import Project
        from ralphx.core.planning_iteration_executor import PlanningIterationExecutor

        project_obj = Project.from_dict(project)

        # Resolve the design doc file path for file-based editing
        from pathlib import Path as _Path
        _doc_dir = _Path(project["path"]) / ".ralphx" / "resources"
        _configured_path = step_config.get("design_doc_path")
        if _configured_path:
            _design_doc_dir = _doc_dir / "design_doc"
            _doc_file = _design_doc_dir / _configured_path
            # Security: verify path stays within design_doc directory
            if (".." in _configured_path or "\0" in _configured_path
                    or not _doc_file.resolve().is_relative_to(_design_doc_dir.resolve())):
                logger.warning(f"Path traversal blocked in design_doc_path for executor: {_configured_path!r}")
                _doc_file = _doc_dir / f"design-doc-{workflow_id}.md"
        else:
            _doc_file = _doc_dir / f"design-doc-{workflow_id}.md"

        executor = PlanningIterationExecutor(
            project=project_obj,
            pdb=pdb,
            session_id=session_id,
            project_id=project.get("id"),
            design_doc_path=str(_doc_file),
        )

        try:
            async for event in executor.run(
                prompt=request.prompt,
                iterations=request.iterations,
                model=model,
                tools=allowed_tools,
            ):
                # Persist every event to DB
                pdb.add_planning_iteration_event(
                    session_id=session_id,
                    event_type=event.get("type", "unknown"),
                    iteration_number=event.get("iteration"),
                    content=event.get("text"),
                    tool_name=event.get("tool"),
                    tool_input=json.dumps(event.get("input"))[:1000] if event.get("input") else None,
                    tool_result=(event.get("result") or "")[:1000] if event.get("result") else None,
                    event_data=json.dumps(event),
                )
        except Exception as e:
            logger.error(f"Background executor error for session {session_id}: {e}", exc_info=True)
            try:
                pdb.update_planning_session(session_id, run_status="error", error_message="Executor failed")
                pdb.add_planning_iteration_event(
                    session_id=session_id,
                    event_type="error",
                    event_data=json.dumps({"type": "error", "message": "Execution failed unexpectedly", "fatal": True}),
                )
            except Exception:
                pass

    task = asyncio.create_task(run_executor_background(), name=f"planning-iteration-{session_id}")

    def _on_task_done(t: asyncio.Task) -> None:
        if t.cancelled():
            logger.warning(f"Planning iteration task {session_id} was cancelled")
        elif t.exception():
            logger.error(f"Planning iteration task {session_id} failed: {t.exception()}")

    task.add_done_callback(_on_task_done)

    return _session_to_iteration_response(session)


@router.get("/workflows/{workflow_id}/planning/iterate/stream/{session_id}")
async def stream_iteration_progress(
    slug: str,
    workflow_id: str,
    session_id: str,
    after_event_id: int = Query(default=0, description="Resume from this event ID"),
):
    """Stream iteration progress via Server-Sent Events (DB-polling).

    This endpoint polls the planning_iteration_events table for new events.
    Supports reconnection: pass after_event_id to resume from where you left off.

    Events include:
    - iteration_start: {iteration: N, total: M}
    - tool_use: {tool: "WebSearch", input: {...}}
    - tool_result: {tool: "WebSearch", result: "..."}
    - content: {text: "..."} - Claude's response text
    - design_doc_updated: {chars_added: N, chars_removed: M}
    - heartbeat: {} - Periodic keepalive
    - iteration_complete: {iteration: N, summary: "..."}
    - error: {message: "..."}
    - cancelled: {iterations_completed: N}
    - done: {iterations_completed: N}
    """
    pdb, project = _get_project_db(slug)

    # Verify session exists and belongs to this workflow
    session = pdb.get_planning_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )

    if session["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found in workflow '{workflow_id}'",
        )

    async def generate_stream():
        """Poll DB for events and stream as SSE."""
        last_id = after_event_id

        # Immediate stale check before entering loop
        current = pdb.get_planning_session(session_id)
        if current and current.get("run_status") == "running":
            last_event_ts = pdb.get_latest_event_timestamp(session_id)
            # Fall back to created_at if no events exist yet
            check_ts = last_event_ts or current.get("created_at")
            if check_ts:
                elapsed = datetime.utcnow() - datetime.fromisoformat(check_ts)
                if elapsed > timedelta(minutes=7):
                    pdb.update_planning_session(
                        session_id, run_status="error",
                        error_message="Session timed out (no activity)",
                    )
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Session timed out (no activity)', 'fatal': True})}\n\n"
                    return

        while True:
            # Fetch new events from DB
            events = pdb.get_planning_iteration_events(session_id, after_id=last_id)
            for evt in events:
                last_id = evt["id"]
                if evt.get("event_data"):
                    try:
                        event_data = json.loads(evt["event_data"])
                    except (json.JSONDecodeError, TypeError):
                        event_data = {"type": evt["event_type"]}
                else:
                    event_data = {"type": evt["event_type"]}
                event_data["_event_id"] = evt["id"]
                yield f"data: {json.dumps(event_data)}\n\n"

            # Check if session reached terminal status
            current = pdb.get_planning_session(session_id)

            # Check for stale session (no events for >7 min while supposedly running)
            if current and current.get("run_status") == "running":
                last_event_ts = pdb.get_latest_event_timestamp(session_id)
                check_ts = last_event_ts or (current.get("created_at") if current else None)
                if check_ts:
                    elapsed = datetime.utcnow() - datetime.fromisoformat(check_ts)
                    if elapsed > timedelta(minutes=7):
                        pdb.update_planning_session(
                            session_id, run_status="error",
                            error_message="Session timed out (no activity)",
                        )
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Session timed out (no activity)', 'fatal': True})}\n\n"
                        break

            if current and current.get("run_status") in ("completed", "error", "cancelled"):
                # Drain any remaining events
                final_events = pdb.get_planning_iteration_events(session_id, after_id=last_id)
                for evt in final_events:
                    last_id = evt["id"]
                    if evt.get("event_data"):
                        try:
                            event_data = json.loads(evt["event_data"])
                        except (json.JSONDecodeError, TypeError):
                            event_data = {"type": evt["event_type"]}
                    else:
                        event_data = {"type": evt["event_type"]}
                    event_data["_event_id"] = evt["id"]
                    yield f"data: {json.dumps(event_data)}\n\n"
                break

            # Heartbeat to keep connection alive
            yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/workflows/{workflow_id}/planning/iterate/cancel",
    response_model=IterationResponse,
)
async def cancel_iteration_session(
    slug: str, workflow_id: str, request: CancelIterationRequest
):
    """Cancel a running iteration session.

    Marks the session as cancelled. The running iteration will complete
    but no further iterations will start.
    """
    pdb, project = _get_project_db(slug)

    session = pdb.get_planning_session(request.session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{request.session_id}' not found",
        )

    if session["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{request.session_id}' not found in workflow '{workflow_id}'",
        )

    if session.get("run_status") != "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is not running",
        )

    # Mark as cancelled (executor will pick this up)
    pdb.cancel_planning_session(request.session_id)

    session = pdb.get_planning_session(request.session_id)
    return _session_to_iteration_response(session)


@router.get(
    "/workflows/{workflow_id}/planning/iterate/{session_id}",
    response_model=IterationResponse,
)
async def get_iteration_session(slug: str, workflow_id: str, session_id: str):
    """Get details of an iteration session including progress."""
    pdb, project = _get_project_db(slug)

    session = pdb.get_planning_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )

    if session["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found in workflow '{workflow_id}'",
        )

    return _session_to_iteration_response(session)


@router.get("/workflows/{workflow_id}/planning/iterate/{session_id}/events")
async def get_iteration_events(
    slug: str,
    workflow_id: str,
    session_id: str,
    after_id: int = Query(default=0, description="Only return events after this ID"),
    limit: int = Query(default=500, ge=1, le=1000),
):
    """Get persisted iteration events for a session.

    Use after_id for pagination. Returns events ordered by ID ascending.
    """
    pdb, project = _get_project_db(slug)

    session = pdb.get_planning_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )

    if session["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found in workflow '{workflow_id}'",
        )

    return pdb.get_planning_iteration_events(session_id, after_id=after_id, limit=limit)


@router.get(
    "/workflows/{workflow_id}/planning/iterate/{session_id}/iterations",
    response_model=list[PlanningIterationSummary],
)
async def list_session_iterations(slug: str, workflow_id: str, session_id: str):
    """List all iterations for a session with their stats."""
    pdb, project = _get_project_db(slug)

    session = pdb.get_planning_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )

    if session["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found in workflow '{workflow_id}'",
        )

    iterations = pdb.list_planning_iterations(session_id)

    return [
        PlanningIterationSummary(
            id=it["id"],
            iteration_number=it["iteration_number"],
            status=it["status"],
            chars_added=it.get("chars_added", 0),
            chars_removed=it.get("chars_removed", 0),
            summary=it.get("summary"),
            started_at=it.get("started_at"),
            completed_at=it.get("completed_at"),
        )
        for it in iterations
    ]


@router.get(
    "/workflows/{workflow_id}/planning/iterate/{session_id}/iterations/{iteration_id}/diff",
    response_model=IterationDiffResponse,
)
async def get_iteration_diff(
    slug: str, workflow_id: str, session_id: str, iteration_id: int
):
    """Get the unified diff for a specific iteration."""
    pdb, project = _get_project_db(slug)

    session = pdb.get_planning_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )

    if session["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found in workflow '{workflow_id}'",
        )

    # Fetch the specific iteration directly (avoids loading all diffs)
    iteration = pdb.get_planning_iteration(iteration_id)
    if not iteration or iteration.get("session_id") != session_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Iteration '{iteration_id}' not found in session '{session_id}'",
        )

    diff_text = iteration.get("diff_text")

    # Fallback: compute diff on-the-fly from doc snapshots if diff_text is missing
    if not diff_text:
        doc_before = iteration.get("doc_before")
        doc_after = iteration.get("doc_after")
        if doc_before is not None and doc_after is not None:
            import difflib

            diff_text = "\n".join(
                difflib.unified_diff(
                    doc_before.splitlines(),
                    doc_after.splitlines(),
                    fromfile="before",
                    tofile="after",
                    lineterm="",
                )
            )

    diff_lines: list[DiffLine] = []

    if diff_text:
        for line in diff_text.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                diff_lines.append(DiffLine(line=line, type="add"))
            elif line.startswith("-") and not line.startswith("---"):
                diff_lines.append(DiffLine(line=line, type="remove"))
            elif line.startswith("@@"):
                diff_lines.append(DiffLine(line=line, type="hunk"))
            elif not line.startswith("+++") and not line.startswith("---"):
                diff_lines.append(DiffLine(line=line, type="context"))

    return IterationDiffResponse(
        iteration_id=iteration["id"],
        iteration_number=iteration["iteration_number"],
        diff_text=diff_text,
        chars_added=iteration.get("chars_added", 0),
        chars_removed=iteration.get("chars_removed", 0),
        diff_lines=diff_lines,
    )


# ============================================================================
# Planning Session History Endpoints (updated for v17)
# ============================================================================


@router.get(
    "/workflows/{workflow_id}/planning/sessions",
    response_model=list[IterationSessionSummary],
)
async def list_workflow_planning_sessions(slug: str, workflow_id: str):
    """List all planning sessions for a workflow.

    Returns sessions in reverse chronological order (newest first).
    Supports both legacy chat-based sessions and new iteration-based sessions.
    """
    pdb, project = _get_project_db(slug)

    # Verify workflow exists
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    sessions = pdb.list_planning_sessions(workflow_id=workflow_id)

    summaries = []
    for session in sessions:
        is_legacy = session.get("is_legacy", False)

        # For legacy sessions, use first user message as prompt preview
        prompt_preview = session.get("prompt")
        if not prompt_preview and is_legacy:
            messages = session.get("messages", [])
            user_messages = [m for m in messages if m.get("role") == "user"]
            if user_messages:
                content = user_messages[0].get("content", "")
                prompt_preview = content[:100] if len(content) > 100 else content

        # Get iterations for this session
        iterations = pdb.list_planning_iterations(session["id"])
        iteration_summaries = [
            PlanningIterationSummary(
                id=it["id"],
                iteration_number=it["iteration_number"],
                status=it["status"],
                chars_added=it.get("chars_added", 0),
                chars_removed=it.get("chars_removed", 0),
                summary=it.get("summary"),
                started_at=it.get("started_at"),
                completed_at=it.get("completed_at"),
            )
            for it in iterations
        ]

        # Calculate totals from iterations
        total_chars_added = sum(it.get("chars_added", 0) for it in iterations)
        total_chars_removed = sum(it.get("chars_removed", 0) for it in iterations)

        summaries.append(
            IterationSessionSummary(
                id=session["id"],
                step_id=session["step_id"],
                status=session["status"],
                run_status=session.get("run_status", "completed" if is_legacy else "pending"),
                is_legacy=is_legacy,
                prompt=prompt_preview,
                iterations_requested=session.get("iterations_requested", 0 if is_legacy else 1),
                iterations_completed=session.get("iterations_completed", 0),
                current_iteration=session.get("current_iteration", 0),
                created_at=session["created_at"],
                updated_at=session["updated_at"],
                total_chars_added=total_chars_added,
                total_chars_removed=total_chars_removed,
                iterations=iteration_summaries,
            )
        )

    return summaries


@router.get(
    "/workflows/{workflow_id}/planning/sessions/{session_id}",
    response_model=PlanningSessionDetail,
)
async def get_planning_session_detail(slug: str, workflow_id: str, session_id: str):
    """Get full details of a specific planning session including all messages."""
    pdb, project = _get_project_db(slug)

    # Verify workflow exists
    workflow = pdb.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found",
        )

    session = pdb.get_planning_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )

    # Verify session belongs to this workflow
    if session["workflow_id"] != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found in workflow '{workflow_id}'",
        )

    messages = [
        PlanningMessage(
            role=m["role"],
            content=m["content"],
            timestamp=m.get("timestamp", ""),
            metadata=m.get("metadata"),
        )
        for m in session.get("messages", [])
    ]

    return PlanningSessionDetail(
        id=session["id"],
        workflow_id=session["workflow_id"],
        step_id=session["step_id"],
        status=session["status"],
        messages=messages,
        artifacts=session.get("artifacts"),
        created_at=session["created_at"],
        updated_at=session["updated_at"],
        initial_content_size=session.get("initial_content_size"),
        final_content_size=session.get("final_content_size"),
    )
