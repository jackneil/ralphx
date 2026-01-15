"""Claude credential management with SQLite storage.

Stores OAuth credentials in database with support for:
- Global credentials (default for all projects)
- Project-specific credentials (override global)
- Auto-refresh of expired tokens
- Credential swap for loop execution
"""

import fcntl
import json
import shutil
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Literal, Optional

import httpx
from pydantic import BaseModel

from ralphx.core.database import Database

# Claude Code's credential location (hardcoded, cannot be changed)
CLAUDE_CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
CLAUDE_CREDENTIALS_BACKUP = Path.home() / ".claude" / ".credentials.backup.json"
CREDENTIAL_LOCK_PATH = Path.home() / ".claude" / ".credentials.lock"

# OAuth configuration
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"


class AuthStatus(BaseModel):
    """Authentication status."""

    connected: bool
    scope: Optional[Literal["project", "global"]] = None
    email: Optional[str] = None  # User's email address
    subscription_type: Optional[str] = None
    rate_limit_tier: Optional[str] = None
    expires_at: Optional[datetime] = None
    expires_in_seconds: Optional[int] = None
    is_expired: bool = False
    using_global_fallback: bool = False  # True if project using global creds
    has_project_credentials: bool = False  # True if project has its own creds


def get_auth_status(project_id: Optional[str] = None) -> AuthStatus:
    """Get auth status from database (project-specific first, then global).

    Returns detailed status including whether project is using global fallback.
    """
    db = Database()

    # Check for project-specific credentials (no fallback)
    project_creds = None
    if project_id:
        project_creds = db.get_credentials_by_scope("project", project_id)

    # Check for global credentials
    global_creds = db.get_credentials_by_scope("global", None)

    # Determine which credentials to use (project takes priority)
    creds = project_creds or global_creds

    # Determine if we're using global as a fallback for a project
    using_fallback = (
        project_id is not None
        and project_creds is None
        and global_creds is not None
    )

    if not creds:
        return AuthStatus(
            connected=False,
            has_project_credentials=project_creds is not None,
        )

    # Check expiry
    now = int(time.time())
    expires_at = creds["expires_at"]
    is_expired = now >= expires_at

    return AuthStatus(
        connected=True,
        scope=creds["scope"],
        email=creds.get("email"),
        expires_at=datetime.fromtimestamp(expires_at),
        expires_in_seconds=max(0, expires_at - now),
        is_expired=is_expired,
        using_global_fallback=using_fallback,
        has_project_credentials=project_creds is not None,
    )


def store_oauth_tokens(
    tokens: dict,
    scope: Literal["project", "global"],
    project_id: Optional[str] = None,
) -> bool:
    """Store OAuth tokens in database.

    Args:
        tokens: Dict with access_token, refresh_token, expires_in, email (optional)
        scope: "project" or "global"
        project_id: Project ID for project-scoped credentials
    """
    db = Database()
    expires_at = int(time.time()) + tokens.get("expires_in", 28800)

    db.store_credentials(
        scope=scope,
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token"),
        expires_at=expires_at,
        project_id=project_id if scope == "project" else None,
        email=tokens.get("email"),
    )
    return True


async def refresh_token_if_needed(project_id: Optional[str] = None) -> bool:
    """Auto-refresh token if expired. Returns True if valid token available.

    Args:
        project_id: Optional project ID to check for project-scoped creds

    Returns:
        True if valid credentials exist (either not expired or successfully refreshed)
        False if no credentials or refresh failed
    """
    db = Database()
    creds = db.get_credentials(project_id)

    if not creds:
        return False

    now = int(time.time())
    # 5 minute buffer before expiry
    if now < creds["expires_at"] - 300:
        return True  # Token still valid

    if not creds.get("refresh_token"):
        return False  # No refresh token, can't refresh

    # Attempt to refresh the token
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                TOKEN_URL,
                json={
                    "grant_type": "refresh_token",
                    "refresh_token": creds["refresh_token"],
                    "client_id": CLIENT_ID,
                },
                headers={"Content-Type": "application/json"},
            )

            if resp.status_code != 200:
                return False

            tokens = resp.json()
            new_expires_at = int(time.time()) + tokens.get("expires_in", 28800)

            # Extract email from account field if present
            account = tokens.get("account", {})
            email = account.get("email_address")

            db.update_credentials(
                creds["id"],
                access_token=tokens["access_token"],
                refresh_token=tokens.get("refresh_token", creds["refresh_token"]),
                expires_at=new_expires_at,
                email=email if email else creds.get("email"),
            )
            return True
    except Exception:
        return False


def clear_credentials(
    scope: Literal["project", "global"],
    project_id: Optional[str] = None,
) -> bool:
    """Remove credentials for the specified scope from database."""
    db = Database()
    return db.delete_credentials(scope, project_id if scope == "project" else None)


@contextmanager
def swap_credentials_for_loop(
    project_id: Optional[str] = None,
) -> Generator[bool, None, None]:
    """Context manager: backup user creds, write from DB, restore after.

    Uses file locking to prevent race conditions when multiple loops run
    concurrently.

    Usage:
        with swap_credentials_for_loop(project_id) as has_creds:
            if has_creds:
                process = subprocess.Popen(["claude", ...])
            else:
                raise AuthError("No credentials")

    Args:
        project_id: Project ID to get credentials for

    Yields:
        True if credentials were written, False if no credentials available
    """
    db = Database()
    creds = db.get_credentials(project_id)

    # Acquire exclusive lock to prevent concurrent credential access
    CREDENTIAL_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(CREDENTIAL_LOCK_PATH, "w")

    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)  # Exclusive lock

        # Backup user's current credentials
        had_backup = False
        if CLAUDE_CREDENTIALS_PATH.exists():
            shutil.copy2(CLAUDE_CREDENTIALS_PATH, CLAUDE_CREDENTIALS_BACKUP)
            had_backup = True

        # Write credentials from DB to Claude's location
        has_creds = False
        if creds:
            creds_data = {
                "claudeAiOauth": {
                    "accessToken": creds["access_token"],
                    "refreshToken": creds["refresh_token"],
                    "expiresAt": creds["expires_at"] * 1000,  # Convert to milliseconds
                }
            }
            CLAUDE_CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
            CLAUDE_CREDENTIALS_PATH.write_text(json.dumps(creds_data, indent=2))
            has_creds = True

        try:
            yield has_creds
        finally:
            # Restore user's original credentials
            if had_backup and CLAUDE_CREDENTIALS_BACKUP.exists():
                shutil.copy2(CLAUDE_CREDENTIALS_BACKUP, CLAUDE_CREDENTIALS_PATH)
                CLAUDE_CREDENTIALS_BACKUP.unlink()
            elif CLAUDE_CREDENTIALS_BACKUP.exists():
                CLAUDE_CREDENTIALS_BACKUP.unlink()
            elif not had_backup and has_creds:
                # We wrote credentials but user had none originally - remove them
                CLAUDE_CREDENTIALS_PATH.unlink(missing_ok=True)
    finally:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()
