"""Planning session API routes for RalphX.

Planning sessions are interactive chat-based conversations with Claude
for the planning step of workflows.
"""

import logging
import sqlite3
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, status
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
        session = pdb.create_planning_session(
            id=session_id,
            workflow_id=workflow_id,
            step_id=current_step["id"],
            messages=[],
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

    # Extract configuration from step
    allowed_tools = step_config.get("allowedTools", [])
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

        try:
            async for event in service.stream_response(
                messages,
                model=model,
                tools=allowed_tools if allowed_tools else None,
                timeout=timeout,
            ):
                if event.type == AdapterEvent.TEXT:
                    text = event.text or ""
                    accumulated += text
                    yield f"data: {json.dumps({'type': 'content', 'content': text})}\n\n"
                elif event.type == AdapterEvent.ERROR:
                    logger.warning(f"Claude error: {event.error_message}")
                    safe_message = _sanitize_error_message(event.error_message or "Claude error")
                    yield f"data: {json.dumps({'type': 'error', 'message': safe_message})}\n\n"
                    return
                elif event.type == AdapterEvent.COMPLETE:
                    break

            # Add assistant message to session
            if accumulated:
                pdb.add_planning_message(
                    session_id=session["id"],
                    role="assistant",
                    content=accumulated,
                )

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            # Log full error for debugging but sanitize for client
            logger.warning(f"Error during streaming response: {e}", exc_info=True)
            try:
                # Sanitize error message to avoid leaking internal paths/details
                safe_message = _sanitize_error_message(str(e))
                yield f"data: {json.dumps({'type': 'error', 'message': safe_message})}\n\n"
            except Exception:
                pass  # Client disconnected

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
