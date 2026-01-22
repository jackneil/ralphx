"""Claude credential management with SQLite storage.

Stores OAuth credentials in database with support for:
- Global credentials (default for all projects)
- Project-specific credentials (override global)
- Auto-refresh of expired tokens
- Credential swap for loop execution with bulletproof restoration
"""

import atexit
import asyncio
import fcntl
import json
import os
import signal
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

# Track if we're in the middle of a credential swap (for emergency restoration)
_credential_swap_active = False


def _emergency_restore_credentials():
    """Emergency restoration of credentials - called on unexpected exit.

    This is a last-resort safety net. If the process crashes or is killed
    while credentials are swapped, this ensures the user's original creds
    are restored.
    """
    global _credential_swap_active
    if not _credential_swap_active:
        return

    try:
        if CLAUDE_CREDENTIALS_BACKUP.exists():
            shutil.copy2(CLAUDE_CREDENTIALS_BACKUP, CLAUDE_CREDENTIALS_PATH)
            CLAUDE_CREDENTIALS_BACKUP.unlink()
            auth_log.warning(
                "emergency_restore",
                "Emergency credential restoration triggered - backup restored",
            )
    except Exception as e:
        # Last resort: at least log what happened
        auth_log.error(
            "emergency_restore_failed",
            f"CRITICAL: Failed to restore credentials on exit: {e}. "
            f"Backup may exist at {CLAUDE_CREDENTIALS_BACKUP}",
        )


def _signal_handler(signum, frame):
    """Handle termination signals to ensure credential restoration."""
    _emergency_restore_credentials()
    # Re-raise the signal to allow normal termination
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def restore_orphaned_backup():
    """Check for and restore orphaned credential backups on startup.

    If a backup exists without an active swap, it means a previous process
    crashed. Restore the backup to ensure the user's credentials are intact.

    Call this at application startup.
    """
    global _credential_swap_active
    if _credential_swap_active:
        # Active swap in progress, don't touch
        return

    if CLAUDE_CREDENTIALS_BACKUP.exists():
        try:
            shutil.copy2(CLAUDE_CREDENTIALS_BACKUP, CLAUDE_CREDENTIALS_PATH)
            CLAUDE_CREDENTIALS_BACKUP.unlink()
            auth_log.warning(
                "orphaned_backup_restored",
                "Found and restored orphaned credential backup from previous crash",
            )
        except Exception as e:
            auth_log.error(
                "orphaned_backup_restore_failed",
                f"Failed to restore orphaned backup: {e}",
            )


# Register safety nets
atexit.register(_emergency_restore_credentials)
# Register signal handlers for common termination signals
for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
    try:
        signal.signal(sig, _signal_handler)
    except (OSError, ValueError):
        # Can't set handler in some contexts (e.g., non-main thread)
        pass

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
    """Get auth status based on effective account for project.

    Returns detailed status including whether project has a specific assignment.
    """
    db = Database()

    # Get effective account (assigned to project, or default, or first active)
    account = db.get_effective_account(project_id)

    # Check if project has explicit assignment
    has_project_assignment = False
    if project_id:
        assignment = db.get_project_account_assignment(project_id)
        has_project_assignment = assignment is not None

    # Check if using default fallback
    using_fallback = project_id is not None and not has_project_assignment and account is not None

    if not account:
        return AuthStatus(
            connected=False,
            has_project_credentials=has_project_assignment,
        )

    # Check expiry
    now = int(time.time())
    expires_at = account["expires_at"]
    is_expired = now >= expires_at

    return AuthStatus(
        connected=True,
        scope="account",  # New: accounts don't have scope like old credentials
        email=account.get("email"),
        expires_at=datetime.fromtimestamp(expires_at),
        expires_in_seconds=max(0, expires_at - now),
        is_expired=is_expired,
        using_global_fallback=using_fallback,
        has_project_credentials=has_project_assignment,
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
    project_id: Optional[str] = None,
) -> bool:
    """Store OAuth tokens in database (accounts table).

    Args:
        tokens: Dict with access_token, refresh_token, expires_in, email (required),
                scopes (optional), subscription_type (optional), rate_limit_tier (optional)
        project_id: Optional project ID to assign this account to

    Returns:
        True if tokens stored successfully

    Raises:
        ValueError: If email not provided in tokens
    """
    email = tokens.get("email")
    if not email:
        raise ValueError("Email is required to store OAuth tokens")

    db = Database()
    expires_at = int(time.time()) + tokens.get("expires_in", 28800)

    # Convert scopes list to JSON string for storage
    scopes_json = None
    if tokens.get("scopes"):
        scopes_json = json.dumps(tokens["scopes"])

    # Create or update account
    db.create_account(
        email=email,
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token"),
        expires_at=expires_at,
        scopes=scopes_json,
        subscription_type=tokens.get("subscription_type"),
        rate_limit_tier=tokens.get("rate_limit_tier"),
    )

    # If project_id provided, assign this account to the project
    if project_id:
        account = db.get_account_by_email(email)
        if account:
            db.assign_account_to_project(project_id, account["id"])

    auth_log.info(
        "login",
        f"Logged in as {email}",
        email=email,
        project_id=project_id,
    )
    return True


