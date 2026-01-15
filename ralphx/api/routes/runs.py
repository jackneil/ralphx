"""Run history API routes."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from ralphx.api.routes.loops import get_managers

router = APIRouter()


@router.get("/{slug}/runs")
async def list_runs(
    slug: str,
    loop_name: Optional[str] = Query(None),
    run_status: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
):
    """List all runs for a project."""
    manager, project, project_db = get_managers(slug)

    # Get runs from project database (supports loop_name and status filtering)
    runs = project_db.list_runs(
        loop_name=loop_name,
        status=run_status,
        limit=limit,
    )

    return [
        {
            "id": r["id"],
            "project_id": project.id,
            "loop_name": r["loop_name"],
            "status": r.get("status", "unknown"),
            "iterations_completed": r.get("iterations_completed", 0),
            "items_generated": r.get("items_generated", 0),
            "started_at": r.get("started_at"),
            "completed_at": r.get("completed_at"),
        }
        for r in runs
    ]


@router.get("/{slug}/runs/{run_id}")
async def get_run(slug: str, run_id: str):
    """Get run details with sessions."""
    manager, project, project_db = get_managers(slug)

    run = project_db.get_run(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )

    # Get sessions for this run
    sessions = project_db.list_sessions(run_id=run_id)

    return {
        "id": run["id"],
        "project_id": project.id,
        "loop_name": run["loop_name"],
        "status": run.get("status", "unknown"),
        "iterations_completed": run.get("iterations_completed", 0),
        "items_generated": run.get("items_generated", 0),
        "started_at": run.get("started_at"),
        "completed_at": run.get("completed_at"),
        "sessions": [
            {
                "session_id": s["session_id"],
                "iteration": s.get("iteration", 0),
                "mode": s.get("mode"),
                "status": s.get("status", "unknown"),
                "started_at": s.get("started_at"),
                "duration_seconds": s.get("duration_seconds"),
            }
            for s in sessions
        ],
    }
