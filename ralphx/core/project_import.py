"""Project import functionality for RalphX.

Enables importing projects with multiple workflows from ZIP archives.
"""

import io
import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ralphx.core.project_db import PROJECT_SCHEMA_VERSION, ProjectDatabase
from ralphx.core.project_export import PROJECT_EXPORT_FORMAT_NAME
from ralphx.core.workflow_export import EXPORT_FORMAT_NAME, EXPORT_FORMAT_VERSION
from ralphx.core.workflow_import import (
    ConflictResolution,
    ImportOptions,
    ImportResult,
    WorkflowImporter,
    MAX_IMPORT_SIZE_MB,
    MAX_COMPRESSION_RATIO,
    MAX_FILES_IN_ARCHIVE,
    _compare_versions,
)


@dataclass
class WorkflowPreviewInfo:
    """Preview info for a workflow in the project export."""
    id: str
    name: str
    steps_count: int
    items_count: int
    resources_count: int
    has_step_artifacts: bool = False  # Whether workflow has step artifacts


@dataclass
class ProjectImportPreview:
    """Preview of what will be imported."""
    # Detect export type
    is_project_export: bool  # True = project export, False = single workflow

    # Project info (if project export)
    project_name: Optional[str] = None
    project_slug: Optional[str] = None

    # Workflows
    workflows: list[WorkflowPreviewInfo] = field(default_factory=list)
    total_items: int = 0
    total_resources: int = 0
    shared_resources_count: int = 0

    # Compatibility
    is_compatible: bool = True
    compatibility_notes: list[str] = field(default_factory=list)

    # Metadata
    exported_at: Optional[str] = None
    ralphx_version: Optional[str] = None
    schema_version: int = 0


@dataclass
class ProjectImportOptions:
    """Options for project import operation."""
    selected_workflow_ids: Optional[list[str]] = None  # None = all workflows
    import_shared_resources: bool = True
    import_step_artifacts: bool = False  # Import step artifacts if present (off by default)
    conflict_resolution: ConflictResolution = ConflictResolution.RENAME


@dataclass
class ProjectImportResult:
    """Result of project import operation."""
    success: bool
    workflows_imported: int
    workflow_results: list[ImportResult]
    shared_resources_imported: int
    warnings: list[str] = field(default_factory=list)