def get_effective_account_for_project(project_id: Optional[str] = None) -> Optional[dict]:
    """Get the effective account for a project.

    Resolution order:
    1. If project has assignment -> use that account
    2. Else -> use default account
    3. If no default -> use first active account

    Args:
        project_id: Optional project ID

    Returns:
        Account dict or None
    """
    db = Database()
    return db.get_effective_account(project_id)


def get_fallback_account_for_rate_limit(
    current_account_id: int,
    failed_account_ids: Optional[list[int]] = None,
) -> Optional[dict]:
    """Get a fallback account after hitting rate limit (429).

    Args:
        current_account_id: Account that hit the rate limit
        failed_account_ids: List of account IDs that already failed

    Returns:
        Account dict for fallback, or None if no fallback available
    """
    db = Database()
    exclude_ids = [current_account_id] + (failed_account_ids or [])
    return db.get_fallback_account(exclude_ids=exclude_ids, prefer_lowest_usage=True)


@contextmanager
def swap_credentials_for_account(
    account: dict,
) -> Generator[bool, None, None]:
    """Context manager: backup user creds, write account creds, restore after.

    Similar to swap_credentials_for_loop but takes an account dict directly.
    Used when we have a specific account to use (e.g., from fallback logic).

    Args:
        account: Account dict with access_token, refresh_token, etc.

    Yields:
        True if credentials were written, False if account invalid
    """
    global _credential_swap_active

    db = Database()

    # Acquire exclusive lock to prevent concurrent credential access
    CREDENTIAL_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(CREDENTIAL_LOCK_PATH, "w")

    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)  # Exclusive lock

        # Backup user's current credentials
        had_backup = False
        original_content = None
        if CLAUDE_CREDENTIALS_PATH.exists():
            original_content = CLAUDE_CREDENTIALS_PATH.read_text()
            shutil.copy2(CLAUDE_CREDENTIALS_PATH, CLAUDE_CREDENTIALS_BACKUP)
            had_backup = True

        _credential_swap_active = True

        # Write account credentials to Claude's location
        has_creds = False
        if account and account.get("access_token"):
            default_scopes = ["user:inference", "user:profile", "user:sessions:claude_code"]
            stored_scopes = account.get("scopes")
            if stored_scopes:
                try:
                    scopes = json.loads(stored_scopes)
                except (json.JSONDecodeError, TypeError):
                    scopes = default_scopes
            else:
                scopes = default_scopes

            creds_data = {
                "claudeAiOauth": {
                    "accessToken": account["access_token"],
                    "refreshToken": account.get("refresh_token"),
                    "expiresAt": account.get("expires_at", 0) * 1000,
                    "scopes": scopes,
                    "subscriptionType": account.get("subscription_type") or "max",
                    "rateLimitTier": account.get("rate_limit_tier") or "default_claude_max_20x",
                }
            }
            CLAUDE_CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
            CLAUDE_CREDENTIALS_PATH.write_text(json.dumps(creds_data, indent=2))
            has_creds = True

            # Update last_used_at for the account
            db.update_account(account["id"], last_used_at=datetime.utcnow().isoformat())

        try:
            yield has_creds
        finally:
            # Capture any token refresh that happened during execution
            if has_creds and CLAUDE_CREDENTIALS_PATH.exists():
                try:
                    current_creds = json.loads(CLAUDE_CREDENTIALS_PATH.read_text())
                    oauth = current_creds.get("claudeAiOauth", {})
                    new_refresh = oauth.get("refreshToken")

                    if new_refresh and new_refresh != account.get("refresh_token"):
                        db.update_account(
                            account["id"],
                            access_token=oauth.get("accessToken"),
                            refresh_token=new_refresh,
                            expires_at=int(oauth.get("expiresAt", 0) / 1000),
                        )
                        auth_log.info(
                            "account_token_captured",
                            f"Captured refreshed token for account {account.get('email')}",
                            account_id=account["id"],
                        )
                except Exception as e:
                    auth_log.warning(
                        "account_token_capture_failed",
                        f"Failed to capture refreshed token for account: {e}",
                        account_id=account.get("id"),
                    )

            # Restore user's original credentials
            restoration_success = False
            try:
                if had_backup and CLAUDE_CREDENTIALS_BACKUP.exists():
                    shutil.copy2(CLAUDE_CREDENTIALS_BACKUP, CLAUDE_CREDENTIALS_PATH)
                    restoration_success = True
                elif not had_backup and has_creds:
                    CLAUDE_CREDENTIALS_PATH.unlink(missing_ok=True)
                    restoration_success = True
                else:
                    restoration_success = True
            except Exception as e:
                auth_log.error(
                    "account_restoration_failed",
                    f"Failed to restore credentials after account swap: {e}",
                )

            if restoration_success and CLAUDE_CREDENTIALS_BACKUP.exists():
                try:
                    CLAUDE_CREDENTIALS_BACKUP.unlink()
                except Exception:
                    pass

            _credential_swap_active = False
    finally:
        _credential_swap_active = False
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
        except Exception:
            pass


