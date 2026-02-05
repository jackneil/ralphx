"""Diagnostics MCP tools.

Tools for system health and diagnostics:
- ralphx_check_system_health: System-wide health checks
- ralphx_diagnose_project: Project-specific diagnostics
- ralphx_get_stop_reason: Explain last run failure
- ralphx_list_stale_runs: Detect stale/zombie runs
- ralphx_cleanup_stale_runs: Clean stale runs
"""

from typing import Optional

from ralphx.mcp.base import (
    MCPError,
    PaginatedResult,
    ToolDefinition,
    ToolError,
    make_schema,
    prop_bool,
    prop_int,
    prop_string,
    scrub_sensitive_data,
    validate_pagination,
)
from ralphx.mcp.tools.projects import get_manager


def check_system_health() -> dict:
    """Run system-wide health checks.

    Checks:
    - Python version
    - Node.js availability
    - Claude CLI installation and auth
    - Network connectivity
    - Required dependencies
    """
    try:
        from ralphx.core.doctor import DoctorCheck, CheckStatus

        doctor = DoctorCheck()
        report = doctor.run_all()

        checks = []
        for check in report.checks:
            passed = check.status == CheckStatus.OK
            checks.append({
                "name": check.name,
                "status": check.status.value,
                "passed": passed,
                "message": check.message,
                "details": check.details,
                "fix_hint": check.fix_hint,
            })

        passed_count = sum(1 for c in report.checks if c.status == CheckStatus.OK)
        failed_count = sum(1 for c in report.checks if c.status == CheckStatus.ERROR)
        warning_count = sum(1 for c in report.checks if c.status == CheckStatus.WARNING)

        return {
            "healthy": not report.has_errors,
            "checks": checks,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "warning_count": warning_count,
        }
    except ImportError:
        # Fallback if DoctorCheck not available
        return {
            "healthy": True,
            "checks": [],
            "message": "Health check module not available",
        }
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Health check failed: {e}",
            details={},
        )


