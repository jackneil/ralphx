"""Authentication routes for Claude accounts."""

import asyncio
import logging
import secrets
import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ralphx.core.database import Database
from ralphx.core.oauth import OAuthFlow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Track active OAuth flows
_active_flows: dict[str, asyncio.Task] = {}


# ============================================================================
# Pydantic Models
# ============================================================================


class AccountUsage(BaseModel):
    """Usage statistics for an account."""

    five_hour: float = Field(description="5-hour utilization percentage (0-100)")
    seven_day: float = Field(description="7-day utilization percentage (0-100)")
    five_hour_resets_at: Optional[str] = Field(None, description="ISO timestamp when 5h limit resets")
    seven_day_resets_at: Optional[str] = Field(None, description="ISO timestamp when 7d limit resets")


class AccountResponse(BaseModel):
    """Response model for a single account."""

    id: int
    email: str
    display_name: Optional[str] = None
    subscription_type: Optional[str] = None
    rate_limit_tier: Optional[str] = None
    is_default: bool
    is_active: bool
    expires_at: Optional[int] = None
    expires_in_seconds: Optional[int] = None
    is_expired: bool
    usage: Optional[AccountUsage] = None
    usage_cached_at: Optional[int] = None
    projects_using: int = 0
    last_error: Optional[str] = None
    last_error_at: Optional[str] = None
    consecutive_failures: int = 0
    # Token validation status
    last_validated_at: Optional[int] = None
    validation_status: Optional[str] = None  # 'unknown', 'valid', 'invalid', 'checking'
    created_at: Optional[str] = None


class AccountUpdateRequest(BaseModel):
    """Request model for updating an account."""

    display_name: Optional[str] = None
    is_active: Optional[bool] = None


class ProjectAccountAssignment(BaseModel):
    """Response model for project account assignment."""

    project_id: str
    account_id: int
    account_email: str
    account_display_name: Optional[str] = None
    subscription_type: Optional[str] = None
    is_active: bool
    is_default: bool
    allow_fallback: bool
    usage: Optional[AccountUsage] = None


class AssignAccountRequest(BaseModel):
    """Request model for assigning account to project."""

    account_id: int = Field(description="Account ID to assign")
    allow_fallback: bool = Field(default=True, description="Allow fallback to other accounts on rate limit")


# ============================================================================
# Helper Functions
# ============================================================================


async def _fetch_account_profile(access_token: str) -> Optional[dict]:
    """Fetch account profile from Anthropic API.

    Returns subscription type, rate limit tier, and other account info.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.anthropic.com/api/oauth/profile",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "anthropic-beta": "oauth-2025-04-20",
                },
                timeout=10.0,
            )

            if response.status_code != 200:
                logger.warning(f"Profile fetch failed: {response.status_code}")
                return None

            data = response.json()
            org = data.get("organization", {})
            account = data.get("account", {})

            # Map organization_type to subscription type
            org_type = org.get("organization_type")
            subscription_map = {
                "claude_max": "max",
                "claude_pro": "pro",
                "claude_enterprise": "enterprise",
                "claude_team": "team",
            }
            subscription_type = subscription_map.get(org_type)

            return {
                "subscription_type": subscription_type,
                "rate_limit_tier": org.get("rate_limit_tier"),
                "has_extra_usage_enabled": org.get("has_extra_usage_enabled"),
                "display_name": account.get("display_name"),
                "full_name": account.get("full_name"),
            }
    except Exception as e:
        logger.warning(f"Profile fetch error: {e}")
        return None


async def _fetch_account_usage(access_token: str) -> Optional[dict]:
    """Fetch usage data from Anthropic API."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.anthropic.com/api/oauth/usage",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "anthropic-beta": "oauth-2025-04-20",
                },
                timeout=10.0,
            )

            if response.status_code != 200:
                return None

            data = response.json()
            five_hour = data.get("five_hour", {})
            seven_day = data.get("seven_day", {})

            return {
                "five_hour": five_hour.get("utilization", 0),
                "seven_day": seven_day.get("utilization", 0),
                "five_hour_resets_at": five_hour.get("resets_at"),
                "seven_day_resets_at": seven_day.get("resets_at"),
            }
    except Exception:
        return None