async def _do_token_refresh(creds: dict, project_id: Optional[str] = None) -> bool:
    """Actually perform the token refresh via OAuth for an account.

    Args:
        account: Account dict from database with id, refresh_token, email
        project_id: Optional project ID for logging

    Returns:
        True if refresh succeeded, False otherwise
    """
    if not account.get("refresh_token"):
        auth_log.warning(
            "token_refresh_failed",
            f"No refresh token available for account {account.get('email', 'unknown')}",
            email=account.get("email"),
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
                    "refresh_token": account["refresh_token"],
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
                    f"Token refresh failed for {account.get('email')}: HTTP {resp.status_code} - {error_body}",
                    email=account.get("email"),
                    account_id=account.get("id"),
                    project_id=project_id,
                    status_code=resp.status_code,
                )
                # Return structured error for better UX
                try:
                    error_json = resp.json()
                    if error_json.get("error") == "invalid_grant":
                        # Mark account as inactive since token is revoked
                        db.update_account(account["id"], is_active=False, last_error="invalid_grant")
                        raise InvalidGrantError("Refresh token expired or revoked. Please re-login.")
                except (ValueError, KeyError):
                    pass
                return False

            tokens = resp.json()
            new_expires_at = int(time.time()) + tokens.get("expires_in", 28800)

            # CRITICAL: If DB update fails after refresh, we've consumed the
            # refresh_token but not saved the new one. Log this clearly.
            try:
                db.update_account(
                    account["id"],
                    access_token=tokens["access_token"],
                    refresh_token=tokens.get("refresh_token", account["refresh_token"]),
                    expires_at=new_expires_at,
                    consecutive_failures=0,  # Reset failure count on success
                )
            except Exception as db_error:
                auth_log.error(
                    "token_db_update_failed",
                    f"Failed to save refreshed token for {account.get('email')}: {db_error}. Token may be lost!",
                    email=account.get("email"),
                    account_id=account.get("id"),
                    project_id=project_id,
                )
                return False

            auth_log.info(
                "token_refresh",
                f"Token refreshed for {account.get('email')}",
                email=account.get("email"),
                account_id=account.get("id"),
                project_id=project_id,
                expires_in=tokens.get("expires_in", 28800),
            )
            return True
    except httpx.HTTPError as http_error:
        auth_log.warning(
            "token_refresh_failed",
            f"Token refresh HTTP error for {account.get('email')}: {http_error}",
            email=account.get("email"),
            account_id=account.get("id"),
            project_id=project_id,
        )
        return False
    except Exception as e:
        auth_log.warning(
            "token_refresh_failed",
            f"Token refresh failed for {account.get('email')}: {e}",
            email=account.get("email"),
            account_id=account.get("id"),
            project_id=project_id,
        )
        return False


