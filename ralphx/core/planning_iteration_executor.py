"""Planning Iteration Executor for RalphX.

Replaces the chat-based planning paradigm with prompt-driven iteration loops.
Users provide a single prompt + iteration count, system runs N iterations
automatically, each refining the design document.
"""

import asyncio
import difflib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional

from ralphx.adapters.base import AdapterEvent, StreamEvent
from ralphx.adapters.claude_cli import ClaudeCLIAdapter
from ralphx.core.project import Project
from ralphx.core.project_db import ProjectDatabase

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================

# Allowed tools for iteration mode (research + file editing)
DEFAULT_ITERATION_TOOLS = [
    "WebSearch",  # Research best practices, technologies
    "WebFetch",  # Deep dive into specific URLs
    "Read",  # Read project files for context
    "Glob",  # Find relevant files
    "Grep",  # Search file contents
    "Edit",  # Edit the design document in place
    "Write",  # Write/rewrite the design document
]

# Timeouts and limits
TIMEOUT_PER_ITERATION = 300  # 5 minutes per iteration
COOLDOWN_BETWEEN_ITERATIONS = 5  # 5 seconds between iterations
MAX_ITERATIONS = 10  # Maximum iterations allowed
HEARTBEAT_INTERVAL = 15  # Heartbeat every 15 seconds

# ============================================================================
# SSE Event Types
# ============================================================================


class SSEEventType:
    """Server-Sent Event types for iteration streaming."""

    ITERATION_START = "iteration_start"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    CONTENT = "content"
    DESIGN_DOC_UPDATED = "design_doc_updated"
    HEARTBEAT = "heartbeat"
    ITERATION_COMPLETE = "iteration_complete"
    ERROR = "error"
    CANCELLED = "cancelled"
    DONE = "done"


# ============================================================================
# Iteration Prompt Template
# ============================================================================

ITERATION_PROMPT_TEMPLATE = """You are refining a design document. This is iteration {current} of {total}.

## User's Guidance
{user_prompt}

## Design Document
The design document is at: {design_doc_file}
Read it, then use Edit to make targeted changes based on your research.

## Instructions
1. Read the design document file at the path above
2. Use tools (WebSearch, Read, etc.) to research as needed
3. Use Edit to make targeted changes to the design document file
4. If the document doesn't exist yet, use Write to create it
5. Provide a brief summary of changes in <changes_summary>...</changes_summary> tags

Do NOT output the entire document in your response. Edit the file directly using the Edit tool.
"""

NO_DOC_PLACEHOLDER = """(No design document exists yet. Create a comprehensive design document based on the user's guidance above.

Structure your document with clear sections:
- Overview / Problem Statement
- Goals and Requirements
- Technical Approach
- Key Components
- Implementation Plan
- Open Questions / Considerations)"""


# ============================================================================
# Executor Class
# ============================================================================


