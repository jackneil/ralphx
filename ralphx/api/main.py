"""FastAPI application for RalphX API server."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, status

logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ralphx import __version__
from ralphx.api.routes import auth, files, filesystem, imports, items, logs, loops, projects, resources, runs, stream, templates
from ralphx.core.workspace import ensure_workspace

# Frontend dist directory (relative to this file)
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend" / "dist"

# Token refresh interval: 30 minutes (aggressive to keep tokens fresh)
TOKEN_REFRESH_INTERVAL = 1800

# Log cleanup interval: 24 hours
LOG_CLEANUP_INTERVAL = 86400


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    from ralphx.core.logger import system_log

    # Startup
    ensure_workspace()

    # Start background tasks
    refresh_task = asyncio.create_task(_token_refresh_loop())
    cleanup_task = asyncio.create_task(_log_cleanup_loop())
    logger.info("Started background tasks (token refresh, log cleanup)")

    # Log server startup
    system_log.info("startup", f"Server started (v{__version__})")

    yield

    # Log server shutdown
    system_log.info("shutdown", "Server stopped")

    # Shutdown: cancel background tasks
    refresh_task.cancel()
    cleanup_task.cancel()
    try:
        await refresh_task
    except asyncio.CancelledError:
        pass
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="RalphX API",
    description="Generic agent loop orchestration system with web dashboard.",
    version=__version__,
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    # Serve static assets
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

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
