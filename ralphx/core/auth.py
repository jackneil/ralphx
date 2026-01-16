"""Claude credential management with SQLite storage.

Stores OAuth credentials in database with support for:
- Global credentials (default for all projects)
- Project-specific credentials (override global)
- Auto-refresh of expired tokens
- Credential swap for loop execution
"""

import asyncio
import fcntl
import json
import shutil
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Generator, Literal, Optional

import httpx
from pydantic import BaseModel

from ralphx.core.database import Database
from ralphx.core.logger import auth_log


class InvalidGrantError(Exception):
    """Raised when OAuth refresh token is invalid/expired."""
    pass

# Claude Code's credential location (hardcoded, cannot be changed)
CLAUDE_CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
CLAUDE_CREDENTIALS_BACKUP = Path.home() / ".claude" / ".credentials.backup.json"
CREDENTIAL_LOCK_PATH = Path.home() / ".claude" / ".credentials.lock"

# OAuth configuration
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"

# Lock file for token refresh operations to prevent concurrent refresh race conditions.
# If two processes try to refresh simultaneously, one might use a stale refresh_token
# that was already consumed by the other, resulting in invalid_grant errors.
TOKEN_REFRESH_LOCK_PATH = Path.home() / ".claude" / ".token_refresh.lock"


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


@asynccontextmanager
async def _token_refresh_lock() -> AsyncGenerator[None, None]:
    """Async context manager for token refresh locking.

    Prevents concurrent refresh operations which could race on the refresh_token.
    Uses file locking for cross-process safety, run in thread pool to avoid blocking.
    """
    TOKEN_REFRESH_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)

    def _acquire_lock():
        lock_file = open(TOKEN_REFRESH_LOCK_PATH, "w")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        return lock_file

    def _release_lock(lock_file):
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()

    # Acquire lock in thread pool to avoid blocking the event loop
    lock_file = await asyncio.to_thread(_acquire_lock)
    try:
        yield
    finally:
        await asyncio.to_thread(_release_lock, lock_file)


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

    auth_log.info(
        "login",
        f"Logged in ({scope})",
        scope=scope,
        email=tokens.get("email"),
        project_id=project_id,
    )
    return True


async def _do_token_refresh(creds: dict, project_id: Optional[str] = None) -> bool:
    """Actually perform the token refresh via OAuth.

    Args:
        creds: Credentials dict from database
        project_id: Optional project ID for logging

    Returns:
        True if refresh succeeded, False otherwise
    """
    if not creds.get("refresh_token"):
        auth_log.warning(
            "token_refresh_failed",
            f"No refresh token available ({creds.get('scope', 'unknown')})",
            scope=creds.get("scope"),
            project_id=project_id,
        )
        return False

    db = Database()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                TOKEN_URL,
                json={
                    "grant_type": "refresh_token",
                    "refresh_token": creds["refresh_token"],
                    "client_id": CLIENT_ID,
                },
                headers={
                    "Content-Type": "application/json",
                    "anthropic-beta": "oauth-2025-04-20",
                },
            )

            if resp.status_code != 200:
                error_body = resp.text[:200] if resp.text else "no response body"
                auth_log.warning(
                    "token_refresh_failed",
                    f"Token refresh failed ({creds['scope']}): HTTP {resp.status_code} - {error_body}",
                    scope=creds["scope"],
                    project_id=project_id,
                    status_code=resp.status_code,
                )
                # Return structured error for better UX
                try:
                    error_json = resp.json()
                    if error_json.get("error") == "invalid_grant":
                        raise InvalidGrantError("Refresh token expired or revoked. Please re-login.")
                except (ValueError, KeyError):
                    pass
                return False

            tokens = resp.json()
            new_expires_at = int(time.time()) + tokens.get("expires_in", 28800)

            # Extract email from account field if present
            account = tokens.get("account", {})
            email = account.get("email_address")

            # CRITICAL: If DB update fails after refresh, we've consumed the
            # refresh_token but not saved the new one. Log this clearly.
            try:
                db.update_credentials(
                    creds["id"],
                    access_token=tokens["access_token"],
                    refresh_token=tokens.get("refresh_token", creds["refresh_token"]),
                    expires_at=new_expires_at,
                    email=email if email else creds.get("email"),
                )
            except Exception as db_error:
                auth_log.error(
                    "token_db_update_failed",
                    f"Failed to save refreshed token ({creds['scope']}): {db_error}. Token may be lost!",
                    scope=creds["scope"],
                    project_id=project_id,
                )
                return False

            auth_log.info(
                "token_refresh",
                f"Token refreshed ({creds['scope']})",
                scope=creds["scope"],
                project_id=project_id,
                expires_in=tokens.get("expires_in", 28800),
            )
            return True
    except httpx.HTTPError as http_error:
        auth_log.warning(
            "token_refresh_failed",
            f"Token refresh HTTP error ({creds['scope']}): {http_error}",
            scope=creds["scope"],
            project_id=project_id,
        )
        return False
    except Exception as e:
        auth_log.warning(
            "token_refresh_failed",
            f"Token refresh failed ({creds['scope']}): {e}",
            scope=creds["scope"],
            project_id=project_id,
        )
        return False


