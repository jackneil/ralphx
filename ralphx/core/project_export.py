"""Project export functionality for RalphX.

Enables exporting entire projects with multiple workflows to a portable ZIP format.
"""

import io
import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from ralphx import __version__
from ralphx.core.project_db import PROJECT_SCHEMA_VERSION, ProjectDatabase
from ralphx.core.workflow_export import (
    EXPORT_FORMAT_VERSION,
    ExportOptions,
    SecretMatch,
    SECRET_PATTERNS,
    WorkflowExporter,
)


# Export format name for project exports
PROJECT_EXPORT_FORMAT_NAME = "ralphx-project-export"

# Security limits
MAX_EXPORT_SIZE_MB = 500


@dataclass
class WorkflowSummary:
    """Summary of a workflow in the project."""
    id: str
    name: str
    namespace: str
    steps_count: int
    items_count: int
    resources_count: int


@dataclass
class ProjectExportPreview:
    """Preview of what will be exported from a project."""
    project_name: str
    project_slug: str
    workflows: list[WorkflowSummary]
    total_items: int
    total_resources: int
    estimated_size_bytes: int
    potential_secrets: list[SecretMatch] = field(default_factory=list)


@dataclass
class ProjectExportOptions:
    """Options for project export operation."""
    workflow_ids: Optional[list[str]] = None  # None = all workflows
    include_runs: bool = False
    include_planning: bool = True
    include_planning_messages: bool = False
    include_step_artifacts: bool = False  # Step outputs (not needed for fresh runs)
    strip_secrets: bool = True  # Strip potential secrets by default for safety
    include_project_resources: bool = True


def _strip_secrets(text: Optional[str]) -> str:
    """Strip potential secrets from text using the shared secret patterns."""
    import re
    if not text:
        return ''
    result = text
    for pattern, _ in SECRET_PATTERNS:
        result = re.sub(pattern, '[REDACTED]', result, flags=re.IGNORECASE)
    return result


