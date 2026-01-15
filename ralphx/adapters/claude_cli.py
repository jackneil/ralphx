"""Claude CLI adapter for RalphX.

Spawns Claude CLI as a subprocess and captures output via stream-json format.
"""

import asyncio
import json
import os
import signal
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Optional

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
    ) -> list[str]:
        """Build the claude command line.

        Args:
            model: Model identifier.
            tools: List of tool names.

        Returns:
            Command as list of strings.
        """
        # Resolve model name
        full_model = MODEL_MAP.get(model, model)

        cmd = [
            "claude",
            "-p",  # Print mode (non-interactive)
            "--model", full_model,
            "--output-format", "stream-json",  # For session tracking
        ]

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
    ) -> ExecutionResult:
        """Execute a prompt and return the result.

        Args:
            prompt: The prompt to send.
            model: Model identifier.
            tools: List of tool names.
            timeout: Timeout in seconds.

        Returns:
            ExecutionResult with output and metadata.
        """
        result = ExecutionResult(started_at=datetime.utcnow())
        text_parts = []
        tool_calls = []

        try:
            async for event in self.stream(prompt, model, tools, timeout):
                if event.type == AdapterEvent.INIT:
                    result.session_id = event.data.get("session_id")
                elif event.type == AdapterEvent.TEXT:
                    if event.text:
                        text_parts.append(event.text)
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

        return result

    async def stream(
        self,
        prompt: str,
        model: str = "sonnet",
        tools: Optional[list[str]] = None,
        timeout: int = 300,
    ) -> AsyncIterator[StreamEvent]:
        """Stream execution events from Claude CLI.

        Automatically handles credential refresh and swap for the execution.

        Args:
            prompt: The prompt to send.
            model: Model identifier.
            tools: List of tool names.
            timeout: Timeout in seconds.

        Yields:
            StreamEvent objects as execution progresses.
        """
        # Refresh token if needed (before spawning)
        if not await refresh_token_if_needed(self._project_id):
            yield StreamEvent(
                type=AdapterEvent.ERROR,
                error_message="No valid credentials. Please login via Settings.",
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
            try:
                async with asyncio.timeout(timeout):
                    if self._process.stdout:
                        async for line in self._process.stdout:
                            line_text = line.decode().strip()
                            if not line_text:
                                continue

                            try:
                                data = json.loads(line_text)
                                event = self._parse_event(data)
                                if event:
                                    yield event
                            except json.JSONDecodeError:
                                # Non-JSON output, treat as plain text
                                yield StreamEvent(
                                    type=AdapterEvent.TEXT,
                                    text=line_text,
                                )

                    # Wait for process to complete
                    await self._process.wait()

            except asyncio.TimeoutError:
                yield StreamEvent(
                    type=AdapterEvent.ERROR,
                    error_message=f"Timeout after {timeout}s",
                    error_code="TIMEOUT",
                )
                await self.stop()
                raise

            # Emit completion event
            exit_code = self._process.returncode or 0
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

        # Init message with session ID
        if msg_type == "init" or "session_id" in data:
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
        if msg_type == "assistant" and "content" in data:
            content = data["content"]
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        return StreamEvent(
                            type=AdapterEvent.TEXT,
                            text=block.get("text", ""),
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