async def validate_token_health(creds: dict) -> tuple[bool, str]:
    """Validate OAuth token by attempting a refresh.

    Since we're using OAuth tokens (not API keys), we validate by
    trying to refresh the token. If the refresh_token is still valid,
    we'll get a new access_token. If it's expired/revoked, we get an error.

    Args:
        creds: Credentials dict with refresh_token

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not creds:
        return False, "No credentials"

    if not creds.get("refresh_token"):
        return False, "No refresh token available"

    try:
        # Use lock to prevent concurrent refresh operations.
        # Re-read creds inside lock in case another process already refreshed.
        async with _token_refresh_lock():
            # Re-fetch credentials to get any updates from concurrent refresh
            db = Database()
            fresh_creds = db.get_credentials_by_id(creds["id"])
            if fresh_creds and fresh_creds.get("refresh_token") != creds.get("refresh_token"):
                # Another process already refreshed - we have fresh tokens
                auth_log.info(
                    "token_already_refreshed",
                    "Token was refreshed by another process",
                    scope=creds.get("scope"),
                )
                return True, ""

            async with httpx.AsyncClient(timeout=10.0) as client:
                # Attempt to refresh - this validates the refresh_token is still good
                resp = await client.post(
                    TOKEN_URL,
                    json={
                        "grant_type": "refresh_token",
                        "refresh_token": creds["refresh_token"],
                        "client_id": CLIENT_ID,
                    },
                    headers={
                        "Content-Type": "application/json",
                        "anthropic-beta": "oauth-2025-04-20",
                    },
                )

                if resp.status_code == 200:
                    # Token is valid and we got a new one - update it
                    tokens = resp.json()
                    new_expires_at = int(time.time()) + tokens.get("expires_in", 28800)
                    account = tokens.get("account", {})
                    email = account.get("email_address")

                    # db already created above in lock, but re-use is fine
                    # CRITICAL: If DB update fails, we've consumed the refresh_token
                    # but not saved the new one. Handle this carefully.
                    try:
                        db.update_credentials(
                            creds["id"],
                            access_token=tokens["access_token"],
                            refresh_token=tokens.get("refresh_token", creds["refresh_token"]),
                            expires_at=new_expires_at,
                            email=email if email else creds.get("email"),
                        )
                    except Exception as db_error:
                        auth_log.error(
                            "token_db_update_failed",
                            f"Failed to save refreshed token: {db_error}. Token may be lost!",
                            scope=creds.get("scope"),
                        )
                        return False, f"Token refresh succeeded but failed to save: {db_error}"

                    auth_log.info(
                        "token_validated",
                        f"Token validated and refreshed ({creds.get('scope', 'unknown')})",
                        scope=creds.get("scope"),
                    )
                    return True, ""

                elif resp.status_code == 400:
                    try:
                        error_json = resp.json()
                        error_type = error_json.get("error", "unknown")
                        error_desc = error_json.get("error_description", "")
                        if error_type == "invalid_grant":
                            return False, f"Refresh token expired or revoked: {error_desc}. Please re-login."
                        return False, f"OAuth error: {error_type} - {error_desc}"
                    except Exception:
                        return False, "OAuth refresh failed (400) - bad request"

                elif resp.status_code == 401:
                    return False, "Token unauthorized (401). Please re-login."

                elif resp.status_code == 403:
                    return False, "Token forbidden (403). Account may be suspended or token revoked. Please re-login."

                elif resp.status_code == 429:
                    return False, "Rate limited (429). Please wait and try again later."

                elif resp.status_code >= 500:
                    return False, f"Server error ({resp.status_code}). This is likely temporary - please try again."

                else:
                    return False, f"OAuth refresh failed: HTTP {resp.status_code}"

    except httpx.TimeoutException:
        auth_log.warning(
            "token_validation_timeout",
            "Token validation timed out - network issue, not a token problem",
        )
        # Return False but with a message indicating this is a network issue,
        # not necessarily an invalid token. The caller can decide what to do.
        return False, "Network timeout during validation - check your connection"
    except Exception as e:
        auth_log.warning(
            "token_validation_error",
            f"Token validation error: {e}",
        )
        return False, str(e)


async def refresh_token_if_needed(
    project_id: Optional[str] = None,
    validate: bool = False,
) -> bool:
    """Auto-refresh token if expired. Returns True if valid token available.

    Args:
        project_id: Optional project ID to check for project-scoped creds
        validate: If True, actually validate the token by calling API

    Returns:
        True if valid credentials exist (either not expired or successfully refreshed)
        False if no credentials or refresh failed
    """
    db = Database()
    creds = db.get_credentials(project_id)

    if not creds:
        return False

    now = int(time.time())

    # If validation requested, actually test the token
    # Note: validate_token_health() attempts a refresh as part of validation.
    # If it fails, the refresh already failed - no point retrying immediately.
    if validate:
        is_valid, error = await validate_token_health(creds)
        if not is_valid:
            auth_log.warning(
                "token_invalid",
                f"Token validation failed: {error}",
                scope=creds.get("scope"),
                project_id=project_id,
            )
            # Don't retry - validate_token_health already tried to refresh.
            # The error message explains what went wrong.
            return False
        return True

    # Otherwise just check expiry timestamp (5 minute buffer)
    if now < creds["expires_at"] - 300:
        return True  # Token assumed valid based on expiry

    return await _do_token_refresh(creds, project_id)


async def force_refresh_token(project_id: Optional[str] = None) -> dict:
    """Force refresh a token regardless of expiry time.

    Args:
        project_id: Optional project ID to check for project-scoped creds

    Returns:
        dict with success status and message
    """
    db = Database()
    creds = db.get_credentials(project_id)

    if not creds:
        return {"success": False, "error": "No credentials found"}

    if not creds.get("refresh_token"):
        return {"success": False, "error": "No refresh token available"}

    try:
        success = await _do_token_refresh(creds, project_id)
        if success:
            return {"success": True, "message": "Token refreshed successfully"}
        else:
            return {"success": False, "error": "Token refresh failed"}
    except InvalidGrantError as e:
        return {"success": False, "error": str(e), "needs_relogin": True}


async def refresh_all_expiring_tokens(buffer_seconds: int = 7200) -> dict:
    """Refresh all tokens expiring within buffer_seconds.

    Called by background task to proactively keep tokens fresh.

    Args:
        buffer_seconds: Refresh tokens expiring within this many seconds (default 2 hours)

    Returns:
        dict with counts: {"checked": N, "refreshed": N, "failed": N}
    """
    db = Database()
    now = int(time.time())
    result = {"checked": 0, "refreshed": 0, "failed": 0}

    # Get all credentials (global + all projects)
    all_creds = db.get_all_credentials()

    for creds in all_creds:
        result["checked"] += 1

        # Skip if not expiring soon
        if now < creds["expires_at"] - buffer_seconds:
            continue

        # Skip if no refresh token
        if not creds.get("refresh_token"):
            continue

        # Attempt refresh with lock to prevent race conditions
        try:
            async with _token_refresh_lock():
                # Re-fetch credentials to check if another process already refreshed
                fresh_creds = db.get_credentials_by_id(creds["id"])
                if fresh_creds and now < fresh_creds["expires_at"] - buffer_seconds:
                    # Token was refreshed by another process, skip
                    continue

                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        TOKEN_URL,
                        json={
                            "grant_type": "refresh_token",
                            "refresh_token": creds["refresh_token"],
                            "client_id": CLIENT_ID,
                        },
                        headers={
                            "Content-Type": "application/json",
                            "anthropic-beta": "oauth-2025-04-20",
                        },
                    )

                    if resp.status_code == 200:
                        tokens = resp.json()
                        new_expires_at = int(time.time()) + tokens.get("expires_in", 28800)
                        account = tokens.get("account", {})
                        email = account.get("email_address")

                        try:
                            db.update_credentials(
                                creds["id"],
                                access_token=tokens["access_token"],
                                refresh_token=tokens.get("refresh_token", creds["refresh_token"]),
                                expires_at=new_expires_at,
                                email=email if email else creds.get("email"),
                            )
                            result["refreshed"] += 1
                            auth_log.info(
                                "token_refresh",
                                f"Token refreshed ({creds['scope']})",
                                scope=creds["scope"],
                                project_id=creds.get("project_id"),
                                expires_in=tokens.get("expires_in", 28800),
                            )
                        except Exception as db_error:
                            result["failed"] += 1
                            auth_log.error(
                                "token_db_update_failed",
                                f"Failed to save refreshed token ({creds['scope']}): {db_error}",
                                scope=creds["scope"],
                                project_id=creds.get("project_id"),
                            )
                    else:
                        result["failed"] += 1
                        auth_log.warning(
                            "token_refresh_failed",
                            f"Token refresh failed ({creds['scope']}): HTTP {resp.status_code}",
                            scope=creds["scope"],
                            project_id=creds.get("project_id"),
                        )
        except Exception as e:
            result["failed"] += 1
            auth_log.error(
                "token_refresh_error",
                f"Token refresh error ({creds['scope']}): {e}",
                scope=creds["scope"],
                project_id=creds.get("project_id"),
                error=str(e),
            )

    return result


def clear_credentials(
    scope: Literal["project", "global"],
    project_id: Optional[str] = None,
) -> bool:
    """Remove credentials for the specified scope from database."""
    db = Database()
    result = db.delete_credentials(scope, project_id if scope == "project" else None)

    if result:
        auth_log.info(
            "logout",
            f"Logged out ({scope})",
            scope=scope,
            project_id=project_id,
        )
    return result


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
            # CRITICAL: Check if Claude CLI refreshed our tokens during execution.
            # If so, save the new tokens to our DB BEFORE restoring the backup.
            # Otherwise we lose the new refresh token and our DB has stale tokens.
            if has_creds and CLAUDE_CREDENTIALS_PATH.exists():
                try:
                    current_creds = json.loads(CLAUDE_CREDENTIALS_PATH.read_text())
                    oauth = current_creds.get("claudeAiOauth", {})
                    new_refresh = oauth.get("refreshToken")

                    # If refresh token changed, Claude CLI refreshed during execution
                    if new_refresh and new_refresh != creds["refresh_token"]:
                        db.update_credentials(
                            creds["id"],
                            access_token=oauth.get("accessToken"),
                            refresh_token=new_refresh,
                            expires_at=int(oauth.get("expiresAt", 0) / 1000),
                        )
                        auth_log.info(
                            "token_captured",
                            f"Captured refreshed token from Claude CLI ({creds['scope']})",
                            scope=creds["scope"],
                            project_id=project_id,
                        )
                except Exception as e:
                    # Don't fail the loop if token capture fails - just log it
                    auth_log.warning(
                        "token_capture_failed",
                        f"Failed to capture refreshed token: {e}",
                        scope=creds.get("scope") if creds else None,
                        project_id=project_id,
                    )

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