def diagnose_project(slug: str) -> dict:
    """Run project-specific diagnostics.

    Checks:
    - Database integrity
    - Loop configurations
    - Workflow states
    - Resource availability
    - Permission settings
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    diagnostics = {
        "project": {
            "slug": project.slug,
            "name": project.name,
            "path": str(project.path),  # Ensure Path is converted to string for JSON
        },
        "checks": [],
        "issues": [],
        "warnings": [],
    }

    project_db = manager.get_project_db(project.path)

    # Check database
    try:
        project_db.check_integrity()
        diagnostics["checks"].append({
            "name": "database_integrity",
            "passed": True,
            "message": "Database integrity OK",
        })
    except Exception as e:
        diagnostics["checks"].append({
            "name": "database_integrity",
            "passed": False,
            "message": f"Database issue: {e}",
        })
        diagnostics["issues"].append(f"Database integrity check failed: {e}")

    # Check for stale runs
    try:
        from ralphx.core.doctor import detect_stale_runs

        stale = detect_stale_runs(project_db)
        if stale:
            diagnostics["warnings"].append(f"Found {len(stale)} stale runs")
            diagnostics["checks"].append({
                "name": "stale_runs",
                "passed": False,
                "message": f"Found {len(stale)} stale/zombie runs",
                "details": {"stale_run_ids": [r["id"] for r in stale[:5]]},
            })
        else:
            diagnostics["checks"].append({
                "name": "stale_runs",
                "passed": True,
                "message": "No stale runs detected",
            })
    except Exception as e:
        diagnostics["warnings"].append(f"Could not check for stale runs: {e}")

    # Check workflows
    try:
        workflows = project_db.list_workflows()
        active_workflows = [w for w in workflows if w["status"] == "active"]
        diagnostics["checks"].append({
            "name": "workflows",
            "passed": True,
            "message": f"Found {len(workflows)} workflows ({len(active_workflows)} active)",
            "details": {
                "total": len(workflows),
                "active": len(active_workflows),
            },
        })
    except Exception as e:
        diagnostics["issues"].append(f"Workflow check failed: {e}")

    # Check loops
    try:
        loops = manager.list_loops(slug)
        diagnostics["checks"].append({
            "name": "loops",
            "passed": True,
            "message": f"Found {len(loops)} configured loops",
            "details": {"loop_names": [l.name for l in loops]},
        })
    except Exception as e:
        diagnostics["warnings"].append(f"Loop check failed: {e}")

    # Summary
    passed = sum(1 for c in diagnostics["checks"] if c.get("passed"))
    failed = sum(1 for c in diagnostics["checks"] if not c.get("passed"))

    diagnostics["summary"] = {
        "passed": passed,
        "failed": failed,
        "warnings": len(diagnostics["warnings"]),
        "issues": len(diagnostics["issues"]),
        "healthy": failed == 0 and len(diagnostics["issues"]) == 0,
    }

    return diagnostics


def get_stop_reason(
    slug: str,
    run_id: Optional[str] = None,
) -> dict:
    """Explain why the last run stopped or failed.

    If run_id is not provided, uses the most recent run.
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    # Get the run
    if run_id:
        run = project_db.get_run(run_id)
        if not run:
            raise ToolError.run_not_found(run_id)
    else:
        # Get most recent run
        runs = project_db.list_runs(limit=1)
        if not runs:
            return {
                "message": "No runs found",
                "reason": None,
            }
        run = runs[0]

    result = {
        "run_id": run["id"],
        "loop_name": run.get("loop_name"),
        "status": run["status"],
        "started_at": run.get("started_at"),
        "completed_at": run.get("completed_at"),
    }

    # Analyze stop reason
    status = run["status"]
    if status == "completed":
        result["reason"] = "Run completed successfully"
        result["category"] = "success"
    elif status == "error":
        error_msg = run.get("error_message", "Unknown error")
        result["reason"] = scrub_sensitive_data(error_msg) if error_msg else "Unknown error"
        result["category"] = "error"

        # Try to get more details from last session
        sessions = project_db.list_sessions(run_id=run["id"])
        if sessions:
            last_session = sessions[-1]
            events = project_db.get_session_events(
                session_id=last_session.get("session_id", last_session.get("id")),
                event_type="error",
                limit=5,
            )
            if events:
                result["last_errors"] = [
                    {
                        "timestamp": e.get("timestamp"),
                        "message": scrub_sensitive_data(e.get("content", "")[:500]),
                    }
                    for e in events
                ]
    elif status == "aborted":
        result["reason"] = "Run was manually stopped or aborted"
        result["category"] = "aborted"
    elif status == "paused":
        result["reason"] = "Run is paused"
        result["category"] = "paused"
    elif status == "running":
        result["reason"] = "Run is still active"
        result["category"] = "running"
    else:
        result["reason"] = f"Unknown status: {status}"
        result["category"] = "unknown"

    # Check for permission issues
    if run.get("error_message") and "permission" in run.get("error_message", "").lower():
        result["suggestion"] = "Run ralphx_check_permissions to diagnose permission issues"

    return result


