"""Loop configuration management for RalphX."""

import uuid
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from ralphx.core.project_db import ProjectDatabase
from ralphx.core.workspace import ensure_workspace
from ralphx.models import LoopConfig, Project


class LoopValidationError(Exception):
    """Error validating loop configuration."""

    def __init__(self, message: str, errors: Optional[list] = None):
        super().__init__(message)
        self.errors = errors or []


class LoopLoader:
    """Loads and validates loop configurations.

    Handles:
    - Loading loops from YAML files
    - Validating loop configuration schema
    - Verifying prompt templates exist
    - Registering loops in the database

    Note: Requires a ProjectDatabase instance for database operations.
          Can be used without db for validation-only operations.
    """

    def __init__(self, db: Optional[ProjectDatabase] = None):
        """Initialize the loop loader.

        Args:
            db: Project-local database instance. Optional for validation-only usage.
        """
        ensure_workspace()
        self._db = db

    @property
    def db(self) -> Optional[ProjectDatabase]:
        """Get the project-local database instance."""
        return self._db

    def _require_db(self) -> ProjectDatabase:
        """Get database, raising if not available."""
        if self._db is None:
            raise RuntimeError("Database required for this operation")
        return self._db

    def load_from_file(
        self,
        yaml_path: Path,
        project_path: Optional[Path] = None,
    ) -> LoopConfig:
        """Load and validate a loop configuration from a YAML file.

        Args:
            yaml_path: Path to the YAML configuration file.
            project_path: Path to the project root (for resolving relative paths).
                          If not provided, uses yaml_path.parent.

        Returns:
            Validated LoopConfig instance.

        Raises:
            FileNotFoundError: If YAML file doesn't exist.
            LoopValidationError: If configuration is invalid.
        """
        if not yaml_path.exists():
            raise FileNotFoundError(f"Loop configuration not found: {yaml_path}")

        if project_path is None:
            project_path = yaml_path.parent

        try:
            with open(yaml_path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise LoopValidationError(f"Invalid YAML: {e}")

        return self.validate(data, project_path)

    def load_from_string(
        self,
        yaml_content: str,
        project_path: Optional[Path] = None,
    ) -> LoopConfig:
        """Load and validate a loop configuration from a YAML string.

        Args:
            yaml_content: YAML content as string.
            project_path: Path to the project root (for resolving relative paths).

        Returns:
            Validated LoopConfig instance.

        Raises:
            LoopValidationError: If configuration is invalid.
        """
        try:
            data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise LoopValidationError(f"Invalid YAML: {e}")

        return self.validate(data, project_path)

    def validate(
        self,
        data: dict,
        project_path: Optional[Path] = None,
    ) -> LoopConfig:
        """Validate loop configuration data.

        Args:
            data: Dictionary with loop configuration.
            project_path: Path to the project root (for resolving relative paths).

        Returns:
            Validated LoopConfig instance.

        Raises:
            LoopValidationError: If configuration is invalid.
        """
        errors = []

        # Validate with Pydantic
        try:
            config = LoopConfig.model_validate(data)
        except ValidationError as e:
            # Collect all validation errors
            for error in e.errors():
                loc = " -> ".join(str(x) for x in error["loc"])
                errors.append(f"{loc}: {error['msg']}")
            raise LoopValidationError(
                f"Configuration validation failed with {len(errors)} error(s)",
                errors=errors,
            )

        # Verify prompt templates exist if project_path provided
        if project_path:
            for mode_name, mode in config.modes.items():
                template_path = project_path / mode.prompt_template
                if not template_path.exists():
                    errors.append(
                        f"modes -> {mode_name} -> prompt_template: "
                        f"File not found: {template_path}"
                    )

            # Verify design_doc exists if specified
            if config.context and config.context.design_doc:
                design_doc_path = project_path / config.context.design_doc
                if not design_doc_path.exists():
                    errors.append(
                        f"context -> design_doc: File not found: {design_doc_path}"
                    )

            # Verify category/phase files exist if specified
            if config.categories and config.categories.source == "file":
                if config.categories.file:
                    cat_path = project_path / config.categories.file
                    if not cat_path.exists():
                        errors.append(
                            f"categories -> file: File not found: {cat_path}"
                        )

            if config.phases and config.phases.source == "file":
                if config.phases.file:
                    phase_path = project_path / config.phases.file
                    if not phase_path.exists():
                        errors.append(
                            f"phases -> file: File not found: {phase_path}"
                        )

        if errors:
            raise LoopValidationError(
                f"Configuration validation failed with {len(errors)} error(s)",
                errors=errors,
            )

        return config

    def register_loop(
        self,
        config: LoopConfig,
    ) -> str:
        """Register a loop configuration in the database.

        Args:
            config: Validated loop configuration.

        Returns:
            The loop ID.
        """
        # Check if loop already exists
        existing = self._require_db().get_loop(config.name)
        if existing:
            # Update existing loop
            self._require_db().update_loop(
                config.name,
                config_yaml=config.to_yaml(),
            )
            return existing["id"]

        # Create new loop
        loop_id = str(uuid.uuid4())
        self._require_db().create_loop(
            id=loop_id,
            name=config.name,
            config_yaml=config.to_yaml(),
        )
        return loop_id

    def get_loop(self, name: str) -> Optional[LoopConfig]:
        """Get a loop configuration by name.

        Args:
            name: Loop name.

        Returns:
            LoopConfig if found, None otherwise.
        """
        data = self._require_db().get_loop(name)
        if data:
            return LoopConfig.from_yaml_string(data["config_yaml"])
        return None

    def list_loops(self) -> list[LoopConfig]:
        """List all loops.

        Returns:
            List of LoopConfig instances.
        """
        loops_data = self._require_db().list_loops()
        return [
            LoopConfig.from_yaml_string(data["config_yaml"])
            for data in loops_data
        ]

    def delete_loop(self, name: str) -> bool:
        """Delete a loop.

        Args:
            name: Loop name.

        Returns:
            True if deleted, False if not found.
        """
        return self._require_db().delete_loop(name)

    def discover_loops(self, project_path: Path) -> list[Path]:
        """Discover loop configuration files in a project.

        Looks for YAML files in:
        - .ralphx/loops/
        - loops/
        - Any *.loop.yaml files in the project root

        Args:
            project_path: Path to the project root.

        Returns:
            List of paths to loop configuration files.
        """
        loop_files = []

        # Check .ralphx/loops/ directory
        ralphx_loops = project_path / ".ralphx" / "loops"
        if ralphx_loops.exists():
            loop_files.extend(ralphx_loops.glob("*.yaml"))
            loop_files.extend(ralphx_loops.glob("*.yml"))

        # Check loops/ directory
        loops_dir = project_path / "loops"
        if loops_dir.exists():
            loop_files.extend(loops_dir.glob("*.yaml"))
            loop_files.extend(loops_dir.glob("*.yml"))

        # Check for *.loop.yaml files in root
        loop_files.extend(project_path.glob("*.loop.yaml"))
        loop_files.extend(project_path.glob("*.loop.yml"))

        return sorted(set(loop_files))

    def sync_loops(self, project: Project) -> dict:
        """Sync loop configurations from project files to database.

        Args:
            project: Project to sync.

        Returns:
            Dictionary with sync results (added, updated, removed counts).
        """
        project_path = Path(project.path)
        discovered = self.discover_loops(project_path)

        # Load and register discovered loops
        added = 0
        updated = 0
        errors = []

        discovered_names = set()
        for loop_file in discovered:
            try:
                config = self.load_from_file(loop_file, project_path)
                discovered_names.add(config.name)

                # Check if already exists
                existing = self._require_db().get_loop(config.name)
                self.register_loop(config)

                if existing:
                    updated += 1
                else:
                    added += 1
            except (LoopValidationError, FileNotFoundError) as e:
                errors.append((loop_file, str(e)))

        # Remove loops that no longer exist in files
        existing_loops = self._require_db().list_loops()
        removed = 0
        for loop_data in existing_loops:
            if loop_data["name"] not in discovered_names:
                self._require_db().delete_loop(loop_data["name"])
                removed += 1

        return {
            "added": added,
            "updated": updated,
            "removed": removed,
            "errors": errors,
        }
