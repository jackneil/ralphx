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

        # Configure available tools
        # --tools specifies which built-in tools are available
        # --allowedTools is for fine-grained permission patterns like Bash(git:*)
        if tools:
            # Enable specific tools
            cmd.extend(["--tools", ",".join(tools)])
        else:
            # Disable all built-in tools to prevent Claude from trying to use them
            # Without this, Claude may try to use Read/Edit/etc and hit API errors
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
            return await self._execute_with_schema(
                prompt, model, tools, timeout, json_schema,
                on_session_start=on_session_start, on_event=on_event,
            )

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
        on_session_start: Optional[Callable[[str], None]] = None,
        on_event: Optional[Callable[[StreamEvent], None]] = None,
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

                        # Fire callbacks for event persistence
                        if on_session_start and result.session_id:
                            on_session_start(result.session_id)
                        if on_event:
                            # Save metadata about the execution
                            on_event(StreamEvent(
                                type=AdapterEvent.INIT,
                                data={
                                    "session_id": result.session_id,
                                    "num_turns": data.get("num_turns"),
                                    "cost_usd": data.get("cost_usd"),
                                    "is_error": data.get("is_error"),
                                },
                            ))
                            # Save the result text
                            if result.text_output:
                                on_event(StreamEvent(
                                    type=AdapterEvent.TEXT,
                                    text=result.text_output,
                                ))
                            # Save completion/error
                            if result.success:
                                on_event(StreamEvent(type=AdapterEvent.COMPLETE))
                            elif result.error_message:
                                on_event(StreamEvent(
                                    type=AdapterEvent.ERROR,
                                    error_message=result.error_message,
                                ))

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
        # Reset session_id to prevent stale values from previous executions
        # leaking into results when the new execution fails before INIT
        self._session_id = None

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

            # Log the exact command for debugging concurrency issues
            import logging
            _cli_log = logging.getLogger(__name__)
            _cli_log.warning(f"[CLAUDE_CLI] Running command: {' '.join(cmd)}")
            _cli_log.warning(f"[CLAUDE_CLI] Working dir: {self.project_path}")
            _cli_log.warning(f"[CLAUDE_CLI] Tools: {tools}")
            _cli_log.warning(f"[CLAUDE_CLI] Prompt length: {len(prompt)} chars")
            _cli_log.warning(f"[CLAUDE_CLI] Prompt preview: {prompt[:500]}...")

            # Start the process
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_path),
                limit=4 * 1024 * 1024,  # 4MB buffer for large JSON lines (e.g. Edit tool inputs)
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
                # Start stderr drain early to prevent buffer deadlock
                if self._process.stderr:
                    stderr_task = asyncio.create_task(drain_stderr())

                if self._process.stdout:
                    import logging
                    import time
                    _stream_log = logging.getLogger(__name__)
                    line_count = 0
                    text_events = 0

                    # Two timeout strategies:
                    # 1. line_timeout: Max time to wait for ANY output (prevents deadlock)
                    # 2. meaningful_timeout: Max time since last meaningful event (TEXT/TOOL_USE/TOOL_RESULT)
                    line_timeout = 30  # 30s max wait for any line
                    meaningful_timeout = min(max(timeout - 30, 60), 270)  # Scale with timeout param, min 60s, max 4.5 min
                    last_meaningful_time = time.time()

                    async def read_line_with_timeout():
                        """Read a line with timeout."""
                        return await asyncio.wait_for(
                            self._process.stdout.readline(),
                            timeout=line_timeout
                        )

                    while True:
                        # Check meaningful event timeout
                        time_since_meaningful = time.time() - last_meaningful_time
                        if time_since_meaningful > meaningful_timeout:
                            _stream_log.warning(f"[STREAM] Meaningful event timeout after {time_since_meaningful:.0f}s")
                            raise asyncio.TimeoutError(f"No meaningful output for {meaningful_timeout}s")

                        try:
                            line = await read_line_with_timeout()
                            if not line:  # EOF
                                break
                        except asyncio.TimeoutError:
                            # Check if it's been too long since meaningful event
                            time_since_meaningful = time.time() - last_meaningful_time
                            if time_since_meaningful > meaningful_timeout:
                                _stream_log.warning(f"[STREAM] Meaningful event timeout after {time_since_meaningful:.0f}s")
                                raise
                            # Otherwise keep waiting - Claude might be working on a tool
                            _stream_log.info(f"[STREAM] No line for {line_timeout}s, but meaningful event was {time_since_meaningful:.0f}s ago, continuing...")
                            continue

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
                            # Log full event structure for debugging
                            _stream_log.warning(f"[STREAM] Line {line_count}: type={msg_type}, keys={list(data.keys())}")
                            if msg_type not in ("content_block_delta", "text"):
                                _stream_log.warning(f"[STREAM] Full event: {json.dumps(data)[:500]}")

                            # Parse events (may return multiple for assistant messages with multiple blocks)
                            for event in self._parse_events(data):
                                # Reset meaningful timeout on actual content
                                if event.type in (AdapterEvent.TEXT, AdapterEvent.TOOL_USE, AdapterEvent.TOOL_RESULT, AdapterEvent.INIT):
                                    last_meaningful_time = time.time()

                                if event.type == AdapterEvent.TEXT:
                                    text_events += 1
                                    text_preview = (event.text or "")[:80].replace("\n", "\\n")
                                    _stream_log.warning(f"[STREAM] TEXT #{text_events}: {len(event.text or '')} chars, preview: {text_preview}")
                                elif event.type == AdapterEvent.TOOL_USE:
                                    _stream_log.warning(f"[STREAM] TOOL_USE: {event.tool_name}")
                                yield event
                        except json.JSONDecodeError:
                            # Non-JSON output, treat as plain text
                            last_meaningful_time = time.time()  # Plain text is meaningful
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
                    error_message="Stream timed out - no response for too long",
                    error_code="TIMEOUT",
                )
                await self.stop()
                return  # Don't re-raise - we handled it by yielding ERROR

            # Emit error if non-zero exit code or stderr content
            exit_code = self._process.returncode or 0
            if exit_code != 0 or stderr_content:
                stderr_text = "\n".join(stderr_content)
                # Log full stderr for debugging (before truncation)
                _cli_log.warning(f"[CLAUDE_CLI] Exit code: {exit_code}")
                _cli_log.warning(f"[CLAUDE_CLI] Full stderr ({len(stderr_text)} chars): {stderr_text}")
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

    def _parse_events(self, data: dict) -> list[StreamEvent]:
        """Parse a stream-json event into StreamEvent(s).

        Args:
            data: Parsed JSON data from stdout.

        Returns:
            List of StreamEvents (may be empty if not recognized).
        """
        events = []
        msg_type = data.get("type")

        # Init message with session ID (only for system/init events)
        if msg_type in ("init", "system"):
            self._session_id = data.get("session_id")
            events.append(StreamEvent(
                type=AdapterEvent.INIT,
                data={"session_id": self._session_id},
            ))
            return events

        # Content block events (streaming API format)
        if msg_type == "content_block_delta":
            delta = data.get("delta", {})
            delta_type = delta.get("type")

            if delta_type == "text_delta":
                events.append(StreamEvent(
                    type=AdapterEvent.TEXT,
                    text=delta.get("text", ""),
                ))

            return events

        if msg_type == "content_block_start":
            content_block = data.get("content_block", {})
            if content_block.get("type") == "tool_use":
                events.append(StreamEvent(
                    type=AdapterEvent.TOOL_USE,
                    tool_name=content_block.get("name"),
                    tool_input=content_block.get("input", {}),
                ))
            return events

        # Tool result (from Claude Code's output)
        if msg_type == "tool_result":
            events.append(StreamEvent(
                type=AdapterEvent.TOOL_RESULT,
                tool_name=data.get("name"),
                tool_result=data.get("result"),
            ))
            return events

        # Error events
        if msg_type == "error":
            events.append(StreamEvent(
                type=AdapterEvent.ERROR,
                error_message=data.get("message", "Unknown error"),
                error_code=data.get("code"),
            ))
            return events

        # Assistant message with content
        # Claude Code stream-json format: {"type": "assistant", "message": {"content": [...]}}
        # Can contain multiple content blocks (text, tool_use, etc.) - emit ALL of them
        if msg_type == "assistant":
            message = data.get("message", {})
            content = message.get("content") or data.get("content")
            if isinstance(content, list):
                for block in content:
                    block_type = block.get("type")
                    if block_type == "tool_use":
                        events.append(StreamEvent(
                            type=AdapterEvent.TOOL_USE,
                            tool_name=block.get("name"),
                            tool_input=block.get("input", {}),
                        ))
                    elif block_type == "text":
                        text = block.get("text", "")
                        if text:  # Only emit non-empty text
                            events.append(StreamEvent(
                                type=AdapterEvent.TEXT,
                                text=text,
                            ))
            return events

        # Tool result from Claude CLI (sent as user message with nested tool_result blocks)
        if msg_type == "user":
            message = data.get("message", {})
            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        result_text = block.get("content", "")
                        events.append(StreamEvent(
                            type=AdapterEvent.TOOL_RESULT,
                            tool_name=None,
                            tool_result=str(result_text)[:500],
                        ))
            return events

        # Result event contains the complete output (final message)
        # Don't duplicate - the assistant message already has the text
        if msg_type == "result":
            # Only emit if we haven't seen any text yet (edge case)
            pass

        # Message completion
        if msg_type == "message_stop":
            events.append(StreamEvent(
                type=AdapterEvent.COMPLETE,
                data={"session_id": self._session_id},
            ))
            return events

        return events

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
