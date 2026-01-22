"""Workflow import functionality for RalphX.

Enables importing workflows from ZIP archives into projects,
with support for selective import, conflict resolution, and ID regeneration.
"""

import hashlib
import io
import json
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from ralphx.core.project_db import PROJECT_SCHEMA_VERSION, ProjectDatabase
from ralphx.core.workflow_export import EXPORT_FORMAT_NAME, EXPORT_FORMAT_VERSION


# Security limits
MAX_IMPORT_SIZE_MB = 500
MAX_COMPRESSION_RATIO = 100  # Max uncompressed/compressed ratio
MAX_FILES_IN_ARCHIVE = 10000


def _compare_versions(v1: str, v2: str) -> int:
    """Compare two semantic version strings.

    Args:
        v1: First version string (e.g., "1.0", "1.10", "2.0.1").
        v2: Second version string.

    Returns:
        -1 if v1 < v2, 0 if v1 == v2, 1 if v1 > v2.
    """
    def parse_version(v: str) -> list[int]:
        try:
            return [int(x) for x in v.split('.')]
        except ValueError:
            return [0]

    parts1 = parse_version(v1)
    parts2 = parse_version(v2)

    # Pad shorter version with zeros
    max_len = max(len(parts1), len(parts2))
    parts1.extend([0] * (max_len - len(parts1)))
    parts2.extend([0] * (max_len - len(parts2)))

    for p1, p2 in zip(parts1, parts2):
        if p1 < p2:
            return -1
        if p1 > p2:
            return 1
    return 0


class ConflictResolution(str, Enum):
    """How to resolve conflicts during import."""
    SKIP = "skip"  # Skip conflicting items
    RENAME = "rename"  # Auto-rename with suffix
    OVERWRITE = "overwrite"  # Overwrite existing


class ConflictType(str, Enum):
    """Types of conflicts that can occur."""
    ITEM_ID = "item_id"
    RESOURCE_NAME = "resource_name"
    STEP_NUMBER = "step_number"
    MISSING_DEPENDENCY = "missing_dependency"


@dataclass
class Conflict:
    """A detected conflict during import preview."""
    conflict_type: ConflictType
    source_id: str
    source_name: str
    target_id: Optional[str] = None
    target_name: Optional[str] = None
    details: Optional[str] = None


@dataclass
class StepPreviewInfo:
    """Preview info for a single step."""
    step_number: int
    name: str
    step_type: str
    items_count: int


@dataclass
class ResourcePreviewInfo:
    """Preview info for a single resource."""
    id: int
    name: str
    resource_type: str


@dataclass
class ImportPreview:
    """Preview of what will be imported."""
    # Basic info
    workflow_name: str
    workflow_id: str
    exported_at: str
    ralphx_version: str
    schema_version: int

    # Counts
    steps_count: int
    items_count: int
    resources_count: int
    has_planning_session: bool
    has_runs: bool

    # Compatibility
    is_compatible: bool

    # Optional fields (must come after required fields)
    has_step_artifacts: bool = False  # Whether export includes step artifacts
    compatibility_notes: list[str] = field(default_factory=list)

    # Detailed breakdown for selective import
    steps: list[StepPreviewInfo] = field(default_factory=list)
    resources: list[ResourcePreviewInfo] = field(default_factory=list)

    # Conflicts (only for import into existing)
    conflicts: list[Conflict] = field(default_factory=list)

    # Security
    potential_secrets_detected: bool = False


@dataclass
class ImportOptions:
    """Options for import operation."""
    conflict_resolution: ConflictResolution = ConflictResolution.RENAME
    import_items: bool = True
    import_resources: bool = True
    import_planning: bool = True
    import_runs: bool = False
    import_step_artifacts: bool = False  # Import step artifacts if present (off by default)
    selected_step_ids: Optional[list[int]] = None  # None = all steps (for new workflow import)
    selected_resource_ids: Optional[list[int]] = None  # None = all resources

    # Merge-specific options
    selected_source_step_ids: Optional[list[int]] = None  # Which source steps to import items from
    target_step_id: Optional[int] = None  # Which target step to import items into (None = first step)
    import_steps_to_target: bool = False  # Add source steps to target workflow during merge


@dataclass
class ImportResult:
    """Result of import operation."""
    success: bool
    workflow_id: str
    workflow_name: str
    steps_created: int
    items_imported: int
    items_renamed: int
    items_skipped: int
    resources_created: int
    resources_renamed: int
    planning_sessions_imported: int
    runs_imported: int
    id_mapping: dict[str, str]  # old_id -> new_id
    warnings: list[str] = field(default_factory=list)


