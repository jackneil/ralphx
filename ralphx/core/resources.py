"""Resource management for RalphX.

Project-level resources (design docs, architecture, coding standards, etc.)
that can be inherited by loops and injected into prompts.

Resources are stored in <project>/.ralphx/resources/ with subdirectories:
- design_doc/
- architecture/
- coding_standards/
- domain_knowledge/
- custom/

Loops can configure which resources to inherit via their ContextConfig.resources field.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from ralphx.core.project_db import ProjectDatabase


class ResourceType(str, Enum):
    """Types of project resources."""

    DESIGN_DOC = "design_doc"
    ARCHITECTURE = "architecture"
    CODING_STANDARDS = "coding_standards"
    DOMAIN_KNOWLEDGE = "domain_knowledge"
    CUSTOM = "custom"


class InjectionPosition(str, Enum):
    """Where to inject content in the prompt.

    The prompt building pipeline injects content in this order:
    1. BEFORE_PROMPT - Coding standards, system guardrails (before everything)
    2. AFTER_DESIGN_DOC - Design docs, architecture, domain knowledge
    3. [TEMPLATE CONTENT] - The base prompt template
    4. BEFORE_TASK - Output guardrails
    5. AFTER_TASK - Custom resources, custom guardrails
    """

    BEFORE_PROMPT = "before_prompt"
    AFTER_DESIGN_DOC = "after_design_doc"
    BEFORE_TASK = "before_task"
    AFTER_TASK = "after_task"


# Default injection positions for each resource type
DEFAULT_POSITIONS: dict[ResourceType, InjectionPosition] = {
    ResourceType.DESIGN_DOC: InjectionPosition.AFTER_DESIGN_DOC,
    ResourceType.ARCHITECTURE: InjectionPosition.AFTER_DESIGN_DOC,
    ResourceType.CODING_STANDARDS: InjectionPosition.BEFORE_PROMPT,
    ResourceType.DOMAIN_KNOWLEDGE: InjectionPosition.AFTER_DESIGN_DOC,
    ResourceType.CUSTOM: InjectionPosition.AFTER_TASK,
}


@dataclass
class Resource:
    """A loaded resource with its content."""

    id: int
    name: str
    resource_type: ResourceType
    file_path: str
    injection_position: InjectionPosition
    enabled: bool
    inherit_default: bool
    priority: int
    content: Optional[str] = None


@dataclass
class ResourceSet:
    """Collection of resources grouped by injection position."""

    resources: list[Resource] = field(default_factory=list)

    def by_position(self, position: InjectionPosition) -> list[Resource]:
        """Get resources for a specific injection position."""
        return [r for r in self.resources if r.injection_position == position]

    def all_names(self) -> list[str]:
        """Get names of all resources in the set."""
        return [r.name for r in self.resources]


class ResourceManager:
    """Manages project-level resources with loop inheritance.

    Resources are markdown files stored in <project>/.ralphx/resources/
    that can be automatically injected into loop prompts based on type
    and configuration.

    Usage:
        manager = ResourceManager(project_path, db)
        resource_set = manager.load_for_loop(loop_config, mode_name)
        for position in InjectionPosition:
            section = manager.build_prompt_section(resource_set, position)
            if section:
                prompt = inject_at_position(prompt, section, position)
    """

    def __init__(
        self,
        project_path: str | Path,
        db: Optional[ProjectDatabase] = None,
    ):
        """Initialize the resource manager.

        Args:
            project_path: Path to the project directory.
            db: Optional database instance (creates one if not provided).
        """
        self.project_path = Path(project_path)
        self._db = db
        self._resources_path = self.project_path / ".ralphx" / "resources"

    @property
    def db(self) -> ProjectDatabase:
        """Get the database instance, creating one if needed."""
        if self._db is None:
            self._db = ProjectDatabase(self.project_path)
        return self._db

    def get_resources_path(self, resource_type: Optional[ResourceType] = None) -> Path:
        """Get the path to resources directory or a specific type subdirectory.

        Args:
            resource_type: Optional type to get subdirectory for.

        Returns:
            Path to resources directory or type subdirectory.
        """
        if resource_type:
            return self._resources_path / resource_type.value
        return self._resources_path

    def sync_from_filesystem(self) -> dict[str, int]:
        """Sync resources from filesystem to database.

        Discovers all markdown files in resources directories and
        creates/updates database entries.

        Returns:
            Dict with counts: added, updated, removed.
        """
        added = 0
        updated = 0
        removed = 0
        discovered_names: set[str] = set()

        # Scan each resource type directory
        for resource_type in ResourceType:
            type_dir = self.get_resources_path(resource_type)
            if not type_dir.exists():
                continue

            # Find all markdown files
            for file_path in type_dir.glob("*.md"):
                # Generate resource name from file path
                name = f"{resource_type.value}/{file_path.stem}"
                discovered_names.add(name)

                # Relative path for storage
                relative_path = str(file_path.relative_to(self._resources_path))

                # Check if already exists
                existing = self.db.get_resource_by_name(name)

                # Default injection position for this type
                default_position = DEFAULT_POSITIONS.get(
                    resource_type, InjectionPosition.AFTER_DESIGN_DOC
                )

                if existing:
                    # Update if file path changed
                    if existing["file_path"] != relative_path:
                        self.db.update_resource(
                            existing["id"],
                            file_path=relative_path,
                        )
                        updated += 1
                else:
                    # Create new resource entry
                    self.db.create_resource(
                        name=name,
                        resource_type=resource_type.value,
                        file_path=relative_path,
                        injection_position=default_position.value,
                    )
                    added += 1

        # Remove resources that no longer exist
        existing_resources = self.db.list_resources()
        for resource in existing_resources:
            if resource["name"] not in discovered_names:
                self.db.delete_resource(resource["id"])
                removed += 1

        return {"added": added, "updated": updated, "removed": removed}

    def load_resource(self, resource_data: dict) -> Optional[Resource]:
        """Load a resource with its content from disk.

        Args:
            resource_data: Resource dict from database.

        Returns:
            Resource with content loaded, or None if file doesn't exist.
        """
        file_path = self._resources_path / resource_data["file_path"]

        if not file_path.exists():
            return None

        try:
            content = file_path.read_text(encoding="utf-8")
        except (IOError, UnicodeDecodeError):
            return None

        return Resource(
            id=resource_data["id"],
            name=resource_data["name"],
            resource_type=ResourceType(resource_data["resource_type"]),
            file_path=resource_data["file_path"],
            injection_position=InjectionPosition(resource_data["injection_position"]),
            enabled=resource_data["enabled"],
            inherit_default=resource_data["inherit_default"],
            priority=resource_data["priority"],
            content=content,
        )

    def load_for_loop(
        self,
        loop_config,  # LoopConfig - avoid circular import
        mode_name: Optional[str] = None,
    ) -> ResourceSet:
        """Load resources for a specific loop based on its configuration.

        Args:
            loop_config: The loop configuration.
            mode_name: Optional mode name (for mode-specific filtering).

        Returns:
            ResourceSet with loaded resources.
        """
        resources: list[Resource] = []

        # Get resource config from loop
        resource_config = None
        if loop_config.context and hasattr(loop_config.context, "resources"):
            resource_config = loop_config.context.resources

        # If resources not configured, use defaults (inherit all with inherit_default=True)
        inherit_project = True
        include_list: Optional[list[str]] = None
        exclude_list: Optional[list[str]] = None

        if resource_config:
            inherit_project = resource_config.inherit_project_resources
            include_list = resource_config.include
            exclude_list = resource_config.exclude

        if not inherit_project:
            # Loop explicitly doesn't want project resources
            return ResourceSet(resources=[])

        # Load enabled resources from database
        db_resources = self.db.list_resources(enabled=True)

        for resource_data in db_resources:
            name = resource_data["name"]

            # Check include list (if specified, only include these)
            if include_list is not None and name not in include_list:
                continue

            # Check exclude list
            if exclude_list is not None and name in exclude_list:
                continue

            # Check inherit_default if no explicit include list
            if include_list is None and not resource_data["inherit_default"]:
                continue

            # Load the resource content
            resource = self.load_resource(resource_data)
            if resource and resource.content:
                resources.append(resource)

        # Sort by priority then name
        resources.sort(key=lambda r: (r.priority, r.name))

        return ResourceSet(resources=resources)

    def build_prompt_section(
        self,
        resource_set: ResourceSet,
        position: InjectionPosition,
        include_headers: bool = True,
    ) -> str:
        """Build the prompt section for a given injection position.

        Args:
            resource_set: Set of loaded resources.
            position: Injection position to build section for.
            include_headers: Whether to include section headers.

        Returns:
            Combined content for this position, or empty string if none.
        """
        resources = resource_set.by_position(position)

        if not resources:
            return ""

        sections = []
        for resource in resources:
            if not resource.content:
                continue

            if include_headers:
                # Create a header based on resource type
                header = self._get_resource_header(resource)
                sections.append(f"\n{header}\n{resource.content}\n")
            else:
                sections.append(resource.content)

        return "\n".join(sections)

    def _get_resource_header(self, resource: Resource) -> str:
        """Get a header string for a resource.

        Args:
            resource: The resource.

        Returns:
            Header string like "## Design Document" or "## Architecture".
        """
        type_labels = {
            ResourceType.DESIGN_DOC: "Design Document",
            ResourceType.ARCHITECTURE: "Architecture",
            ResourceType.CODING_STANDARDS: "Coding Standards",
            ResourceType.DOMAIN_KNOWLEDGE: "Domain Knowledge",
            ResourceType.CUSTOM: "Additional Context",
        }
        label = type_labels.get(resource.resource_type, "Resource")

        # Include filename for disambiguation if needed
        filename = Path(resource.file_path).stem
        if filename != resource.resource_type.value:
            return f"## {label}: {filename}"
        return f"## {label}"

    def list_resources(
        self,
        resource_type: Optional[ResourceType] = None,
        enabled: Optional[bool] = None,
    ) -> list[dict]:
        """List resources with optional filters.

        Args:
            resource_type: Filter by type.
            enabled: Filter by enabled status.

        Returns:
            List of resource dicts from database.
        """
        return self.db.list_resources(
            resource_type=resource_type.value if resource_type else None,
            enabled=enabled,
        )

    def get_resource(self, resource_id: int) -> Optional[dict]:
        """Get a resource by ID.

        Args:
            resource_id: Resource ID.

        Returns:
            Resource dict or None.
        """
        return self.db.get_resource(resource_id)

    def create_resource(
        self,
        name: str,
        resource_type: ResourceType,
        content: str,
        injection_position: Optional[InjectionPosition] = None,
    ) -> dict:
        """Create a new resource with content.

        Creates both the file and database entry.

        Args:
            name: Resource name (e.g., "design_doc/main").
            resource_type: Type of resource.
            content: Markdown content.
            injection_position: Where to inject (defaults based on type).

        Returns:
            Created resource dict.
        """
        # Determine file path
        if "/" in name:
            # Name includes type prefix
            file_name = name.split("/", 1)[1]
        else:
            file_name = name

        file_path = self.get_resources_path(resource_type) / f"{file_name}.md"

        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        file_path.write_text(content, encoding="utf-8")

        # Determine injection position
        if injection_position is None:
            injection_position = DEFAULT_POSITIONS.get(
                resource_type, InjectionPosition.AFTER_DESIGN_DOC
            )

        # Relative path for storage
        relative_path = str(file_path.relative_to(self._resources_path))

        # Normalized name
        normalized_name = f"{resource_type.value}/{file_name}"

        # Create database entry
        return self.db.create_resource(
            name=normalized_name,
            resource_type=resource_type.value,
            file_path=relative_path,
            injection_position=injection_position.value,
        )

    def update_resource(
        self,
        resource_id: int,
        content: Optional[str] = None,
        injection_position: Optional[InjectionPosition] = None,
        enabled: Optional[bool] = None,
        inherit_default: Optional[bool] = None,
        priority: Optional[int] = None,
    ) -> bool:
        """Update a resource.

        Args:
            resource_id: Resource ID.
            content: New content (updates file).
            injection_position: New injection position.
            enabled: Enable/disable.
            inherit_default: Whether loops inherit by default.
            priority: Ordering priority.

        Returns:
            True if updated.
        """
        resource = self.db.get_resource(resource_id)
        if not resource:
            return False

        # Update file content if provided
        if content is not None:
            file_path = self._resources_path / resource["file_path"]
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

        # Update database fields
        updates = {}
        if injection_position is not None:
            updates["injection_position"] = injection_position.value
        if enabled is not None:
            updates["enabled"] = enabled
        if inherit_default is not None:
            updates["inherit_default"] = inherit_default
        if priority is not None:
            updates["priority"] = priority

        if updates:
            return self.db.update_resource(resource_id, **updates)

        return True

    def delete_resource(self, resource_id: int, delete_file: bool = True) -> bool:
        """Delete a resource.

        Args:
            resource_id: Resource ID.
            delete_file: Whether to delete the file too.

        Returns:
            True if deleted.
        """
        resource = self.db.get_resource(resource_id)
        if not resource:
            return False

        # Delete file if requested
        if delete_file:
            file_path = self._resources_path / resource["file_path"]
            if file_path.exists():
                file_path.unlink()

        # Delete database entry
        return self.db.delete_resource(resource_id)
