"""Workspace management for RalphX.

Handles initialization and management of:
- Global workspace: ~/.ralphx/ (app data, project registry)
- Project workspace: <project>/.ralphx/ (project-specific data, portable)
"""

import os
import re
from pathlib import Path
from typing import Optional

# Default global workspace location
DEFAULT_WORKSPACE = Path.home() / ".ralphx"

# Project-local workspace directory name
PROJECT_WORKSPACE_DIR = ".ralphx"


def get_workspace_path() -> Path:
    """Get the workspace path, respecting RALPHX_HOME environment variable.

    Returns:
        Path to the RalphX workspace directory.
    """
    env_path = os.environ.get("RALPHX_HOME")
    if env_path:
        return Path(env_path)
    return DEFAULT_WORKSPACE


def ensure_workspace() -> Path:
    """Ensure the workspace directory exists with proper structure.

    Creates the following structure:
        ~/.ralphx/
        ├── ralphx.db              # SQLite database
        ├── projects/              # Per-project workspaces
        ├── guardrails/            # Global guardrails
        │   ├── system/
        │   ├── safety/
        │   ├── domain/
        │   ├── output/
        │   └── custom/
        ├── templates/             # Loop templates
        ├── logs/                  # Log files
        └── backups/               # Database backups

    Returns:
        Path to the workspace directory.
    """
    workspace = get_workspace_path()

    # Create main workspace directory
    workspace.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    subdirs = [
        "projects",
        "guardrails/system",
        "guardrails/safety",
        "guardrails/domain",
        "guardrails/output",
        "guardrails/custom",
        "templates",
        "logs",
        "backups",
    ]

    for subdir in subdirs:
        (workspace / subdir).mkdir(parents=True, exist_ok=True)

    return workspace


def get_project_workspace(slug: str) -> Path:
    """Get the workspace path for a specific project.

    Args:
        slug: Project slug (lowercase, alphanumeric + underscores).

    Returns:
        Path to the project workspace directory.
    """
    workspace = get_workspace_path()
    return workspace / "projects" / slug


def ensure_project_workspace(slug: str) -> Path:
    """Ensure a project workspace exists with proper structure.

    Creates the following structure:
        ~/.ralphx/projects/{slug}/
        ├── guardrails/            # Project-specific guardrails
        ├── prompts/               # Generated prompts (for debugging)
        └── sessions/              # Session metadata

    Args:
        slug: Project slug.

    Returns:
        Path to the project workspace directory.
    """
    project_path = get_project_workspace(slug)

    subdirs = [
        "guardrails",
        "prompts",
        "sessions",
    ]

    for subdir in subdirs:
        (project_path / subdir).mkdir(parents=True, exist_ok=True)

    return project_path


def get_database_path() -> Path:
    """Get the path to the SQLite database.

    Returns:
        Path to the database file.
    """
    return get_workspace_path() / "ralphx.db"


def get_global_guardrails_path() -> Path:
    """Get the path to global guardrails directory.

    Returns:
        Path to the global guardrails directory.
    """
    return get_workspace_path() / "guardrails"


def get_logs_path() -> Path:
    """Get the path to logs directory.

    Returns:
        Path to the logs directory.
    """
    return get_workspace_path() / "logs"


def get_backups_path() -> Path:
    """Get the path to backups directory.

    Returns:
        Path to the backups directory.
    """
    return get_workspace_path() / "backups"


def workspace_exists() -> bool:
    """Check if the workspace has been initialized.

    Returns:
        True if workspace exists, False otherwise.
    """
    workspace = get_workspace_path()
    return workspace.exists() and (workspace / "projects").exists()


def clean_workspace(confirm: bool = False) -> None:
    """Remove the entire workspace directory.

    WARNING: This is destructive and will delete all RalphX data.

    Args:
        confirm: Must be True to actually delete.

    Raises:
        ValueError: If confirm is not True.
    """
    if not confirm:
        raise ValueError("Must pass confirm=True to clean workspace")

    import shutil

    workspace = get_workspace_path()
    if workspace.exists():
        shutil.rmtree(workspace)


# ========== Project-Local Workspace Functions ==========


def get_project_ralphx_path(project_path: str | Path) -> Path:
    """Get the .ralphx directory path for a project.

    Args:
        project_path: Path to the project directory.

    Returns:
        Path to <project>/.ralphx/
    """
    return Path(project_path) / PROJECT_WORKSPACE_DIR


def ensure_project_ralphx(project_path: str | Path) -> Path:
    """Ensure a project's .ralphx directory exists with proper structure.

    Creates the following structure:
        <project>/.ralphx/
        ├── ralphx.db              # Project-local database
        ├── config.yaml            # Project-level settings
        ├── loops/                 # Per-loop directories
        ├── templates/             # Permission templates
        └── resources/             # Project resources
            ├── design_doc/        # Design documents
            ├── architecture/      # Architecture docs
            ├── coding_standards/  # Coding standards
            ├── domain_knowledge/  # Domain-specific knowledge
            └── custom/            # Custom resources

    Args:
        project_path: Path to the project directory.

    Returns:
        Path to the .ralphx directory.
    """
    ralphx_path = get_project_ralphx_path(project_path)

    # Create main .ralphx directory
    ralphx_path.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    subdirs = [
        "loops",
        "templates",
        "resources/design_doc",
        "resources/architecture",
        "resources/coding_standards",
        "resources/domain_knowledge",
        "resources/custom",
    ]

    for subdir in subdirs:
        (ralphx_path / subdir).mkdir(parents=True, exist_ok=True)

    return ralphx_path


def get_project_database_path(project_path: str | Path) -> Path:
    """Get the path to a project's local database.

    Args:
        project_path: Path to the project directory.

    Returns:
        Path to <project>/.ralphx/ralphx.db
    """
    return get_project_ralphx_path(project_path) / "ralphx.db"


