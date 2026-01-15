"""Project management for RalphX.

Uses two-tier database architecture:
- GlobalDatabase: Project registry at ~/.ralphx/ralphx.db
- ProjectDatabase: Project data at <project>/.ralphx/ralphx.db
"""

import uuid
from pathlib import Path
from typing import Optional

from ralphx.core.global_db import GlobalDatabase
from ralphx.core.project_db import ProjectDatabase
from ralphx.core.workspace import (
    ensure_project_ralphx,
    ensure_workspace,
    get_project_database_path,
    project_has_ralphx,
)
from ralphx.models import Project, ProjectCreate
from ralphx.models.project import generate_slug


class ProjectManager:
    """Manages RalphX projects.

    Uses two-tier database architecture:
    - GlobalDatabase: Project registry and cached stats
    - ProjectDatabase: Per-project data (items, runs, loops, etc.)

    Handles:
    - Adding projects to the workspace
    - Listing registered projects
    - Removing projects
    - Project workspace directory management
    """

    def __init__(self, global_db: Optional[GlobalDatabase] = None):
        """Initialize the project manager.

        Args:
            global_db: Global database instance. If not provided, creates one.
        """
        ensure_workspace()
        self._global_db = global_db or GlobalDatabase()
        self._project_dbs: dict[str, ProjectDatabase] = {}

    @property
    def global_db(self) -> GlobalDatabase:
        """Get the global database instance."""
        return self._global_db

    def get_project_db(self, project_path: str | Path) -> ProjectDatabase:
        """Get or create a ProjectDatabase for a project.

        Args:
            project_path: Path to the project directory.

        Returns:
            ProjectDatabase instance for the project.
        """
        path_str = str(Path(project_path).resolve())
        if path_str not in self._project_dbs:
            self._project_dbs[path_str] = ProjectDatabase(path_str)
        return self._project_dbs[path_str]

    def get_project_db_by_slug(self, slug: str) -> Optional[ProjectDatabase]:
        """Get ProjectDatabase by project slug.

        Args:
            slug: Project slug.

        Returns:
            ProjectDatabase instance if project exists, None otherwise.
        """
        project_data = self._global_db.get_project(slug)
        if not project_data:
            return None
        return self.get_project_db(project_data["path"])

    def add_project(
        self,
        path: Path,
        name: Optional[str] = None,
        design_doc: Optional[str] = None,
        slug: Optional[str] = None,
    ) -> Project:
        """Add a new project to RalphX.

        This will:
        1. Register the project in the global database
        2. Create <project>/.ralphx/ directory with local database
        3. Initialize project-local database schema

        Args:
            path: Absolute path to the project directory.
            name: Human-readable project name (defaults to directory name).
            design_doc: Path to design document (relative to project).
            slug: URL-friendly identifier (auto-generated if not provided).

        Returns:
            The created Project.

        Raises:
            ValueError: If path doesn't exist, is not a directory, or slug already exists.
            FileExistsError: If a project with the same slug already exists.
        """
        # Resolve to absolute path
        path = path.resolve()

        # Validate path
        if not path.exists():
            raise ValueError(f"Path does not exist: {path}")
        if not path.is_dir():
            raise ValueError(f"Path is not a directory: {path}")

        # Use directory name if no name provided
        if name is None:
            name = path.name

        # Generate slug if not provided
        if slug is None:
            slug = generate_slug(name)

        # Check for existing project with same slug
        existing = self._global_db.get_project(slug)
        if existing:
            raise FileExistsError(f"Project with slug '{slug}' already exists")

        # Check for existing project with same path
        existing_by_path = self._global_db.get_project_by_path(str(path))
        if existing_by_path:
            raise FileExistsError(
                f"Path already registered as project '{existing_by_path['slug']}'"
            )

        # Validate design doc exists if specified
        if design_doc:
            design_doc_path = path / design_doc
            if not design_doc_path.exists():
                raise ValueError(f"Design document not found: {design_doc_path}")

        # Create project ID
        project_id = str(uuid.uuid4())

        # Create .ralphx directory in project (initializes local DB)
        ensure_project_ralphx(path)

        # Initialize project-local database
        project_db = self.get_project_db(path)

        # Register in global database
        self._global_db.register_project(
            id=project_id,
            slug=slug,
            name=name,
            path=str(path),
            design_doc=design_doc,
        )

        # Return the created project
        return self.get_project(slug)

    def get_project(self, slug: str) -> Optional[Project]:
        """Get a project by slug.

        Args:
            slug: Project slug.

        Returns:
            Project if found, None otherwise.
        """
        data = self._global_db.get_project(slug)
        if data:
            # Touch last_accessed
            self._global_db.touch_project(slug)
            return Project.from_dict(data)
        return None

    def get_project_by_id(self, id: str) -> Optional[Project]:
        """Get a project by ID.

        Args:
            id: Project UUID.

        Returns:
            Project if found, None otherwise.
        """
        data = self._global_db.get_project_by_id(id)
        if data:
            return Project.from_dict(data)
        return None

    def list_projects(self) -> list[Project]:
        """List all registered projects.

        Returns:
            List of all projects, ordered by last accessed (newest first).
        """
        projects_data = self._global_db.list_projects()
        return [Project.from_dict(data) for data in projects_data]

    def remove_project(
        self,
        slug: str,
        delete_local_data: bool = False,
    ) -> bool:
        """Remove a project from RalphX.

        Args:
            slug: Project slug to remove.
            delete_local_data: If True, also delete .ralphx/ directory in project.

        Returns:
            True if project was removed, False if not found.
        """
        project_data = self._global_db.get_project(slug)
        if not project_data:
            return False

        project_path = project_data["path"]

        # Close any open project database connection
        if project_path in self._project_dbs:
            self._project_dbs[project_path].close()
            del self._project_dbs[project_path]

        # Unregister from global database
        result = self._global_db.unregister_project(slug)

        # Optionally delete .ralphx/ directory
        if delete_local_data and result:
            import shutil
            from ralphx.core.workspace import get_project_ralphx_path

            ralphx_path = get_project_ralphx_path(project_path)
            if ralphx_path.exists():
                shutil.rmtree(ralphx_path)

        return result

    def update_project(
        self,
        slug: str,
        name: Optional[str] = None,
        design_doc: Optional[str] = None,
    ) -> Optional[Project]:
        """Update a project's metadata.

        Args:
            slug: Project slug.
            name: New name (optional).
            design_doc: New design doc path (optional).

        Returns:
            Updated project if found, None otherwise.
        """
        updates = {}
        if name is not None:
            updates["name"] = name
        if design_doc is not None:
            updates["design_doc"] = design_doc

        if updates:
            self._global_db.update_project(slug, **updates)

        return self.get_project(slug)

    def project_exists(self, slug: str) -> bool:
        """Check if a project exists.

        Args:
            slug: Project slug.

        Returns:
            True if project exists, False otherwise.
        """
        return self._global_db.get_project(slug) is not None

    def get_project_stats(self, slug: str) -> Optional[dict]:
        """Get statistics for a project.

        Args:
            slug: Project slug.

        Returns:
            Dictionary with work item stats, or None if project not found.
        """
        project_data = self._global_db.get_project(slug)
        if not project_data:
            return None

        project_db = self.get_project_db(project_data["path"])
        stats = project_db.get_work_item_stats()

        # Add loop count
        loops = project_db.list_loops()
        stats["loops"] = len(loops)

        # Add active runs count
        active_runs = project_db.list_runs(status="running")
        stats["active_runs"] = len(active_runs)

        # Update cache
        self._global_db.update_cache(
            project_id=project_data["id"],
            total_items=stats["total"],
            pending_items=stats["by_status"].get("pending", 0),
            completed_items=stats["by_status"].get("completed", 0),
            loop_count=stats["loops"],
            active_runs=stats["active_runs"],
        )

        return stats

    def import_existing_project(self, path: Path, slug: Optional[str] = None) -> Project:
        """Import an existing project that already has .ralphx/ directory.

        Use this when cloning a repository that already has RalphX data.

        Args:
            path: Path to project directory with existing .ralphx/.
            slug: Optional slug override.

        Returns:
            The imported project.

        Raises:
            ValueError: If path doesn't have .ralphx/ directory.
            FileExistsError: If project already registered.
        """
        path = path.resolve()

        if not project_has_ralphx(path):
            raise ValueError(f"Project does not have .ralphx/ directory: {path}")

        # Check for existing registration
        existing = self._global_db.get_project_by_path(str(path))
        if existing:
            raise FileExistsError(
                f"Path already registered as project '{existing['slug']}'"
            )

        # Get project database to read config
        project_db = self.get_project_db(path)

        # Generate name and slug from path if not provided
        name = path.name
        if slug is None:
            slug = generate_slug(name)

        # Check slug not taken
        if self._global_db.get_project(slug):
            raise FileExistsError(f"Project with slug '{slug}' already exists")

        # Register in global database
        project_id = str(uuid.uuid4())
        self._global_db.register_project(
            id=project_id,
            slug=slug,
            name=name,
            path=str(path),
        )

        return self.get_project(slug)

    def refresh_cache(self, slug: str) -> None:
        """Refresh cached stats for a project.

        Args:
            slug: Project slug.
        """
        self.get_project_stats(slug)

    def cleanup_stale_projects(self, dry_run: bool = True) -> list[str]:
        """Find and optionally remove projects whose paths no longer exist.

        Args:
            dry_run: If True, only return stale slugs without deleting.

        Returns:
            List of stale project slugs.
        """
        return self._global_db.cleanup_stale_projects(dry_run=dry_run)


