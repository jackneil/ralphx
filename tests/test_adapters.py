"""Tests for RalphX LLM adapters."""

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ralphx.adapters import (
    AdapterEvent,
    ClaudeCLIAdapter,
    ExecutionResult,
    LLMAdapter,
    StreamEvent,
)
from ralphx.adapters.base import LLMAdapter


class TestStreamEvent:
    """Test StreamEvent dataclass."""

    def test_create_text_event(self):
        """Test creating a text event."""
        event = StreamEvent(
            type=AdapterEvent.TEXT,
            text="Hello world",
        )
        assert event.type == AdapterEvent.TEXT
        assert event.text == "Hello world"

    def test_create_tool_use_event(self):
        """Test creating a tool use event."""
        event = StreamEvent(
            type=AdapterEvent.TOOL_USE,
            tool_name="Read",
            tool_input={"file_path": "/test.py"},
        )
        assert event.type == AdapterEvent.TOOL_USE
        assert event.tool_name == "Read"

    def test_create_error_event(self):
        """Test creating an error event."""
        event = StreamEvent(
            type=AdapterEvent.ERROR,
            error_message="Something went wrong",
            error_code="API_ERROR",
        )
        assert event.type == AdapterEvent.ERROR
        assert event.error_message == "Something went wrong"


class TestExecutionResult:
    """Test ExecutionResult dataclass."""

    def test_duration_calculation(self):
        """Test duration calculation."""
        started = datetime(2026, 1, 13, 10, 0, 0)
        completed = datetime(2026, 1, 13, 10, 0, 30)

        result = ExecutionResult(
            started_at=started,
            completed_at=completed,
        )
        assert result.duration_seconds == 30.0

    def test_duration_none_when_incomplete(self):
        """Test duration is None when not completed."""
        result = ExecutionResult(started_at=datetime.utcnow())
        assert result.duration_seconds is None


class TestLLMAdapterBase:
    """Test LLMAdapter base class."""

    def test_build_run_marker(self):
        """Test run marker generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a concrete implementation for testing
            class TestAdapter(LLMAdapter):
                async def execute(self, prompt, model="sonnet", tools=None, timeout=300):
                    pass
                async def stream(self, prompt, model="sonnet", tools=None, timeout=300):
                    yield StreamEvent(type=AdapterEvent.TEXT)
                async def stop(self):
                    pass
                @property
                def is_running(self):
                    return False

            adapter = TestAdapter(Path(tmpdir))
            marker = adapter.build_run_marker(
                run_id="run-123",
                project_slug="my-app",
                iteration=5,
                mode="turbo",
            )

            assert "RALPHX_TRACKING" in marker
            assert 'run_id="run-123"' in marker
            assert 'project="my-app"' in marker
            assert "iteration=5" in marker
            assert 'mode="turbo"' in marker


class TestClaudeCLIAdapter:
    """Test Claude CLI adapter."""

    @pytest.fixture
    def project_dir(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def adapter(self, project_dir):
        """Create a Claude CLI adapter."""
        return ClaudeCLIAdapter(project_dir)

    def test_build_command_basic(self, adapter):
        """Test building basic command."""
        cmd = adapter._build_command("sonnet")
        assert "claude" in cmd
        assert "-p" in cmd
        assert "--output-format" in cmd
        assert "stream-json" in cmd
        assert "claude-sonnet-4-20250514" in cmd

    def test_build_command_with_tools(self, adapter):
        """Test building command with tools."""
        cmd = adapter._build_command("sonnet", tools=["Read", "Write"])
        assert "--allowedTools" in cmd
        assert "Read" in cmd
        assert "Write" in cmd

    def test_build_command_model_mapping(self, adapter):
        """Test model name mapping."""
        cmd_opus = adapter._build_command("opus")
        assert "claude-opus-4-20250514" in cmd_opus

        cmd_haiku = adapter._build_command("haiku")
        assert "claude-haiku-3-20240307" in cmd_haiku

    def test_is_running_initially_false(self, adapter):
        """Test is_running is False initially."""
        assert adapter.is_running is False

    def test_parse_init_event(self, adapter):
        """Test parsing init event with session ID."""
        data = {"type": "init", "session_id": "abc-123"}
        event = adapter._parse_event(data)
        assert event.type == AdapterEvent.INIT
        assert event.data["session_id"] == "abc-123"
        assert adapter._session_id == "abc-123"

    def test_parse_text_delta(self, adapter):
        """Test parsing text delta event."""
        data = {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "Hello"},
        }
        event = adapter._parse_event(data)
        assert event.type == AdapterEvent.TEXT
        assert event.text == "Hello"

    def test_parse_tool_use(self, adapter):
        """Test parsing tool use event."""
        data = {
            "type": "content_block_start",
            "content_block": {
                "type": "tool_use",
                "name": "Read",
                "input": {"file_path": "/test.py"},
            },
        }
        event = adapter._parse_event(data)
        assert event.type == AdapterEvent.TOOL_USE
        assert event.tool_name == "Read"

    def test_parse_error_event(self, adapter):
        """Test parsing error event."""
        data = {"type": "error", "message": "Rate limited", "code": "RATE_LIMIT"}
        event = adapter._parse_event(data)
        assert event.type == AdapterEvent.ERROR
        assert event.error_message == "Rate limited"
        assert event.error_code == "RATE_LIMIT"

    def test_parse_message_stop(self, adapter):
        """Test parsing message stop event."""
        adapter._session_id = "test-123"
        data = {"type": "message_stop"}
        event = adapter._parse_event(data)
        assert event.type == AdapterEvent.COMPLETE

    @pytest.mark.asyncio
    async def test_execute_with_mock(self, adapter):
        """Test execute method with mocked subprocess."""
        # Create mock process
        mock_stdout = AsyncMock()
        mock_stdout.__aiter__.return_value = [
            b'{"type": "init", "session_id": "test-123"}\n',
            b'{"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}}\n',
            b'{"type": "message_stop"}\n',
        ]

        mock_process = MagicMock()
        mock_process.stdout = mock_stdout
        mock_process.stdin = AsyncMock()
        mock_process.stdin.write = MagicMock()
        mock_process.stdin.drain = AsyncMock()
        mock_process.stdin.close = MagicMock()
        mock_process.stdin.wait_closed = AsyncMock()
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await adapter.execute("Test prompt", timeout=10)

        assert result.session_id == "test-123"
        assert "Hello" in result.text_output

    @pytest.mark.asyncio
    async def test_stop_terminates_process(self, adapter):
        """Test stop method terminates process."""
        mock_process = MagicMock()
        mock_process.returncode = None
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        adapter._process = mock_process
        await adapter.stop()

        mock_process.terminate.assert_called_once()
        assert adapter._process is None


class TestClaudeCLIAvailability:
    """Test Claude CLI availability checks."""

    def test_is_available_with_claude(self):
        """Test is_available when claude is in PATH."""
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            assert ClaudeCLIAdapter.is_available() is True

    def test_is_available_without_claude(self):
        """Test is_available when claude is not in PATH."""
        with patch("shutil.which", return_value=None):
            assert ClaudeCLIAdapter.is_available() is False

    @pytest.mark.asyncio
    async def test_check_auth_success(self):
        """Test check_auth when authenticated."""
        mock_process = MagicMock()
        mock_process.wait = AsyncMock()
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await ClaudeCLIAdapter.check_auth()
        assert result is True

    @pytest.mark.asyncio
    async def test_check_auth_failure(self):
        """Test check_auth when not authenticated."""
        mock_process = MagicMock()
        mock_process.wait = AsyncMock()
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await ClaudeCLIAdapter.check_auth()
        assert result is False