def get_project_config_path(project_path: str | Path) -> Path:
    """Get the path to a project's config file.

    Args:
        project_path: Path to the project directory.

    Returns:
        Path to <project>/.ralphx/config.yaml
    """
    return get_project_ralphx_path(project_path) / "config.yaml"


def project_has_ralphx(project_path: str | Path) -> bool:
    """Check if a project has a .ralphx directory.

    Args:
        project_path: Path to the project directory.

    Returns:
        True if .ralphx/ exists, False otherwise.
    """
    return get_project_ralphx_path(project_path).exists()


# ========== Loop Directory Functions ==========

# Valid loop name pattern: alphanumeric, underscores, hyphens only
LOOP_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_loop_name(loop_name: str) -> None:
    """Validate that a loop name is safe and doesn't contain path traversal.

    Args:
        loop_name: Name of the loop to validate.

    Raises:
        ValueError: If loop name is invalid.
    """
    if not loop_name:
        raise ValueError("Loop name cannot be empty")
    if not LOOP_NAME_PATTERN.match(loop_name):
        raise ValueError(
            f"Invalid loop name '{loop_name}'. "
            "Use only letters, numbers, underscores, and hyphens."
        )
    if len(loop_name) > 100:
        raise ValueError("Loop name too long (max 100 characters)")


def get_loop_path(project_path: str | Path, loop_name: str) -> Path:
    """Get the path to a loop's directory.

    Args:
        project_path: Path to the project directory.
        loop_name: Name of the loop.

    Returns:
        Path to <project>/.ralphx/loops/{loop_name}/

    Raises:
        ValueError: If loop_name is invalid (path traversal attempt, etc.)
    """
    validate_loop_name(loop_name)
    return get_project_ralphx_path(project_path) / "loops" / loop_name


def ensure_loop_directory(project_path: str | Path, loop_name: str) -> Path:
    """Ensure a loop's directory exists with proper structure.

    Creates the following structure:
        <project>/.ralphx/loops/{loop_name}/
        ├── loop.yaml              # Loop configuration
        ├── settings.json          # Claude Code permissions
        ├── inputs/                # Imported files
        └── prompts/               # Prompt templates

    Args:
        project_path: Path to the project directory.
        loop_name: Name of the loop.

    Returns:
        Path to the loop directory.
    """
    loop_path = get_loop_path(project_path, loop_name)

    # Create main loop directory
    loop_path.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    subdirs = [
        "inputs",
        "prompts",
    ]

    for subdir in subdirs:
        (loop_path / subdir).mkdir(parents=True, exist_ok=True)

    return loop_path


def get_loop_config_path(project_path: str | Path, loop_name: str) -> Path:
    """Get the path to a loop's configuration file.

    Args:
        project_path: Path to the project directory.
        loop_name: Name of the loop.

    Returns:
        Path to <project>/.ralphx/loops/{loop_name}/loop.yaml
    """
    return get_loop_path(project_path, loop_name) / "loop.yaml"


def get_loop_settings_path(project_path: str | Path, loop_name: str) -> Path:
    """Get the path to a loop's Claude Code settings file.

    Args:
        project_path: Path to the project directory.
        loop_name: Name of the loop.

    Returns:
        Path to <project>/.ralphx/loops/{loop_name}/settings.json
    """
    return get_loop_path(project_path, loop_name) / "settings.json"


def get_loop_inputs_path(project_path: str | Path, loop_name: str) -> Path:
    """Get the path to a loop's inputs directory.

    Args:
        project_path: Path to the project directory.
        loop_name: Name of the loop.

    Returns:
        Path to <project>/.ralphx/loops/{loop_name}/inputs/
    """
    return get_loop_path(project_path, loop_name) / "inputs"


def get_loop_prompts_path(project_path: str | Path, loop_name: str) -> Path:
    """Get the path to a loop's prompts directory.

    Args:
        project_path: Path to the project directory.
        loop_name: Name of the loop.

    Returns:
        Path to <project>/.ralphx/loops/{loop_name}/prompts/
    """
    return get_loop_path(project_path, loop_name) / "prompts"


def list_loop_directories(project_path: str | Path) -> list[str]:
    """List all loop directories in a project.

    Args:
        project_path: Path to the project directory.

    Returns:
        List of loop names (directory names).
    """
    loops_dir = get_project_ralphx_path(project_path) / "loops"
    if not loops_dir.exists():
        return []

    return [
        d.name for d in loops_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ]


# ========== Resource Directory Functions ==========


def get_resources_path(project_path: str | Path) -> Path:
    """Get the path to a project's resources directory.

    Args:
        project_path: Path to the project directory.

    Returns:
        Path to <project>/.ralphx/resources/
    """
    return get_project_ralphx_path(project_path) / "resources"


def get_resource_type_path(project_path: str | Path, resource_type: str) -> Path:
    """Get the path to a specific resource type directory.

    Args:
        project_path: Path to the project directory.
        resource_type: Type of resource (design_doc, architecture, etc.).

    Returns:
        Path to <project>/.ralphx/resources/{resource_type}/
    """
    return get_resources_path(project_path) / resource_type


def ensure_resources_directories(project_path: str | Path) -> Path:
    """Ensure all resource type directories exist.

    Args:
        project_path: Path to the project directory.

    Returns:
        Path to resources directory.
    """
    resources_path = get_resources_path(project_path)

    resource_types = [
        "design_doc",
        "architecture",
        "coding_standards",
        "domain_knowledge",
        "custom",
    ]

    for resource_type in resource_types:
        (resources_path / resource_type).mkdir(parents=True, exist_ok=True)

    return resources_path