def _build_account_response(account: dict, db: Database) -> AccountResponse:
    """Build AccountResponse from database account dict."""
    now = int(time.time())
    expires_at = account.get("expires_at", 0)
    is_expired = now >= expires_at if expires_at else True

    usage = None
    if account.get("cached_usage_5h") is not None or account.get("cached_usage_7d") is not None:
        usage = AccountUsage(
            five_hour=account.get("cached_usage_5h", 0) or 0,
            seven_day=account.get("cached_usage_7d", 0) or 0,
            five_hour_resets_at=account.get("cached_5h_resets_at"),
            seven_day_resets_at=account.get("cached_7d_resets_at"),
        )

    return AccountResponse(
        id=account["id"],
        email=account["email"],
        display_name=account.get("display_name"),
        subscription_type=account.get("subscription_type"),
        rate_limit_tier=account.get("rate_limit_tier"),
        is_default=bool(account.get("is_default")),
        is_active=bool(account.get("is_active")),
        expires_at=expires_at,
        expires_in_seconds=max(0, expires_at - now) if expires_at else None,
        is_expired=is_expired,
        usage=usage,
        usage_cached_at=account.get("usage_cached_at"),
        projects_using=db.count_projects_using_account(account["id"]),
        last_error=account.get("last_error"),
        last_error_at=account.get("last_error_at"),
        consecutive_failures=account.get("consecutive_failures", 0),
        last_validated_at=account.get("last_validated_at"),
        validation_status=account.get("validation_status", "unknown"),
        created_at=account.get("created_at"),
    )


def _build_usage_from_account(account: dict) -> Optional[AccountUsage]:
    """Build AccountUsage from account dict if usage data exists."""
    if account.get("cached_usage_5h") is None and account.get("cached_usage_7d") is None:
        return None
    return AccountUsage(
        five_hour=account.get("cached_usage_5h", 0) or 0,
        seven_day=account.get("cached_usage_7d", 0) or 0,
        five_hour_resets_at=account.get("cached_5h_resets_at"),
        seven_day_resets_at=account.get("cached_7d_resets_at"),
    )


# ============================================================================
# Legacy Frontend Endpoints (backwards compatibility with AuthPanel.tsx)
# These endpoints adapt the new accounts system to the frontend's expectations
# ============================================================================


from typing import Literal

from ralphx.core.auth import (
    AuthStatus,
    CLIENT_ID,
    TOKEN_URL,
    _token_refresh_lock,
    get_auth_status,
    refresh_token_if_needed,
    force_refresh_token,
    store_oauth_tokens,
    validate_account_token,
)


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
    """Get authentication status, refreshing if close to expiry.

    Proactively refreshes tokens when within 5 minutes of expiry,
    keeping tokens fresh when dashboard is being monitored.
    """
    project_id = _get_project_id(project_path)

    # Proactively refresh if close to expiry (within 5 min)
    await refresh_token_if_needed(project_id)

    return get_auth_status(project_id)


@router.post("/login")
async def start_login(request: LoginRequest):
    """Start OAuth flow - opens browser for authentication.

    Stores tokens in accounts table. For project scope, assigns the
    new/existing account to the project.
    """
    project_id = _get_project_id(request.project_path)

    async def run_flow():
        flow = OAuthFlow()
        result = await flow.start()
        if result.get("success"):
            tokens = result["tokens"]
            store_oauth_tokens(tokens, project_id)
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
    """Logout: soft-delete the effective account for the scope.

    Note: In the accounts system, we don't actually delete the account,
    we just mark it as inactive. The frontend will show "not connected".
    """
    project_id = _get_project_id(request.project_path)
    db = Database()

    # Get effective account
    account = db.get_effective_account(project_id)
    if account:
        # Mark as inactive (soft logout)
        db.update_account(account["id"], is_active=False)

    return {"success": True}


