"""Display utilities for RalphX CLI output.

Provides enhanced formatting for loop execution:
- Timestamped console output
- Configuration and summary banners
- Iteration headers with elapsed time
- Prompt size reporting
"""

import math
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from ralphx.models.loop import LoopConfig
from ralphx.models.project import Project


def format_elapsed(seconds: float) -> str:
    """Format elapsed time as human-readable string.

    Args:
        seconds: Elapsed time in seconds.

    Returns:
        Formatted string like "2h 15m 30s" or "45s" for short durations.
    """
    # Handle edge cases: negative, nan, inf
    if math.isnan(seconds) or seconds < 0:
        return "0s"
    if math.isinf(seconds):
        return "inf"

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or hours > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")

    return " ".join(parts)


def estimate_tokens(text: str) -> int:
    """Estimate token count for text.

    Uses a rough heuristic of ~4 characters per token.

    Args:
        text: Input text.

    Returns:
        Estimated token count.
    """
    return len(text) // 4


def format_prompt_size(prompt: str) -> str:
    """Format prompt size statistics.

    Args:
        prompt: The prompt text.

    Returns:
        Formatted string like "Prompt: 45,231 chars, 892 lines, ~11,307 tokens"
    """
    chars = len(prompt)
    # Empty string has 0 lines, non-empty has count of newlines + 1
    lines = prompt.count("\n") + 1 if prompt else 0
    tokens = estimate_tokens(prompt)

    return f"Prompt: {chars:,} chars, {lines:,} lines, ~{tokens:,} tokens"


def build_config_banner(
    project: Project,
    config: LoopConfig,
    max_iterations: int,
    dry_run: bool = False,
    resume: bool = False,
    mode_name: Optional[str] = None,
) -> Panel:
    """Build a Rich Panel showing run configuration.

    Args:
        project: Project being run.
        config: Loop configuration.
        max_iterations: Maximum iterations for this run.
        dry_run: Whether this is a dry run.
        resume: Whether resuming from checkpoint.
        mode_name: Initial mode name (for fixed strategy).

    Returns:
        Rich Panel with configuration details.
    """
    # Get initial mode for display
    if mode_name is None:
        if config.mode_selection.strategy.value == "fixed":
            mode_name = config.mode_selection.fixed_mode
        elif config.modes:
            mode_name = list(config.modes.keys())[0]
        else:
            mode_name = "default"

    mode = config.modes.get(mode_name) if config.modes else None
    model = mode.model if mode else "sonnet"
    timeout = mode.timeout if mode else 300

    # Build table for aligned key-value display
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="dim", width=14)
    table.add_column("Value")

    # Escape user-provided strings to prevent Rich markup injection
    table.add_row("Project", f"{escape(project.name)} ({escape(project.slug)})")
    table.add_row("Path", escape(str(project.path)))
    table.add_row("Loop", escape(config.display_name))
    table.add_row("Type", config.type.value if hasattr(config, "type") else "unknown")
    table.add_row("Strategy", config.mode_selection.strategy.value)
    table.add_row("Mode", escape(mode_name))
    table.add_row("Model", escape(model))
    table.add_row("Timeout", f"{timeout}s")
    table.add_row("Max Iter", str(max_iterations))
    table.add_row("Max Runtime", f"{config.limits.max_runtime_seconds}s")
    table.add_row("Started", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))

    if dry_run:
        table.add_row("Dry Run", "[yellow]Yes[/yellow]")
    if resume:
        table.add_row("Resume", "[blue]Yes[/blue]")

    return Panel(
        table,
        title="[bold]RalphX Run Configuration[/bold]",
        border_style="blue",
    )