class WorkflowImporter:
    """Imports workflows from ZIP archives.

    Supports:
    - Full import (create new workflow)
    - Selective import (pick components)
    - Import into existing workflow (merge)
    """

    def __init__(self, project_db: ProjectDatabase):
        """Initialize importer.

        Args:
            project_db: ProjectDatabase instance for the project.
        """
        self.db = project_db

    def get_preview(self, zip_data: bytes) -> ImportPreview:
        """Get a preview of what will be imported from the ZIP.

        Args:
            zip_data: ZIP file content as bytes.

        Returns:
            ImportPreview with contents and compatibility info.

        Raises:
            ValueError: If archive is invalid or fails security checks.
        """
        # Validate archive
        self._validate_archive(zip_data)

        with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
            # Read and parse manifest
            manifest = self._read_manifest(zf)

            # Check compatibility
            is_compatible, notes = self._check_compatibility(manifest)

            # Read workflow info
            workflow_data = self._read_workflow(zf)

            # Detect if step artifacts are present
            # Check manifest first (preferred), then check actual step data
            has_step_artifacts = manifest.get('export_options', {}).get('include_step_artifacts', False)
            if not has_step_artifacts:
                # Also check actual workflow data for any non-null artifacts
                for step in workflow_data.get('steps', []):
                    if step.get('artifacts'):
                        has_step_artifacts = True
                        break

            # Build detailed step info with item counts per step
            steps_preview: list[StepPreviewInfo] = []
            items_data = self._read_items(zf)
            step_item_counts: dict[int, int] = {}
            for item in items_data:
                step_id = item.get('source_step_id')
                if step_id is not None:
                    step_item_counts[step_id] = step_item_counts.get(step_id, 0) + 1

            for step in workflow_data.get('steps', []):
                step_id = step.get('id')
                steps_preview.append(StepPreviewInfo(
                    step_number=step.get('step_number', 0),
                    name=step.get('name', 'Unknown'),
                    step_type=step.get('step_type', 'interactive'),
                    items_count=step_item_counts.get(step_id, 0),
                ))

            # Build detailed resource info
            resources_preview: list[ResourcePreviewInfo] = []
            resources_data = self._read_resources(zf)
            for i, resource in enumerate(resources_data):
                resources_preview.append(ResourcePreviewInfo(
                    id=resource.get('id', i),
                    name=resource.get('name', 'Unknown'),
                    resource_type=resource.get('resource_type', 'custom'),
                ))

            return ImportPreview(
                workflow_name=manifest['workflow']['name'],
                workflow_id=manifest['workflow']['id'],
                exported_at=manifest['exported_at'],
                ralphx_version=manifest.get('ralphx_version', 'unknown'),
                schema_version=manifest.get('schema_version', 0),
                steps_count=manifest['contents']['steps'],
                items_count=manifest['contents']['items_total'],
                resources_count=manifest['contents']['resources'],
                has_planning_session=manifest['contents']['has_planning_session'],
                has_runs=manifest['contents'].get('has_runs', False),
                has_step_artifacts=has_step_artifacts,
                is_compatible=is_compatible,
                compatibility_notes=notes,
                steps=steps_preview,
                resources=resources_preview,
                potential_secrets_detected=manifest.get('security', {}).get('potential_secrets_detected', False),
            )

    def get_merge_preview(
        self,
        zip_data: bytes,
        target_workflow_id: str,
    ) -> ImportPreview:
        """Get a preview for merging into an existing workflow.

        Args:
            zip_data: ZIP file content as bytes.
            target_workflow_id: ID of workflow to merge into.

        Returns:
            ImportPreview with detected conflicts.

        Raises:
            ValueError: If archive is invalid or target workflow not found.
        """
        preview = self.get_preview(zip_data)

        # Get target workflow
        target_workflow = self.db.get_workflow(target_workflow_id)
        if not target_workflow:
            raise ValueError(f"Target workflow '{target_workflow_id}' not found")

        # Detect conflicts
        conflicts = self._detect_conflicts(zip_data, target_workflow_id)
        preview.conflicts = conflicts

        return preview

    def import_workflow(
        self,
        zip_data: bytes,
        options: Optional[ImportOptions] = None,
    ) -> ImportResult:
        """Import a workflow from ZIP as a new workflow.

        IDs are always regenerated to prevent collisions.

        Args:
            zip_data: ZIP file content as bytes.
            options: Import options.

        Returns:
            ImportResult with details of what was imported.

        Raises:
            ValueError: If import fails validation.
        """
        if options is None:
            options = ImportOptions()

        # Validate archive
        self._validate_archive(zip_data)

        with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
            # Read all data
            manifest = self._read_manifest(zf)
            workflow_data = self._read_workflow(zf)
            items_data = self._read_items(zf)
            resources_data = self._read_resources(zf)
            step_resources_data = self._read_step_resources(zf)
            planning_data = self._read_planning(zf) if options.import_planning else []
            runs_data = self._read_runs(zf) if options.import_runs else []

        # Check compatibility
        is_compatible, notes = self._check_compatibility(manifest)
        if not is_compatible:
            raise ValueError(f"Import not compatible: {'; '.join(notes)}")

        # Generate new IDs
        id_mapping = self._generate_id_mapping(workflow_data, items_data, resources_data)

        # Create workflow in a transaction
        result = self._execute_import(
            workflow_data,
            items_data,
            resources_data,
            step_resources_data,
            planning_data,
            runs_data,
            id_mapping,
            options,
            manifest,
        )

        return result

    def merge_into_workflow(
        self,
        zip_data: bytes,
        target_workflow_id: str,
        options: Optional[ImportOptions] = None,
    ) -> ImportResult:
        """Merge imported data into an existing workflow.

        Args:
            zip_data: ZIP file content as bytes.
            target_workflow_id: ID of workflow to merge into.
            options: Import options with conflict resolution.

        Returns:
            ImportResult with details of what was merged.

        Raises:
            ValueError: If merge fails.
        """
        if options is None:
            options = ImportOptions()

        # Validate archive and target
        self._validate_archive(zip_data)

        target_workflow = self.db.get_workflow(target_workflow_id)
        if not target_workflow:
            raise ValueError(f"Target workflow '{target_workflow_id}' not found")

        # Check for active runs
        active_runs = self.db.list_runs(workflow_id=target_workflow_id, status='running')
        if active_runs:
            raise ValueError("Cannot merge into workflow with active runs")

        with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
            manifest = self._read_manifest(zf)
            workflow_data = self._read_workflow(zf) if options.import_steps_to_target else None
            items_data = self._read_items(zf)
            resources_data = self._read_resources(zf)
            planning_data = self._read_planning(zf) if options.import_planning else []

        # Execute merge
        result = self._execute_merge(
            target_workflow_id,
            target_workflow,
            workflow_data,
            items_data,
            resources_data,
            planning_data,
            options,
            manifest,
        )

        return result

    def _validate_archive(self, zip_data: bytes) -> None:
        """Validate ZIP archive for security and format.

        Raises:
            ValueError: If validation fails.
        """
        # Size check
        if len(zip_data) > MAX_IMPORT_SIZE_MB * 1024 * 1024:
            raise ValueError(f"Archive exceeds maximum size of {MAX_IMPORT_SIZE_MB}MB")

        # Check it's a valid ZIP
        if not zipfile.is_zipfile(io.BytesIO(zip_data)):
            raise ValueError("Invalid ZIP file")

        with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
            # Check file count
            if len(zf.namelist()) > MAX_FILES_IN_ARCHIVE:
                raise ValueError(f"Archive contains too many files (max {MAX_FILES_IN_ARCHIVE})")

            # Calculate total uncompressed size and check each entry
            total_uncompressed = 0
            for info in zf.infolist():
                # Zip Slip prevention: reject paths that could escape extraction directory
                filename = info.filename

                # Reject absolute paths (Unix or Windows style)
                if filename.startswith('/') or filename.startswith('\\'):
                    raise ValueError(f"Absolute path not allowed in archive: {filename}")

                # Reject backslashes (Windows path separator could bypass Unix checks)
                if '\\' in filename:
                    raise ValueError(f"Backslash not allowed in archive path: {filename}")

                # Check each path component for ".." traversal
                # This catches "foo/../bar" but NOT "foo/..bar" (valid filename)
                parts = filename.split('/')
                for part in parts:
                    if part == '..':
                        raise ValueError(f"Path traversal (..) not allowed in archive: {filename}")

                # Reject symlinks (external_attr high nibble 0xA = symlink)
                if info.external_attr >> 28 == 0xA:
                    raise ValueError(f"Symlinks not allowed: {filename}")

                total_uncompressed += info.file_size

            # Zip bomb protection
            if len(zip_data) > 0:
                ratio = total_uncompressed / len(zip_data)
                if ratio > MAX_COMPRESSION_RATIO:
                    raise ValueError(f"Compression ratio too high ({ratio:.0f}:1), possible zip bomb")

            if total_uncompressed > MAX_IMPORT_SIZE_MB * 1024 * 1024:
                raise ValueError(f"Uncompressed size exceeds {MAX_IMPORT_SIZE_MB}MB")

            # Verify required files exist
            names = zf.namelist()
            if 'manifest.json' not in names:
                raise ValueError("Missing manifest.json")
            if 'workflow.json' not in names:
                raise ValueError("Missing workflow.json")

    def _read_manifest(self, zf: zipfile.ZipFile) -> dict:
        """Read and parse manifest.json."""
        try:
            content = zf.read('manifest.json').decode('utf-8')
            manifest = json.loads(content)
        except (KeyError, json.JSONDecodeError) as e:
            raise ValueError(f"Invalid manifest.json: {e}")

        # Validate format
        if manifest.get('format') != EXPORT_FORMAT_NAME:
            raise ValueError(f"Unknown export format: {manifest.get('format')}")

        return manifest

    def _read_workflow(self, zf: zipfile.ZipFile) -> dict:
        """Read and parse workflow.json."""
        try:
            content = zf.read('workflow.json').decode('utf-8')
            return json.loads(content)
        except (KeyError, json.JSONDecodeError) as e:
            raise ValueError(f"Invalid workflow.json: {e}")

    def _read_items(self, zf: zipfile.ZipFile) -> list[dict]:
        """Read and parse items.jsonl."""
        if 'items.jsonl' not in zf.namelist():
            return []

        try:
            content = zf.read('items.jsonl').decode('utf-8')
            items = []
            for line in content.strip().split('\n'):
                if line.strip():
                    items.append(json.loads(line))
            return items
        except (KeyError, json.JSONDecodeError) as e:
            raise ValueError(f"Invalid items.jsonl: {e}")

    def _read_resources(self, zf: zipfile.ZipFile) -> list[dict]:
        """Read and parse resources."""
        if 'resources/resources.json' not in zf.namelist():
            return []

        try:
            content = zf.read('resources/resources.json').decode('utf-8')
            return json.loads(content)
        except (KeyError, json.JSONDecodeError) as e:
            raise ValueError(f"Invalid resources.json: {e}")

    def _read_step_resources(self, zf: zipfile.ZipFile) -> dict:
        """Read and parse step resources."""
        if 'step-resources/step-resources.json' not in zf.namelist():
            return {}

        try:
            content = zf.read('step-resources/step-resources.json').decode('utf-8')
            return json.loads(content)
        except (KeyError, json.JSONDecodeError) as e:
            raise ValueError(f"Invalid step-resources.json: {e}")

    def _read_planning(self, zf: zipfile.ZipFile) -> list[dict]:
        """Read and parse planning sessions."""
        if 'planning/session.json' not in zf.namelist():
            return []

        try:
            content = zf.read('planning/session.json').decode('utf-8')
            return json.loads(content)
        except (KeyError, json.JSONDecodeError) as e:
            raise ValueError(f"Invalid planning session.json: {e}")

    def _read_runs(self, zf: zipfile.ZipFile) -> list[dict]:
        """Read and parse runs."""
        if 'runs/runs.json' not in zf.namelist():
            return []

        try:
            content = zf.read('runs/runs.json').decode('utf-8')
            return json.loads(content)
        except (KeyError, json.JSONDecodeError) as e:
            raise ValueError(f"Invalid runs.json: {e}")

    def _check_compatibility(self, manifest: dict) -> tuple[bool, list[str]]:
        """Check if the export is compatible with this version.

        Returns:
            Tuple of (is_compatible, list of notes/warnings).
        """
        notes = []
        is_compatible = True

        # Check export format version (using semantic version comparison)
        export_version = manifest.get('version', '0.0')
        if _compare_versions(export_version, EXPORT_FORMAT_VERSION) > 0:
            notes.append(f"Export format {export_version} is newer than supported {EXPORT_FORMAT_VERSION}")
            is_compatible = False

        # Check schema version
        schema_version = manifest.get('schema_version', 0)
        if schema_version > PROJECT_SCHEMA_VERSION:
            notes.append(f"Schema version {schema_version} is newer than current {PROJECT_SCHEMA_VERSION}")
            is_compatible = False
        elif schema_version < PROJECT_SCHEMA_VERSION - 5:
            notes.append(f"Schema version {schema_version} is quite old, some data may not migrate perfectly")

        # Check for secrets warning
        if manifest.get('security', {}).get('potential_secrets_detected'):
            notes.append("Export contains potential secrets - review content before sharing")

        return is_compatible, notes

    def _detect_conflicts(
        self,
        zip_data: bytes,
        target_workflow_id: str,
    ) -> list[Conflict]:
        """Detect conflicts for merging into existing workflow."""
        conflicts = []

        with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
            items_data = self._read_items(zf)
            resources_data = self._read_resources(zf)

        # Get existing items and resources
        existing_items, _ = self.db.list_work_items(workflow_id=target_workflow_id, limit=100000)
        existing_resources = self.db.list_workflow_resources(target_workflow_id)

        existing_item_ids = {i['id'] for i in existing_items}
        existing_resource_names = {r['name'] for r in existing_resources}

        # Check item ID conflicts
        for item in items_data:
            if item['id'] in existing_item_ids:
                conflicts.append(Conflict(
                    conflict_type=ConflictType.ITEM_ID,
                    source_id=item['id'],
                    source_name=item.get('title', item['id']),
                    target_id=item['id'],
                    details="Item ID already exists in target workflow",
                ))

        # Check resource name conflicts
        for resource in resources_data:
            if resource['name'] in existing_resource_names:
                conflicts.append(Conflict(
                    conflict_type=ConflictType.RESOURCE_NAME,
                    source_id=str(resource['id']),
                    source_name=resource['name'],
                    target_name=resource['name'],
                    details="Resource name already exists in target workflow",
                ))

        # Check for missing dependencies
        import_item_ids = {i['id'] for i in items_data}
        for item in items_data:
            deps = item.get('dependencies', []) or []
            for dep_id in deps:
                if dep_id not in import_item_ids and dep_id not in existing_item_ids:
                    conflicts.append(Conflict(
                        conflict_type=ConflictType.MISSING_DEPENDENCY,
                        source_id=item['id'],
                        source_name=item.get('title', item['id']),
                        target_id=dep_id,
                        details=f"Dependency '{dep_id}' not found in import or target",
                    ))

        return conflicts

    def _generate_id_mapping(
        self,
        workflow_data: dict,
        items_data: list[dict],
        resources_data: list[dict],
    ) -> dict[str, str]:
        """Generate new IDs for all entities.

        Returns:
            Mapping of old_id -> new_id.
        """
        mapping = {}

        # Workflow ID
        old_wf_id = workflow_data['workflow']['id']
        new_wf_id = f"wf-{uuid.uuid4().hex[:12]}"
        mapping[old_wf_id] = new_wf_id

        # Item IDs: preserve prefix, add unique suffix
        for item in items_data:
            old_id = item['id']
            hash_suffix = hashlib.md5(
                f"{old_id}-{uuid.uuid4().hex}".encode()
            ).hexdigest()[:8]
            new_id = f"{old_id}-{hash_suffix}"
            mapping[old_id] = new_id

        # Resource IDs (numeric, just generate new sequence)
        for i, resource in enumerate(resources_data):
            old_id = str(resource['id'])
            mapping[old_id] = f"res-{i}"  # Placeholder, actual ID from DB insert

        return mapping

    def _update_references(
        self,
        items_data: list[dict],
        id_mapping: dict[str, str],
    ) -> list[dict]:
        """Update all internal references with new IDs."""
        updated_items = []
        for item in items_data:
            new_item = item.copy()

            # Update workflow_id
            if 'workflow_id' in new_item and new_item['workflow_id'] in id_mapping:
                new_item['workflow_id'] = id_mapping[new_item['workflow_id']]

            # Update dependencies
            deps = new_item.get('dependencies', []) or []
            if deps:
                new_deps = []
                for dep_id in deps:
                    new_deps.append(id_mapping.get(dep_id, dep_id))
                new_item['dependencies'] = new_deps

            # Update duplicate_of
            if new_item.get('duplicate_of') and new_item['duplicate_of'] in id_mapping:
                new_item['duplicate_of'] = id_mapping[new_item['duplicate_of']]

            # Update item ID
            if new_item['id'] in id_mapping:
                new_item['id'] = id_mapping[new_item['id']]

            updated_items.append(new_item)

        return updated_items

    def _execute_import(
        self,
        workflow_data: dict,
        items_data: list[dict],
        resources_data: list[dict],
        step_resources_data: dict,
        planning_data: list[dict],
        runs_data: list[dict],
        id_mapping: dict[str, str],
        options: ImportOptions,
        manifest: dict,
    ) -> ImportResult:
        """Execute the import in a transaction."""
        warnings = []
        items_imported = 0
        items_renamed = 0
        resources_created = 0
        resources_renamed = 0
        planning_imported = 0
        runs_imported = 0

        # Get new workflow ID
        old_wf_id = workflow_data['workflow']['id']
        new_wf_id = id_mapping[old_wf_id]

        # Update items with new IDs
        updated_items = self._update_references(items_data, id_mapping)

        # Create workflow
        workflow = self.db.create_workflow(
            id=new_wf_id,
            name=workflow_data['workflow']['name'],
            template_id=workflow_data['workflow'].get('template_id'),
            status='draft',
        )

        # Create step ID mapping (old step ID -> new step ID)
        step_id_mapping: dict[int, int] = {}

        # Create steps
        steps_created = 0
        for step_def in workflow_data.get('steps', []):
            old_step_id = step_def['id']

            # Check if step should be imported
            if options.selected_step_ids is not None:
                if old_step_id not in options.selected_step_ids:
                    continue

            step = self.db.create_workflow_step(
                workflow_id=new_wf_id,
                step_number=step_def['step_number'],
                name=step_def['name'],
                step_type=step_def['step_type'],
                config=step_def.get('config'),
                loop_name=step_def.get('loop_name'),
                status='pending',
            )
            step_id_mapping[old_step_id] = step['id']
            steps_created += 1

            # Import artifacts if option is enabled and artifacts exist
            if options.import_step_artifacts and step_def.get('artifacts'):
                try:
                    self.db.update_workflow_step(step['id'], artifacts=step_def['artifacts'])
                except Exception as e:
                    warnings.append(f"Failed to import artifacts for step {step_def['name']}: {e}")

        # Import items
        if options.import_items:
            # Skip item import if no steps were created
            if not step_id_mapping:
                if updated_items:
                    warnings.append(f"Skipping {len(updated_items)} items: no steps were imported to associate them with")
            else:
                for item in updated_items:
                    # Check if item's step was imported
                    old_step_id = item.get('source_step_id')
                    if old_step_id and old_step_id not in step_id_mapping:
                        continue

                    # Use mapped step ID or fall back to first available step
                    new_step_id = step_id_mapping.get(old_step_id) if old_step_id else None
                    if new_step_id is None:
                        new_step_id = list(step_id_mapping.values())[0]

                    try:
                        self.db.create_work_item(
                            id=item['id'],
                            workflow_id=new_wf_id,
                            source_step_id=new_step_id,
                            content=item.get('content', ''),
                            title=item.get('title'),
                            priority=item.get('priority'),
                            status='pending',
                            category=item.get('category'),
                            metadata=item.get('metadata'),
                            item_type=item.get('item_type'),
                            dependencies=item.get('dependencies'),
                            phase=item.get('phase'),
                            duplicate_of=item.get('duplicate_of'),
                        )
                        items_imported += 1
                        # Update tags if present (not supported in create_work_item)
                        if item.get('tags'):
                            self.db.update_work_item(item['id'], tags=item['tags'])
                    except Exception as e:
                        warnings.append(f"Failed to import item {item['id']}: {e}")

        # Import resources
        if options.import_resources:
            resource_id_mapping: dict[int, int] = {}
            for resource in resources_data:
                # Check if resource should be imported
                if options.selected_resource_ids is not None:
                    if resource['id'] not in options.selected_resource_ids:
                        continue

                try:
                    # NOTE: We intentionally ignore file_path from imports.
                    # Accepting arbitrary file paths from imported data could allow
                    # an attacker to plant paths that get read during later exports.
                    new_resource = self.db.create_workflow_resource(
                        workflow_id=new_wf_id,
                        resource_type=resource['resource_type'],
                        name=resource['name'],
                        content=resource.get('content'),
                        file_path=None,  # Never import file paths from archives
                        source='imported',
                        enabled=resource.get('enabled', True),
                    )
                    resource_id_mapping[resource['id']] = new_resource['id']
                    resources_created += 1
                except Exception as e:
                    warnings.append(f"Failed to import resource {resource['name']}: {e}")

            # Import step resources
            for old_step_id_str, step_res_list in step_resources_data.items():
                old_step_id = int(old_step_id_str)
                if old_step_id not in step_id_mapping:
                    continue

                new_step_id = step_id_mapping[old_step_id]
                for step_res in step_res_list:
                    try:
                        # Map workflow_resource_id if present
                        wf_res_id = step_res.get('workflow_resource_id')
                        new_wf_res_id = resource_id_mapping.get(wf_res_id) if wf_res_id else None

                        # NOTE: We intentionally ignore file_path from imports.
                        self.db.create_step_resource(
                            step_id=new_step_id,
                            mode=step_res.get('mode', 'add'),
                            workflow_resource_id=new_wf_res_id,
                            resource_type=step_res.get('resource_type'),
                            name=step_res.get('name'),
                            content=step_res.get('content'),
                            file_path=None,  # Never import file paths from archives
                            enabled=step_res.get('enabled', True),
                            priority=step_res.get('priority', 0),
                        )
                    except Exception as e:
                        warnings.append(f"Failed to import step resource: {e}")

        # Import planning sessions
        if options.import_planning and planning_data:
            for session in planning_data:
                old_step_id = session.get('step_id')
                if old_step_id not in step_id_mapping:
                    continue

                try:
                    new_session_id = f"ps-{uuid.uuid4().hex[:12]}"
                    self.db.create_planning_session(
                        id=new_session_id,
                        workflow_id=new_wf_id,
                        step_id=step_id_mapping[old_step_id],
                        messages=session.get('messages', []),
                        artifacts=session.get('artifacts'),
                        status='completed',
                    )
                    planning_imported += 1
                except Exception as e:
                    warnings.append(f"Failed to import planning session: {e}")

        # Store original IDs in workflow metadata for traceability
        original_metadata = {
            'imported_from': {
                'original_workflow_id': old_wf_id,
                'export_timestamp': manifest.get('exported_at'),
                'export_version': manifest.get('ralphx_version'),
            },
            'id_mapping': {
                'items': {old: new for old, new in id_mapping.items() if not old.startswith('wf-')},
            },
        }

        # TODO: Store metadata in workflow (need to add metadata column or use config)

        return ImportResult(
            success=True,
            workflow_id=new_wf_id,
            workflow_name=workflow['name'],
            steps_created=steps_created,
            items_imported=items_imported,
            items_renamed=items_renamed,
            items_skipped=len(items_data) - items_imported,
            resources_created=resources_created,
            resources_renamed=resources_renamed,
            planning_sessions_imported=planning_imported,
            runs_imported=runs_imported,
            id_mapping=id_mapping,
            warnings=warnings,
        )

    def _execute_merge(
        self,
        target_workflow_id: str,
        target_workflow: dict,
        workflow_data: Optional[dict],
        items_data: list[dict],
        resources_data: list[dict],
        planning_data: list[dict],
        options: ImportOptions,
        manifest: dict,
    ) -> ImportResult:
        """Execute merge into existing workflow."""
        warnings = []
        items_imported = 0
        items_renamed = 0
        items_skipped = 0
        resources_created = 0
        resources_renamed = 0
        steps_created = 0

        # Get existing items and resources for conflict detection
        existing_items, _ = self.db.list_work_items(workflow_id=target_workflow_id, limit=100000)
        existing_resources = self.db.list_workflow_resources(target_workflow_id)
        existing_item_ids = {i['id'] for i in existing_items}
        existing_resource_names = {r['name'] for r in existing_resources}

        # Get target steps for mapping source_step_id
        target_steps = self.db.list_workflow_steps(target_workflow_id)
        if not target_steps and not options.import_steps_to_target:
            raise ValueError("Target workflow has no steps")

        # Build step ID mapping for imported steps (source step ID -> target step ID)
        step_id_mapping: dict[int, int] = {}

        # Import steps to target if requested
        if options.import_steps_to_target and workflow_data:
            source_steps = workflow_data.get('steps', [])

            # Filter by selected source step IDs if specified
            if options.selected_source_step_ids is not None:
                source_steps = [s for s in source_steps if s['id'] in options.selected_source_step_ids]

            # Get max step number in target
            max_step_number = max((s['step_number'] for s in target_steps), default=0) if target_steps else 0

            for step_def in source_steps:
                try:
                    new_step = self.db.create_workflow_step(
                        workflow_id=target_workflow_id,
                        step_number=max_step_number + 1,
                        name=step_def['name'],
                        step_type=step_def['step_type'],
                        config=step_def.get('config'),
                        loop_name=step_def.get('loop_name'),
                        status='pending',
                    )
                    step_id_mapping[step_def['id']] = new_step['id']
                    max_step_number += 1
                    steps_created += 1

                    # Import artifacts if option is enabled
                    if options.import_step_artifacts and step_def.get('artifacts'):
                        try:
                            self.db.update_workflow_step(new_step['id'], artifacts=step_def['artifacts'])
                        except Exception as e:
                            warnings.append(f"Failed to import artifacts for step {step_def['name']}: {e}")
                except Exception as e:
                    warnings.append(f"Failed to import step {step_def['name']}: {e}")

            # Refresh target steps after adding new ones
            target_steps = self.db.list_workflow_steps(target_workflow_id)

        # Determine which step to assign items to
        if options.target_step_id is not None:
            # Use specified target step
            default_step_id = options.target_step_id
        elif target_steps:
            # Use first step as default
            default_step_id = target_steps[0]['id']
        else:
            raise ValueError("No target step available for items")

        # Import items with conflict resolution
        if options.import_items:
            for item in items_data:
                # Filter by selected source step IDs if specified
                # Note: Items with None source_step_id are included unless explicitly filtered
                source_step_id = item.get('source_step_id')
                if options.selected_source_step_ids is not None:
                    if source_step_id is not None and source_step_id not in options.selected_source_step_ids:
                        continue

                item_id = item['id']
                has_conflict = item_id in existing_item_ids

                if has_conflict:
                    if options.conflict_resolution == ConflictResolution.SKIP:
                        items_skipped += 1
                        continue
                    elif options.conflict_resolution == ConflictResolution.RENAME:
                        hash_suffix = hashlib.md5(
                            f"{item_id}-{uuid.uuid4().hex}".encode()
                        ).hexdigest()[:8]
                        item_id = f"{item['id']}-{hash_suffix}"
                        items_renamed += 1
                    elif options.conflict_resolution == ConflictResolution.OVERWRITE:
                        # Delete existing item first - use raw SQL for composite key
                        try:
                            with self.db._writer() as conn:
                                conn.execute(
                                    "DELETE FROM work_items WHERE id = ? AND workflow_id = ?",
                                    (item['id'], target_workflow_id),
                                )
                        except Exception:
                            pass

                # Determine target step: use mapped step if available, else default
                target_step_for_item = step_id_mapping.get(source_step_id, default_step_id)

                try:
                    self.db.create_work_item(
                        id=item_id,
                        workflow_id=target_workflow_id,
                        source_step_id=target_step_for_item,
                        content=item.get('content', ''),
                        title=item.get('title'),
                        priority=item.get('priority'),
                        status='pending',
                        category=item.get('category'),
                        metadata=item.get('metadata'),
                        item_type=item.get('item_type'),
                        dependencies=item.get('dependencies'),
                        phase=item.get('phase'),
                        duplicate_of=item.get('duplicate_of'),
                    )
                    items_imported += 1
                    # Update tags if present (not supported in create_work_item)
                    if item.get('tags'):
                        self.db.update_work_item(item_id, tags=item['tags'])
                except Exception as e:
                    warnings.append(f"Failed to import item {item_id}: {e}")
                    items_skipped += 1

        # Import resources with conflict resolution
        if options.import_resources:
            for resource in resources_data:
                resource_name = resource['name']
                has_conflict = resource_name in existing_resource_names

                if has_conflict:
                    if options.conflict_resolution == ConflictResolution.SKIP:
                        continue
                    elif options.conflict_resolution == ConflictResolution.RENAME:
                        hash_suffix = hashlib.md5(
                            f"{resource_name}-{uuid.uuid4().hex}".encode()
                        ).hexdigest()[:6]
                        resource_name = f"{resource['name']}-{hash_suffix}"
                        resources_renamed += 1
                    elif options.conflict_resolution == ConflictResolution.OVERWRITE:
                        # Find and delete existing
                        for existing in existing_resources:
                            if existing['name'] == resource_name:
                                try:
                                    self.db.delete_workflow_resource(existing['id'])
                                except Exception:
                                    pass
                                break

                try:
                    # NOTE: We intentionally ignore file_path from imports.
                    self.db.create_workflow_resource(
                        workflow_id=target_workflow_id,
                        resource_type=resource['resource_type'],
                        name=resource_name,
                        content=resource.get('content'),
                        file_path=None,  # Never import file paths from archives
                        source='imported',
                        enabled=resource.get('enabled', True),
                    )
                    resources_created += 1
                except Exception as e:
                    warnings.append(f"Failed to import resource {resource_name}: {e}")

        # Import planning sessions
        planning_imported = 0
        if options.import_planning and planning_data:
            # Get existing step IDs for the target workflow
            target_steps = self.db.list_workflow_steps(target_workflow_id)
            if target_steps:
                # Use first step as default for planning sessions
                default_step_id = target_steps[0]['id']
                for session in planning_data:
                    try:
                        new_session_id = f"ps-{uuid.uuid4().hex[:12]}"
                        self.db.create_planning_session(
                            id=new_session_id,
                            workflow_id=target_workflow_id,
                            step_id=default_step_id,
                            messages=session.get('messages', []),
                            artifacts=session.get('artifacts'),
                            status='completed',
                        )
                        planning_imported += 1
                    except Exception as e:
                        warnings.append(f"Failed to import planning session: {e}")

        return ImportResult(
            success=True,
            workflow_id=target_workflow_id,
            workflow_name=target_workflow['name'],
            steps_created=steps_created,
            items_imported=items_imported,
            items_renamed=items_renamed,
            items_skipped=items_skipped,
            resources_created=resources_created,
            resources_renamed=resources_renamed,
            planning_sessions_imported=planning_imported,
            runs_imported=0,
            id_mapping=step_id_mapping,
            warnings=warnings,
        )