@router.post("/refresh")
async def refresh_token(request: LoginRequest):
    """Manually refresh the OAuth token.

    Forces a token refresh regardless of expiry time.
    """
    project_id = _get_project_id(request.project_path)
    result = await force_refresh_token(project_id)
    return result


@router.get("/validate")
async def validate_credentials(
    project_path: Optional[str] = Query(
        None, description="Project path for scoped credentials"
    ),
):
    """Validate that stored credentials are actually working.

    Makes a real API call to verify the refresh_token is still valid.
    """
    project_id = _get_project_id(project_path)
    db = Database()
    account = db.get_effective_account(project_id)

    if not account:
        return {
            "valid": False,
            "error": "No account found",
            "scope": None,
        }

    is_valid, error = await validate_account_token(account)

    return {
        "valid": is_valid,
        "error": error if not is_valid else None,
        "scope": "account",
        "email": account.get("email"),
        "refreshed": is_valid,  # If valid, we also refreshed the token
    }


@router.get("/usage")
async def get_usage(
    project_path: Optional[str] = Query(
        None, description="Project path for scoped credentials"
    ),
):
    """Get Claude API usage statistics.

    Returns 5-hour and 7-day utilization percentages.
    """
    project_id = _get_project_id(project_path)
    db = Database()
    account = db.get_effective_account(project_id)

    if not account or not account.get("access_token"):
        return {
            "success": False,
            "error": "No account found",
        }

    usage_data = await _fetch_account_usage(account["access_token"])

    if not usage_data:
        return {
            "success": False,
            "error": "Failed to fetch usage data",
        }

    return {
        "success": True,
        "five_hour_utilization": usage_data["five_hour"],
        "five_hour_resets_at": usage_data.get("five_hour_resets_at"),
        "seven_day_utilization": usage_data["seven_day"],
        "seven_day_resets_at": usage_data.get("seven_day_resets_at"),
    }


# ============================================================================
# Account Management Endpoints
# ============================================================================


@router.get("/accounts", response_model=list[AccountResponse])
async def list_accounts(
    include_inactive: bool = Query(False, description="Include disabled accounts"),
):
    """List all connected Claude accounts with usage statistics."""
    db = Database()
    accounts = db.list_accounts(include_inactive=include_inactive)
    return [_build_account_response(acc, db) for acc in accounts]


@router.post("/accounts/add")
async def add_account(expected_email: Optional[str] = None):
    """Start OAuth flow to add a new account.

    Opens browser for authentication. On success, creates a new account
    or updates existing if email matches.

    Args:
        expected_email: If provided (re-auth flow), checks if OAuth email matches.
                        On mismatch, still saves the account but flags the mismatch.
    """

    async def run_flow():
        flow = OAuthFlow()
        result = await flow.start()
        if result.get("success"):
            tokens = result["tokens"]
            email = tokens.get("email")
            if not email:
                return {"success": False, "error": "No email in OAuth response"}

            # Check for email mismatch (re-auth flow)
            email_mismatch = expected_email and email.lower() != expected_email.lower()

            # Use store_oauth_tokens to properly serialize scopes to JSON
            account = store_oauth_tokens(tokens)
            db = Database()

            # Fetch profile to get subscription type
            profile_data = await _fetch_account_profile(tokens["access_token"])
            if profile_data:
                update_fields = {}
                if profile_data.get("subscription_type"):
                    update_fields["subscription_type"] = profile_data["subscription_type"]
                if profile_data.get("rate_limit_tier"):
                    update_fields["rate_limit_tier"] = profile_data["rate_limit_tier"]
                if update_fields:
                    db.update_account(account["id"], **update_fields)

            # Fetch usage data
            usage_data = await _fetch_account_usage(tokens["access_token"])
            if usage_data:
                db.update_account_usage_cache(
                    account["id"],
                    five_hour=usage_data["five_hour"],
                    seven_day=usage_data["seven_day"],
                    five_hour_resets_at=usage_data.get("five_hour_resets_at"),
                    seven_day_resets_at=usage_data.get("seven_day_resets_at"),
                )

            # Return success with mismatch info if applicable
            response = {"success": True, "account_id": account["id"], "email": email}
            if email_mismatch:
                response["email_mismatch"] = True
                response["expected_email"] = expected_email
                response["message"] = (
                    f"Signed in as {email} instead of {expected_email}. "
                    f"Tokens saved for {email}. "
                    f"To fix {expected_email}, sign out of {email} in your browser first, then re-auth."
                )
            return response
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
    }


