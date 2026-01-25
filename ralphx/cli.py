"""RalphX CLI - Command-line interface for agent loop orchestration."""

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from ralphx import __version__
from ralphx.core.executor import ExecutorEvent, ExecutorEventData, LoopExecutor
from ralphx.core.loop import LoopLoader, LoopValidationError
from ralphx.core.project import ProjectManager
from ralphx.core.workspace import ensure_workspace, get_workspace_path

# Create the main app
app = typer.Typer(
    name="ralphx",
    help="Generic agent loop orchestration system with web dashboard.",
    no_args_is_help=True,
)

# Create subcommand groups
projects_app = typer.Typer(help="Manage projects")
loops_app = typer.Typer(help="Manage loops")
guardrails_app = typer.Typer(help="Manage guardrails")
import_app = typer.Typer(help="Import content into loops")

# Add subcommands to main app
app.add_typer(projects_app, name="projects")
app.add_typer(loops_app, name="loops")
app.add_typer(guardrails_app, name="guardrails")
app.add_typer(import_app, name="import")

console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"ralphx version {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """RalphX - Generic agent loop orchestration system."""
    # Ensure workspace exists on every CLI invocation
    ensure_workspace()


# =============================================================================
# Project Commands
# =============================================================================


@app.command("add")
def add_project(
    path: Path = typer.Argument(
        ...,
        help="Path to the project directory",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Human-readable project name (defaults to directory name)",
    ),
    design_doc: Optional[str] = typer.Option(
        None,
        "--design-doc",
        "-d",
        help="Path to design document (relative to project)",
    ),
    detect: bool = typer.Option(
        True,
        "--detect/--no-detect",
        help="Detect AI instruction files (CLAUDE.md, etc.)",
    ),
    detect_only: bool = typer.Option(
        False,
        "--detect-only",
        help="Only detect AI files, don't add project",
    ),
) -> None:
    """Add a project to RalphX."""
    from ralphx.core.guardrails import GuardrailDetector

    # Handle detect-only mode
    if detect_only:
        console.print(f"[bold]Detecting AI instruction files in:[/bold] {path}\n")

        detector = GuardrailDetector(path)
        report = detector.detect()

        if not report.detected_files:
            console.print("[yellow]No AI instruction files found[/yellow]")
            return

        # Show security warning if cloned repo
        if report.has_security_warning:
            console.print(Panel(
                "\n".join(report.warnings),
                title="[yellow]Security Warning[/yellow]",
                border_style="yellow",
            ))
            console.print()

        # Show detected files
        table = Table(show_header=True, header_style="bold")
        table.add_column("File", style="cyan")
        table.add_column("Size")
        table.add_column("Valid")

        for df in report.detected_files:
            valid_str = "[green]Yes[/green]" if df.is_valid else "[red]No[/red]"
            table.add_row(
                str(df.path.relative_to(path)),
                f"{df.size} bytes",
                valid_str,
            )

        console.print(table)
        console.print(f"\n{report.summary()}")
        return

    # Normal add flow
    try:
        manager = ProjectManager()
        project = manager.add_project(
            path=path,
            name=name,
            design_doc=design_doc,
        )
        console.print(f"[green]Added project:[/green] {project.name}")
        console.print(f"  Slug: {project.slug}")
        console.print(f"  Path: {project.path}")
        if project.design_doc:
            console.print(f"  Design doc: {project.design_doc}")

        # Detect AI instruction files if enabled
        if detect:
            console.print()
            detector = GuardrailDetector(path)
            report = detector.detect()

            if report.detected_files:
                console.print(f"[bold]Detected {len(report.detected_files)} AI instruction file(s):[/bold]")
                for df in report.detected_files:
                    status = "[green]valid[/green]" if df.is_valid else "[yellow]invalid[/yellow]"
                    console.print(f"  - {df.path.name} ({status})")

                if report.has_security_warning:
                    console.print("\n[yellow]Warning:[/yellow] This is a cloned repository.")
                    console.print("  Review detected files before using as guardrails.")

                console.print(f"\nUse [cyan]ralphx guardrails detect --project {project.slug} --copy[/cyan] to use")

    except FileExistsError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@projects_app.command("show")
def show_project(
    slug: str = typer.Argument(..., help="Project slug"),
) -> None:
    """Show details for a specific project."""
    manager = ProjectManager()
    project = manager.get_project(slug)

    if not project:
        console.print(f"[red]Project not found:[/red] {slug}")
        raise typer.Exit(1)

    console.print(f"[bold]{project.name}[/bold]")
    console.print(f"  ID: {project.id}")
    console.print(f"  Slug: {project.slug}")
    console.print(f"  Path: {project.path}")
    if project.design_doc:
        console.print(f"  Design doc: {project.design_doc}")
    console.print(f"  Created: {project.created_at}")

    # Show stats if available
    stats = manager.get_project_stats(slug)
    if stats and stats["total"] > 0:
        console.print(f"\n[bold]Work Items:[/bold]")
        console.print(f"  Total: {stats['total']}")
        for status, count in stats.get("by_status", {}).items():
            console.print(f"    {status}: {count}")


@projects_app.command("list")
def list_projects_cmd() -> None:
    """List all registered projects."""
    manager = ProjectManager()
    projects = manager.list_projects()

    if not projects:
        console.print("[yellow]No projects registered yet[/yellow]")
        console.print("\nUse [cyan]ralphx add <path>[/cyan] to add a project.")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Slug", style="cyan")
    table.add_column("Name")
    table.add_column("Path")
    table.add_column("Design Doc")

    for project in projects:
        table.add_row(
            project.slug,
            project.name,
            str(project.path),
            project.design_doc or "-",
        )

    console.print(table)


@app.command("remove")
def remove_project_cmd(
    slug: str = typer.Argument(..., help="Project slug to remove"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force removal without confirmation"
    ),
    delete_workspace: bool = typer.Option(
        False, "--delete-workspace", help="Also delete workspace files"
    ),
) -> None:
    """Remove a project from RalphX."""
    manager = ProjectManager()
    project = manager.get_project(slug)

    if not project:
        console.print(f"[red]Project not found:[/red] {slug}")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f"Remove project '{project.name}' ({slug})?")
        if not confirm:
            raise typer.Abort()

    result = manager.remove_project(slug, delete_local_data=delete_workspace)
    if result:
        console.print(f"[green]Removed project:[/green] {slug}")
        if delete_workspace:
            console.print("  Workspace files deleted")
    else:
        console.print(f"[red]Failed to remove project:[/red] {slug}")
        raise typer.Exit(1)


# =============================================================================
# Loop Commands
# =============================================================================


@loops_app.command("sync")
def sync_loops_cmd(
    project: str = typer.Option(..., "--project", "-p", help="Project slug"),
) -> None:
    """Sync loops from project files to database."""
    proj_manager = ProjectManager()
    proj = proj_manager.get_project(project)

    if not proj:
        console.print(f"[red]Project not found:[/red] {project}")
        raise typer.Exit(1)

    project_db = proj_manager.get_project_db(proj.path)
    loader = LoopLoader(db=project_db)
    result = loader.sync_loops(proj)

    console.print(f"[bold]Synced loops for:[/bold] {project}")
    console.print(f"  Added: {result['added']}")
    console.print(f"  Updated: {result['updated']}")
    console.print(f"  Removed: {result['removed']}")

    if result["errors"]:
        console.print("\n[yellow]Errors:[/yellow]")
        for path, error in result["errors"]:
            console.print(f"  {path}: {error}")


@loops_app.command("show")
def show_loop_cmd(
    loop_name: str = typer.Argument(..., help="Loop name"),
    project: str = typer.Option(..., "--project", "-p", help="Project slug"),
) -> None:
    """Show details for a specific loop."""
    proj_manager = ProjectManager()
    proj = proj_manager.get_project(project)

    if not proj:
        console.print(f"[red]Project not found:[/red] {project}")
        raise typer.Exit(1)

    project_db = proj_manager.get_project_db(proj.path)
    loader = LoopLoader(db=project_db)
    config = loader.get_loop(loop_name)

    if not config:
        console.print(f"[red]Loop not found:[/red] {loop_name}")
        raise typer.Exit(1)

    console.print(f"[bold]{config.display_name}[/bold]")
    console.print(f"  Name: {config.name}")
    console.print(f"  Type: {config.type.value}")
    console.print(f"  Strategy: {config.mode_selection.strategy.value}")

    console.print("\n[bold]Modes:[/bold]")
    for mode_name, mode in config.modes.items():
        console.print(f"  {mode_name}:")
        console.print(f"    Model: {mode.model}")
        console.print(f"    Timeout: {mode.timeout}s")
        console.print(f"    Tools: {', '.join(mode.tools) or 'none'}")
        console.print(f"    Template: {mode.prompt_template}")

    console.print(f"\n[bold]Limits:[/bold]")
    console.print(f"  Max iterations: {config.limits.max_iterations}")
    console.print(f"  Max runtime: {config.limits.max_runtime_seconds}s")
    console.print(f"  Max consecutive errors: {config.limits.max_consecutive_errors}")


@loops_app.command("list")
def list_loops_cmd(
    project: str = typer.Option(..., "--project", "-p", help="Project slug"),
) -> None:
    """List all loops for a project."""
    proj_manager = ProjectManager()
    proj = proj_manager.get_project(project)

    if not proj:
        console.print(f"[red]Project not found:[/red] {project}")
        raise typer.Exit(1)

    project_db = proj_manager.get_project_db(proj.path)
    loader = LoopLoader(db=project_db)
    loops = loader.list_loops()

    if not loops:
        console.print(f"[yellow]No loops registered for project:[/yellow] {project}")
        console.print("\nDiscover loops with [cyan]ralphx loops sync --project {project}[/cyan]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Type")
    table.add_column("Modes")
    table.add_column("Strategy")

    for loop in loops:
        modes_str = ", ".join(loop.modes.keys())
        table.add_row(
            loop.name,
            loop.type.value,
            modes_str,
            loop.mode_selection.strategy.value,
        )

    console.print(table)


@app.command("validate")
def validate_loop(
    loop_file: Path = typer.Argument(
        ...,
        help="Path to loop configuration YAML file",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    check_files: bool = typer.Option(
        True,
        "--check-files/--no-check-files",
        help="Verify referenced files exist",
    ),
) -> None:
    """Validate a loop configuration file."""
    console.print(f"[bold]Validating:[/bold] {loop_file}")

    loader = LoopLoader()
    project_path = loop_file.parent if check_files else None

    try:
        config = loader.load_from_file(loop_file, project_path=project_path)
        console.print(f"[green]Valid[/green] - {config.display_name}")
        console.print(f"  Name: {config.name}")
        console.print(f"  Type: {config.type.value}")
        console.print(f"  Modes: {', '.join(config.modes.keys())}")
        console.print(f"  Strategy: {config.mode_selection.strategy.value}")
        console.print(f"  Max iterations: {config.limits.max_iterations}")
    except LoopValidationError as e:
        console.print(f"[red]Invalid[/red] - {e}")
        if e.errors:
            for error in e.errors:
                console.print(f"  - {error}")
        raise typer.Exit(1)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# =============================================================================
# Run Command
# =============================================================================


@app.command("run")
def run_loop(
    loop: str = typer.Argument(..., help="Loop name to run"),
    project: str = typer.Option(..., "--project", "-p", help="Project slug"),
    iterations: Optional[int] = typer.Option(
        None, "--iterations", "-n", help="Number of iterations (overrides config)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without executing"
    ),
    resume: bool = typer.Option(
        False, "--resume", help="Resume from last checkpoint"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress progress output"
    ),
) -> None:
    """Run a loop for a project."""
    # Get project
    proj_manager = ProjectManager()
    proj = proj_manager.get_project(project)

    if not proj:
        console.print(f"[red]Project not found:[/red] {project}")
        raise typer.Exit(1)

    # Get loop config
    project_db = proj_manager.get_project_db(proj.path)
    loader = LoopLoader(db=project_db)
    config = loader.get_loop(loop)

    if not config:
        console.print(f"[red]Loop not found:[/red] {loop}")
        console.print(f"\nSync loops first: [cyan]ralphx loops sync --project {project}[/cyan]")
        raise typer.Exit(1)

    # Calculate max iterations for display and execution
    max_iter = iterations or config.limits.max_iterations

    if not quiet:
        from ralphx.core.display import build_config_banner, TimestampedConsole

        # Show configuration banner
        banner = build_config_banner(
            project=proj,
            config=config,
            max_iterations=max_iter,
            dry_run=dry_run,
            resume=resume,
        )
        console.print(banner)
        console.print()

        # Create timestamped console for run output
        ts_console = TimestampedConsole(console)

    # Create executor using project-local database for portability
    project_db = proj_manager.get_project_db(proj.path)
    executor = LoopExecutor(
        project=proj,
        loop_config=config,
        db=project_db,
        dry_run=dry_run,
    )

    # Track run start time for elapsed calculation
    from datetime import datetime
    run_start_time = datetime.utcnow()

    # Event handler for CLI output with timestamps
    def on_event(event: ExecutorEventData) -> None:
        if quiet:
            return

        # Import here to avoid issues when quiet=True
        from ralphx.core.display import format_iteration_header
        from rich.markup import escape

        if event.event == ExecutorEvent.ITERATION_STARTED:
            mode = event.data.get("mode", "unknown")
            # Get mode config for model and timeout
            mode_config = config.modes.get(mode)
            model = mode_config.model if mode_config else "sonnet"
            timeout = mode_config.timeout if mode_config else 300

            # Calculate elapsed time
            elapsed = (datetime.utcnow() - run_start_time).total_seconds()

            # Format iteration header
            main_line, detail_line = format_iteration_header(
                iteration=event.iteration,
                max_iterations=max_iter,
                elapsed_seconds=elapsed,
                mode=mode,
                model=model,
                timeout=timeout,
            )
            ts_console.print(main_line)
            ts_console.print_continuation(detail_line)

        elif event.event == ExecutorEvent.PROMPT_PREPARED:
            # Show prompt size statistics
            ts_console.print(event.message)

        elif event.event == ExecutorEvent.ITEM_ADDED:
            item_id = event.data.get("item_id", "?")
            ts_console.print(f"[green]+[/green] {escape(item_id)}")

        elif event.event == ExecutorEvent.ERROR:
            # Include consecutive error count
            consecutive = event.data.get("consecutive_errors", 0)
            max_consecutive = event.data.get("max_consecutive_errors", 3)
            error_msg = escape(event.message or "Unknown error")
            if consecutive > 0:
                ts_console.print(f"[red]Error:[/red] {error_msg} (consecutive: {consecutive}/{max_consecutive})")
            else:
                ts_console.print(f"[red]Error:[/red] {error_msg}")

        elif event.event == ExecutorEvent.WARNING:
            ts_console.print(f"[yellow]Warning:[/yellow] {escape(event.message or '')}")

        elif event.event == ExecutorEvent.RUN_COMPLETED:
            ts_console.print_blank()
            ts_console.print(f"[green]Completed:[/green] {escape(event.message or '')}")

        elif event.event == ExecutorEvent.RUN_ABORTED:
            ts_console.print_blank()
            ts_console.print(f"[yellow]Aborted:[/yellow] {escape(event.message or '')}")

    executor.add_event_handler(on_event)

    # Run the loop
    try:
        run = asyncio.run(executor.run(max_iterations=iterations))

        if not quiet:
            from ralphx.core.display import build_summary_banner

            console.print()  # Blank line before summary
            summary_banner = build_summary_banner(
                run_id=run.id,
                status=run.status.value,
                iterations=run.iterations_completed,
                items_generated=run.items_generated,
                duration_seconds=run.duration_seconds,
                error_message=run.error_message,
            )
            console.print(summary_banner)

        if run.status.value == "error":
            raise typer.Exit(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        raise typer.Exit(130)


# =============================================================================
# Serve Command
# =============================================================================


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8765, "--port", "-p", help="Port to bind to"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
) -> None:
    """Start the RalphX API server."""
    import uvicorn

    console.print(f"[bold]Starting RalphX server[/bold]")
    console.print(f"  URL: http://{host}:{port}")
    console.print(f"  API docs: http://{host}:{port}/docs")
    console.print(f"  Health: http://{host}:{port}/api/health")
    console.print()

    uvicorn.run(
        "ralphx.api.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


# =============================================================================
# Doctor Command
# =============================================================================


@app.command("doctor")
def doctor() -> None:
    """Run diagnostic checks."""
    from ralphx.core.doctor import CheckStatus, DoctorCheck

    console.print("[bold]RalphX Doctor[/bold]\n")

    doc = DoctorCheck()
    report = doc.run_all()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Details")

    for check in report.checks:
        if check.status == CheckStatus.OK:
            status = "[green]OK[/green]"
        elif check.status == CheckStatus.WARNING:
            status = "[yellow]WARN[/yellow]"
        elif check.status == CheckStatus.ERROR:
            status = "[red]FAIL[/red]"
        else:
            status = "[dim]SKIP[/dim]"

        details = check.message
        if check.fix_hint:
            details += f"\n  [dim]Fix: {check.fix_hint}[/dim]"

        table.add_row(check.name, status, details)

    console.print(table)
    console.print(f"\n{report.summary()}")

    if report.has_errors:
        raise typer.Exit(1)


@app.command("diagnose")
def diagnose(
    project: str = typer.Option(..., "--project", "-p", help="Project slug"),
) -> None:
    """Run project-specific diagnostics."""
    from ralphx.core.doctor import CheckStatus, ProjectDiagnostics

    proj_manager = ProjectManager()
    proj = proj_manager.get_project(project)

    if not proj:
        console.print(f"[red]Project not found:[/red] {project}")
        raise typer.Exit(1)

    console.print(f"[bold]Diagnosing project:[/bold] {proj.name}\n")

    diag = ProjectDiagnostics(proj_manager.db)
    report = diag.diagnose(proj)

    table = Table(show_header=True, header_style="bold")
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Details")

    for check in report.checks:
        if check.status == CheckStatus.OK:
            status = "[green]OK[/green]"
        elif check.status == CheckStatus.WARNING:
            status = "[yellow]WARN[/yellow]"
        elif check.status == CheckStatus.ERROR:
            status = "[red]FAIL[/red]"
        else:
            status = "[dim]SKIP[/dim]"

        details = check.message
        if check.fix_hint:
            details += f"\n  [dim]Fix: {check.fix_hint}[/dim]"

        table.add_row(check.name, status, details)

    console.print(table)
    console.print(f"\n{report.summary()}")


@app.command("why")
def why_stopped(
    project: str = typer.Option(..., "--project", "-p", help="Project slug"),
) -> None:
    """Explain why the last run stopped."""
    from ralphx.core.doctor import ProjectDiagnostics

    proj_manager = ProjectManager()
    proj = proj_manager.get_project(project)

    if not proj:
        console.print(f"[red]Project not found:[/red] {project}")
        raise typer.Exit(1)

    diag = ProjectDiagnostics(proj_manager.db)
    result = diag.why_stopped(proj)

    if not result:
        console.print(f"[yellow]No runs found for project:[/yellow] {project}")
        return

    console.print(f"[bold]Last run status for:[/bold] {proj.name}\n")
    console.print(f"  Run ID: {result['run_id']}")
    console.print(f"  Loop: {result['loop_name']}")
    console.print(f"  Status: {result['status']}")

    if result['started_at']:
        console.print(f"  Started: {result['started_at']}")
    if result['completed_at']:
        console.print(f"  Completed: {result['completed_at']}")
    if result['duration_seconds']:
        console.print(f"  Duration: {result['duration_seconds']:.1f}s")

    console.print(f"  Iterations: {result['iterations_completed']}")
    console.print(f"  Items generated: {result['items_generated']}")

    console.print(f"\n[bold]Stop reason:[/bold] {result['reason']}")
    if result['details']:
        console.print(f"  {result['details']}")


# =============================================================================
# Guardrails Commands
# =============================================================================


@guardrails_app.command("validate")
def validate_guardrails(
    project: str = typer.Option(..., "--project", "-p", help="Project slug"),
    loop_name: Optional[str] = typer.Option(None, "--loop", "-l", help="Loop to validate for"),
) -> None:
    """Validate guardrails configuration for a project."""
    from ralphx.core.guardrails import GuardrailsManager

    proj_manager = ProjectManager()
    proj = proj_manager.get_project(project)

    if not proj:
        console.print(f"[red]Project not found:[/red] {project}")
        raise typer.Exit(1)

    console.print(f"[bold]Validating guardrails for:[/bold] {proj.name}\n")

    manager = GuardrailsManager(proj.path, project)

    # Get loop config if specified
    loop_config = None
    if loop_name:
        project_db = proj_manager.get_project_db(proj.path)
        loader = LoopLoader(db=project_db)
        loop_config = loader.get_loop(loop_name)
        if not loop_config:
            console.print(f"[red]Loop not found:[/red] {loop_name}")
            raise typer.Exit(1)
        console.print(f"  Loop: {loop_name}")

    errors = manager.validate(loop_config)

    if errors:
        console.print("[red]Validation errors:[/red]")
        for error in errors:
            console.print(f"  - {error}")
        raise typer.Exit(1)
    else:
        console.print("[green]Guardrails configuration is valid[/green]")


@guardrails_app.command("preview")
def preview_guardrails(
    loop: str = typer.Argument(..., help="Loop name"),
    project: str = typer.Option(..., "--project", "-p", help="Project slug"),
    mode: Optional[str] = typer.Option(None, "--mode", "-m", help="Specific mode to preview"),
    position: Optional[str] = typer.Option(None, "--position", help="Show only specific position"),
) -> None:
    """Preview assembled guardrails for a loop."""
    from ralphx.core.guardrails import GuardrailsManager, InjectionPosition

    proj_manager = ProjectManager()
    proj = proj_manager.get_project(project)

    if not proj:
        console.print(f"[red]Project not found:[/red] {project}")
        raise typer.Exit(1)

    # Get loop config
    project_db = proj_manager.get_project_db(proj.path)
    loader = LoopLoader(db=project_db)
    loop_config = loader.get_loop(loop)

    if not loop_config:
        console.print(f"[red]Loop not found:[/red] {loop}")
        raise typer.Exit(1)

    console.print(f"[bold]Guardrails preview[/bold]")
    console.print(f"  Loop: {loop_config.display_name}")
    if mode:
        console.print(f"  Mode: {mode}")
    console.print()

    manager = GuardrailsManager(proj.path, project)
    gs = manager.load_all(loop_config, mode)

    if not gs.guardrails:
        console.print("[yellow]No guardrails found[/yellow]")
        return

    # Show by position
    positions = [InjectionPosition(position)] if position else list(InjectionPosition)

    for pos in positions:
        guardrails = gs.get_by_position(pos)
        if not guardrails:
            continue

        console.print(f"\n[bold]{pos.value}[/bold]")
        for g in guardrails:
            console.print(f"  [{g.source.value}] {g.filename} ({g.category.value})")
            # Show first 200 chars of content
            preview = g.content[:200].replace("\n", " ")
            if len(g.content) > 200:
                preview += "..."
            console.print(f"    [dim]{preview}[/dim]")

    console.print(f"\n[bold]Total:[/bold] {len(gs.guardrails)} guardrails, {gs.total_size} bytes")


@guardrails_app.command("list")
def list_guardrails(
    project: str = typer.Option(..., "--project", "-p", help="Project slug"),
) -> None:
    """List all guardrails for a project."""
    from ralphx.core.guardrails import GuardrailsManager

    proj_manager = ProjectManager()
    proj = proj_manager.get_project(project)

    if not proj:
        console.print(f"[red]Project not found:[/red] {project}")
        raise typer.Exit(1)

    console.print(f"[bold]Guardrails for:[/bold] {proj.name}\n")

    manager = GuardrailsManager(proj.path, project)
    files = manager.list_files()

    if not files:
        console.print("[yellow]No guardrail files found[/yellow]")
        console.print("\nCreate guardrails in:")
        console.print(f"  - {proj.path}/.ralphx/guardrails/")
        console.print(f"  - {get_workspace_path()}/projects/{project}/guardrails/")
        console.print(f"  - {get_workspace_path()}/guardrails/")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Source", style="cyan")
    table.add_column("Path")
    table.add_column("Size")
    table.add_column("Valid")

    for f in files:
        valid_str = "[green]Yes[/green]" if f["valid"] else "[red]No[/red]"
        # Shorten path for display
        path = f["path"]
        if len(path) > 50:
            path = "..." + path[-47:]
        table.add_row(
            f["source"],
            path,
            f"{f['size']} bytes",
            valid_str,
        )

    console.print(table)


@guardrails_app.command("detect")
def detect_guardrails(
    project: str = typer.Option(..., "--project", "-p", help="Project slug"),
    copy: bool = typer.Option(False, "--copy", help="Copy detected files to workspace"),
) -> None:
    """Detect AI instruction files in a project."""
    from ralphx.core.guardrails import GuardrailDetector
    from ralphx.core.workspace import ensure_project_workspace

    proj_manager = ProjectManager()
    proj = proj_manager.get_project(project)

    if not proj:
        console.print(f"[red]Project not found:[/red] {project}")
        raise typer.Exit(1)

    console.print(f"[bold]Detecting AI instruction files in:[/bold] {proj.name}\n")

    detector = GuardrailDetector(proj.path)
    report = detector.detect()

    if not report.detected_files:
        console.print("[yellow]No AI instruction files found[/yellow]")
        return

    # Show repo warning if applicable
    if report.has_security_warning:
        console.print(Panel(
            "\n".join(report.warnings),
            title="[yellow]Security Warning[/yellow]",
            border_style="yellow",
        ))
        console.print()

    # Show detected files
    table = Table(show_header=True, header_style="bold")
    table.add_column("File", style="cyan")
    table.add_column("Size")
    table.add_column("Valid")
    table.add_column("Warnings")

    for df in report.detected_files:
        valid_str = "[green]Yes[/green]" if df.is_valid else "[red]No[/red]"
        warnings = ", ".join(df.warnings) if df.warnings else "-"
        table.add_row(
            str(df.path.relative_to(proj.path)),
            f"{df.size} bytes",
            valid_str,
            warnings,
        )

    console.print(table)

    # Show previews
    console.print("\n[bold]Content previews:[/bold]")
    for df in report.detected_files:
        if df.preview:
            console.print(f"\n[cyan]{df.path.name}[/cyan]")
            console.print(Panel(df.preview, border_style="dim"))

    # Copy if requested
    if copy:
        workspace_path = ensure_project_workspace(project) / "guardrails"
        console.print(f"\n[bold]Copying to workspace:[/bold] {workspace_path}")

        copied = 0
        for df in report.detected_files:
            if df.is_valid:
                result = detector.copy_to_workspace(df, workspace_path)
                if result:
                    console.print(f"  [green]+[/green] {result.name}")
                    copied += 1

        console.print(f"\n[green]Copied {copied} file(s)[/green]")


@guardrails_app.command("templates")
def list_guardrail_templates(
    create: Optional[str] = typer.Option(None, "--create", help="Create template for project"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project slug (for --create)"),
) -> None:
    """List or create guardrail templates."""
    from ralphx.core.guardrails import create_template_guardrails, list_templates

    if create:
        # Create template
        if not project:
            console.print("[red]Error:[/red] --project is required with --create")
            raise typer.Exit(1)

        proj_manager = ProjectManager()
        proj = proj_manager.get_project(project)

        if not proj:
            console.print(f"[red]Project not found:[/red] {project}")
            raise typer.Exit(1)

        output_dir = proj.path / ".ralphx" / "guardrails"
        console.print(f"[bold]Creating '{create}' template in:[/bold] {output_dir}")

        try:
            created = create_template_guardrails(create, output_dir)
            console.print(f"[green]Created {len(created)} guardrail file(s):[/green]")
            for path in created:
                console.print(f"  - {path.relative_to(proj.path)}")
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    else:
        # List templates
        templates = list_templates()
        console.print("[bold]Available guardrail templates:[/bold]\n")

        for name in templates:
            console.print(f"  - [cyan]{name}[/cyan]")

        console.print(f"\nUse [cyan]ralphx guardrails templates --create <name> --project <slug>[/cyan] to create")


# =============================================================================
# Permissions Commands
# =============================================================================


@app.command("permissions")
def permissions_cmd(
    action: str = typer.Argument(..., help="Action: setup, check, or preset"),
    project: str = typer.Option(..., "--project", "-p", help="Project slug"),
    loop_name: Optional[str] = typer.Option(None, "--loop", "-l", help="Loop to check/setup for"),
    preset: Optional[str] = typer.Option(None, "--preset", help="Permission preset (research, implementation, full)"),
) -> None:
    """Manage Claude CLI permissions for a project."""
    from ralphx.core.permissions import PermissionManager

    if action not in ("setup", "check", "preset"):
        console.print(f"[red]Unknown action: {action}[/red]")
        console.print("Valid actions: setup, check, preset")
        raise typer.Exit(1)

    proj_manager = ProjectManager()
    proj = proj_manager.get_project(project)

    if not proj:
        console.print(f"[red]Project not found:[/red] {project}")
        raise typer.Exit(1)

    perm_manager = PermissionManager(proj.path)

    if action == "check":
        console.print(f"[bold]Permission check for:[/bold] {proj.name}\n")

        if loop_name:
            # Check specific loop
            project_db = proj_manager.get_project_db(proj.path)
            loader = LoopLoader(db=project_db)
            loop_config = loader.get_loop(loop_name)
            if not loop_config:
                console.print(f"[red]Loop not found:[/red] {loop_name}")
                raise typer.Exit(1)

            report = perm_manager.check_loop_permissions(loop_config)
        else:
            # Show current settings
            allowed = perm_manager.get_allowed_tools()
            blocked = perm_manager.get_blocked_tools()

            console.print(f"Settings file: {perm_manager.settings_path}")
            console.print(f"  Exists: {perm_manager.settings_exist()}")
            console.print(f"\nAllowed tools: {', '.join(allowed) if allowed else '(all)'}")
            console.print(f"Blocked tools: {', '.join(blocked) if blocked else '(none)'}")
            return

        # Show report
        table = Table(show_header=True, header_style="bold")
        table.add_column("Tool", style="cyan")
        table.add_column("Status")
        table.add_column("Source")

        for check in report.checks:
            if check.allowed:
                status = "[green]Allowed[/green]"
            elif check.blocked:
                status = "[red]Blocked[/red]"
            else:
                status = "[yellow]Missing[/yellow]"

            table.add_row(check.tool, status, check.source)

        console.print(table)
        console.print(f"\n{report.summary()}")

        if not report.all_allowed:
            raise typer.Exit(1)

    elif action == "setup":
        console.print(f"[bold]Permission setup for:[/bold] {proj.name}\n")

        if not loop_name:
            console.print("[red]Error:[/red] --loop is required for setup")
            raise typer.Exit(1)

        project_db = proj_manager.get_project_db(proj.path)
        loader = LoopLoader(db=project_db)
        loop_config = loader.get_loop(loop_name)
        if not loop_config:
            console.print(f"[red]Loop not found:[/red] {loop_name}")
            raise typer.Exit(1)

        # Auto-configure
        added = perm_manager.auto_configure(loop_config)

        if added:
            console.print(f"[green]Added tools:[/green] {', '.join(added)}")
        else:
            console.print("[green]All required tools already allowed[/green]")

        # Show suggested preset
        suggested = perm_manager.suggest_preset(loop_config)
        console.print(f"\n[dim]Suggested preset: {suggested}[/dim]")

    elif action == "preset":
        if not preset:
            console.print("[red]Error:[/red] --preset is required")
            console.print("Available presets: research, implementation, full")
            raise typer.Exit(1)

        console.print(f"[bold]Applying preset:[/bold] {preset}\n")

        try:
            perm_manager.apply_preset(preset)
            console.print(f"[green]Applied preset:[/green] {preset}")

            # Show what was set
            allowed = perm_manager.get_allowed_tools()
            blocked = perm_manager.get_blocked_tools()
            console.print(f"\nAllowed: {', '.join(allowed) if allowed else '(all)'}")
            console.print(f"Blocked: {', '.join(blocked) if blocked else '(none)'}")
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)


# =============================================================================
# Import Commands
# =============================================================================


@import_app.command("markdown")
def import_markdown(
    source: Path = typer.Argument(
        ...,
        help="Path to markdown file or glob pattern",
        exists=False,  # Allow globs
    ),
    project: str = typer.Option(..., "--project", "-p", help="Project slug"),
    loop: str = typer.Option(..., "--loop", "-l", help="Target loop name"),
    rename: Optional[str] = typer.Option(None, "--rename", "-r", help="Rename file"),
) -> None:
    """Import markdown file(s) into a loop's inputs directory."""
    from ralphx.core.import_manager import ImportManager

    proj_manager = ProjectManager()
    proj = proj_manager.get_project(project)

    if not proj:
        console.print(f"[red]Project not found:[/red] {project}")
        raise typer.Exit(1)

    import_manager = ImportManager(proj.path)

    # Check if source contains wildcards (glob pattern)
    source_str = str(source)
    if "*" in source_str or "?" in source_str:
        result = import_manager.import_markdown_glob(source_str, loop)
    else:
        if not source.exists():
            console.print(f"[red]File not found:[/red] {source}")
            raise typer.Exit(1)
        result = import_manager.import_markdown(source, loop, rename=rename)

    if result.success:
        console.print(f"[green]Imported {result.files_imported} file(s)[/green]")
        for path in result.paths:
            console.print(f"  - {path.name}")
    else:
        console.print("[red]Import failed:[/red]")
        for error in result.errors:
            console.print(f"  - {error}")
        raise typer.Exit(1)


