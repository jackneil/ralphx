"""Base adapter class for LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Optional


class AdapterEvent(str, Enum):
    """Types of events emitted by adapters."""

    INIT = "init"           # Session initialized
    TEXT = "text"           # Text output from model
    TOOL_USE = "tool_use"   # Model is using a tool
    TOOL_RESULT = "tool_result"  # Tool returned a result
    ERROR = "error"         # Error occurred
    COMPLETE = "complete"   # Execution completed


@dataclass
class StreamEvent:
    """Event emitted during streaming execution."""

    type: AdapterEvent
    timestamp: datetime = field(default_factory=datetime.utcnow)
    data: dict = field(default_factory=dict)

    # Text content for TEXT events
    text: Optional[str] = None

    # Tool details for TOOL_USE events
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None

    # Tool result for TOOL_RESULT events
    tool_result: Optional[str] = None

    # Error details for ERROR events
    error_message: Optional[str] = None
    error_code: Optional[str] = None


@dataclass
class ExecutionResult:
    """Result of an LLM execution."""

    session_id: Optional[str] = None
    success: bool = True
    exit_code: int = 0

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        """Get execution duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    # Output
    text_output: str = ""
    tool_calls: list = field(default_factory=list)

    # Extracted items (work items parsed from output)
    items: list = field(default_factory=list)

    # Error details
    error_message: Optional[str] = None
    timeout: bool = False
    permission_blocked: bool = False


class LLMAdapter(ABC):
    """Abstract base class for LLM provider adapters.

    Adapters handle the actual communication with LLM providers,
    whether that's via CLI subprocess, API calls, or other methods.
    """

    def __init__(self, project_path: Path):
        """Initialize the adapter.

        Args:
            project_path: Path to the project directory (for context).
        """
        self.project_path = project_path

    @abstractmethod
    async def execute(
        self,
        prompt: str,
        model: str = "sonnet",
        tools: Optional[list[str]] = None,
        timeout: int = 300,
    ) -> ExecutionResult:
        """Execute a prompt and return the result.

        Args:
            prompt: The prompt to send to the LLM.
            model: Model identifier (e.g., "sonnet", "opus", "haiku").
            tools: List of tool names to enable.
            timeout: Timeout in seconds.

        Returns:
            ExecutionResult with session info and output.
        """
        pass

    @abstractmethod
    async def stream(
        self,
        prompt: str,
        model: str = "sonnet",
        tools: Optional[list[str]] = None,
        timeout: int = 300,
    ) -> AsyncIterator[StreamEvent]:
        """Stream execution events.

        Args:
            prompt: The prompt to send to the LLM.
            model: Model identifier.
            tools: List of tool names to enable.
            timeout: Timeout in seconds.

        Yields:
            StreamEvent objects as execution progresses.
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the current execution if running."""
        pass

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """Check if an execution is currently in progress."""
        pass

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
        return f"""

<!-- RALPHX_TRACKING run_id="{run_id}" project="{project_slug}" iteration={iteration} mode="{mode}" ts="{now}" -->"""