# Backward compatibility: expose Database-like interface through ProjectManager
# This allows gradual migration of code that expects old Database instance
class LegacyDatabaseBridge:
    """Bridge to provide old Database interface using new two-tier architecture.

    This is for backward compatibility during migration.
    """

    def __init__(self, manager: ProjectManager):
        self._manager = manager

    def get_project(self, slug: str) -> Optional[dict]:
        return self._manager.global_db.get_project(slug)

    def get_project_by_id(self, id: str) -> Optional[dict]:
        return self._manager.global_db.get_project_by_id(id)

    def list_projects(self) -> list[dict]:
        return self._manager.global_db.list_projects()

    def create_project(self, id: str, slug: str, name: str, path: str, design_doc: Optional[str] = None) -> dict:
        # For backward compatibility, design_doc is stored in project config file
        self._manager.global_db.register_project(id=id, slug=slug, name=name, path=path)
        return self._manager.global_db.get_project(slug)

    def delete_project(self, slug: str) -> bool:
        return self._manager.global_db.unregister_project(slug)

    def update_project(self, slug: str, **kwargs) -> bool:
        return self._manager.global_db.update_project(slug, **kwargs)

    # Work item methods delegate to project database
    def get_work_item_stats(self, project_id: str) -> dict:
        project = self._manager.global_db.get_project_by_id(project_id)
        if not project:
            return {"total": 0, "by_status": {}, "by_category": {}, "by_priority": {}}
        project_db = self._manager.get_project_db(project["path"])
        return project_db.get_work_item_stats()
