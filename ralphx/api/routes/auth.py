"""Authentication routes for Claude Code credentials."""

import asyncio
import secrets
from typing import Literal, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ralphx.core.auth import (
    AuthStatus,
    clear_credentials,
    get_auth_status,
    store_oauth_tokens,
)
from ralphx.core.database import Database
from ralphx.core.oauth import OAuthFlow

router = APIRouter(prefix="/auth", tags=["auth"])

# Track active OAuth flows
_active_flows: dict[str, asyncio.Task] = {}


class LoginRequest(BaseModel):
    """Request body for login endpoint."""

    scope: Literal["project", "global"] = "global"
    project_path: Optional[str] = None  # Path to project directory


def _get_project_id(project_path: Optional[str]) -> Optional[str]:
    """Look up project ID from path."""
    if not project_path:
        return None
    db = Database()
    # Find project by path
    projects = db.list_projects()
    for project in projects:
        if project["path"] == project_path:
            return project["id"]
    return None


@router.get("/status")
async def get_status(
    project_path: Optional[str] = Query(
        None, description="Project path for scoped credentials"
    ),
) -> AuthStatus:
    """Get authentication status from database (project-specific, then global)."""
    project_id = _get_project_id(project_path)
    return get_auth_status(project_id)


@router.post("/login")
async def start_login(request: LoginRequest):
    """Start OAuth flow - opens browser for authentication.

    Flow:
    1. Starts localhost callback server
    2. Opens browser to Anthropic OAuth
    3. User authorizes
    4. Callback receives code, exchanges for tokens
    5. Tokens stored in database
    """
    project_id = _get_project_id(request.project_path)

    async def run_flow():
        flow = OAuthFlow()
        result = await flow.start()
        if result.get("success"):
            tokens = result["tokens"]
            store_oauth_tokens(tokens, request.scope, project_id)
        return result

    flow_id = secrets.token_urlsafe(8)
    task = asyncio.create_task(run_flow())
    _active_flows[flow_id] = task

    # Clean up completed flows
    for fid in list(_active_flows.keys()):
        if _active_flows[fid].done():
            del _active_flows[fid]

    return {
        "success": True,
        "flow_id": flow_id,
        "message": "Browser opened for authentication",
        "scope": request.scope,
    }


@router.get("/flow/{flow_id}")
async def get_flow_status(flow_id: str):
    """Check status of an OAuth flow."""
    if flow_id not in _active_flows:
        return {"status": "not_found"}

    task = _active_flows[flow_id]
    if task.done():
        try:
            result = task.result()
            del _active_flows[flow_id]
            return {"status": "completed", "result": result}
        except Exception as e:
            del _active_flows[flow_id]
            return {"status": "error", "error": str(e)}

    return {"status": "pending"}


@router.post("/logout")
async def logout(request: LoginRequest):
    """Clear credentials for the specified scope from database."""
    project_id = _get_project_id(request.project_path)
    clear_credentials(request.scope, project_id)
    return {"success": True}