@router.get("/accounts/{account_id}", response_model=AccountResponse)
async def get_account(account_id: int):
    """Get details for a specific account."""
    db = Database()
    account = db.get_account(account_id)

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    return _build_account_response(account, db)


@router.patch("/accounts/{account_id}", response_model=AccountResponse)
async def update_account(account_id: int, request: AccountUpdateRequest):
    """Update an account's display name or active status."""
    db = Database()
    account = db.get_account(account_id)

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    updates = {}
    if request.display_name is not None:
        updates["display_name"] = request.display_name
    if request.is_active is not None:
        updates["is_active"] = request.is_active

    if updates:
        db.update_account(account_id, **updates)
        account = db.get_account(account_id)

    return _build_account_response(account, db)


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: int):
    """Remove an account (soft delete).

    Cannot delete the default account if other accounts exist.
    Cannot delete an account that is assigned to projects.
    """
    db = Database()
    account = db.get_account(account_id)

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Check if account is assigned to any projects
    projects_using = db.count_projects_using_account(account_id)
    if projects_using > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete account: assigned to {projects_using} project(s). Unassign first.",
        )

    # Check if this is the default and there are other accounts
    if account.get("is_default"):
        other_accounts = [a for a in db.list_accounts() if a["id"] != account_id]
        if other_accounts:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete default account. Set another account as default first.",
            )

    db.delete_account(account_id)
    return {"success": True}


@router.post("/accounts/{account_id}/set-default", response_model=AccountResponse)
async def set_default_account(account_id: int):
    """Set an account as the default."""
    db = Database()
    account = db.get_account(account_id)

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if not account.get("is_active"):
        raise HTTPException(status_code=400, detail="Cannot set inactive account as default")

    db.set_default_account(account_id)
    account = db.get_account(account_id)

    return _build_account_response(account, db)


@router.post("/accounts/{account_id}/refresh")
async def refresh_account_token(account_id: int):
    """Refresh an account's OAuth token."""
    db = Database()
    account = db.get_account(account_id)

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if not account.get("refresh_token"):
        return {"success": False, "message": "No refresh token available"}

    try:
        # Use token refresh lock to prevent race conditions with background
        # refresh tasks or concurrent manual refresh requests
        async with _token_refresh_lock():
            # Re-fetch account inside lock to get latest refresh_token
            # (another process may have refreshed while we waited for lock)
            account = db.get_account(account_id)
            if not account or not account.get("refresh_token"):
                return {"success": False, "message": "No refresh token available"}

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
                    return {"success": False, "message": f"Token refresh failed: {resp.status_code}"}

                tokens = resp.json()
                new_expires_at = int(time.time()) + tokens.get("expires_in", 28800)

                # Build update dict with all available fields
                update_data = {
                    "access_token": tokens["access_token"],
                    "refresh_token": tokens.get("refresh_token", account["refresh_token"]),
                    "expires_at": new_expires_at,
                }

                db.update_account(account_id, **update_data)

            # Fetch profile outside the lock (uses the new access_token, not refresh_token)
            profile_data = await _fetch_account_profile(tokens["access_token"])
            subscription_type = None
            if profile_data:
                if profile_data.get("subscription_type"):
                    subscription_type = profile_data["subscription_type"]
                    db.update_account(account_id, subscription_type=subscription_type)
                if profile_data.get("rate_limit_tier"):
                    db.update_account(account_id, rate_limit_tier=profile_data["rate_limit_tier"])

            return {
                "success": True,
                "expires_at": new_expires_at,
                "subscription_type": subscription_type,
            }
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/accounts/{account_id}/refresh-usage")
async def refresh_account_usage(account_id: int):
    """Refresh usage statistics for an account."""
    db = Database()
    account = db.get_account(account_id)

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    usage_data = await _fetch_account_usage(account["access_token"])

    if not usage_data:
        return {"success": False, "error": "Failed to fetch usage data"}

    db.update_account_usage_cache(
        account_id,
        five_hour=usage_data["five_hour"],
        seven_day=usage_data["seven_day"],
        five_hour_resets_at=usage_data.get("five_hour_resets_at"),
        seven_day_resets_at=usage_data.get("seven_day_resets_at"),
    )

    return {"success": True, "usage": usage_data}