class ProjectImporter:
    """Imports projects with multiple workflows from ZIP archives.

    Supports both:
    - Project exports (multiple workflows)
    - Single workflow exports (auto-detected)
    """

    def __init__(self, project_db: ProjectDatabase):
        """Initialize importer.

        Args:
            project_db: ProjectDatabase instance for the project.
        """
        self.db = project_db
        self.workflow_importer = WorkflowImporter(project_db)

    def get_preview(self, zip_data: bytes) -> ProjectImportPreview:
        """Get a preview of what will be imported.

        Auto-detects whether this is a project export or single workflow export.

        Args:
            zip_data: ZIP file content as bytes.

        Returns:
            ProjectImportPreview with contents info.

        Raises:
            ValueError: If archive is invalid.
        """
        # Validate archive
        self._validate_archive(zip_data)

        with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
            manifest = self._read_manifest(zf)

            # Detect export type
            export_format = manifest.get('format')

            if export_format == PROJECT_EXPORT_FORMAT_NAME:
                return self._preview_project_export(zf, manifest)
            elif export_format == EXPORT_FORMAT_NAME:
                # Single workflow export
                return self._preview_workflow_export(zf, manifest)
            else:
                raise ValueError(f"Unknown export format: {export_format}")

    def import_project(
        self,
        zip_data: bytes,
        options: Optional[ProjectImportOptions] = None,
    ) -> ProjectImportResult:
        """Import a project or workflow from ZIP.

        Auto-detects export type and handles appropriately.

        Args:
            zip_data: ZIP file content as bytes.
            options: Import options.

        Returns:
            ProjectImportResult with details.

        Raises:
            ValueError: If import fails.
        """
        if options is None:
            options = ProjectImportOptions()

        # Validate archive
        self._validate_archive(zip_data)

        with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
            manifest = self._read_manifest(zf)
            export_format = manifest.get('format')

            if export_format == PROJECT_EXPORT_FORMAT_NAME:
                return self._import_project_export(zf, manifest, options)
            elif export_format == EXPORT_FORMAT_NAME:
                # Single workflow export - delegate to workflow importer
                return self._import_single_workflow(zip_data, options)
            else:
                raise ValueError(f"Unknown export format: {export_format}")

    def _validate_archive(self, zip_data: bytes) -> None:
        """Validate ZIP archive for security and format."""
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

            # Calculate total uncompressed size
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
                    raise ValueError(f"Compression ratio too high ({ratio:.0f}:1)")

            if total_uncompressed > MAX_IMPORT_SIZE_MB * 1024 * 1024:
                raise ValueError(f"Uncompressed size exceeds {MAX_IMPORT_SIZE_MB}MB")

            # Verify manifest exists
            if 'manifest.json' not in zf.namelist():
                raise ValueError("Missing manifest.json")

    def _read_manifest(self, zf: zipfile.ZipFile) -> dict:
        """Read and parse manifest.json."""
        try:
            content = zf.read('manifest.json').decode('utf-8')
            return json.loads(content)
        except (KeyError, json.JSONDecodeError) as e:
            raise ValueError(f"Invalid manifest.json: {e}")

    def _check_compatibility(self, manifest: dict) -> tuple[bool, list[str]]:
        """Check if the export is compatible."""
        notes = []
        is_compatible = True

        export_version = manifest.get('version', '0.0')
        if _compare_versions(export_version, EXPORT_FORMAT_VERSION) > 0:
            notes.append(f"Export format {export_version} is newer than supported {EXPORT_FORMAT_VERSION}")
            is_compatible = False

        schema_version = manifest.get('schema_version', 0)
        if schema_version > PROJECT_SCHEMA_VERSION:
            notes.append(f"Schema version {schema_version} is newer than current {PROJECT_SCHEMA_VERSION}")
            is_compatible = False
        elif schema_version < PROJECT_SCHEMA_VERSION - 5:
            notes.append(f"Schema version {schema_version} is quite old")

        return is_compatible, notes

    def _preview_project_export(
        self,
        zf: zipfile.ZipFile,
        manifest: dict,
    ) -> ProjectImportPreview:
        """Preview a project export."""
        is_compatible, notes = self._check_compatibility(manifest)

        workflows_info = []
        total_items = 0
        total_resources = 0

        # Get workflow info from manifest
        for wf_info in manifest.get('contents', {}).get('workflows', []):
            wf_id = wf_info['id']
            # Support both new (workflow_id) and old (namespace) path formats
            wf_prefix = f"workflows/{wf_id}/"
            # Check for old namespace-based paths for backward compatibility
            old_namespace = wf_info.get('namespace')
            if old_namespace and f"workflows/{old_namespace}/workflow.json" in zf.namelist():
                wf_prefix = f"workflows/{old_namespace}/"

            # Count items
            items_count = 0
            if f"{wf_prefix}items.jsonl" in zf.namelist():
                try:
                    content = zf.read(f"{wf_prefix}items.jsonl").decode('utf-8')
                    items_count = len([l for l in content.strip().split('\n') if l.strip()])
                except Exception:
                    pass

            # Count resources
            resources_count = 0
            if f"{wf_prefix}resources/resources.json" in zf.namelist():
                try:
                    content = zf.read(f"{wf_prefix}resources/resources.json").decode('utf-8')
                    resources_count = len(json.loads(content))
                except Exception:
                    pass

            # Count steps from workflow.json and detect artifacts
            steps_count = 0
            has_step_artifacts = False
            if f"{wf_prefix}workflow.json" in zf.namelist():
                try:
                    content = zf.read(f"{wf_prefix}workflow.json").decode('utf-8')
                    wf_data = json.loads(content)
                    steps = wf_data.get('steps', [])
                    steps_count = len(steps)
                    # Check if any step has artifacts
                    for step in steps:
                        if step.get('artifacts'):
                            has_step_artifacts = True
                            break
                except Exception:
                    pass

            workflows_info.append(WorkflowPreviewInfo(
                id=wf_info['id'],
                name=wf_info['name'],
                steps_count=steps_count,
                items_count=items_count,
                resources_count=resources_count,
                has_step_artifacts=has_step_artifacts,
            ))

            total_items += items_count
            total_resources += resources_count

        # Count shared resources
        shared_resources = 0
        if 'shared-resources/resources.json' in zf.namelist():
            try:
                content = zf.read('shared-resources/resources.json').decode('utf-8')
                shared_resources = len(json.loads(content))
            except Exception:
                pass

        return ProjectImportPreview(
            is_project_export=True,
            project_name=manifest.get('project', {}).get('name'),
            project_slug=manifest.get('project', {}).get('slug'),
            workflows=workflows_info,
            total_items=total_items,
            total_resources=total_resources,
            shared_resources_count=shared_resources,
            is_compatible=is_compatible,
            compatibility_notes=notes,
            exported_at=manifest.get('exported_at'),
            ralphx_version=manifest.get('ralphx_version'),
            schema_version=manifest.get('schema_version', 0),
        )

    def _preview_workflow_export(
        self,
        zf: zipfile.ZipFile,
        manifest: dict,
    ) -> ProjectImportPreview:
        """Preview a single workflow export."""
        is_compatible, notes = self._check_compatibility(manifest)

        wf_info = manifest.get('workflow', {})
        contents = manifest.get('contents', {})

        return ProjectImportPreview(
            is_project_export=False,
            workflows=[WorkflowPreviewInfo(
                id=wf_info.get('id', ''),
                name=wf_info.get('name', ''),
                steps_count=contents.get('steps', 0),
                items_count=contents.get('items_total', 0),
                resources_count=contents.get('resources', 0),
            )],
            total_items=contents.get('items_total', 0),
            total_resources=contents.get('resources', 0),
            shared_resources_count=0,
            is_compatible=is_compatible,
            compatibility_notes=notes,
            exported_at=manifest.get('exported_at'),
            ralphx_version=manifest.get('ralphx_version'),
            schema_version=manifest.get('schema_version', 0),
        )

    def _import_project_export(
        self,
        zf: zipfile.ZipFile,
        manifest: dict,
        options: ProjectImportOptions,
    ) -> ProjectImportResult:
        """Import a project export with multiple workflows."""
        warnings = []
        workflow_results = []
        shared_resources_imported = 0

        # Check compatibility
        is_compatible, notes = self._check_compatibility(manifest)
        if not is_compatible:
            raise ValueError(f"Import not compatible: {'; '.join(notes)}")

        # Import shared resources first
        if options.import_shared_resources:
            shared_resources_imported = self._import_shared_resources(zf)

        # Get workflows to import
        all_workflows = manifest.get('contents', {}).get('workflows', [])

        if options.selected_workflow_ids is not None:
            workflows_to_import = [
                w for w in all_workflows
                if w['id'] in options.selected_workflow_ids
            ]
        else:
            workflows_to_import = all_workflows

        # Import each workflow
        for wf_info in workflows_to_import:
            try:
                result = self._import_workflow_from_project(
                    zf,
                    wf_info,
                    options.conflict_resolution,
                    import_step_artifacts=options.import_step_artifacts,
                )
                workflow_results.append(result)
            except Exception as e:
                warnings.append(f"Failed to import workflow '{wf_info['name']}': {e}")

        return ProjectImportResult(
            success=len(workflow_results) > 0,
            workflows_imported=len(workflow_results),
            workflow_results=workflow_results,
            shared_resources_imported=shared_resources_imported,
            warnings=warnings,
        )

    def _import_single_workflow(
        self,
        zip_data: bytes,
        options: ProjectImportOptions,
    ) -> ProjectImportResult:
        """Import a single workflow export."""
        import_options = ImportOptions(
            conflict_resolution=options.conflict_resolution,
            import_step_artifacts=options.import_step_artifacts,
        )

        result = self.workflow_importer.import_workflow(zip_data, import_options)

        return ProjectImportResult(
            success=result.success,
            workflows_imported=1 if result.success else 0,
            workflow_results=[result],
            shared_resources_imported=0,
            warnings=result.warnings,
        )

    def _import_shared_resources(self, zf: zipfile.ZipFile) -> int:
        """Import shared project resources."""
        if 'shared-resources/resources.json' not in zf.namelist():
            return 0

        try:
            content = zf.read('shared-resources/resources.json').decode('utf-8')
            resources = json.loads(content)
        except Exception:
            return 0

        imported = 0
        for resource in resources:
            try:
                # NOTE: We intentionally ignore file_path from imports.
                # Accepting arbitrary file paths from imported data could allow
                # an attacker to plant paths that get read during later exports.
                self.db.create_project_resource(
                    resource_type=resource['resource_type'],
                    name=resource['name'],
                    content=resource.get('content'),
                    file_path=None,  # Never import file paths from archives
                    auto_inherit=resource.get('auto_inherit', False),
                )
                imported += 1
            except Exception:
                # Resource may already exist, skip
                pass

        return imported

    def _import_workflow_from_project(
        self,
        zf: zipfile.ZipFile,
        wf_info: dict,
        conflict_resolution: ConflictResolution,
        import_step_artifacts: bool = False,
    ) -> ImportResult:
        """Import a single workflow from a project export."""
        import hashlib
        import uuid

        wf_id = wf_info['id']
        # Support both new (workflow_id) and old (namespace) path formats
        wf_prefix = f"workflows/{wf_id}/"
        # Check for old namespace-based paths for backward compatibility
        old_namespace = wf_info.get('namespace')
        if old_namespace and f"workflows/{old_namespace}/workflow.json" in zf.namelist():
            wf_prefix = f"workflows/{old_namespace}/"

        # Read workflow data
        workflow_data = json.loads(zf.read(f"{wf_prefix}workflow.json").decode('utf-8'))

        # Read items
        items_data = []
        if f"{wf_prefix}items.jsonl" in zf.namelist():
            content = zf.read(f"{wf_prefix}items.jsonl").decode('utf-8')
            for line in content.strip().split('\n'):
                if line.strip():
                    items_data.append(json.loads(line))

        # Read resources
        resources_data = []
        if f"{wf_prefix}resources/resources.json" in zf.namelist():
            content = zf.read(f"{wf_prefix}resources/resources.json").decode('utf-8')
            resources_data = json.loads(content)

        # Read planning sessions
        planning_data = []
        if f"{wf_prefix}planning/session.json" in zf.namelist():
            content = zf.read(f"{wf_prefix}planning/session.json").decode('utf-8')
            planning_data = json.loads(content)

        # Generate new IDs
        old_wf_id = workflow_data['workflow']['id']
        new_wf_id = f"wf-{uuid.uuid4().hex[:12]}"

        id_mapping = {old_wf_id: new_wf_id}

        # Map item IDs
        for item in items_data:
            old_id = item['id']
            hash_suffix = hashlib.md5(f"{old_id}-{uuid.uuid4().hex}".encode()).hexdigest()[:8]
            id_mapping[old_id] = f"{old_id}-{hash_suffix}"

        # Create workflow
        workflow = self.db.create_workflow(
            id=new_wf_id,
            name=workflow_data['workflow']['name'],
            template_id=workflow_data['workflow'].get('template_id'),
            status='draft',
        )

        # Create steps
        step_id_mapping = {}
        steps_created = 0
        warnings = []  # Initialize warnings list before step loop

        for step_def in workflow_data.get('steps', []):
            step = self.db.create_workflow_step(
                workflow_id=new_wf_id,
                step_number=step_def['step_number'],
                name=step_def['name'],
                step_type=step_def['step_type'],
                config=step_def.get('config'),
                loop_name=step_def.get('loop_name'),
                status='pending',
            )
            step_id_mapping[step_def['id']] = step['id']
            steps_created += 1

            # Import artifacts if option is enabled and artifacts exist
            if import_step_artifacts and step_def.get('artifacts'):
                try:
                    self.db.update_workflow_step(step['id'], artifacts=step_def['artifacts'])
                except Exception as e:
                    warnings.append(f"Failed to import artifacts for step {step_def['name']}: {e}")

        # Import items
        items_imported = 0
        items_renamed = 0

        # Skip item import if no steps were created
        if not step_id_mapping:
            if items_data:
                warnings.append(f"Skipping {len(items_data)} items: no steps were imported to associate them with")
        else:
            for item in items_data:
                new_item_id = id_mapping.get(item['id'], item['id'])

                # Update dependencies
                deps = item.get('dependencies', []) or []
                new_deps = [id_mapping.get(d, d) for d in deps]

                # Get step ID - use mapped step ID or fall back to first available step
                old_step_id = item.get('source_step_id')
                new_step_id = step_id_mapping.get(old_step_id) if old_step_id else None
                if new_step_id is None:
                    new_step_id = list(step_id_mapping.values())[0]

                # Update duplicate_of with new ID if mapped
                duplicate_of = item.get('duplicate_of')
                if duplicate_of and duplicate_of in id_mapping:
                    duplicate_of = id_mapping[duplicate_of]

                try:
                    self.db.create_work_item(
                        id=new_item_id,
                        workflow_id=new_wf_id,
                        source_step_id=new_step_id,
                        content=item.get('content', ''),
                        title=item.get('title'),
                        priority=item.get('priority'),
                        status='pending',
                        category=item.get('category'),
                        metadata=item.get('metadata'),
                        item_type=item.get('item_type'),
                        dependencies=new_deps,
                        phase=item.get('phase'),
                        duplicate_of=duplicate_of,
                    )
                    items_imported += 1
                    if new_item_id != item['id']:
                        items_renamed += 1
                    # Update tags if present (not supported in create_work_item)
                    if item.get('tags'):
                        self.db.update_work_item(new_item_id, tags=item['tags'])
                except Exception as e:
                    warnings.append(f"Failed to import item {item['id']}: {e}")

        # Import resources
        resources_created = 0
        for resource in resources_data:
            try:
                # NOTE: We intentionally ignore file_path from imports.
                self.db.create_workflow_resource(
                    workflow_id=new_wf_id,
                    resource_type=resource['resource_type'],
                    name=resource['name'],
                    content=resource.get('content'),
                    file_path=None,  # Never import file paths from archives
                    source='imported',
                    enabled=resource.get('enabled', True),
                )
                resources_created += 1
            except Exception as e:
                warnings.append(f"Failed to import resource {resource['name']}: {e}")

        # Import planning sessions
        planning_imported = 0
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

        return ImportResult(
            success=True,
            workflow_id=new_wf_id,
            workflow_name=workflow['name'],
            steps_created=steps_created,
            items_imported=items_imported,
            items_renamed=items_renamed,
            items_skipped=len(items_data) - items_imported,
            resources_created=resources_created,
            resources_renamed=0,
            planning_sessions_imported=planning_imported,
            runs_imported=0,
            id_mapping=id_mapping,
            warnings=warnings,
        )