@import_app.command("jsonl")
def import_jsonl(
    source: Path = typer.Argument(
        ...,
        help="Path to JSONL file",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    project: str = typer.Option(..., "--project", "-p", help="Project slug"),
    loop: str = typer.Option(..., "--loop", "-l", help="Source loop name for items"),
) -> None:
    """Import JSONL file as work items.

    Each line should be a JSON object with:
    - id: Item identifier (optional, auto-generated)
    - content: Item content (required)
    - priority, category, tags, metadata: Optional fields
    """
    from ralphx.core.import_manager import ImportManager

    proj_manager = ProjectManager()
    proj = proj_manager.get_project(project)

    if not proj:
        console.print(f"[red]Project not found:[/red] {project}")
        raise typer.Exit(1)

    project_db = proj_manager.get_project_db(proj.path)
    import_manager = ImportManager(proj.path, project_db)

    result = import_manager.import_jsonl(source, loop, proj.id)

    if result.success:
        console.print(f"[green]Imported {result.items_created} item(s)[/green]")
        if result.errors:
            console.print("[yellow]Warnings:[/yellow]")
            for error in result.errors:
                console.print(f"  - {error}")
    else:
        console.print("[red]Import failed:[/red]")
        for error in result.errors:
            console.print(f"  - {error}")
        raise typer.Exit(1)


@import_app.command("paste")
def import_paste(
    project: str = typer.Option(..., "--project", "-p", help="Project slug"),
    loop: str = typer.Option(..., "--loop", "-l", help="Target loop name"),
    filename: str = typer.Option(..., "--filename", "-f", help="Filename for content"),
) -> None:
    """Import content by pasting into stdin.

    Reads from stdin until EOF (Ctrl+D on Unix, Ctrl+Z on Windows).
    """
    import sys

    from ralphx.core.import_manager import ImportManager

    proj_manager = ProjectManager()
    proj = proj_manager.get_project(project)

    if not proj:
        console.print(f"[red]Project not found:[/red] {project}")
        raise typer.Exit(1)

    console.print("Paste content and press Ctrl+D (Unix) or Ctrl+Z (Windows) when done:")
    content = sys.stdin.read()

    if not content.strip():
        console.print("[red]No content provided[/red]")
        raise typer.Exit(1)

    import_manager = ImportManager(proj.path)
    result = import_manager.import_paste(content, loop, filename)

    if result.success:
        console.print(f"[green]Created file:[/green] {result.paths[0].name}")
    else:
        console.print("[red]Import failed:[/red]")
        for error in result.errors:
            console.print(f"  - {error}")
        raise typer.Exit(1)


@import_app.command("list")
def list_imports(
    project: str = typer.Option(..., "--project", "-p", help="Project slug"),
    loop: str = typer.Option(..., "--loop", "-l", help="Loop name"),
) -> None:
    """List input files for a loop."""
    from ralphx.core.import_manager import ImportManager

    proj_manager = ProjectManager()
    proj = proj_manager.get_project(project)

    if not proj:
        console.print(f"[red]Project not found:[/red] {project}")
        raise typer.Exit(1)

    import_manager = ImportManager(proj.path)
    files = import_manager.list_inputs(loop)

    if not files:
        console.print(f"[yellow]No input files for loop:[/yellow] {loop}")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Size")
    table.add_column("Modified")

    for f in files:
        size_kb = f["size"] / 1024
        table.add_row(f["name"], f"{size_kb:.1f} KB", f["modified"][:19])

    console.print(table)


# =============================================================================
# MCP Command
# =============================================================================


@app.command("mcp")
def mcp_server() -> None:
    """Start the MCP server for Claude Code integration.

    This command starts the MCP (Model Context Protocol) server that exposes
    67 tools for full RalphX management through Claude Code.

    To add RalphX to Claude Code, run:
        Linux/Mac: claude mcp add ralphx -e PYTHONDONTWRITEBYTECODE=1 -- "$(which ralphx)" mcp
        Mac (zsh): if "which" fails, first run: conda init zsh && source ~/.zshrc
        Windows:   find path with "where.exe ralphx", then:
                   claude mcp add ralphx -e PYTHONDONTWRITEBYTECODE=1 -- C:\\path\\to\\ralphx.exe mcp

    Then in Claude Code, you can ask Claude to:
        - Manage projects (add, remove, list, diagnose)
        - Control loops (start, stop, configure, validate)
        - Create and run workflows (multi-step task pipelines)
        - Track work items (user stories, tasks, research notes)
        - Monitor runs and view logs
        - Set up permissions and guardrails
        - Import content and manage resources
        - Run system health checks and diagnostics

    Example prompts:
        "List my RalphX projects"
        "Start the planning loop on my-app"
        "Create a workflow for implementing the auth feature"
        "Why did the last run fail?"
        "Check if my system is set up correctly"
    """
    from ralphx.mcp_server import main as mcp_main

    mcp_main()


# =============================================================================
# Entry Point
# =============================================================================


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