def list_stale_runs(
    slug: str,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Detect stale/zombie runs.

    Runs are considered stale if:
    - Status is 'running' but executor process is not alive
    - No activity for extended period (configurable timeout)
    """
    limit, offset = validate_pagination(limit, offset)
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    try:
        from ralphx.core.doctor import detect_stale_runs

        stale_runs = detect_stale_runs(project_db)
    except ImportError:
        # Fallback detection
        runs = project_db.list_runs(status="running")
        stale_runs = []
        for run in runs:
            # Check if process is alive
            pid = run.get("executor_pid")
            if pid:
                import os
                try:
                    os.kill(pid, 0)
                except OSError:
                    stale_runs.append(run)
            else:
                # No PID means likely stale
                stale_runs.append(run)
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to detect stale runs: {e}",
            details={"slug": slug},
        )

    total = len(stale_runs)
    paginated = stale_runs[offset : offset + limit]

    return PaginatedResult(
        items=[
            {
                "id": r["id"],
                "loop_name": r.get("loop_name"),
                "workflow_id": r.get("workflow_id"),
                "executor_pid": r.get("executor_pid"),
                "started_at": r.get("started_at"),
                "last_activity_at": r.get("last_activity_at"),
            }
            for r in paginated
        ],
        total=total,
        limit=limit,
        offset=offset,
    ).to_dict()


def cleanup_stale_runs(
    slug: str,
    dry_run: bool = True,
) -> dict:
    """Clean up stale/zombie runs.

    Marks stale runs as 'aborted' so they don't block new runs.

    Args:
        slug: Project slug
        dry_run: If True, only report what would be cleaned (default: True)
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    try:
        from ralphx.core.doctor import detect_stale_runs, cleanup_stale_runs as do_cleanup

        stale_runs = detect_stale_runs(project_db)

        if dry_run:
            return {
                "dry_run": True,
                "would_clean": len(stale_runs),
                "runs": [
                    {
                        "id": r["id"],
                        "loop_name": r.get("loop_name"),
                        "started_at": r.get("started_at"),
                    }
                    for r in stale_runs
                ],
                "message": f"Would mark {len(stale_runs)} stale runs as aborted",
            }

        cleaned = do_cleanup(project_db, dry_run=False)

        return {
            "dry_run": False,
            "cleaned": len(cleaned),
            "runs": [
                {
                    "id": r["id"],
                    "loop_name": r.get("loop_name"),
                }
                for r in cleaned
            ],
            "message": f"Marked {len(cleaned)} stale runs as aborted",
        }
    except ImportError:
        # Fallback cleanup
        runs = project_db.list_runs(status="running")
        stale_runs = []
        for run in runs:
            pid = run.get("executor_pid")
            is_stale = False
            if pid:
                import os
                try:
                    os.kill(pid, 0)
                except OSError:
                    is_stale = True
            else:
                is_stale = True

            if is_stale:
                stale_runs.append(run)

        if dry_run:
            return {
                "dry_run": True,
                "would_clean": len(stale_runs),
                "runs": [{"id": r["id"], "loop_name": r.get("loop_name")} for r in stale_runs],
            }

        for run in stale_runs:
            project_db.update_run(run["id"], status="aborted")

        return {
            "dry_run": False,
            "cleaned": len(stale_runs),
            "runs": [{"id": r["id"]} for r in stale_runs],
        }
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to cleanup stale runs: {e}",
            details={"slug": slug},
        )


def get_diagnostics_tools() -> list[ToolDefinition]:
    """Get all diagnostics tool definitions."""
    return [
        ToolDefinition(
            name="ralphx_check_system_health",
            description="Run system-wide health checks (Python, Node.js, Claude CLI, network)",
            handler=check_system_health,
            input_schema=make_schema(
                properties={},
                required=[],
            ),
        ),
        ToolDefinition(
            name="ralphx_diagnose_project",
            description="Run comprehensive project diagnostics (database, workflows, loops, resources)",
            handler=diagnose_project,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_get_stop_reason",
            description="Explain why a run stopped or failed. Uses most recent run if run_id not provided.",
            handler=get_stop_reason,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "run_id": prop_string("Run ID (optional, defaults to most recent)"),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_list_stale_runs",
            description="Detect stale/zombie runs that are marked running but process is dead",
            handler=list_stale_runs,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "limit": prop_int("Max runs to return (1-500)", minimum=1, maximum=500),
                    "offset": prop_int("Number of runs to skip", minimum=0),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_cleanup_stale_runs",
            description="Clean up stale/zombie runs by marking them as aborted",
            handler=cleanup_stale_runs,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "dry_run": prop_bool("Only report what would be cleaned (default: true)"),
                },
                required=["slug"],
            ),
        ),
    ]
