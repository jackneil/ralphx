"""FastAPI application for RalphX API server."""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, status
from pydantic import BaseModel

from ralphx.core.workspace import get_workspace_path


def _private_log_file() -> Path:
    """Return the server log path in the workspace, created owner-only (0600).

    The log used to live in /tmp, where every local user can read it.
    """
    log_dir = get_workspace_path() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "server.log"
    fd = os.open(log_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.close(fd)
    if os.name == "posix":
        os.chmod(log_file, 0o600)
    return log_file


# Configure logging to file and console
LOG_FILE = _private_log_file()
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a"),
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger(__name__)
logger.info(f"RalphX API server starting - logging to {LOG_FILE}")
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ralphx import __version__
from ralphx.api.routes import auth, config, export_import, files, filesystem, imports, items, logs, loops, planning, projects, resources, runs, stream, templates, workflows
from ralphx.api.security import SESSION_COOKIE, LocalAccessGuard
from ralphx.core.api_auth import get_api_token, token_matches
from ralphx.core.auth import restore_orphaned_backup
from ralphx.core.workspace import ensure_workspace

# Frontend static files directory
# Check two locations: package static dir (pip install) and dev frontend/dist
_PACKAGE_STATIC_DIR = Path(__file__).parent.parent / "static"
_DEV_FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend" / "dist"

# Use package static dir if it exists (pip install), otherwise dev dir
FRONTEND_DIR = _PACKAGE_STATIC_DIR if _PACKAGE_STATIC_DIR.exists() else _DEV_FRONTEND_DIR

# Token refresh interval: 30 minutes (aggressive to keep tokens fresh)
TOKEN_REFRESH_INTERVAL = 1800

# Log cleanup interval: 24 hours
LOG_CLEANUP_INTERVAL = 86400

# Stale run cleanup interval: 2 minutes
STALE_RUN_CLEANUP_INTERVAL = 120


async def _token_refresh_loop():
    """Background task to refresh tokens every 30 minutes."""
    while True:
        await asyncio.sleep(TOKEN_REFRESH_INTERVAL)
        try:
            from ralphx.core.auth import refresh_all_expiring_tokens

            # Refresh tokens within 4 hours of expiry (more aggressive)
            result = await refresh_all_expiring_tokens(buffer_seconds=14400)
            if result["refreshed"] > 0 or result["failed"] > 0:
                logger.info(
                    f"Token refresh: checked={result['checked']}, "
                    f"refreshed={result['refreshed']}, failed={result['failed']}"
                )
        except Exception as e:
            logger.warning(f"Token refresh error: {e}")


async def _log_cleanup_loop():
    """Background task to clean up old logs daily."""
    from ralphx.core.database import Database

    while True:
        await asyncio.sleep(LOG_CLEANUP_INTERVAL)
        try:
            db = Database()
            deleted = db.cleanup_old_logs(days=30)
            if deleted > 0:
                logger.info(f"Log cleanup: deleted {deleted} entries older than 30 days")
        except Exception as e:
            logger.warning(f"Log cleanup error: {e}")


async def _stale_run_cleanup_loop():
    """Background task to clean up stale runs every 2 minutes.

    Detects runs that are stuck in 'running' status but whose executor
    process has died (checked via PID) or hasn't had activity for too long.
    """
    from ralphx.core.database import Database
    from ralphx.core.doctor import cleanup_stale_runs
    from ralphx.core.project_db import ProjectDatabase

    while True:
        await asyncio.sleep(STALE_RUN_CLEANUP_INTERVAL)
        try:
            # Get all projects and clean up stale runs in each
            db = Database()
            projects = db.list_projects()

            total_cleaned = 0
            for project in projects:
                try:
                    project_path = Path(project.get("path", ""))
                    if project_path.exists():
                        project_db = ProjectDatabase(project_path)
                        cleaned = cleanup_stale_runs(
                            project_db,
                            max_inactivity_minutes=15,
                        )
                        total_cleaned += len(cleaned)
                except Exception as e:
                    logger.debug(f"Stale run cleanup error for {project.get('slug')}: {e}")

            if total_cleaned > 0:
                logger.info(f"Stale run cleanup: marked {total_cleaned} stale runs as aborted")
        except Exception as e:
            logger.warning(f"Stale run cleanup error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    from ralphx.core.logger import system_log
    from ralphx.core.sample_project import ensure_sample_project_created

    # Startup
    ensure_workspace()

    # Boot guard: refuse to start without a usable API token. This raises
    # APITokenError when RALPHX_API_TOKEN is too short or the token file
    # cannot be created or read.
    get_api_token()

    # Create sample project on first run
    try:
        ensure_sample_project_created()
    except Exception as e:
        logger.warning(f"Sample project creation failed: {e}")

    # Restore any orphaned credential backups from previous crashes
    # This ensures user's main credentials are ALWAYS restored
    restore_orphaned_backup()

    # Start background tasks
    refresh_task = asyncio.create_task(_token_refresh_loop())
    cleanup_task = asyncio.create_task(_log_cleanup_loop())
    stale_run_task = asyncio.create_task(_stale_run_cleanup_loop())
    logger.info("Started background tasks (token refresh, log cleanup, stale run cleanup)")

    # Log server startup
    system_log.info("startup", f"Server started (v{__version__})")

    yield

    # Log server shutdown
    system_log.info("shutdown", "Server stopped")

    # Shutdown: cancel background tasks
    refresh_task.cancel()
    cleanup_task.cancel()
    stale_run_task.cancel()
    try:
        await refresh_task
    except asyncio.CancelledError:
        pass
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    try:
        await stale_run_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="RalphX API",
    description="Generic agent loop orchestration system with web dashboard.",
    version=__version__,
    lifespan=lifespan,
)

# Access guard: Host check (DNS rebinding), Origin check (cross-site pages)
# and the API token on every /api route. There is no CORS middleware: the
# dashboard is served from the same origin, so no cross-origin page may read
# an API response.
app.add_middleware(LocalAccessGuard)


# Error response model
class ErrorResponse:
    """Standard error response."""

    def __init__(
        self,
        message: str,
        detail: Any = None,
        code: str = "error",
    ):
        self.message = message
        self.detail = detail
        self.code = code

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {"error": {"message": self.message, "code": self.code}}
        if self.detail:
            result["error"]["detail"] = self.detail
        return result


# Exception handlers
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle ValueError exceptions."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ErrorResponse(str(exc), code="validation_error").to_dict(),
    )