class PlanningIterationExecutor:
    """Executes N iterations of design doc refinement.

    Each iteration:
    1. Writes the current design doc to a file for Claude to edit in place
    2. Builds a prompt referencing the file path (not the doc content)
    3. Streams Claude response (with Edit/Write tools)
    4. Re-reads the file to capture Claude's edits, saves to DB
    5. Records iteration metrics
    """

    def __init__(
        self,
        project: Project,
        pdb: ProjectDatabase,
        session_id: str,
        project_id: Optional[str] = None,
        design_doc_path: Optional[str] = None,
    ):
        """Initialize the executor.

        Args:
            project: Project object with path.
            pdb: Project database for persistence.
            session_id: Planning session ID.
            project_id: Optional project ID for credentials.
            design_doc_path: Absolute path to design doc file for file-based editing.
        """
        self.project = project
        self.pdb = pdb
        self.session_id = session_id
        self.project_id = project_id
        self.design_doc_path = design_doc_path
        self._adapter: Optional[ClaudeCLIAdapter] = None
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation of the execution loop."""
        self._cancelled = True

    async def _check_cancelled(self) -> bool:
        """Check if cancellation has been requested.

        Also checks the database for external cancellation.
        """
        if self._cancelled:
            return True

        # Check database for cancelled status
        session = self.pdb.get_planning_session(self.session_id)
        if session and session.get("run_status") == "cancelled":
            self._cancelled = True
            return True

        return False

    def _load_design_doc(self) -> str:
        """Load the current design document from session artifacts.

        Returns:
            The design doc content, or empty string if none exists.
        """
        session = self.pdb.get_planning_session(self.session_id)
        if not session:
            return ""

        artifacts = session.get("artifacts") or {}
        return artifacts.get("design_doc", "")

    def _save_design_doc(self, content: str) -> None:
        """Save the design document to session artifacts.

        Args:
            content: The updated design doc content.
        """
        session = self.pdb.get_planning_session(self.session_id)
        if not session:
            return

        artifacts = session.get("artifacts") or {}
        artifacts["design_doc"] = content
        self.pdb.update_planning_session(self.session_id, artifacts=artifacts)

    def _build_iteration_prompt(
        self,
        user_prompt: str,
        design_doc_file: str,
        current: int,
        total: int,
    ) -> str:
        """Build the prompt for an iteration.

        Args:
            user_prompt: User's guidance for this session.
            design_doc_file: Path to the design doc file on disk.
            current: Current iteration number (1-indexed).
            total: Total iterations requested.

        Returns:
            Full prompt string.
        """
        return ITERATION_PROMPT_TEMPLATE.format(
            current=current,
            total=total,
            user_prompt=user_prompt,
            design_doc_file=design_doc_file,
        )

    def _extract_design_doc(self, response: str) -> Optional[str]:
        """Extract the design document from Claude's response.

        Args:
            response: Full response text from Claude.

        Returns:
            Extracted design doc content, or None if not found.
        """
        # Look for <design_doc>...</design_doc> tags
        match = re.search(
            r"<design_doc>(.*?)</design_doc>",
            response,
            re.DOTALL | re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()

        # Fallback: if response looks like a design doc (has markdown headers),
        # use the whole response
        if len(response) > 200 and any(h in response for h in ["# ", "## "]):
            logger.warning(
                "No <design_doc> tags found, using response as design doc (has markdown)"
            )
            return response.strip()

        return None

    def _extract_summary(self, response: str) -> Optional[str]:
        """Extract the changes summary from Claude's response.

        Args:
            response: Full response text from Claude.

        Returns:
            Extracted summary, or None if not found.
        """
        match = re.search(
            r"<changes_summary>(.*?)</changes_summary>",
            response,
            re.DOTALL | re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
        return None

    def _calculate_diff(
        self, old_doc: str, new_doc: str
    ) -> tuple[int, int]:
        """Calculate characters added and removed using sequence matching.

        Uses difflib to compute actual additions and removals, not just
        length difference. This correctly handles replacements (e.g., 100
        chars replaced with 100 different chars shows both adds and removes).

        Args:
            old_doc: Previous document content.
            new_doc: New document content.

        Returns:
            Tuple of (chars_added, chars_removed).
        """
        if not old_doc and not new_doc:
            return 0, 0
        if not old_doc:
            return len(new_doc), 0
        if not new_doc:
            return 0, len(old_doc)

        old_lines = old_doc.splitlines(keepends=True)
        new_lines = new_doc.splitlines(keepends=True)

        chars_added = 0
        chars_removed = 0

        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, old_lines, new_lines
        ).get_opcodes():
            if tag == "replace":
                chars_removed += sum(len(line) for line in old_lines[i1:i2])
                chars_added += sum(len(line) for line in new_lines[j1:j2])
            elif tag == "delete":
                chars_removed += sum(len(line) for line in old_lines[i1:i2])
            elif tag == "insert":
                chars_added += sum(len(line) for line in new_lines[j1:j2])

        return chars_added, chars_removed

    def _compute_unified_diff(self, old_doc: str, new_doc: str) -> str:
        """Compute a unified diff between old and new document content.

        Args:
            old_doc: Previous document content.
            new_doc: New document content.

        Returns:
            Unified diff string.
        """
        return "".join(
            difflib.unified_diff(
                old_doc.splitlines(keepends=True),
                new_doc.splitlines(keepends=True),
                fromfile="before",
                tofile="after",
            )
        )

    def _resolve_doc_path(self) -> Path:
        """Resolve the design doc file path.

        Uses the configured design_doc_path if set, otherwise defaults to
        a session-specific file under .ralphx/resources/.
        """
        if self.design_doc_path:
            return Path(self.design_doc_path)
        # Default: project/.ralphx/resources/design-doc-<session>.md
        return Path(self.project.path) / ".ralphx" / "resources" / f"design-doc-iteration-{self.session_id}.md"

    async def run(
        self,
        prompt: str,
        iterations: int,
        model: str = "opus",
        tools: Optional[list[str]] = None,
    ) -> AsyncIterator[dict]:
        """Run the iteration loop.

        Args:
            prompt: User's guidance prompt.
            iterations: Number of iterations to run.
            model: Model to use (default: opus for design docs).
            tools: Tools to enable (default: DEFAULT_ITERATION_TOOLS).

        Yields:
            SSE event dicts as execution progresses.
        """
        if tools is None:
            tools = DEFAULT_ITERATION_TOOLS

        iterations = min(iterations, MAX_ITERATIONS)

        # Resolve the file path Claude will edit directly
        doc_file_path = self._resolve_doc_path()

        # Update session status to running
        self.pdb.update_planning_session(
            self.session_id,
            run_status="running",
            current_iteration=0,
            iterations_completed=0,
        )

        completed_iterations = 0
        last_event_time = asyncio.get_event_loop().time()

        try:
            for i in range(1, iterations + 1):
                # Check for cancellation before each iteration
                if await self._check_cancelled():
                    yield {
                        "type": SSEEventType.CANCELLED,
                        "iterations_completed": completed_iterations,
                    }
                    self.pdb.update_planning_session(
                        self.session_id,
                        run_status="cancelled",
                        iterations_completed=completed_iterations,
                    )
                    return

                # Update current iteration
                self.pdb.update_planning_session(
                    self.session_id,
                    current_iteration=i,
                )

                # Create iteration record
                iteration_record = self.pdb.create_planning_iteration(
                    session_id=self.session_id,
                    iteration_number=i,
                    status="running",
                )
                iteration_id = iteration_record["id"] if iteration_record else None
                if iteration_id:
                    self.pdb.start_planning_iteration(iteration_id)

                yield {
                    "type": SSEEventType.ITERATION_START,
                    "iteration": i,
                    "total": iterations,
                }

                # Load current design doc and write to file for Claude to edit
                old_doc = self._load_design_doc()
                doc_file_path.parent.mkdir(parents=True, exist_ok=True)
                if old_doc:
                    doc_file_path.write_text(old_doc)
                elif doc_file_path.exists():
                    old_doc = doc_file_path.read_text()

                # Build iteration prompt (references file path, not doc content)
                full_prompt = self._build_iteration_prompt(
                    prompt, str(doc_file_path), i, iterations
                )

                # Create adapter for this iteration
                self._adapter = ClaudeCLIAdapter(
                    project_path=Path(self.project.path),
                    project_id=self.project_id,
                )

                # Stream Claude response
                response_text = ""
                tool_calls: list[dict] = []
                error_message: Optional[str] = None

                try:
                    async for event in self._adapter.stream(
                        prompt=full_prompt,
                        model=model,
                        tools=tools,
                        timeout=TIMEOUT_PER_ITERATION,
                    ):
                        last_event_time = asyncio.get_event_loop().time()

                        if event.type == AdapterEvent.TEXT:
                            text = event.text or ""
                            response_text += text
                            yield {
                                "type": SSEEventType.CONTENT,
                                "text": text,
                            }

                        elif event.type == AdapterEvent.TOOL_USE:
                            tool_call = {
                                "tool": event.tool_name,
                                "input_preview": str(event.tool_input)[:100],
                                "start_time": datetime.utcnow().isoformat(),
                            }
                            tool_calls.append(tool_call)
                            yield {
                                "type": SSEEventType.TOOL_USE,
                                "tool": event.tool_name,
                                "input": event.tool_input,
                            }

                        elif event.type == AdapterEvent.TOOL_RESULT:
                            # Update the last tool call with result
                            if tool_calls:
                                tool_calls[-1]["duration_ms"] = 0  # Could calculate
                            result_preview = str(event.tool_result or "")[:200]
                            if len(str(event.tool_result or "")) > 200:
                                result_preview += "..."
                            yield {
                                "type": SSEEventType.TOOL_RESULT,
                                "tool": event.tool_name,
                                "result": result_preview,
                            }

                        elif event.type == AdapterEvent.ERROR:
                            error_message = event.error_message
                            break

                        elif event.type == AdapterEvent.COMPLETE:
                            break

                except asyncio.TimeoutError:
                    error_message = f"Iteration {i} timed out"
                    logger.warning(f"Iteration {i} timed out after {TIMEOUT_PER_ITERATION}s")

                except Exception as e:
                    error_message = f"Error in iteration {i}: {str(e)}"
                    logger.warning(f"Error in iteration {i}: {str(e)}", exc_info=True)

                # Process iteration result
                if error_message:
                    if iteration_id:
                        self.pdb.fail_planning_iteration(iteration_id, error_message)
                    yield {
                        "type": SSEEventType.ERROR,
                        "message": error_message,
                        "iteration": i,
                    }
                    # Continue to next iteration on non-fatal errors
                    continue

                # Re-read the file to get Claude's edits
                summary = self._extract_summary(response_text)
                new_doc = ""
                if doc_file_path.exists():
                    try:
                        new_doc = doc_file_path.read_text()
                    except Exception as e:
                        logger.warning(f"Failed to read design doc file: {e}")

                if new_doc and new_doc != old_doc:
                    # Calculate diff
                    chars_added, chars_removed = self._calculate_diff(old_doc, new_doc)
                    diff_text = self._compute_unified_diff(old_doc or "", new_doc)

                    # Save the updated design doc to DB artifacts
                    self._save_design_doc(new_doc)

                    yield {
                        "type": SSEEventType.DESIGN_DOC_UPDATED,
                        "chars_added": chars_added,
                        "chars_removed": chars_removed,
                    }

                    # Complete iteration record
                    if iteration_id:
                        self.pdb.complete_planning_iteration(
                            iteration_id,
                            chars_added=chars_added,
                            chars_removed=chars_removed,
                            tool_calls=tool_calls[:10],  # Limit stored tool calls
                            summary=summary,
                            diff_text=diff_text,
                            doc_before=old_doc or "",
                            doc_after=new_doc,
                        )
                elif new_doc == old_doc and old_doc:
                    # File unchanged — Claude may not have edited it
                    # Still count as completed if no error occurred
                    if iteration_id:
                        self.pdb.complete_planning_iteration(
                            iteration_id,
                            chars_added=0,
                            chars_removed=0,
                            tool_calls=tool_calls[:10],
                            summary=summary or "No changes made",
                            diff_text="",
                            doc_before=old_doc or "",
                            doc_after=old_doc or "",
                        )
                else:
                    # No doc file at all — fallback: try extracting from response text
                    fallback_doc = self._extract_design_doc(response_text)
                    if fallback_doc:
                        self._save_design_doc(fallback_doc)
                        doc_file_path.write_text(fallback_doc)
                        chars_added, chars_removed = self._calculate_diff(old_doc, fallback_doc)
                        diff_text = self._compute_unified_diff(old_doc or "", fallback_doc)
                        yield {
                            "type": SSEEventType.DESIGN_DOC_UPDATED,
                            "chars_added": chars_added,
                            "chars_removed": chars_removed,
                        }
                        if iteration_id:
                            self.pdb.complete_planning_iteration(
                                iteration_id,
                                chars_added=chars_added,
                                chars_removed=chars_removed,
                                tool_calls=tool_calls[:10],
                                summary=summary,
                                diff_text=diff_text,
                                doc_before=old_doc or "",
                                doc_after=fallback_doc,
                            )
                    else:
                        if iteration_id:
                            self.pdb.fail_planning_iteration(
                                iteration_id,
                                "No design doc changes detected",
                            )
                        yield {
                            "type": SSEEventType.ERROR,
                            "message": "No design doc changes detected",
                            "iteration": i,
                        }
                        continue

                completed_iterations = i

                yield {
                    "type": SSEEventType.ITERATION_COMPLETE,
                    "iteration": i,
                    "iteration_id": iteration_id,
                    "summary": summary or "Updated design document",
                }

                # Update session progress
                self.pdb.update_planning_session(
                    self.session_id,
                    iterations_completed=completed_iterations,
                )

                # Cooldown between iterations (unless this is the last one)
                if i < iterations:
                    await asyncio.sleep(COOLDOWN_BETWEEN_ITERATIONS)

            # All iterations complete — mark run as completed but keep session active
            # so user can review results and explicitly complete the planning step
            self.pdb.update_planning_session(
                self.session_id,
                run_status="completed",
                iterations_completed=completed_iterations,
            )

            yield {
                "type": SSEEventType.DONE,
                "iterations_completed": completed_iterations,
            }

        except Exception as e:
            logger.error(f"Fatal error in iteration executor: {e}", exc_info=True)
            self.pdb.update_planning_session(
                self.session_id,
                run_status="error",
                error_message=str(e),  # Internal DB record keeps full error
                iterations_completed=completed_iterations,
            )
            yield {
                "type": SSEEventType.ERROR,
                "message": "Execution failed unexpectedly. Check server logs for details.",
                "fatal": True,
            }

    async def stop(self) -> None:
        """Stop any running Claude process."""
        if self._adapter:
            await self._adapter.stop()