def build_summary_banner(
    run_id: str,
    status: str,
    iterations: int,
    items_generated: int,
    duration_seconds: Optional[float] = None,
    error_message: Optional[str] = None,
) -> Panel:
    """Build a Rich Panel showing run summary.

    Args:
        run_id: Run identifier.
        status: Final run status.
        iterations: Number of iterations completed.
        items_generated: Number of items generated.
        duration_seconds: Total duration in seconds.
        error_message: Error message if run failed.

    Returns:
        Rich Panel with summary details.
    """
    # Status color
    status_display = status.upper()
    if status.lower() == "completed":
        status_display = f"[green]{status_display}[/green]"
    elif status.lower() in ("error", "aborted"):
        status_display = f"[red]{status_display}[/red]"
    elif status.lower() == "paused":
        status_display = f"[yellow]{status_display}[/yellow]"

    # Build table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="dim", width=12)
    table.add_column("Value")

    table.add_row("Run ID", escape(run_id))
    table.add_row("Status", status_display)
    table.add_row("Iterations", str(iterations))
    table.add_row("Items", str(items_generated))

    if duration_seconds is not None:
        table.add_row("Duration", format_elapsed(duration_seconds))

    table.add_row("Completed", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))

    if error_message:
        # Escape error message but wrap in red styling
        table.add_row("Error", f"[red]{escape(error_message)}[/red]")

    return Panel(
        table,
        title="[bold]Run Summary[/bold]",
        border_style="green" if status.lower() == "completed" else "red",
    )


def format_iteration_header(
    iteration: int,
    max_iterations: int,
    elapsed_seconds: float,
    mode: str,
    model: str,
    timeout: int,
) -> tuple[str, str]:
    """Format iteration header lines.

    Args:
        iteration: Current iteration number.
        max_iterations: Maximum iterations.
        elapsed_seconds: Elapsed time since run start.
        mode: Mode name.
        model: Model name.
        timeout: Timeout in seconds.

    Returns:
        Tuple of (main_line, detail_line) for display.
    """
    elapsed = format_elapsed(elapsed_seconds)
    main_line = f"=== Iteration {iteration}/{max_iterations} ({elapsed} elapsed) ==="
    # Escape mode/model in case they contain Rich markup characters
    detail_line = f"mode={escape(mode)} model={escape(model)} timeout={timeout}s"
    return main_line, detail_line


class TimestampedConsole:
    """Console wrapper that prefixes output with timestamps.

    Wraps a Rich Console to add [YYYY-MM-DD HH:MM:SS] prefix to output.
    """

    def __init__(self, console: Optional[Console] = None):
        """Initialize timestamped console.

        Args:
            console: Rich Console to wrap. Creates new one if not provided.
        """
        self._console = console or Console()
        self._show_timestamps = True

    @property
    def show_timestamps(self) -> bool:
        """Whether to show timestamps."""
        return self._show_timestamps

    @show_timestamps.setter
    def show_timestamps(self, value: bool) -> None:
        """Set whether to show timestamps."""
        self._show_timestamps = value

    def _timestamp(self) -> str:
        """Get current timestamp string."""
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    def print(self, *args, timestamp: bool = True, **kwargs) -> None:
        """Print with optional timestamp prefix.

        Args:
            *args: Arguments to print. Rich markup is supported.
                   Use rich.markup.escape() for user-provided strings.
            timestamp: Whether to add timestamp (default True).
            **kwargs: Keyword arguments passed to Rich Console.
        """
        if self._show_timestamps and timestamp and args:
            # Add timestamp prefix to first argument
            first = str(args[0])
            timestamped = f"[dim][{self._timestamp()}][/dim] {first}"
            self._console.print(timestamped, *args[1:], **kwargs)
        else:
            self._console.print(*args, **kwargs)

    def print_continuation(self, text: str, **kwargs) -> None:
        """Print continuation line (indented to align with timestamped content).

        Args:
            text: Text to print.
            **kwargs: Keyword arguments passed to Rich Console.
        """
        # Indent to align with content after timestamp
        # Timestamp is "[YYYY-MM-DD HH:MM:SS] " = 22 chars
        indent = " " * 22
        self._console.print(f"{indent}{text}", **kwargs)

    def print_panel(self, panel: Panel, **kwargs) -> None:
        """Print a Rich Panel without timestamp.

        Args:
            panel: Rich Panel to print.
            **kwargs: Keyword arguments passed to Rich Console.
        """
        self._console.print(panel, **kwargs)

    def print_blank(self) -> None:
        """Print a blank line."""
        self._console.print()
