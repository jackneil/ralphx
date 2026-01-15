"""Permission management for RalphX.

Implements:
- PermissionManager for Claude CLI permission configuration
- Permission presets for research and implementation modes
- Pre-flight permission checking
- Permission block detection
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ralphx.models.loop import LoopConfig, Mode


# Permission presets
RESEARCH_PERMISSIONS = {
    "allowedTools": [
        "Read",
        "Glob",
        "Grep",
        "WebSearch",
        "WebFetch",
    ],
    "blockedTools": [
        "Write",
        "Edit",
        "Bash",
        "NotebookEdit",
    ],
}

IMPLEMENTATION_PERMISSIONS = {
    "allowedTools": [
        "Read",
        "Write",
        "Edit",
        "Glob",
        "Grep",
        "Bash",
        "NotebookEdit",
    ],
    "blockedTools": [],
}

FULL_PERMISSIONS = {
    "allowedTools": [],  # Empty means all allowed
    "blockedTools": [],
}


@dataclass
class PermissionCheck:
    """Result of a permission check."""

    tool: str
    allowed: bool
    blocked: bool
    source: str  # "settings", "loop", "default"


@dataclass
class PermissionReport:
    """Complete permission report."""

    checks: list[PermissionCheck] = field(default_factory=list)
    missing_tools: list[str] = field(default_factory=list)
    blocked_tools: list[str] = field(default_factory=list)

    @property
    def all_allowed(self) -> bool:
        """Check if all required tools are allowed."""
        return len(self.missing_tools) == 0 and len(self.blocked_tools) == 0

    def summary(self) -> str:
        """Get a summary."""
        if self.all_allowed:
            return "All required permissions are configured"
        parts = []
        if self.missing_tools:
            parts.append(f"Missing: {', '.join(self.missing_tools)}")
        if self.blocked_tools:
            parts.append(f"Blocked: {', '.join(self.blocked_tools)}")
        return "; ".join(parts)


class PermissionManager:
    """Manages Claude CLI permissions for a project.

    Features:
    - Read/write .claude/settings.json
    - Apply permission presets
    - Check required permissions for loops
    - Detect permission blocks in output
    """

    def __init__(self, project_path: Path):
        """Initialize the permission manager.

        Args:
            project_path: Path to the project directory.
        """
        self.project_path = project_path
        self._settings_path = project_path / ".claude" / "settings.json"

    @property
    def settings_path(self) -> Path:
        """Get the path to settings.json."""
        return self._settings_path

    def settings_exist(self) -> bool:
        """Check if settings file exists."""
        return self._settings_path.exists()

    def read_settings(self) -> dict:
        """Read current settings.

        Returns:
            Settings dictionary or empty dict.
        """
        if not self._settings_path.exists():
            return {}

        try:
            with open(self._settings_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def write_settings(self, settings: dict) -> None:
        """Write settings to file.

        Args:
            settings: Settings dictionary.
        """
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._settings_path, 'w') as f:
            json.dump(settings, f, indent=2)

    def get_allowed_tools(self) -> list[str]:
        """Get list of allowed tools from settings.

        Returns:
            List of tool names. Empty list means all allowed.
        """
        settings = self.read_settings()
        return settings.get("allowedTools", [])

    def get_blocked_tools(self) -> list[str]:
        """Get list of blocked tools from settings.

        Returns:
            List of blocked tool names.
        """
        settings = self.read_settings()
        return settings.get("blockedTools", [])

    def set_allowed_tools(self, tools: list[str]) -> None:
        """Set allowed tools.

        Args:
            tools: List of tool names to allow.
        """
        settings = self.read_settings()
        settings["allowedTools"] = tools
        self.write_settings(settings)

    def set_blocked_tools(self, tools: list[str]) -> None:
        """Set blocked tools.

        Args:
            tools: List of tool names to block.
        """
        settings = self.read_settings()
        settings["blockedTools"] = tools
        self.write_settings(settings)

    def apply_preset(self, preset: str) -> None:
        """Apply a permission preset.

        Args:
            preset: Preset name ("research", "implementation", "full").
        """
        if preset == "research":
            permissions = RESEARCH_PERMISSIONS
        elif preset == "implementation":
            permissions = IMPLEMENTATION_PERMISSIONS
        elif preset == "full":
            permissions = FULL_PERMISSIONS
        else:
            raise ValueError(f"Unknown preset: {preset}")

        settings = self.read_settings()
        settings.update(permissions)
        self.write_settings(settings)

    def get_required_tools(self, loop_config: LoopConfig) -> set[str]:
        """Get all tools required by a loop configuration.

        Args:
            loop_config: Loop configuration.

        Returns:
            Set of required tool names.
        """
        tools = set()
        for mode in loop_config.modes.values():
            if mode.tools:
                tools.update(mode.tools)
        return tools

    def get_mode_tools(self, mode: Mode) -> set[str]:
        """Get tools required by a specific mode.

        Args:
            mode: Mode configuration.

        Returns:
            Set of required tool names.
        """
        return set(mode.tools) if mode.tools else set()

    def check_permissions(
        self,
        required_tools: set[str],
    ) -> PermissionReport:
        """Check if required tools are allowed.

        Args:
            required_tools: Set of tools that need to be allowed.

        Returns:
            PermissionReport with check results.
        """
        allowed = set(self.get_allowed_tools())
        blocked = set(self.get_blocked_tools())

        report = PermissionReport()

        for tool in required_tools:
            check = PermissionCheck(
                tool=tool,
                allowed=False,
                blocked=False,
                source="default",
            )

            # Check if blocked
            if tool in blocked:
                check.blocked = True
                check.source = "settings"
                report.blocked_tools.append(tool)

            # Check if allowed (empty list means all allowed)
            elif not allowed or tool in allowed:
                check.allowed = True
                check.source = "settings" if allowed else "default"

            else:
                # Tool not in allowed list
                report.missing_tools.append(tool)

            report.checks.append(check)

        return report

    def check_loop_permissions(
        self,
        loop_config: LoopConfig,
    ) -> PermissionReport:
        """Check permissions for a loop configuration.

        Args:
            loop_config: Loop configuration.

        Returns:
            PermissionReport with check results.
        """
        required = self.get_required_tools(loop_config)
        return self.check_permissions(required)

    def auto_configure(
        self,
        loop_config: LoopConfig,
        allow_all: bool = False,
    ) -> list[str]:
        """Auto-configure permissions for a loop.

        Args:
            loop_config: Loop configuration.
            allow_all: If True, allows all tools, otherwise adds required.

        Returns:
            List of tools that were added.
        """
        if allow_all:
            self.apply_preset("full")
            return []

        required = self.get_required_tools(loop_config)
        current = set(self.get_allowed_tools())
        blocked = set(self.get_blocked_tools())

        # Remove required tools from blocked list
        new_blocked = blocked - required
        if new_blocked != blocked:
            self.set_blocked_tools(list(new_blocked))

        # Add required tools to allowed list
        added = []
        if current:  # Only if not empty (empty means all allowed)
            new_allowed = current | required
            if new_allowed != current:
                added = list(required - current)
                self.set_allowed_tools(list(new_allowed))

        return added

    @staticmethod
    def detect_permission_block(output: str) -> Optional[str]:
        """Detect if output indicates a permission block.

        Args:
            output: Claude CLI output text.

        Returns:
            Blocked tool name if detected, None otherwise.
        """
        # Common permission block patterns
        patterns = [
            "permission to use",
            "not allowed to use",
            "blocked tool",
            "requires permission",
            "access denied",
            "tool is blocked",
        ]

        lower_output = output.lower()
        for pattern in patterns:
            if pattern in lower_output:
                # Try to extract tool name
                tools = ["Read", "Write", "Edit", "Bash", "Glob", "Grep",
                         "WebSearch", "WebFetch", "NotebookEdit"]
                for tool in tools:
                    if tool.lower() in lower_output:
                        return tool
                return "unknown"

        return None

    def suggest_preset(self, loop_config: LoopConfig) -> str:
        """Suggest a permission preset based on loop configuration.

        Args:
            loop_config: Loop configuration.

        Returns:
            Suggested preset name.
        """
        required = self.get_required_tools(loop_config)

        # Check for write/edit operations
        write_tools = {"Write", "Edit", "Bash", "NotebookEdit"}
        if required & write_tools:
            return "implementation"

        return "research"