@router.post("/accounts/{account_id}/validate")
async def validate_account(account_id: int):
    """Validate that an account's token is actually working.

    Makes a real API call to verify the refresh_token is still valid.
    Returns validation result without blocking.
    """
    db = Database()
    account = db.get_account(account_id)

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    is_valid, error = await validate_account_token(account)

    # Update account with validation status
    now = int(time.time())
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    update_kwargs = {
        "last_validated_at": now,
        "validation_status": 'valid' if is_valid else 'invalid',
    }
    if is_valid:
        update_kwargs["last_error"] = None
        update_kwargs["last_error_at"] = None
    else:
        update_kwargs["last_error"] = error
        update_kwargs["last_error_at"] = now_iso

    try:
        updated = db.update_account(account_id, **update_kwargs)
        if not updated:
            # Account was deleted between get and update - rare race condition
            raise HTTPException(status_code=404, detail="Account was deleted during validation")
    except HTTPException:
        raise
    except Exception as e:
        # Log but don't fail - validation result is still valid
        # The validation already happened (and token may have been refreshed)
        logger.warning(
            f"Failed to update validation status for account {account_id}: {e}"
        )

    return {
        "valid": is_valid,
        "error": error if not is_valid else None,
        "email": account.get("email"),
    }


@router.post("/accounts/refresh-all-usage")
async def refresh_all_accounts_usage():
    """Refresh usage statistics for all active accounts."""
    db = Database()
    accounts = db.list_accounts(include_inactive=False)

    results = {"refreshed": 0, "failed": 0, "accounts": []}

    for account in accounts:
        usage_data = await _fetch_account_usage(account["access_token"])

        if usage_data:
            db.update_account_usage_cache(
                account["id"],
                five_hour=usage_data["five_hour"],
                seven_day=usage_data["seven_day"],
                five_hour_resets_at=usage_data.get("five_hour_resets_at"),
                seven_day_resets_at=usage_data.get("seven_day_resets_at"),
            )
            results["refreshed"] += 1
            results["accounts"].append({"id": account["id"], "email": account["email"], "success": True})
        else:
            results["failed"] += 1
            results["accounts"].append({"id": account["id"], "email": account["email"], "success": False})

    return results


# ============================================================================
# Project Account Assignment Endpoints
# ============================================================================


@router.get("/projects/{project_id}/account", response_model=Optional[ProjectAccountAssignment])
async def get_project_account(project_id: str):
    """Get the account assigned to a project (if any)."""
    db = Database()

    # Verify project exists
    project = db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    assignment = db.get_project_account_assignment(project_id)
    if not assignment:
        return None

    account = db.get_account(assignment["account_id"])
    if not account:
        return None

    return ProjectAccountAssignment(
        project_id=project_id,
        account_id=account["id"],
        account_email=account["email"],
        account_display_name=account.get("display_name"),
        subscription_type=account.get("subscription_type"),
        is_active=bool(account.get("is_active")),
        is_default=bool(account.get("is_default")),
        allow_fallback=bool(assignment.get("allow_fallback", True)),
        usage=_build_usage_from_account(account),
    )


