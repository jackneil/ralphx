"""Claude CLI adapter for RalphX.

Spawns Claude CLI as a subprocess and streams events via JSONL session file tailing.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Callable, Optional

logger = logging.getLogger(__name__)

from ralphx.adapters.base import (
    AdapterEvent,
    ExecutionResult,
    LLMAdapter,
    StreamEvent,
)
from ralphx.core.auth import refresh_account_token
from ralphx.core.database import Database

# Rate limit detection patterns for 429 errors
RATE_LIMIT_PATTERNS = ["429", "rate limit", "overloaded", "rate_limit_error", "too many requests"]


# Model name mappings
MODEL_MAP = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
    "haiku": "claude-haiku-3-20240307",
}


class ClaudeCLIAdapter(LLMAdapter):
    """Adapter for Claude CLI (claude command).

    Features:
    - Spawns claude -p with json output
    - Streams events by tailing the JSONL session file Claude writes
    - Captures session_id from queue-operation event
    - Streams text, thinking, tool_use, tool_result, and usage events
    - Handles timeouts and signals
    - Supports per-loop Claude Code settings files
    """

    def __init__(
        self,
        project_path: Path,
        settings_path: Optional[Path] = None,
        project_id: Optional[str] = None,
    ):
        """Initialize the Claude CLI adapter.

        Args:
            project_path: Path to the project directory.
            settings_path: Optional path to Claude Code settings.json file.
                          If provided, will be passed via --settings flag.
            project_id: Optional project ID for credential lookup.
                       If provided, will use project-scoped credentials.
        """
        super().__init__(project_path)
        self._process: Optional[asyncio.subprocess.Process] = None
        self._session_id: Optional[str] = None
        self._settings_path = settings_path
        self._project_id = project_id
        self._structured_output: Optional[dict] = None
        self._final_result_text: str = ""
        self._is_rate_limited: bool = False

    @property
    def is_running(self) -> bool:
        """Check if Claude is currently running."""
        return self._process is not None and self._process.returncode is None

    async def stop(self) -> None:
        """Stop the current Claude process if running."""
        if self._process and self._process.returncode is None:
            # Send SIGTERM first for graceful shutdown
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                # Force kill if it doesn't stop
                self._process.kill()
                await self._process.wait()
            self._process = None

    def _build_command(
        self,
        model: str,
        tools: Optional[list[str]] = None,
        json_schema: Optional[dict] = None,
    ) -> list[str]:
        """Build the claude command line.

        Args:
            model: Model identifier.
            tools: List of tool names.
            json_schema: Optional JSON schema for structured output.

        Returns:
            Command as list of strings.
        """
        # Resolve model name
        full_model = MODEL_MAP.get(model, model)

        # Always use json output format — we stream via JSONL file tailing,
        # stdout is only used for final metadata (cost, structured_output)
        cmd = [
            "claude",
            "-p",  # Print mode (non-interactive)
            "--model", full_model,
            "--output-format", "json",
        ]

        # Add JSON schema for structured output
        if json_schema:
            cmd.extend(["--json-schema", json.dumps(json_schema)])

        # Add loop-specific settings file if provided
        if self._settings_path and self._settings_path.exists():
            cmd.extend(["--settings", str(self._settings_path)])

        # Configure available tools
        # --tools specifies which built-in tools are available
        # --allowedTools is for fine-grained permission patterns like Bash(git:*)
        # Three-way semantics:
        #   tools=None  → omit --tools flag → Claude uses all default tools
        #   tools=[]    → --tools "" → explicitly disable all tools
        #   tools=[...] → --tools "Read,Glob" → only listed tools
        if tools is not None:
            if tools:
                cmd.extend(["--tools", ",".join(tools)])
            else:
                cmd.extend(["--tools", ""])

        return cmd

    async def execute(
        self,
        prompt: str,
        model: str = "sonnet",
        tools: Optional[list[str]] = None,
        timeout: int = 300,
        json_schema: Optional[dict] = None,
        on_session_start: Optional[Callable[[str], None]] = None,
        on_event: Optional[Callable[[StreamEvent], None]] = None,
        account_id: Optional[int] = None,
    ) -> ExecutionResult:
        """Execute a prompt and return the result.

        Streams events via JSONL file tailing for all execution modes.
        Structured output (json_schema) is extracted from stdout JSON after completion.
        """
        # Reset per-execution state
        self._structured_output = None
        self._final_result_text = ""
        self._is_rate_limited = False

        result = ExecutionResult(started_at=datetime.utcnow())
        text_parts = []
        tool_calls = []

        try:
            async for event in self.stream(prompt, model, tools, timeout, json_schema, account_id=account_id):
                if event.type == AdapterEvent.INIT:
                    result.session_id = event.data.get("session_id")
                    if on_session_start and result.session_id:
                        on_session_start(result.session_id)
                elif event.type == AdapterEvent.TEXT:
                    if event.text:
                        text_parts.append(event.text)
                elif event.type == AdapterEvent.TOOL_USE:
                    tool_calls.append({
                        "name": event.tool_name,
                        "input": event.tool_input,
                    })
                elif event.type == AdapterEvent.THINKING:
                    pass  # Don't aggregate thinking into text_output
                elif event.type == AdapterEvent.USAGE:
                    pass  # Usage tracked via on_event callback
                elif event.type == AdapterEvent.ERROR:
                    result.error_message = event.error_message
                    result.success = False
                elif event.type == AdapterEvent.COMPLETE:
                    result.exit_code = event.data.get("exit_code", 0)

                # Fire on_event callback for event persistence
                if on_event:
                    on_event(event)

        except asyncio.TimeoutError:
            result.timeout = True
            result.success = False
            result.error_message = f"Execution timed out after {timeout}s"
            if on_event:
                on_event(StreamEvent(
                    type=AdapterEvent.ERROR,
                    error_message=result.error_message,
                    error_code="TIMEOUT",
                ))
            await self.stop()

        result.completed_at = datetime.utcnow()
        result.text_output = "".join(text_parts)
        result.tool_calls = tool_calls
        result.session_id = self._session_id

        # Pick up structured output and final result text from stream()'s stdout parsing
        result.structured_output = self._structured_output
        if not result.text_output and self._final_result_text:
            result.text_output = self._final_result_text

        # Propagate rate limit detection from stream
        result.is_rate_limited = self._is_rate_limited

        return result

    async def stream(
        self,
        prompt: str,
        model: str = "sonnet",
        tools: Optional[list[str]] = None,
        timeout: int = 300,
        json_schema: Optional[dict] = None,
        account_id: Optional[int] = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream execution events by tailing Claude's JSONL session file.

        Instead of parsing stdout (stream-json format), we:
        1. Resolve account and get fresh access token
        2. Spawn Claude CLI with CLAUDE_CODE_OAUTH_TOKEN env var
        3. Discover the JSONL session file Claude creates
        4. Tail that file for real-time events (richer than stdout)
        5. Read stdout after completion for final metadata

        Yields:
            StreamEvent objects as execution progresses.
        """
        # Reset session state
        self._session_id = None
        self._structured_output = None
        self._final_result_text = ""
        self._is_rate_limited = False

        # Resolve account — explicit account_id overrides project default
        db = Database()
        if account_id:
            account = db.get_account(account_id)
        else:
            account = db.get_effective_account(self._project_id)

        if not account:
            yield StreamEvent(
                type=AdapterEvent.ERROR,
                error_message="No account available. Please login via Settings.",
                error_code="AUTH_REQUIRED",
            )
            return

        # Get fresh access token, refreshing via OAuth if expired
        access_token = await refresh_account_token(account["id"])
        if not access_token:
            yield StreamEvent(
                type=AdapterEvent.ERROR,
                error_message=f"Token expired for {account.get('email', 'unknown')}. Please re-login via Settings.",
                error_code="AUTH_REQUIRED",
            )
            return

        # Build subprocess env — CLAUDE_CODE_OAUTH_TOKEN completely overrides creds file
        # No file swapping, no locking — each subprocess has its own isolated environment
        proc_env = {**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": access_token}

        # Compute session directory for JSONL file discovery
        normalized = str(self.project_path).replace("/", "-")
        session_dir = Path.home() / ".claude" / "projects" / normalized

        # Snapshot existing session files before spawn
        existing_files: set[str] = set()
        if session_dir.exists():
            existing_files = {
                f.name for f in session_dir.iterdir() if f.suffix == ".jsonl"
            }

        cmd = self._build_command(model, tools, json_schema)

        # Start the process with account token via env var
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.project_path),
            limit=4 * 1024 * 1024,  # 4MB buffer
            env=proc_env,
        )

        # Send the prompt
        if self._process.stdin:
            self._process.stdin.write(prompt.encode())
            await self._process.stdin.drain()
            self._process.stdin.close()
            await self._process.stdin.wait_closed()

        # Drain stdout/stderr in background to prevent pipe deadlock
        stdout_task = asyncio.create_task(
            self._drain_pipe(self._process.stdout)
        )
        stderr_task = asyncio.create_task(
            self._drain_pipe(self._process.stderr)
        )

        # Discover the new JSONL session file
        session_file = await self._discover_session_file(
            session_dir, existing_files, max_wait=15
        )

        if not session_file:
            # Process may have died before creating session file
            await self._process.wait()
            stdout_task.cancel()
            stderr_data = await stderr_task
            stderr_text = stderr_data.decode(errors="replace").strip() if stderr_data else ""
            # Check if this was a rate limit error before session file creation
            if any(p in stderr_text.lower() for p in RATE_LIMIT_PATTERNS):
                self._is_rate_limited = True
            yield StreamEvent(
                type=AdapterEvent.ERROR,
                error_message=f"Could not find session file. stderr: {stderr_text[:500]}",
                error_code="RATE_LIMITED" if self._is_rate_limited else "NO_SESSION_FILE",
            )
            yield StreamEvent(
                type=AdapterEvent.COMPLETE,
                data={"exit_code": self._process.returncode or 1},
            )
            self._process = None
            return

        # Tail the JSONL file for streaming events
        async for event in self._tail_session_file(session_file, timeout):
            yield event

        # Wait for process to complete
        await self._process.wait()

        # Collect stdout/stderr
        stdout_data = await stdout_task
        stderr_data = await stderr_task

        # Parse stdout JSON for final metadata
        exit_code = self._process.returncode or 0
        completion_data: dict = {
            "exit_code": exit_code,
            "session_id": self._session_id,
        }

        if stdout_data:
            try:
                final = json.loads(stdout_data.decode())
                completion_data["cost_usd"] = final.get("cost_usd")
                completion_data["num_turns"] = final.get("num_turns")
                self._structured_output = final.get("structured_output")
                self._final_result_text = final.get("result", "")

                # Check for errors in final result (Layer 3: stdout JSON)
                if final.get("is_error"):
                    result_text = final.get("result", "")
                    if any(p in result_text.lower() for p in RATE_LIMIT_PATTERNS):
                        self._is_rate_limited = True
                    yield StreamEvent(
                        type=AdapterEvent.ERROR,
                        error_message=result_text or "Unknown error",
                        error_code="RATE_LIMITED" if self._is_rate_limited else "CLI_ERROR",
                    )
                elif final.get("subtype") == "error_max_structured_output_retries":
                    yield StreamEvent(
                        type=AdapterEvent.ERROR,
                        error_message="Could not produce valid structured output",
                        error_code="STRUCTURED_OUTPUT_FAILED",
                    )
            except json.JSONDecodeError:
                pass

        # Emit error for non-zero exit or stderr (Layer 2: stderr)
        if exit_code != 0:
            stderr_text = stderr_data.decode(errors="replace").strip() if stderr_data else ""
            if stderr_text:
                if any(p in stderr_text.lower() for p in RATE_LIMIT_PATTERNS):
                    self._is_rate_limited = True
                logger.warning(f"Claude CLI exit code: {exit_code}, stderr: {stderr_text[:500]}")
                yield StreamEvent(
                    type=AdapterEvent.ERROR,
                    error_message=f"Claude CLI error (exit {exit_code}): {stderr_text[:500]}",
                    error_code="RATE_LIMITED" if self._is_rate_limited else f"EXIT_{exit_code}",
                )

        # Emit completion
        yield StreamEvent(
            type=AdapterEvent.COMPLETE,
            data=completion_data,
        )

        self._process = None

    # ========== JSONL File Tailing Helpers ==========

    async def _discover_session_file(
        self,
        session_dir: Path,
        existing_files: set[str],
        max_wait: float = 15,
    ) -> Optional[Path]:
        """Poll directory for a new .jsonl session file created by Claude CLI.

        Args:
            session_dir: Directory where Claude stores session files.
            existing_files: Set of filenames that existed before process spawn.
            max_wait: Maximum seconds to wait for file to appear.

        Returns:
            Path to new session file, or None if not found.
        """
        start = time.time()
        while time.time() - start < max_wait:
            if session_dir.exists():
                try:
                    current = {
                        f.name for f in session_dir.iterdir() if f.suffix == ".jsonl"
                    }
                    new_files = current - existing_files
                    if new_files:
                        # Return the newest file by modification time
                        newest = max(
                            new_files,
                            key=lambda f: (session_dir / f).stat().st_mtime,
                        )
                        return session_dir / newest
                except OSError:
                    pass  # Directory listing failed, retry

            # Check if process already exited before creating a file
            if self._process and self._process.returncode is not None:
                return None

            await asyncio.sleep(0.2)

        return None

    async def _tail_session_file(
        self,
        session_file: Path,
        timeout: int,
    ) -> AsyncIterator[StreamEvent]:
        """Tail a JSONL session file, yielding StreamEvents.

        Reads new lines as they're written by Claude CLI.
        Stops when the process exits and all remaining lines are read.

        Args:
            session_file: Path to the .jsonl file.
            timeout: Timeout in seconds for the overall execution.

        Yields:
            StreamEvent objects parsed from JSONL lines.
        """
        position = 0
        last_event_time = time.time()
        meaningful_timeout = min(max(timeout - 30, 60), 270)

        while True:
            # Check if process has exited
            process_done = (
                self._process is not None
                and self._process.returncode is not None
            )

            # Read new content from file
            try:
                size = session_file.stat().st_size
            except FileNotFoundError:
                break

            if size > position:
                try:
                    with open(session_file, "r") as f:
                        f.seek(position)
                        new_content = f.read()
                        position = f.tell()
                except (IOError, PermissionError):
                    break

                for line in new_content.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        for event in self._parse_jsonl_event(data):
                            if event.type in (
                                AdapterEvent.TEXT,
                                AdapterEvent.TOOL_USE,
                                AdapterEvent.TOOL_RESULT,
                                AdapterEvent.THINKING,
                                AdapterEvent.INIT,
                            ):
                                last_event_time = time.time()
                            yield event
                    except json.JSONDecodeError:
                        continue

            if process_done:
                # Final read to catch any remaining lines
                try:
                    final_size = session_file.stat().st_size
                    if final_size > position:
                        with open(session_file, "r") as f:
                            f.seek(position)
                            remaining = f.read()
                        for line in remaining.split("\n"):
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                                for event in self._parse_jsonl_event(data):
                                    yield event
                            except json.JSONDecodeError:
                                continue
                except (FileNotFoundError, IOError):
                    pass
                break

            # Check meaningful event timeout
            if time.time() - last_event_time > meaningful_timeout:
                yield StreamEvent(
                    type=AdapterEvent.ERROR,
                    error_message=f"No meaningful output for {meaningful_timeout}s",
                    error_code="TIMEOUT",
                )
                break

            await asyncio.sleep(0.1)

    def _parse_jsonl_event(self, data: dict) -> list[StreamEvent]:
        """Parse a session JSONL line into StreamEvent(s).

        Claude's session JSONL format uses full message objects:
        - queue-operation: Session start (contains sessionId)
        - assistant: Claude's response (text, thinking, tool_use blocks + usage)
        - user: User messages and tool results

        Args:
            data: Parsed JSON data from a JSONL line.

        Returns:
            List of StreamEvents (may be empty for unrecognized events).
        """
        events: list[StreamEvent] = []
        event_type = data.get("type")

        # Session start — first line of every session file
        if event_type == "queue-operation":
            self._session_id = data.get("sessionId")
            events.append(StreamEvent(
                type=AdapterEvent.INIT,
                data={"session_id": self._session_id},
            ))
            return events

        # Assistant message — may contain text, thinking, tool_use blocks
        if event_type == "assistant":
            message = data.get("message", {})
            content_blocks = message.get("content", [])
            usage = message.get("usage")
            is_error = data.get("isApiErrorMessage", False)

            if is_error:
                error_text = ""
                if isinstance(content_blocks, list):
                    for block in content_blocks:
                        if block.get("type") == "text":
                            error_text = block.get("text", "")
                # Layer 1: Detect rate limiting from JSONL API error messages
                if any(p in (error_text or "").lower() for p in RATE_LIMIT_PATTERNS):
                    self._is_rate_limited = True
                events.append(StreamEvent(
                    type=AdapterEvent.ERROR,
                    error_message=error_text or data.get("error", "API error"),
                    error_code="RATE_LIMITED" if self._is_rate_limited else data.get("error"),
                ))
                return events

            if isinstance(content_blocks, list):
                for block in content_blocks:
                    block_type = block.get("type")
                    if block_type == "thinking":
                        thinking_text = block.get("thinking", "")
                        if thinking_text:
                            events.append(StreamEvent(
                                type=AdapterEvent.THINKING,
                                thinking=thinking_text,
                            ))
                    elif block_type == "text":
                        text = block.get("text", "")
                        if text:
                            events.append(StreamEvent(
                                type=AdapterEvent.TEXT,
                                text=text,
                            ))
                    elif block_type == "tool_use":
                        events.append(StreamEvent(
                            type=AdapterEvent.TOOL_USE,
                            tool_name=block.get("name"),
                            tool_input=block.get("input"),
                        ))

            # Emit usage data if present
            if usage:
                events.append(StreamEvent(
                    type=AdapterEvent.USAGE,
                    usage=usage,
                ))

            return events

        # User message — may contain tool results
        if event_type == "user":
            message = data.get("message", {})
            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        result_text = block.get("content", "")
                        events.append(StreamEvent(
                            type=AdapterEvent.TOOL_RESULT,
                            tool_name=None,
                            tool_result=str(result_text)[:1000],
                        ))

            return events

        return events  # Ignore unrecognized event types

    async def _drain_pipe(self, pipe) -> bytes:
        """Read all data from a subprocess pipe without parsing.

        Used to drain stdout/stderr in background to prevent pipe buffer deadlock.

        Args:
            pipe: asyncio subprocess pipe (stdout or stderr).

        Returns:
            All bytes read from the pipe.
        """
        if not pipe:
            return b""
        chunks = []
        max_size = 4 * 1024 * 1024  # 4MB max
        total = 0
        while total < max_size:
            chunk = await pipe.read(8192)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        return b"".join(chunks)

    def build_run_marker(
        self,
        run_id: str,
        project_slug: str,
        iteration: int,
        mode: str,
    ) -> str:
        """Build the run tracking marker to inject into prompts.

        This marker is placed at the END of prompts to track which
        session belongs to which run.

        Args:
            run_id: The run identifier.
            project_slug: Project slug.
            iteration: Current iteration number.
            mode: Current mode name.

        Returns:
            Marker string to append to prompt.
        """
        now = datetime.utcnow().isoformat()
        # Sanitize values to prevent HTML comment injection (e.g., --> in mode name)
        safe_run_id = run_id.replace("--", "").replace('"', "")
        safe_slug = project_slug.replace("--", "").replace('"', "")
        safe_mode = mode.replace("--", "").replace('"', "")
        return f"""

<!-- RALPHX_TRACKING run_id="{safe_run_id}" project="{safe_slug}" iteration={iteration} mode="{safe_mode}" ts="{now}" -->"""
