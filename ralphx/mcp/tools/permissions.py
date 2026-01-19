"""Permissions MCP tools.

Tools for managing Claude CLI permissions:
- ralphx_check_permissions: Check current permissions
- ralphx_setup_permissions: Auto-configure permissions
- ralphx_apply_permission_preset: Apply preset (research/impl/full)
"""

from typing import Optional

from ralphx.mcp.base import (
    MCPError,
    ToolDefinition,
    ToolError,
    make_schema,
    prop_bool,
    prop_enum,
    prop_string,
)
from ralphx.mcp.tools.projects import get_manager


def check_permissions(
    slug: str,
    loop_name: Optional[str] = None,
) -> dict:
    """Check Claude CLI permissions for a project.

    Verifies that required tools and permissions are configured
    for the specified loop or project defaults.
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    try:
        from pathlib import Path as PathLib
        from ralphx.core.permissions import PermissionManager

        pm = PermissionManager(PathLib(project.path))
        allowed = pm.get_allowed_tools()
        blocked = pm.get_blocked_tools()

        return {
            "configured": pm.settings_exist(),
            "missing": [],
            "available": allowed,
            "blocked": blocked,
            "warnings": [],
            "settings_path": str(pm.settings_path),
        }
    except ImportError:
        # Fallback: basic check
        import os
        import json
        from pathlib import Path

        settings_path = Path(project.path) / ".claude" / "settings.json"

        if not settings_path.exists():
            return {
                "configured": False,
                "missing": ["settings.json not found"],
                "available": [],
                "warnings": ["Could not verify permissions - settings file not found"],
                "settings_path": str(settings_path),
            }

        try:
            with open(settings_path) as f:
                settings = json.load(f)

            permissions = settings.get("permissions", {})
            allow = permissions.get("allow", [])

            return {
                "configured": len(allow) > 0,
                "missing": [],
                "available": allow,
                "warnings": [],
                "settings_path": str(settings_path),
            }
        except Exception as e:
            return {
                "configured": False,
                "missing": [f"Error reading settings: {e}"],
                "available": [],
                "warnings": [str(e)],
            }
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Permission check failed: {e}",
            details={"slug": slug},
        )


def setup_permissions(
    slug: str,
    loop_name: Optional[str] = None,
    dry_run: bool = True,
) -> dict:
    """Auto-configure Claude CLI permissions for a project.

    Analyzes required tools for loops and configures permissions
    in Claude's settings.json.

    Args:
        slug: Project slug
        loop_name: Optional specific loop to configure for
        dry_run: If True, only show what would be configured
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    try:
        from ralphx.core.permissions import PermissionManager

        pm = PermissionManager(project.path)

        if dry_run:
            result = pm.analyze(loop_name=loop_name)
            return {
                "dry_run": True,
                "would_add": result.get("required", []),
                "current": result.get("current", []),
                "loop_name": loop_name,
            }

        result = pm.auto_configure(loop_name=loop_name)

        return {
            "dry_run": False,
            "added": result.get("added", []),
            "already_present": result.get("already_present", []),
            "settings_path": result.get("settings_path"),
            "message": "Permissions configured successfully",
        }
    except ImportError:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message="Permissions module not available",
            details={"slug": slug},
        )
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Permission setup failed: {e}",
            details={"slug": slug},
        )


def apply_permission_preset(
    slug: str,
    preset: str,
    dry_run: bool = True,
) -> dict:
    """Apply a permission preset.

    Presets:
    - research: Read-only tools (Read, Glob, Grep, WebFetch)
    - implementation: Read + write tools (Edit, Write, Bash limited)
    - full: All tools including Bash

    Args:
        slug: Project slug
        preset: Preset name (research, implementation, full)
        dry_run: If True, only show what would be configured
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    valid_presets = ["research", "implementation", "full"]
    if preset not in valid_presets:
        raise ToolError.validation_error(
            f"Invalid preset: {preset}. Must be one of: {valid_presets}",
        )

    try:
        from ralphx.core.permissions import PermissionManager, PRESETS

        pm = PermissionManager(project.path)
        preset_tools = PRESETS.get(preset, [])

        if dry_run:
            current = pm.get_current_permissions()
            return {
                "dry_run": True,
                "preset": preset,
                "would_set": preset_tools,
                "current": current,
            }

        result = pm.apply_preset(preset)

        return {
            "dry_run": False,
            "preset": preset,
            "applied": preset_tools,
            "settings_path": result.get("settings_path"),
            "message": f"Applied '{preset}' preset successfully",
        }
    except ImportError:
        # Fallback: manual preset application
        import json
        from pathlib import Path

        presets = {
            "research": [
                "Read(*)",
                "Glob(*)",
                "Grep(*)",
                "WebFetch(*)",
                "WebSearch(*)",
            ],
            "implementation": [
                "Read(*)",
                "Glob(*)",
                "Grep(*)",
                "Edit(*)",
                "Write(*)",
                "Bash(npm test:*)",
                "Bash(git:*)",
            ],
            "full": [
                "Read(*)",
                "Glob(*)",
                "Grep(*)",
                "Edit(*)",
                "Write(*)",
                "Bash(*)",
                "WebFetch(*)",
                "WebSearch(*)",
            ],
        }

        preset_tools = presets.get(preset, [])
        settings_path = Path(project.path) / ".claude" / "settings.json"

        if dry_run:
            current = []
            if settings_path.exists():
                try:
                    with open(settings_path) as f:
                        settings = json.load(f)
                    current = settings.get("permissions", {}).get("allow", [])
                except Exception:
                    pass

            return {
                "dry_run": True,
                "preset": preset,
                "would_set": preset_tools,
                "current": current,
            }

        # Apply preset
        settings_path.parent.mkdir(parents=True, exist_ok=True)

        settings = {}
        if settings_path.exists():
            try:
                with open(settings_path) as f:
                    settings = json.load(f)
            except Exception:
                pass

        if "permissions" not in settings:
            settings["permissions"] = {}
        settings["permissions"]["allow"] = preset_tools

        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)

        return {
            "dry_run": False,
            "preset": preset,
            "applied": preset_tools,
            "settings_path": str(settings_path),
            "message": f"Applied '{preset}' preset successfully",
        }
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to apply preset: {e}",
            details={"preset": preset},
        )


def get_permissions_tools() -> list[ToolDefinition]:
    """Get all permissions tool definitions."""
    return [
        ToolDefinition(
            name="ralphx_check_permissions",
            description="Check Claude CLI permissions for a project",
            handler=check_permissions,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "loop_name": prop_string("Loop name to check permissions for"),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_setup_permissions",
            description="Auto-configure Claude CLI permissions based on loop requirements",
            handler=setup_permissions,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "loop_name": prop_string("Loop name to configure for"),
                    "dry_run": prop_bool("Only show what would be configured (default: true)"),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_apply_permission_preset",
            description="Apply a permission preset (research=read-only, implementation=read+write, full=all)",
            handler=apply_permission_preset,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "preset": prop_enum("Preset name", ["research", "implementation", "full"]),
                    "dry_run": prop_bool("Only show what would be configured (default: true)"),
                },
                required=["slug", "preset"],
            ),
        ),
    ]