async def validate_account_token(account: dict) -> tuple[bool, str]:
    """Validate account's OAuth token by attempting a refresh.

    Since we're using OAuth tokens (not API keys), we validate by
    trying to refresh the token. If the refresh_token is still valid,
    we'll get a new access_token. If it's expired/revoked, we get an error.

    Args:
        account: Account dict with refresh_token

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not account:
        return False, "No account"

    if not account.get("refresh_token"):
        return False, "No refresh token available"

    try:
        # Use lock to prevent concurrent refresh operations.
        # Re-read account inside lock in case another process already refreshed.
        async with _token_refresh_lock():
            # Re-fetch account to get any updates from concurrent refresh
            db = Database()
            fresh_account = db.get_account(account["id"])
            if fresh_account and fresh_account.get("refresh_token") != account.get("refresh_token"):
                # Another process already refreshed - we have fresh tokens
                auth_log.info(
                    "token_already_refreshed",
                    "Token was refreshed by another process",
                    email=account.get("email"),
                )
                return True, ""

            async with httpx.AsyncClient(timeout=10.0) as client:
                # Attempt to refresh - this validates the refresh_token is still good
                resp = await client.post(
                    TOKEN_URL,
                    json={
                        "grant_type": "refresh_token",
                        "refresh_token": account["refresh_token"],
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

                    # CRITICAL: If DB update fails, we've consumed the refresh_token
                    # but not saved the new one. Handle this carefully.
                    try:
                        db.update_account(
                            account["id"],
                            access_token=tokens["access_token"],
                            refresh_token=tokens.get("refresh_token", account["refresh_token"]),
                            expires_at=new_expires_at,
                            consecutive_failures=0,
                        )
                    except Exception as db_error:
                        auth_log.error(
                            "token_db_update_failed",
                            f"Failed to save refreshed token: {db_error}. Token may be lost!",
                            email=account.get("email"),
                        )
                        return False, f"Token refresh succeeded but failed to save: {db_error}"

                    auth_log.info(
                        "token_validated",
                        f"Token validated and refreshed for {account.get('email')}",
                        email=account.get("email"),
                    )
                    return True, ""

                elif resp.status_code == 400:
                    try:
                        error_json = resp.json()
                        error_type = error_json.get("error", "unknown")
                        error_desc = error_json.get("error_description", "")
                        if error_type == "invalid_grant":
                            # Mark account as needing re-auth
                            db.update_account(account["id"], is_active=False, last_error="invalid_grant")
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
        project_id: Optional project ID to get effective account for
        validate: If True, actually validate the token by calling API

    Returns:
        True if valid account exists (either not expired or successfully refreshed)
        False if no account or refresh failed
    """
    db = Database()
    account = db.get_effective_account(project_id)

    if not account:
        return False

    now = int(time.time())

    # If validation requested, actually test the token
    # Note: validate_account_token() attempts a refresh as part of validation.
    # If it fails, the refresh already failed - no point retrying immediately.
    if validate:
        is_valid, error = await validate_account_token(account)
        if not is_valid:
            auth_log.warning(
                "token_invalid",
                f"Token validation failed: {error}",
                email=account.get("email"),
                project_id=project_id,
            )
            # Don't retry - validate_account_token already tried to refresh.
            # The error message explains what went wrong.
            return False
        return True

    # Otherwise just check expiry timestamp (5 minute buffer)
    if now < account["expires_at"] - 300:
        return True  # Token assumed valid based on expiry

    return await _do_token_refresh(account, project_id)