@app.exception_handler(FileNotFoundError)
async def not_found_handler(request: Request, exc: FileNotFoundError):
    """Handle FileNotFoundError exceptions."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=ErrorResponse(str(exc), code="not_found").to_dict(),
    )


@app.exception_handler(FileExistsError)
async def exists_handler(request: Request, exc: FileExistsError):
    """Handle FileExistsError exceptions."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=ErrorResponse(str(exc), code="already_exists").to_dict(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions.

    Note: Exception details are intentionally NOT exposed to prevent
    leaking internal paths, stack traces, or sensitive information.
    Errors are logged server-side for debugging.
    """
    # Log the actual exception for debugging (server-side only)
    import logging
    logging.exception("Unhandled exception: %s", exc)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            "An internal error occurred",
            code="internal_error",
        ).to_dict(),
    )


# Dashboard session (exchanges the API token for an HttpOnly cookie)
SESSION_MAX_AGE = 30 * 24 * 3600


class SessionRequest(BaseModel):
    """Body of POST /api/session."""

    token: str


@app.post("/api/session")
async def create_session(body: SessionRequest, request: Request):
    """Log the dashboard in: check the API token and set the session cookie."""
    if not token_matches(body.token):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=ErrorResponse("Invalid token", code="unauthorized").to_dict(),
        )
    response = JSONResponse({"authenticated": True})
    response.set_cookie(
        SESSION_COOKIE,
        body.token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/session")
async def get_session():
    """Return 200 when the request is authenticated (the guard returns 401 otherwise)."""
    return {"authenticated": True}


@app.delete("/api/session")
async def delete_session():
    """Log the dashboard out: clear the session cookie."""
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict")
    return response


# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Check API health status."""
    return {
        "status": "healthy",
        "version": __version__,
        "timestamp": datetime.utcnow().isoformat(),
    }


# Include routers
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(loops.router, prefix="/api/projects", tags=["loops"])
app.include_router(items.router, prefix="/api/projects", tags=["items"])
app.include_router(stream.router, prefix="/api/projects", tags=["streaming"])
app.include_router(runs.router, prefix="/api/projects", tags=["runs"])
app.include_router(filesystem.router, prefix="/api/filesystem", tags=["filesystem"])
app.include_router(templates.router, prefix="/api", tags=["templates"])
app.include_router(imports.router, prefix="/api/projects", tags=["imports"])
app.include_router(resources.router, prefix="/api/projects", tags=["resources"])
app.include_router(files.router, prefix="/api/projects", tags=["files"])
app.include_router(logs.router, prefix="/api", tags=["logs"])
app.include_router(config.router, prefix="/api/projects", tags=["config"])
app.include_router(workflows.router, prefix="/api/projects/{slug}", tags=["workflows"])
app.include_router(planning.router, prefix="/api/projects/{slug}", tags=["planning"])
app.include_router(export_import.router, prefix="/api/projects/{slug}", tags=["export-import"])


# Root endpoint
@app.get("/api")
async def root():
    """API root endpoint."""
    return {
        "name": "RalphX API",
        "version": __version__,
        "docs": "/docs",
        "health": "/api/health",
    }


# Static files and SPA routing
if FRONTEND_DIR.exists():
    # Serve static assets (only if assets directory exists)
    _assets_dir = FRONTEND_DIR / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    # Catch-all for SPA routing (must be last)
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the SPA for all non-API routes."""
        # Don't serve SPA for API routes
        if full_path.startswith("api/"):
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": {"message": "Not found", "code": "not_found"}},
            )

        # Serve static files if they exist
        # SECURITY: Resolve path and verify it's under FRONTEND_DIR to prevent
        # path traversal attacks (e.g., requests for "../../etc/passwd")
        file_path = (FRONTEND_DIR / full_path).resolve()
        frontend_resolved = FRONTEND_DIR.resolve()

        # Check that resolved path is under frontend directory
        try:
            file_path.relative_to(frontend_resolved)
        except ValueError:
            # Path traversal attempt - path is outside FRONTEND_DIR
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": {"message": "Invalid path", "code": "bad_request"}},
            )

        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        # Otherwise serve index.html for SPA routing
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)

        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": {"message": "Frontend not built", "code": "not_found"}},
        )
