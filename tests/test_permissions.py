"""Tests for RalphX permission management."""

import json
import tempfile
from pathlib import Path

import pytest

from ralphx.core.permissions import (
    FULL_PERMISSIONS,
    IMPLEMENTATION_PERMISSIONS,
    PermissionCheck,
    PermissionManager,
    PermissionReport,
    RESEARCH_PERMISSIONS,
)
from ralphx.models.loop import (
    LoopConfig,
    LoopType,
    Mode,
    ModeSelection,
    ModeSelectionStrategy,
)


@pytest.fixture
def project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def perm_manager(project_dir):
    """Create a permission manager."""
    return PermissionManager(project_dir)


@pytest.fixture
def loop_config():
    """Create a sample loop config."""
    return LoopConfig(
        name="research",
        display_name="Research Loop",
        type=LoopType.GENERATOR,
        modes={
            "default": Mode(
                timeout=300,
                model="sonnet",
                prompt_template="prompts/default.md",
                tools=["Read", "Glob", "Grep", "WebSearch"],
            ),
        },
        mode_selection=ModeSelection(
            strategy=ModeSelectionStrategy.FIXED,
            fixed_mode="default",
        ),
    )


class TestPermissionPresets:
    """Test permission presets."""

    def test_research_preset(self):
        """Test research preset values."""
        assert "Read" in RESEARCH_PERMISSIONS["allowedTools"]
        assert "Glob" in RESEARCH_PERMISSIONS["allowedTools"]
        assert "Write" in RESEARCH_PERMISSIONS["blockedTools"]
        assert "Bash" in RESEARCH_PERMISSIONS["blockedTools"]

    def test_implementation_preset(self):
        """Test implementation preset values."""
        assert "Read" in IMPLEMENTATION_PERMISSIONS["allowedTools"]
        assert "Write" in IMPLEMENTATION_PERMISSIONS["allowedTools"]
        assert "Edit" in IMPLEMENTATION_PERMISSIONS["allowedTools"]
        assert len(IMPLEMENTATION_PERMISSIONS["blockedTools"]) == 0

    def test_full_preset(self):
        """Test full preset values."""
        assert len(FULL_PERMISSIONS["allowedTools"]) == 0
        assert len(FULL_PERMISSIONS["blockedTools"]) == 0


class TestPermissionCheck:
    """Test PermissionCheck dataclass."""

    def test_default_values(self):
        """Test default values."""
        check = PermissionCheck(
            tool="Read",
            allowed=True,
            blocked=False,
            source="settings",
        )
        assert check.tool == "Read"
        assert check.allowed is True
        assert check.blocked is False
        assert check.source == "settings"


class TestPermissionReport:
    """Test PermissionReport dataclass."""

    def test_empty_report(self):
        """Test empty report."""
        report = PermissionReport()
        assert report.all_allowed is True
        assert report.summary() == "All required permissions are configured"

    def test_report_with_missing(self):
        """Test report with missing tools."""
        report = PermissionReport(
            missing_tools=["Write", "Edit"],
        )
        assert report.all_allowed is False
        assert "Missing: Write, Edit" in report.summary()

    def test_report_with_blocked(self):
        """Test report with blocked tools."""
        report = PermissionReport(
            blocked_tools=["Bash"],
        )
        assert report.all_allowed is False
        assert "Blocked: Bash" in report.summary()