async def force_refresh_token(project_id: Optional[str] = None) -> dict:
    """Force refresh a token regardless of expiry time.

    Args:
        project_id: Optional project ID to get effective account for

    Returns:
        dict with success status and message
    """
    db = Database()
    account = db.get_effective_account(project_id)

    if not account:
        return {"success": False, "error": "No account found"}

    if not account.get("refresh_token"):
        return {"success": False, "error": "No refresh token available"}

    try:
        success = await _do_token_refresh(account, project_id)
        if success:
            return {"success": True, "message": "Token refreshed successfully"}
        else:
            return {"success": False, "error": "Token refresh failed"}
    except InvalidGrantError as e:
        return {"success": False, "error": str(e), "needs_relogin": True}


async def refresh_all_expiring_tokens(buffer_seconds: int = 7200) -> dict:
    """Refresh all account tokens expiring within buffer_seconds.

    Called by background task to proactively keep tokens fresh.

    Args:
        buffer_seconds: Refresh tokens expiring within this many seconds (default 2 hours)

    Returns:
        dict with counts: {"checked": N, "refreshed": N, "failed": N}
    """
    db = Database()
    now = int(time.time())
    result = {"checked": 0, "refreshed": 0, "failed": 0}

    # Get all active accounts
    all_accounts = db.list_accounts(include_inactive=False, include_deleted=False)

    for account in all_accounts:
        result["checked"] += 1

        # Skip if not expiring soon
        if now < account["expires_at"] - buffer_seconds:
            continue

        # Skip if no refresh token
        if not account.get("refresh_token"):
            continue

        # Attempt refresh with lock to prevent race conditions
        try:
            async with _token_refresh_lock():
                # Re-fetch account to check if another process already refreshed
                fresh_account = db.get_account(account["id"])
                if fresh_account and now < fresh_account["expires_at"] - buffer_seconds:
                    # Token was refreshed by another process, skip
                    continue

                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        TOKEN_URL,
                        json={
                            "grant_type": "refresh_token",
                            "refresh_token": account["refresh_token"],
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

                        try:
                            db.update_account(
                                account["id"],
                                access_token=tokens["access_token"],
                                refresh_token=tokens.get("refresh_token", account["refresh_token"]),
                                expires_at=new_expires_at,
                                consecutive_failures=0,
                            )
                            result["refreshed"] += 1
                            auth_log.info(
                                "token_refresh",
                                f"Token refreshed for {account.get('email')}",
                                email=account.get("email"),
                                account_id=account.get("id"),
                                expires_in=tokens.get("expires_in", 28800),
                            )
                        except Exception as db_error:
                            result["failed"] += 1
                            auth_log.error(
                                "token_db_update_failed",
                                f"Failed to save refreshed token for {account.get('email')}: {db_error}",
                                email=account.get("email"),
                                account_id=account.get("id"),
                            )
                    else:
                        result["failed"] += 1
                        # Track consecutive failures
                        db.update_account(
                            account["id"],
                            consecutive_failures=account.get("consecutive_failures", 0) + 1,
                        )
                        auth_log.warning(
                            "token_refresh_failed",
                            f"Token refresh failed for {account.get('email')}: HTTP {resp.status_code}",
                            email=account.get("email"),
                            account_id=account.get("id"),
                        )
        except Exception as e:
            result["failed"] += 1
            auth_log.error(
                "token_refresh_error",
                f"Token refresh error for {account.get('email')}: {e}",
                email=account.get("email"),
                account_id=account.get("id"),
                error=str(e),
            )

    return result


@contextmanager
def swap_credentials_for_loop(
    project_id: Optional[str] = None,
) -> Generator[bool, None, None]:
    """Context manager: backup user creds, write from DB, restore after.

    Uses file locking to prevent race conditions when multiple loops run
    concurrently. Has multiple safety nets to ensure credentials are ALWAYS
    restored:
    - try/finally for normal cleanup
    - atexit handler for unexpected exit
    - signal handlers for SIGTERM/SIGHUP/SIGINT
    - startup check for orphaned backups

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
    global _credential_swap_active

    db = Database()
    # Get the effective account for this project (assigned or default)
    account = db.get_effective_account(project_id)

    # Acquire exclusive lock to prevent concurrent credential access
    CREDENTIAL_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(CREDENTIAL_LOCK_PATH, "w")

    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)  # Exclusive lock

        # Backup user's current credentials
        had_backup = False
        original_content = None
        if CLAUDE_CREDENTIALS_PATH.exists():
            # Read content for verification later
            original_content = CLAUDE_CREDENTIALS_PATH.read_text()
            shutil.copy2(CLAUDE_CREDENTIALS_PATH, CLAUDE_CREDENTIALS_BACKUP)
            had_backup = True

        # Mark swap as active AFTER backup is complete
        _credential_swap_active = True

        # Write account credentials to Claude's location
        has_creds = False
        if account:
            # Default scopes if not stored
            # These are the minimum scopes Claude Code CLI needs for execution
            default_scopes = ["user:inference", "user:profile", "user:sessions:claude_code"]
            stored_scopes = account.get("scopes")
            if stored_scopes:
                try:
                    scopes = json.loads(stored_scopes)
                except (json.JSONDecodeError, TypeError):
                    scopes = default_scopes
            else:
                scopes = default_scopes

            creds_data = {
                "claudeAiOauth": {
                    "accessToken": account["access_token"],
                    "refreshToken": account["refresh_token"],
                    "expiresAt": account["expires_at"] * 1000,  # Convert to milliseconds
                    "scopes": scopes,
                    # subscriptionType: Claude subscription tier. Values include "free", "pro", "max".
                    # Default to "max" as RalphX is designed for Max subscription users.
                    "subscriptionType": account.get("subscription_type") or "max",
                    # rateLimitTier: API rate limit tier. "default_claude_max_20x" indicates
                    # the 20x rate limit multiplier for Max subscribers.
                    "rateLimitTier": account.get("rate_limit_tier") or "default_claude_max_20x",
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
                    if new_refresh and new_refresh != account["refresh_token"]:
                        db.update_account(
                            account["id"],
                            access_token=oauth.get("accessToken"),
                            refresh_token=new_refresh,
                            expires_at=int(oauth.get("expiresAt", 0) / 1000),
                        )
                        auth_log.info(
                            "token_captured",
                            f"Captured refreshed token from Claude CLI ({account['email']})",
                            email=account["email"],
                            account_id=account["id"],
                            project_id=project_id,
                        )
                except Exception as e:
                    # Don't fail the loop if token capture fails - just log it
                    auth_log.warning(
                        "token_capture_failed",
                        f"Failed to capture refreshed token: {e}",
                        email=account.get("email") if account else None,
                        project_id=project_id,
                    )

            # Restore user's original credentials
            restoration_success = False
            try:
                if had_backup and CLAUDE_CREDENTIALS_BACKUP.exists():
                    shutil.copy2(CLAUDE_CREDENTIALS_BACKUP, CLAUDE_CREDENTIALS_PATH)
                    # Verify restoration succeeded
                    if original_content is not None:
                        restored_content = CLAUDE_CREDENTIALS_PATH.read_text()
                        if restored_content == original_content:
                            restoration_success = True
                        else:
                            auth_log.warning(
                                "restoration_mismatch",
                                "Restored credentials differ from original - may indicate issue",
                            )
                            restoration_success = True  # Still count as success, content is valid
                    else:
                        restoration_success = True
                elif not had_backup and has_creds:
                    # We wrote credentials but user had none originally - remove them
                    CLAUDE_CREDENTIALS_PATH.unlink(missing_ok=True)
                    restoration_success = True
                else:
                    # No backup needed, nothing to restore
                    restoration_success = True
            except Exception as e:
                auth_log.error(
                    "restoration_failed",
                    f"Failed to restore credentials: {e}",
                )

            # Only delete backup after verified restoration
            if restoration_success and CLAUDE_CREDENTIALS_BACKUP.exists():
                try:
                    CLAUDE_CREDENTIALS_BACKUP.unlink()
                except Exception:
                    pass  # Non-critical, backup will be cleaned on next startup

            # Mark swap as complete
            _credential_swap_active = False
    finally:
        # Always mark swap as inactive and release lock, even on error
        _credential_swap_active = False
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
        except Exception:
            pass  # Lock release failure is non-critical
