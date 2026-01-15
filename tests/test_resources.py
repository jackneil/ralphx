"""Tests for project resource management."""

import tempfile
from pathlib import Path

import pytest

from ralphx.core.project_db import ProjectDatabase
from ralphx.core.resources import (
    InjectionPosition,
    ResourceManager,
    ResourceType,
)


@pytest.fixture
def project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        # Create .ralphx directory structure
        ralphx_dir = project_path / ".ralphx"
        ralphx_dir.mkdir()

        # Create resources directories
        resources_dir = ralphx_dir / "resources"
        for resource_type in ResourceType:
            (resources_dir / resource_type.value).mkdir(parents=True)

        yield project_path


@pytest.fixture
def db(project_dir):
    """Create a project database."""
    db = ProjectDatabase(project_dir)
    yield db
    db.close()


@pytest.fixture
def resource_manager(project_dir, db):
    """Create a resource manager."""
    return ResourceManager(project_dir, db=db)


class TestResourceManager:
    """Test ResourceManager functionality."""

    def test_create_resource(self, resource_manager):
        """Test creating a resource."""
        resource = resource_manager.create_resource(
            name="main",
            resource_type=ResourceType.DESIGN_DOC,
            content="# Design Document\n\nThis is the design.",
        )

        assert resource["name"] == "design_doc/main"
        assert resource["resource_type"] == "design_doc"
        assert resource["enabled"]  # SQLite stores as 0/1

        # Verify file was created
        file_path = resource_manager._resources_path / resource["file_path"]
        assert file_path.exists()
        assert "Design Document" in file_path.read_text()

    def test_get_resource(self, resource_manager):
        """Test getting a resource by ID."""
        created = resource_manager.create_resource(
            name="test",
            resource_type=ResourceType.ARCHITECTURE,
            content="# Architecture",
        )

        resource = resource_manager.get_resource(created["id"])
        assert resource is not None
        assert resource["name"] == "architecture/test"

    def test_list_resources(self, resource_manager):
        """Test listing resources."""
        # Create multiple resources
        resource_manager.create_resource(
            name="design", resource_type=ResourceType.DESIGN_DOC, content="# Design"
        )
        resource_manager.create_resource(
            name="arch", resource_type=ResourceType.ARCHITECTURE, content="# Arch"
        )
        resource_manager.create_resource(
            name="standards",
            resource_type=ResourceType.CODING_STANDARDS,
            content="# Standards",
        )

        # List all
        resources = resource_manager.list_resources()
        assert len(resources) == 3

        # List by type
        design_docs = resource_manager.list_resources(resource_type=ResourceType.DESIGN_DOC)
        assert len(design_docs) == 1
        assert design_docs[0]["name"] == "design_doc/design"

    def test_update_resource(self, resource_manager):
        """Test updating a resource."""
        created = resource_manager.create_resource(
            name="test",
            resource_type=ResourceType.CUSTOM,
            content="# Original Content",
        )

        # Update content and settings
        success = resource_manager.update_resource(
            resource_id=created["id"],
            content="# Updated Content",
            enabled=False,
            priority=50,
        )
        assert success

        # Verify updates
        resource = resource_manager.get_resource(created["id"])
        assert not resource["enabled"]  # SQLite stores as 0/1
        assert resource["priority"] == 50

        # Verify file content updated
        loaded = resource_manager.load_resource(resource)
        assert "Updated Content" in loaded.content

    def test_delete_resource(self, resource_manager):
        """Test deleting a resource."""
        created = resource_manager.create_resource(
            name="to_delete",
            resource_type=ResourceType.CUSTOM,
            content="# To Delete",
        )

        file_path = resource_manager._resources_path / created["file_path"]
        assert file_path.exists()

        # Delete
        success = resource_manager.delete_resource(created["id"])
        assert success

        # Verify deleted
        assert resource_manager.get_resource(created["id"]) is None
        assert not file_path.exists()

    def test_sync_from_filesystem(self, resource_manager, project_dir):
        """Test syncing resources from filesystem."""
        # Create files directly in filesystem
        design_dir = project_dir / ".ralphx" / "resources" / "design_doc"
        (design_dir / "manual1.md").write_text("# Manual Design 1")
        (design_dir / "manual2.md").write_text("# Manual Design 2")

        arch_dir = project_dir / ".ralphx" / "resources" / "architecture"
        (arch_dir / "system.md").write_text("# System Architecture")

        # Sync
        result = resource_manager.sync_from_filesystem()
        assert result["added"] == 3
        assert result["updated"] == 0
        assert result["removed"] == 0

        # Verify resources created
        resources = resource_manager.list_resources()
        assert len(resources) == 3

        # Sync again should not add duplicates
        result = resource_manager.sync_from_filesystem()
        assert result["added"] == 0

        # Remove a file and sync
        (design_dir / "manual1.md").unlink()
        result = resource_manager.sync_from_filesystem()
        assert result["removed"] == 1

    def test_load_resource_content(self, resource_manager):
        """Test loading resource with content."""
        created = resource_manager.create_resource(
            name="loadme",
            resource_type=ResourceType.DOMAIN_KNOWLEDGE,
            content="# Domain Knowledge\n\nImportant domain info.",
        )

        resource = resource_manager.db.get_resource(created["id"])
        loaded = resource_manager.load_resource(resource)

        assert loaded is not None
        assert loaded.content is not None
        assert "Domain Knowledge" in loaded.content
        assert loaded.resource_type == ResourceType.DOMAIN_KNOWLEDGE

    def test_load_for_loop_default_inheritance(self, resource_manager):
        """Test loading resources for a loop with default inheritance."""
        from ralphx.models.loop import LoopConfig

        # Create resources with different inherit_default settings
        resource_manager.create_resource(
            name="inherited",
            resource_type=ResourceType.DESIGN_DOC,
            content="# Inherited",
        )
        resource_manager.update_resource(
            resource_id=resource_manager.db.get_resource_by_name("design_doc/inherited")["id"],
            inherit_default=True,
        )

        resource_manager.create_resource(
            name="not_inherited",
            resource_type=ResourceType.CUSTOM,
            content="# Not Inherited",
        )
        resource_manager.update_resource(
            resource_id=resource_manager.db.get_resource_by_name("custom/not_inherited")["id"],
            inherit_default=False,
        )

        # Create a minimal loop config
        loop_config = LoopConfig(
            name="test_loop",
            display_name="Test Loop",
            type="generator",
            modes={
                "default": {
                    "timeout": 300,
                    "model": "sonnet",
                    "prompt_template": "prompts/default.md",
                }
            },
            mode_selection={"strategy": "fixed", "fixed_mode": "default"},
        )

        # Load resources for loop
        resource_set = resource_manager.load_for_loop(loop_config)

        # Should only include the inherited resource
        names = resource_set.all_names()
        assert "design_doc/inherited" in names
        assert "custom/not_inherited" not in names

    def test_build_prompt_section(self, resource_manager):
        """Test building prompt sections from resources."""
        # Create resources at different positions
        resource_manager.create_resource(
            name="standards",
            resource_type=ResourceType.CODING_STANDARDS,
            content="# Coding Standards\n\nFollow these rules.",
        )

        resource_manager.create_resource(
            name="design",
            resource_type=ResourceType.DESIGN_DOC,
            content="# Design\n\nThe design is...",
        )

        # Load resources
        from ralphx.models.loop import LoopConfig

        loop_config = LoopConfig(
            name="test",
            display_name="Test",
            type="generator",
            modes={"default": {"timeout": 300, "model": "sonnet", "prompt_template": "x.md"}},
            mode_selection={"strategy": "fixed", "fixed_mode": "default"},
        )
        resource_set = resource_manager.load_for_loop(loop_config)

        # Build sections
        before_prompt = resource_manager.build_prompt_section(
            resource_set, InjectionPosition.BEFORE_PROMPT
        )
        after_design_doc = resource_manager.build_prompt_section(
            resource_set, InjectionPosition.AFTER_DESIGN_DOC
        )

        # Coding standards should be in BEFORE_PROMPT
        assert "Coding Standards" in before_prompt

        # Design doc should be in AFTER_DESIGN_DOC
        assert "Design" in after_design_doc


class TestInjectionPosition:
    """Test injection position enum."""

    def test_all_positions(self):
        """Test all injection positions exist."""
        assert InjectionPosition.BEFORE_PROMPT.value == "before_prompt"
        assert InjectionPosition.AFTER_DESIGN_DOC.value == "after_design_doc"
        assert InjectionPosition.BEFORE_TASK.value == "before_task"
        assert InjectionPosition.AFTER_TASK.value == "after_task"


class TestResourceType:
    """Test resource type enum."""

    def test_all_types(self):
        """Test all resource types exist."""
        assert ResourceType.DESIGN_DOC.value == "design_doc"
        assert ResourceType.ARCHITECTURE.value == "architecture"
        assert ResourceType.CODING_STANDARDS.value == "coding_standards"
        assert ResourceType.DOMAIN_KNOWLEDGE.value == "domain_knowledge"
        assert ResourceType.CUSTOM.value == "custom"
