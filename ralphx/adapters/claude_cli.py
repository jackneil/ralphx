"""Claude CLI adapter for RalphX.

Spawns Claude CLI as a subprocess and captures output via stream-json format.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Callable, Optional

from ralphx.adapters.base import (
    AdapterEvent,
    ExecutionResult,
    LLMAdapter,
    StreamEvent,
)
from ralphx.core.auth import refresh_token_if_needed, swap_credentials_for_loop


# Model name mappings
MODEL_MAP = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
    "haiku": "claude-haiku-3-20240307",
}


class ClaudeCLIAdapter(LLMAdapter):
    """Adapter for Claude CLI (claude command).

    Features:
    - Spawns claude -p with stream-json output
    - Captures session_id from init message
    - Streams text and tool_use events
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

        # When using json_schema, we need --output-format json (not stream-json)
        # because structured_output is only in the final JSON result
        output_format = "json" if json_schema else "stream-json"

        cmd = [
            "claude",
            "-p",  # Print mode (non-interactive)
            "--verbose",  # Required when using -p with stream-json
            "--model", full_model,
            "--output-format", output_format,
        ]

        # Add JSON schema for structured output
        if json_schema:
            cmd.extend(["--json-schema", json.dumps(json_schema)])

        # Add loop-specific settings file if provided
        if self._settings_path and self._settings_path.exists():
            cmd.extend(["--settings", str(self._settings_path)])

        # Add allowed tools
        if tools:
            for tool in tools:
                cmd.extend(["--allowedTools", tool])

        return cmd

    async def execute(
        self,
        prompt: str,
        model: str = "sonnet",
        tools: Optional[list[str]] = None,
        timeout: int = 300,
        json_schema: Optional[dict] = None,
        on_session_start: Optional[Callable[[str], None]] = None,
    ) -> ExecutionResult:
        """Execute a prompt and return the result.

        Args:
            prompt: The prompt to send.
            model: Model identifier.
            tools: List of tool names.
            timeout: Timeout in seconds.
            json_schema: Optional JSON schema for structured output.

        Returns:
            ExecutionResult with output and metadata.
        """
        # When using json_schema, use dedicated non-streaming execution
        if json_schema:
            return await self._execute_with_schema(prompt, model, tools, timeout, json_schema)

        # Standard streaming execution
        import logging
        _exec_log = logging.getLogger(__name__)

        result = ExecutionResult(started_at=datetime.utcnow())
        text_parts = []
        tool_calls = []

        try:
            async for event in self.stream(prompt, model, tools, timeout):
                if event.type == AdapterEvent.INIT:
                    result.session_id = event.data.get("session_id")
                    if on_session_start and result.session_id:
                        on_session_start(result.session_id)
                elif event.type == AdapterEvent.TEXT:
                    if event.text:
                        text_parts.append(event.text)
                        _exec_log.warning(f"[EXEC] Appended text part, total parts: {len(text_parts)}")
                elif event.type == AdapterEvent.TOOL_USE:
                    tool_calls.append({
                        "name": event.tool_name,
                        "input": event.tool_input,
                    })
                elif event.type == AdapterEvent.ERROR:
                    result.error_message = event.error_message
                    result.success = False
                elif event.type == AdapterEvent.COMPLETE:
                    result.exit_code = event.data.get("exit_code", 0)

        except asyncio.TimeoutError:
            result.timeout = True
            result.success = False
            result.error_message = f"Execution timed out after {timeout}s"
            await self.stop()

        result.completed_at = datetime.utcnow()
        result.text_output = "".join(text_parts)
        result.tool_calls = tool_calls
        result.session_id = self._session_id

        _exec_log.warning(f"[EXEC] Final text_output: {len(result.text_output)} chars from {len(text_parts)} parts")
        if result.text_output:
            _exec_log.warning(f"[EXEC] text_output preview: {result.text_output[:300]}...")

        return result

    async def _execute_with_schema(
        self,
        prompt: str,
        model: str,
        tools: Optional[list[str]],
        timeout: int,
        json_schema: dict,
    ) -> ExecutionResult:
        """Execute with JSON schema for structured output.

        Uses --output-format json which returns a single JSON result
        containing structured_output.

        Args:
            prompt: The prompt to send.
            model: Model identifier.
            tools: List of tool names.
            timeout: Timeout in seconds.
            json_schema: JSON schema for structured output validation.

        Returns:
            ExecutionResult with structured_output populated.
        """
        result = ExecutionResult(started_at=datetime.utcnow())

        # Validate and refresh token
        if not await refresh_token_if_needed(self._project_id, validate=True):
            result.success = False
            result.error_message = "No valid credentials. Token may be expired."
            return result

        # Swap credentials for execution
        with swap_credentials_for_loop(self._project_id) as has_creds:
            if not has_creds:
                result.success = False
                result.error_message = "No credentials available."
                return result

            cmd = self._build_command(model, tools, json_schema)

            try:
                # Start process
                self._process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.project_path),
                )

                # Send prompt
                if self._process.stdin:
                    self._process.stdin.write(prompt.encode())
                    await self._process.stdin.drain()
                    self._process.stdin.close()
                    await self._process.stdin.wait_closed()

                # Read output with timeout
                async with asyncio.timeout(timeout):
                    stdout, stderr = await self._process.communicate()

                result.exit_code = self._process.returncode or 0
                result.completed_at = datetime.utcnow()

                # Parse JSON result
                if stdout:
                    try:
                        data = json.loads(stdout.decode())
                        result.session_id = data.get("session_id")
                        result.structured_output = data.get("structured_output")

                        # Check for errors in result
                        if data.get("is_error"):
                            result.success = False
                            result.error_message = data.get("result", "Unknown error")
                        elif data.get("subtype") == "error_max_structured_output_retries":
                            result.success = False
                            result.error_message = "Could not produce valid structured output"
                        else:
                            result.success = True

                        # Extract text from result if available
                        result.text_output = data.get("result", "")

                    except json.JSONDecodeError as e:
                        result.success = False
                        result.error_message = f"Failed to parse JSON output: {e}"

                # Handle stderr
                if stderr:
                    stderr_text = stderr.decode(errors="replace").strip()
                    if stderr_text and not result.error_message:
                        result.error_message = stderr_text[:500]

                if result.exit_code != 0 and result.success:
                    result.success = False
                    if not result.error_message:
                        result.error_message = f"Exit code {result.exit_code}"

            except asyncio.TimeoutError:
                result.timeout = True
                result.success = False
                result.error_message = f"Execution timed out after {timeout}s"
                await self.stop()

            except Exception as e:
                result.success = False
                result.error_message = str(e)

            finally:
                self._process = None

        return result

    async def stream(
        self,
        prompt: str,
        model: str = "sonnet",
        tools: Optional[list[str]] = None,
        timeout: int = 300,
        json_schema: Optional[dict] = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream execution events from Claude CLI.

        Automatically handles credential refresh and swap for the execution.

        Note: When json_schema is provided, streaming is not truly supported.
        Use execute() instead for structured output.

        Args:
            prompt: The prompt to send.
            model: Model identifier.
            tools: List of tool names.
            timeout: Timeout in seconds.
            json_schema: Optional JSON schema (not recommended for streaming).

        Yields:
            StreamEvent objects as execution progresses.
        """
        # Validate and refresh token if needed (before spawning)
        # Use validate=True to actually test the token works
        if not await refresh_token_if_needed(self._project_id, validate=True):
            yield StreamEvent(
                type=AdapterEvent.ERROR,
                error_message="No valid credentials. Token may be expired - please re-login via Settings.",
                error_code="AUTH_REQUIRED",
            )
            return

        # Swap credentials for this execution
        with swap_credentials_for_loop(self._project_id) as has_creds:
            if not has_creds:
                yield StreamEvent(
                    type=AdapterEvent.ERROR,
                    error_message="No credentials available. Please login via Settings.",
                    error_code="AUTH_REQUIRED",
                )
                return

            cmd = self._build_command(model, tools)

            # Start the process
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_path),
            )

            # Send the prompt
            if self._process.stdin:
                self._process.stdin.write(prompt.encode())
                await self._process.stdin.drain()
                self._process.stdin.close()
                await self._process.stdin.wait_closed()

            # Read output with timeout
            # Note: We read stderr concurrently with stdout to avoid deadlock
            # if stderr buffer fills before stdout completes
            stderr_content = []
            stderr_task = None

            async def drain_stderr():
                """Read stderr in background to prevent buffer deadlock."""
                chunks = []
                if self._process and self._process.stderr:
                    # Read in chunks with a max total size limit (1MB)
                    max_size = 1024 * 1024
                    total = 0
                    while total < max_size:
                        chunk = await self._process.stderr.read(8192)
                        if not chunk:
                            break
                        chunks.append(chunk)
                        total += len(chunk)
                return b"".join(chunks)

            try:
                async with asyncio.timeout(timeout):
                    # Start stderr drain early to prevent buffer deadlock
                    if self._process.stderr:
                        stderr_task = asyncio.create_task(drain_stderr())

                    if self._process.stdout:
                        import logging
                        _stream_log = logging.getLogger(__name__)
                        line_count = 0
                        text_events = 0
                        async for line in self._process.stdout:
                            line_count += 1
                            try:
                                line_text = line.decode(errors="replace").strip()
                            except Exception:
                                continue  # Skip lines that can't be decoded
                            if not line_text:
                                continue

                            try:
                                data = json.loads(line_text)
                                msg_type = data.get("type", "unknown")
                                _stream_log.warning(f"[STREAM] Line {line_count}: type={msg_type}")

                                event = self._parse_event(data)
                                if event:
                                    if event.type == AdapterEvent.TEXT:
                                        text_events += 1
                                        text_preview = (event.text or "")[:80].replace("\n", "\\n")
                                        _stream_log.warning(f"[STREAM] TEXT #{text_events}: {len(event.text or '')} chars, preview: {text_preview}")
                                    yield event
                            except json.JSONDecodeError:
                                # Non-JSON output, treat as plain text
                                yield StreamEvent(
                                    type=AdapterEvent.TEXT,
                                    text=line_text,
                                )
                        _stream_log.warning(f"[STREAM] Done: {line_count} lines, {text_events} TEXT events")

                    # Wait for process to complete
                    await self._process.wait()

                    # Collect stderr result
                    if stderr_task:
                        stderr_data = await stderr_task
                        if stderr_data:
                            stderr_content.append(stderr_data.decode(errors="replace").strip())

            except asyncio.TimeoutError:
                # Cancel stderr task if still running
                if stderr_task and not stderr_task.done():
                    stderr_task.cancel()
                    try:
                        await stderr_task
                    except asyncio.CancelledError:
                        pass
                yield StreamEvent(
                    type=AdapterEvent.ERROR,
                    error_message=f"Timeout after {timeout}s",
                    error_code="TIMEOUT",
                )
                await self.stop()
                raise

            # Emit error if non-zero exit code or stderr content
            exit_code = self._process.returncode or 0
            if exit_code != 0 or stderr_content:
                stderr_text = "\n".join(stderr_content)
                error_msg = f"Claude CLI error (exit {exit_code})"
                if stderr_text:
                    # Truncate stderr to 500 chars with indicator
                    truncated = stderr_text[:500]
                    if len(stderr_text) > 500:
                        truncated += "... [truncated]"
                    error_msg = f"{error_msg}: {truncated}"
                yield StreamEvent(
                    type=AdapterEvent.ERROR,
                    error_message=error_msg,
                    error_code=f"EXIT_{exit_code}",
                )

            # Emit completion event
            yield StreamEvent(
                type=AdapterEvent.COMPLETE,
                data={"exit_code": exit_code, "session_id": self._session_id},
            )

            self._process = None

    def _parse_event(self, data: dict) -> Optional[StreamEvent]:
        """Parse a stream-json event into a StreamEvent.

        Args:
            data: Parsed JSON data from stdout.

        Returns:
            StreamEvent or None if not recognized.
        """
        msg_type = data.get("type")

        # Init message with session ID (only for system/init events)
        if msg_type in ("init", "system"):
            self._session_id = data.get("session_id")
            return StreamEvent(
                type=AdapterEvent.INIT,
                data={"session_id": self._session_id},
            )

        # Content block events
        if msg_type == "content_block_delta":
            delta = data.get("delta", {})
            delta_type = delta.get("type")

            if delta_type == "text_delta":
                return StreamEvent(
                    type=AdapterEvent.TEXT,
                    text=delta.get("text", ""),
                )

            if delta_type == "input_json_delta":
                # Tool input being streamed
                return None  # Accumulate in content_block_stop

        if msg_type == "content_block_start":
            content_block = data.get("content_block", {})
            if content_block.get("type") == "tool_use":
                return StreamEvent(
                    type=AdapterEvent.TOOL_USE,
                    tool_name=content_block.get("name"),
                    tool_input=content_block.get("input", {}),
                )

        # Tool result (from Claude Code's output)
        if msg_type == "tool_result":
            return StreamEvent(
                type=AdapterEvent.TOOL_RESULT,
                tool_name=data.get("name"),
                tool_result=data.get("result"),
            )

        # Error events
        if msg_type == "error":
            return StreamEvent(
                type=AdapterEvent.ERROR,
                error_message=data.get("message", "Unknown error"),
                error_code=data.get("code"),
            )

        # Assistant message with content
        # Claude Code stream-json format: {"type": "assistant", "message": {"content": [...]}}
        if msg_type == "assistant":
            message = data.get("message", {})
            content = message.get("content") or data.get("content")
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        return StreamEvent(
                            type=AdapterEvent.TEXT,
                            text=block.get("text", ""),
                        )

        # Result event contains the complete output (final message)
        if msg_type == "result":
            result_text = data.get("result", "")
            if result_text:
                return StreamEvent(
                    type=AdapterEvent.TEXT,
                    text=result_text,
                )

        # Message completion
        if msg_type == "message_stop":
            return StreamEvent(
                type=AdapterEvent.COMPLETE,
                data={"session_id": self._session_id},
            )

        return None

    @staticmethod
    def is_available() -> bool:
        """Check if Claude CLI is available.

        Returns:
            True if claude command is found in PATH.
        """
        import shutil
        return shutil.which("claude") is not None

    @staticmethod
    async def check_auth() -> bool:
        """Check if Claude CLI is authenticated.

        Returns:
            True if authenticated.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            return proc.returncode == 0
        except Exception:
            return False
