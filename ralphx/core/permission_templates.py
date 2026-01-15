"""Permission templates for Claude Code settings.

Pre-built settings.json templates for different loop types:
- planning: Read-only + web search (no file writes)
- implementation: Full file/bash access
- safe_implementation: Files only, limited bash
- read_only: Read files only, no modifications
"""

import json
from pathlib import Path
from typing import Optional


# Permission template definitions
TEMPLATES = {
    "planning": {
        "name": "Planning",
        "description": "Read-only + web search for generating stories/plans",
        "settings": {
            "permissions": {
                "allow": [
                    "Read(**)",
                    "Glob(**)",
                    "Grep(**)",
                    "WebSearch",
                    "WebFetch(*)",
                ],
                "deny": [
                    "Write(**)",
                    "Edit(**)",
                    "Bash(*)",
                    "NotebookEdit(**)",
                ],
            }
        },
    },
    "implementation": {
        "name": "Implementation",
        "description": "Full file/bash access for implementing code",
        "settings": {
            "permissions": {
                "allow": [
                    "Read(**)",
                    "Write(**)",
                    "Edit(**)",
                    "Glob(**)",
                    "Grep(**)",
                    "Bash(*)",
                    "NotebookEdit(**)",
                ],
                "deny": [],
            }
        },
    },
    "safe_implementation": {
        "name": "Safe Implementation",
        "description": "File access with limited bash (no destructive commands)",
        "settings": {
            "permissions": {
                "allow": [
                    "Read(**)",
                    "Write(**)",
                    "Edit(**)",
                    "Glob(**)",
                    "Grep(**)",
                    "Bash(npm test)",
                    "Bash(npm run *)",
                    "Bash(pytest *)",
                    "Bash(python -m pytest *)",
                    "Bash(git status)",
                    "Bash(git diff *)",
                    "Bash(git log *)",
                    "NotebookEdit(**)",
                ],
                "deny": [
                    "Bash(rm *)",
                    "Bash(sudo *)",
                    "Bash(chmod *)",
                    "Bash(git push *)",
                    "Bash(git reset *)",
                ],
            }
        },
    },
    "read_only": {
        "name": "Read Only",
        "description": "Read files only, no modifications at all",
        "settings": {
            "permissions": {
                "allow": [
                    "Read(**)",
                    "Glob(**)",
                    "Grep(**)",
                ],
                "deny": [
                    "Write(**)",
                    "Edit(**)",
                    "Bash(*)",
                    "NotebookEdit(**)",
                    "WebSearch",
                    "WebFetch(*)",
                ],
            }
        },
    },
    "research": {
        "name": "Research",
        "description": "Web search and file reading for research tasks",
        "settings": {
            "permissions": {
                "allow": [
                    "Read(**)",
                    "Glob(**)",
                    "Grep(**)",
                    "WebSearch",
                    "WebFetch(*)",
                ],
                "deny": [
                    "Write(**)",
                    "Edit(**)",
                    "Bash(*)",
                    "NotebookEdit(**)",
                ],
            }
        },
    },
}


def list_templates() -> list[dict]:
    """List all available permission templates.

    Returns:
        List of template info dicts with name, id, and description.
    """
    return [
        {
            "id": template_id,
            "name": template["name"],
            "description": template["description"],
        }
        for template_id, template in TEMPLATES.items()
    ]


def get_template(template_id: str) -> Optional[dict]:
    """Get a permission template by ID.

    Args:
        template_id: Template identifier (e.g., 'planning', 'implementation').

    Returns:
        Template dict with name, description, and settings, or None if not found.
    """
    return TEMPLATES.get(template_id)


def get_template_settings(template_id: str) -> Optional[dict]:
    """Get just the settings portion of a template.

    Args:
        template_id: Template identifier.

    Returns:
        Settings dict ready to write to settings.json, or None if not found.
    """
    template = TEMPLATES.get(template_id)
    if template:
        return template["settings"]
    return None


def write_settings_file(
    settings_path: Path,
    template_id: Optional[str] = None,
    custom_settings: Optional[dict] = None,
) -> None:
    """Write a Claude Code settings.json file.

    Args:
        settings_path: Path to write the settings.json file.
        template_id: Optional template to use as base.
        custom_settings: Optional custom settings to merge/override.

    Raises:
        ValueError: If template_id is invalid.
    """
    settings = {}

    if template_id:
        template = TEMPLATES.get(template_id)
        if not template:
            raise ValueError(f"Unknown template: {template_id}")
        settings = template["settings"].copy()

    if custom_settings:
        # Deep merge custom settings
        settings = _deep_merge(settings, custom_settings)

    # Ensure parent directory exists
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Write settings file
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)


def apply_template_to_loop(
    project_path: Path,
    loop_name: str,
    template_id: str,
) -> Path:
    """Apply a permission template to a loop's settings file.

    Args:
        project_path: Path to the project directory.
        loop_name: Name of the loop.
        template_id: Permission template to apply.

    Returns:
        Path to the created settings.json file.

    Raises:
        ValueError: If template_id is invalid.
    """
    from ralphx.core.workspace import get_loop_settings_path, ensure_loop_directory

    # Ensure loop directory exists
    ensure_loop_directory(project_path, loop_name)

    # Get settings path
    settings_path = get_loop_settings_path(project_path, loop_name)

    # Write settings
    write_settings_file(settings_path, template_id=template_id)

    return settings_path


def read_settings_file(settings_path: Path) -> Optional[dict]:
    """Read a Claude Code settings.json file.

    Args:
        settings_path: Path to the settings.json file.

    Returns:
        Settings dict, or None if file doesn't exist.
    """
    if not settings_path.exists():
        return None

    with open(settings_path) as f:
        return json.load(f)


def merge_settings(
    settings_path: Path,
    additional_allow: Optional[list[str]] = None,
    additional_deny: Optional[list[str]] = None,
) -> None:
    """Merge additional permissions into an existing settings file.

    Args:
        settings_path: Path to the settings.json file.
        additional_allow: Additional patterns to allow.
        additional_deny: Additional patterns to deny.
    """
    settings = read_settings_file(settings_path) or {"permissions": {"allow": [], "deny": []}}

    if "permissions" not in settings:
        settings["permissions"] = {"allow": [], "deny": []}

    if additional_allow:
        existing_allow = set(settings["permissions"].get("allow", []))
        existing_allow.update(additional_allow)
        settings["permissions"]["allow"] = sorted(existing_allow)

    if additional_deny:
        existing_deny = set(settings["permissions"].get("deny", []))
        existing_deny.update(additional_deny)
        settings["permissions"]["deny"] = sorted(existing_deny)

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries.

    Args:
        base: Base dictionary.
        override: Override dictionary (values take precedence).

    Returns:
        Merged dictionary.
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value

    return result