class TestPermissionManager:
    """Test PermissionManager functionality."""

    def test_settings_path(self, perm_manager, project_dir):
        """Test settings path calculation."""
        expected = project_dir / ".claude" / "settings.json"
        assert perm_manager.settings_path == expected

    def test_settings_not_exist(self, perm_manager):
        """Test settings don't exist initially."""
        assert perm_manager.settings_exist() is False

    def test_read_empty_settings(self, perm_manager):
        """Test reading non-existent settings."""
        settings = perm_manager.read_settings()
        assert settings == {}

    def test_write_and_read_settings(self, perm_manager):
        """Test writing and reading settings."""
        settings = {
            "allowedTools": ["Read", "Write"],
            "blockedTools": ["Bash"],
        }
        perm_manager.write_settings(settings)

        assert perm_manager.settings_exist() is True

        loaded = perm_manager.read_settings()
        assert loaded == settings

    def test_get_allowed_tools(self, perm_manager):
        """Test getting allowed tools."""
        perm_manager.write_settings({
            "allowedTools": ["Read", "Glob"],
        })
        assert perm_manager.get_allowed_tools() == ["Read", "Glob"]

    def test_get_blocked_tools(self, perm_manager):
        """Test getting blocked tools."""
        perm_manager.write_settings({
            "blockedTools": ["Bash"],
        })
        assert perm_manager.get_blocked_tools() == ["Bash"]

    def test_set_allowed_tools(self, perm_manager):
        """Test setting allowed tools."""
        perm_manager.set_allowed_tools(["Read", "Write"])
        assert perm_manager.get_allowed_tools() == ["Read", "Write"]

    def test_set_blocked_tools(self, perm_manager):
        """Test setting blocked tools."""
        perm_manager.set_blocked_tools(["Bash"])
        assert perm_manager.get_blocked_tools() == ["Bash"]

    def test_apply_research_preset(self, perm_manager):
        """Test applying research preset."""
        perm_manager.apply_preset("research")
        assert "Read" in perm_manager.get_allowed_tools()
        assert "Write" in perm_manager.get_blocked_tools()

    def test_apply_implementation_preset(self, perm_manager):
        """Test applying implementation preset."""
        perm_manager.apply_preset("implementation")
        assert "Write" in perm_manager.get_allowed_tools()
        assert perm_manager.get_blocked_tools() == []

    def test_apply_full_preset(self, perm_manager):
        """Test applying full preset."""
        perm_manager.apply_preset("full")
        assert perm_manager.get_allowed_tools() == []
        assert perm_manager.get_blocked_tools() == []

    def test_apply_invalid_preset(self, perm_manager):
        """Test applying invalid preset."""
        with pytest.raises(ValueError):
            perm_manager.apply_preset("invalid")

    def test_get_required_tools(self, perm_manager, loop_config):
        """Test getting required tools from loop config."""
        required = perm_manager.get_required_tools(loop_config)
        assert "Read" in required
        assert "Glob" in required
        assert "WebSearch" in required

    def test_get_mode_tools(self, perm_manager, loop_config):
        """Test getting tools from a mode."""
        mode = loop_config.modes["default"]
        tools = perm_manager.get_mode_tools(mode)
        assert tools == {"Read", "Glob", "Grep", "WebSearch"}

    def test_check_permissions_all_allowed(self, perm_manager):
        """Test checking permissions when all allowed."""
        perm_manager.set_allowed_tools(["Read", "Glob", "Grep"])
        report = perm_manager.check_permissions({"Read", "Glob"})
        assert report.all_allowed is True

    def test_check_permissions_missing(self, perm_manager):
        """Test checking permissions with missing tools."""
        perm_manager.set_allowed_tools(["Read"])
        report = perm_manager.check_permissions({"Read", "Write"})
        assert report.all_allowed is False
        assert "Write" in report.missing_tools

    def test_check_permissions_blocked(self, perm_manager):
        """Test checking permissions with blocked tools."""
        perm_manager.set_blocked_tools(["Bash"])
        report = perm_manager.check_permissions({"Read", "Bash"})
        assert report.all_allowed is False
        assert "Bash" in report.blocked_tools

    def test_check_loop_permissions(self, perm_manager, loop_config):
        """Test checking loop permissions."""
        perm_manager.apply_preset("research")
        report = perm_manager.check_loop_permissions(loop_config)
        assert report.all_allowed is True

    def test_auto_configure(self, perm_manager, loop_config):
        """Test auto-configuring permissions."""
        perm_manager.set_allowed_tools(["Read"])
        added = perm_manager.auto_configure(loop_config)

        # Should add the missing tools
        assert "Glob" in added or "Grep" in added or "WebSearch" in added

        # Check they're now allowed
        allowed = set(perm_manager.get_allowed_tools())
        for tool in loop_config.modes["default"].tools:
            assert tool in allowed

    def test_auto_configure_removes_blocked(self, perm_manager, loop_config):
        """Test auto-configure removes blocked tools."""
        perm_manager.set_blocked_tools(["Read", "Bash"])
        perm_manager.auto_configure(loop_config)

        # Read should be removed from blocked (it's required)
        blocked = perm_manager.get_blocked_tools()
        assert "Read" not in blocked
        # Bash should still be blocked (not required)
        assert "Bash" in blocked

    def test_detect_permission_block_with_tool(self, perm_manager):
        """Test detecting permission block."""
        output = "Claude needs permission to use the Write tool"
        tool = PermissionManager.detect_permission_block(output)
        assert tool == "Write"

    def test_detect_permission_block_no_block(self, perm_manager):
        """Test no permission block detection."""
        output = "Here is the file content you requested."
        tool = PermissionManager.detect_permission_block(output)
        assert tool is None

    def test_suggest_preset_research(self, perm_manager):
        """Test suggesting research preset."""
        config = LoopConfig(
            name="research",
            display_name="Research",
            type=LoopType.GENERATOR,
            modes={
                "default": Mode(
                    timeout=300,
                    model="sonnet",
                    prompt_template="prompts/default.md",
                    tools=["Read", "Glob", "WebSearch"],
                ),
            },
            mode_selection=ModeSelection(
                strategy=ModeSelectionStrategy.FIXED,
                fixed_mode="default",
            ),
        )
        preset = perm_manager.suggest_preset(config)
        assert preset == "research"

    def test_suggest_preset_implementation(self, perm_manager):
        """Test suggesting implementation preset."""
        config = LoopConfig(
            name="implement",
            display_name="Implementation",
            type=LoopType.GENERATOR,
            modes={
                "default": Mode(
                    timeout=300,
                    model="sonnet",
                    prompt_template="prompts/default.md",
                    tools=["Read", "Write", "Edit", "Bash"],
                ),
            },
            mode_selection=ModeSelection(
                strategy=ModeSelectionStrategy.FIXED,
                fixed_mode="default",
            ),
        )
        preset = perm_manager.suggest_preset(config)
        assert preset == "implementation"