class ProjectExporter:
    """Exports projects with multiple workflows to ZIP archives.

    Export format:
    - manifest.json: Project metadata, workflow list
    - project.json: Project settings and resources
    - workflows/
      - workflow-1/
        - workflow.json
        - items.jsonl
        - resources/
      - workflow-2/
        - ...
    - shared-resources/: Project-level resources
    """

    def __init__(self, project_db: ProjectDatabase, project_info: dict):
        """Initialize exporter.

        Args:
            project_db: ProjectDatabase instance for the project.
            project_info: Project metadata dict (name, slug, path, etc.).
        """
        self.db = project_db
        self.project_info = project_info
        self.workflow_exporter = WorkflowExporter(project_db)

    def get_preview(
        self,
        options: Optional[ProjectExportOptions] = None,
    ) -> ProjectExportPreview:
        """Get a preview of what will be exported.

        Args:
            options: Export options (workflow_ids filter, etc.).

        Returns:
            ProjectExportPreview with workflow list and totals.
        """
        if options is None:
            options = ProjectExportOptions()

        # Get all workflows
        all_workflows = self.db.list_workflows()

        # Filter by selected IDs if specified
        if options.workflow_ids is not None:
            workflows = [w for w in all_workflows if w['id'] in options.workflow_ids]
        else:
            workflows = all_workflows

        # Build workflow summaries
        summaries = []
        total_items = 0
        total_resources = 0
        all_secrets: list[SecretMatch] = []

        for wf in workflows:
            wf_preview = self.workflow_exporter.get_preview(wf['id'])
            summaries.append(WorkflowSummary(
                id=wf['id'],
                name=wf['name'],
                namespace=wf['namespace'],
                steps_count=wf_preview.steps_count,
                items_count=wf_preview.items_total,
                resources_count=wf_preview.resources_count,
            ))
            total_items += wf_preview.items_total
            total_resources += wf_preview.resources_count
            all_secrets.extend(wf_preview.potential_secrets)

        # Get project resources
        try:
            project_resources = self.db.list_project_resources()
            total_resources += len(project_resources)
        except Exception:
            project_resources = []

        # Estimate size
        estimated_size = self._estimate_export_size(workflows, total_items, total_resources)

        return ProjectExportPreview(
            project_name=self.project_info.get('name', 'Unknown'),
            project_slug=self.project_info.get('slug', 'unknown'),
            workflows=summaries,
            total_items=total_items,
            total_resources=total_resources,
            estimated_size_bytes=estimated_size,
            potential_secrets=all_secrets,
        )

    def export_project(
        self,
        options: Optional[ProjectExportOptions] = None,
    ) -> tuple[bytes, str]:
        """Export project to ZIP archive.

        Args:
            options: Export options.

        Returns:
            Tuple of (zip_bytes, filename).

        Raises:
            ValueError: If export fails validation.
        """
        if options is None:
            options = ProjectExportOptions()

        # Get workflows to export
        all_workflows = self.db.list_workflows()
        if options.workflow_ids is not None:
            workflows = [w for w in all_workflows if w['id'] in options.workflow_ids]
        else:
            workflows = all_workflows

        # Get project resources
        project_resources = []
        if options.include_project_resources:
            try:
                project_resources = self.db.list_project_resources()
            except Exception:
                pass

        # Build manifest
        manifest = self._build_manifest(workflows, project_resources, options)

        # Create ZIP archive
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Write manifest
            zf.writestr('manifest.json', json.dumps(manifest, indent=2, default=str))

            # Write project info
            project_data = {
                'name': self.project_info.get('name'),
                'slug': self.project_info.get('slug'),
                'path': None,  # Don't export path
                'created_at': self.project_info.get('created_at'),
            }
            zf.writestr('project.json', json.dumps(project_data, indent=2, default=str))

            # Write project resources
            if project_resources:
                resources_data = self._serialize_project_resources(project_resources, options)
                zf.writestr('shared-resources/resources.json', json.dumps(resources_data, indent=2, default=str))

            # Write each workflow
            workflow_export_options = ExportOptions(
                include_runs=options.include_runs,
                include_planning=options.include_planning,
                include_planning_messages=options.include_planning_messages,
                strip_secrets=options.strip_secrets,
            )

            for wf in workflows:
                wf_prefix = f"workflows/{wf['namespace']}/"

                # Get workflow data
                steps = self.db.list_workflow_steps(wf['id'])
                resources = self.db.list_workflow_resources(wf['id'])
                items, _ = self.db.list_work_items(workflow_id=wf['id'], limit=100000)

                # Write workflow.json
                serialized_steps = []
                for s in steps:
                    step_data = {
                        'id': s['id'],
                        'workflow_id': s['workflow_id'],
                        'step_number': s['step_number'],
                        'name': s['name'],
                        'step_type': s['step_type'],
                        'status': 'pending',
                        'config': s.get('config'),
                        'loop_name': s.get('loop_name'),
                    }
                    # Only include artifacts if explicitly requested (off by default)
                    if options.include_step_artifacts:
                        step_data['artifacts'] = s.get('artifacts')
                    serialized_steps.append(step_data)

                workflow_data = {
                    'workflow': {
                        'id': wf['id'],
                        'template_id': wf.get('template_id'),
                        'name': wf['name'],
                        'namespace': wf['namespace'],
                        'status': 'draft',
                        'current_step': 1,
                        'created_at': wf.get('created_at'),
                        'updated_at': wf.get('updated_at'),
                    },
                    'steps': serialized_steps,
                }
                zf.writestr(
                    wf_prefix + 'workflow.json',
                    json.dumps(workflow_data, indent=2, default=str),
                )

                # Write items.jsonl
                items_lines = []
                for item in items:
                    content = item.get('content', '')
                    title = item.get('title')
                    # Apply secret stripping if enabled
                    if options.strip_secrets:
                        content = _strip_secrets(content)
                        title = _strip_secrets(title) if title else title

                    item_data = {
                        'id': item['id'],
                        'workflow_id': item['workflow_id'],
                        'source_step_id': item.get('source_step_id'),
                        'content': content,
                        'title': title,
                        'priority': item.get('priority'),
                        'status': 'pending',
                        'category': item.get('category'),
                        'tags': item.get('tags'),
                        'metadata': item.get('metadata'),
                        'item_type': item.get('item_type'),
                        'dependencies': item.get('dependencies'),
                        'phase': item.get('phase'),
                        'duplicate_of': item.get('duplicate_of'),
                        'created_at': item.get('created_at'),
                    }
                    items_lines.append(json.dumps(item_data, default=str))
                zf.writestr(wf_prefix + 'items.jsonl', '\n'.join(items_lines))

                # Write resources
                # NOTE: We intentionally do NOT read from file_path here.
                # Resources with file_path references are project-local and should
                # only include content that was explicitly inlined. Reading arbitrary
                # file paths during export could leak sensitive files if a malicious
                # import planted a crafted file_path.
                resources_data = []
                for r in resources:
                    content = r.get('content')

                    # Apply secret stripping if enabled
                    if options.strip_secrets and content:
                        content = _strip_secrets(content)

                    resources_data.append({
                        'id': r['id'],
                        'workflow_id': r['workflow_id'],
                        'resource_type': r['resource_type'],
                        'name': r['name'],
                        'content': content,
                        'file_path': None,  # Never export file paths
                        'source': r.get('source'),
                        'enabled': r.get('enabled', True),
                    })
                zf.writestr(
                    wf_prefix + 'resources/resources.json',
                    json.dumps(resources_data, indent=2, default=str),
                )

                # Write planning sessions if requested
                if options.include_planning:
                    try:
                        planning_sessions = self.db.list_planning_sessions(workflow_id=wf['id'])
                        if planning_sessions:
                            planning_data = []
                            for s in planning_sessions:
                                data = {
                                    'id': s['id'],
                                    'workflow_id': s['workflow_id'],
                                    'step_id': s['step_id'],
                                    'artifacts': s.get('artifacts'),
                                    'status': s.get('status'),
                                    'created_at': s.get('created_at'),
                                }
                                if options.include_planning_messages:
                                    data['messages'] = s.get('messages', [])
                                planning_data.append(data)
                            zf.writestr(
                                wf_prefix + 'planning/session.json',
                                json.dumps(planning_data, indent=2, default=str),
                            )
                    except Exception:
                        pass

                # Write runs if requested
                if options.include_runs:
                    try:
                        runs = self.db.list_runs(workflow_id=wf['id'])
                        if runs:
                            runs_data = [
                                {
                                    'id': r['id'],
                                    'loop_name': r['loop_name'],
                                    'status': r['status'],
                                    'workflow_id': r['workflow_id'],
                                    'step_id': r['step_id'],
                                    'started_at': r.get('started_at'),
                                    'completed_at': r.get('completed_at'),
                                    'iterations_completed': r.get('iterations_completed', 0),
                                    'items_generated': r.get('items_generated', 0),
                                }
                                for r in runs
                            ]
                            zf.writestr(
                                wf_prefix + 'runs/runs.json',
                                json.dumps(runs_data, indent=2, default=str),
                            )
                    except Exception:
                        pass

        # Generate filename
        timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
        slug = self.project_info.get('slug', 'project')
        filename = f"project-{slug}-{timestamp}.ralphx.zip"

        zip_bytes = zip_buffer.getvalue()

        # Validate size
        if len(zip_bytes) > MAX_EXPORT_SIZE_MB * 1024 * 1024:
            raise ValueError(f"Export exceeds maximum size of {MAX_EXPORT_SIZE_MB}MB")

        return zip_bytes, filename

    def _estimate_export_size(
        self,
        workflows: list[dict],
        total_items: int,
        total_resources: int,
    ) -> int:
        """Estimate export size in bytes."""
        # Rough estimate: 1KB per item, 2KB per resource, 500B per workflow
        size = (total_items * 1024) + (total_resources * 2048) + (len(workflows) * 512)
        # Add overhead and apply compression estimate (60%)
        return int(size * 0.6)

    def _build_manifest(
        self,
        workflows: list[dict],
        project_resources: list[dict],
        options: ProjectExportOptions,
    ) -> dict:
        """Build the project manifest."""
        return {
            'version': EXPORT_FORMAT_VERSION,
            'format': PROJECT_EXPORT_FORMAT_NAME,
            'exported_at': datetime.utcnow().isoformat() + 'Z',
            'ralphx_version': __version__,
            'schema_version': PROJECT_SCHEMA_VERSION,
            'project': {
                'name': self.project_info.get('name'),
                'slug': self.project_info.get('slug'),
            },
            'contents': {
                'workflows_count': len(workflows),
                'workflows': [
                    {
                        'id': w['id'],
                        'name': w['name'],
                        'namespace': w['namespace'],
                    }
                    for w in workflows
                ],
                'shared_resources_count': len(project_resources),
            },
            'export_options': {
                'include_runs': options.include_runs,
                'include_planning': options.include_planning,
                'include_step_artifacts': options.include_step_artifacts,
                'include_project_resources': options.include_project_resources,
            },
        }

    def _serialize_project_resources(
        self,
        resources: list[dict],
        options: ProjectExportOptions,
    ) -> list[dict]:
        """Serialize project resources."""
        # NOTE: We intentionally do NOT read from file_path here.
        # See workflow resources comment above for rationale.
        result = []
        for r in resources:
            content = r.get('content')

            # Apply secret stripping if enabled
            if options.strip_secrets and content:
                content = _strip_secrets(content)

            result.append({
                'id': r['id'],
                'resource_type': r['resource_type'],
                'name': r['name'],
                'content': content,
                'file_path': None,  # Never export file paths
                'auto_inherit': r.get('auto_inherit', False),
            })
        return result