@router.post("/projects/{project_id}/account", response_model=ProjectAccountAssignment)
async def assign_project_account(project_id: str, request: AssignAccountRequest):
    """Assign an account to a project."""
    db = Database()

    # Verify project exists
    project = db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Verify account exists and is active
    account = db.get_account(request.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if not account.get("is_active"):
        raise HTTPException(status_code=400, detail="Cannot assign inactive account")

    # Create or update assignment
    db.assign_account_to_project(project_id, request.account_id, request.allow_fallback)

    return ProjectAccountAssignment(
        project_id=project_id,
        account_id=account["id"],
        account_email=account["email"],
        account_display_name=account.get("display_name"),
        subscription_type=account.get("subscription_type"),
        is_active=bool(account.get("is_active")),
        is_default=bool(account.get("is_default")),
        allow_fallback=request.allow_fallback,
        usage=_build_usage_from_account(account),
    )


@router.delete("/projects/{project_id}/account")
async def unassign_project_account(project_id: str):
    """Remove account assignment from a project (will use default)."""
    db = Database()

    # Verify project exists
    project = db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    db.unassign_account_from_project(project_id)
    return {"success": True}


@router.get("/projects/{project_id}/effective-account", response_model=Optional[AccountResponse])
async def get_effective_project_account(project_id: str):
    """Get the effective account for a project (assigned or default)."""
    db = Database()

    # Verify project exists
    project = db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    account = db.get_effective_account(project_id)
    if not account:
        return None

    return _build_account_response(account, db)


# ============================================================================
# Credentials Export Endpoint (for CLI usage)
# ============================================================================


class CredentialsExportResponse(BaseModel):
    """Response for credentials export."""

    success: bool
    error: Optional[str] = None
    scope: Optional[str] = None
    email: Optional[str] = None
    credentials: Optional[dict] = None


@router.get("/credentials/export", response_model=CredentialsExportResponse)
async def export_credentials(
    scope: str = Query("global", description="Scope: 'global' or 'project'"),
    project_path: Optional[str] = Query(None, description="Project path for project scope"),
):
    """Export credentials in Claude CLI format for manual use.

    Returns credentials in the format expected by ~/.claude/.credentials.json
    """
    import json

    db = Database()

    # Determine project_id if project scope
    project_id = None
    if scope == "project" and project_path:
        # Find project by path
        projects = db.list_projects()
        for p in projects:
            if p.get("path") == project_path:
                project_id = p.get("id")
                break

    # Get effective account
    account = db.get_effective_account(project_id)

    if not account:
        return CredentialsExportResponse(
            success=False,
            error="No account found. Please login first.",
            scope=scope,
        )

    # Build credentials in Claude CLI format
    default_scopes = ["user:inference", "user:profile", "user:sessions:claude_code"]
    stored_scopes = account.get("scopes")
    if stored_scopes:
        try:
            scopes = json.loads(stored_scopes) if isinstance(stored_scopes, str) else stored_scopes
        except (json.JSONDecodeError, TypeError):
            scopes = default_scopes
    else:
        scopes = default_scopes

    credentials = {
        "claudeAiOauth": {
            "accessToken": account["access_token"],
            "refreshToken": account.get("refresh_token"),
            "expiresAt": account.get("expires_at", 0) * 1000,  # Convert to milliseconds
            "scopes": scopes,
            "subscriptionType": account.get("subscription_type") or "max",
            "rateLimitTier": account.get("rate_limit_tier") or "default_claude_max_20x",
        }
    }

    return CredentialsExportResponse(
        success=True,
        scope=scope,
        email=account.get("email"),
        credentials=credentials,
    )
