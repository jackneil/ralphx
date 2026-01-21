"""Workflow export functionality for RalphX.

Enables exporting entire workflows (with resources, steps, items, settings)
to a portable ZIP format that can be imported into other projects.
"""

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ralphx import __version__
from ralphx.core.project_db import PROJECT_SCHEMA_VERSION, ProjectDatabase


# Export format version
EXPORT_FORMAT_VERSION = "1.0"
EXPORT_FORMAT_NAME = "ralphx-workflow-export"

# Security limits
MAX_EXPORT_SIZE_MB = 500
MAX_FILES_IN_ARCHIVE = 10000

# Patterns for detecting potential secrets
SECRET_PATTERNS = [
    # API keys
    (r'sk-[a-zA-Z0-9]{20,}', 'API key (sk-*)'),
    (r'api[_-]?key["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{16,}', 'API key assignment'),
    (r'key[_-]?["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{32,}', 'Generic key'),
    # OAuth/JWT tokens
    (r'eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+', 'JWT token'),
    (r'oauth[_-]?token["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{20,}', 'OAuth token'),
    (r'bearer\s+[a-zA-Z0-9_.-]{20,}', 'Bearer token'),
    # Database URIs with passwords
    (r'(postgres|mysql|mongodb)://[^:]+:[^@]+@', 'Database URI with password'),
    # Private keys
    (r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----', 'Private key'),
    (r'-----BEGIN\s+OPENSSH\s+PRIVATE\s+KEY-----', 'SSH private key'),
    # Common patterns
    (r'password["\']?\s*[:=]\s*["\']?[^\s"\']{8,}', 'Password assignment'),
    (r'secret["\']?\s*[:=]\s*["\']?[^\s"\']{8,}', 'Secret assignment'),
    (r'token["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{20,}', 'Token assignment'),
    # AWS
    (r'AKIA[0-9A-Z]{16}', 'AWS access key'),
    (r'aws[_-]?secret[_-]?access[_-]?key', 'AWS secret key reference'),
]


@dataclass
class SecretMatch:
    """A potential secret found during scanning."""
    pattern_name: str
    location: str  # e.g., "workflow_resources.Design Doc"
    snippet: str  # Redacted snippet showing context


@dataclass
class ExportPreview:
    """Preview of what will be exported."""
    workflow_name: str
    workflow_namespace: str
    steps_count: int
    items_total: int
    items_by_step: dict[int, int]  # step_id -> count
    resources_count: int
    has_planning_session: bool
    runs_count: int
    estimated_size_bytes: int
    potential_secrets: list[SecretMatch] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ExportOptions:
    """Options for export operation."""
    include_runs: bool = False
    include_planning: bool = True
    include_planning_messages: bool = False  # Only artifacts by default
    include_step_artifacts: bool = False  # Step outputs (not needed for fresh runs)
    strip_secrets: bool = True  # Strip potential secrets by default for safety
    as_template: bool = False


class WorkflowExporter:
    """Exports workflows to portable ZIP archives.

    Export format:
    - manifest.json: Metadata, version, contents summary
    - workflow.json: Workflow definition + steps
    - items.jsonl: All work items (JSONL format)
    - resources/: Workflow resources
    - step-resources/: Step-level resource overrides
    - planning/: Planning session (optional)
    - runs/: Execution history (optional)
    """

    def __init__(self, project_db: ProjectDatabase):
        """Initialize exporter.

        Args:
            project_db: ProjectDatabase instance for the project.
        """
        self.db = project_db

    def get_preview(self, workflow_id: str) -> ExportPreview:
        """Get a preview of what will be exported.

        Args:
            workflow_id: ID of the workflow to export.

        Returns:
            ExportPreview with counts and size estimates.

        Raises:
            ValueError: If workflow not found.
        """
        workflow = self.db.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow '{workflow_id}' not found")

        steps = self.db.list_workflow_steps(workflow_id)
        resources = self.db.list_workflow_resources(workflow_id)
        items, total_items = self.db.list_work_items(workflow_id=workflow_id, limit=100000)
        runs = self.db.list_runs(workflow_id=workflow_id)

        # Get planning session if exists
        planning_sessions = self._get_planning_sessions(workflow_id)

        # Check for truncation warning
        export_warnings: list[str] = []
        if total_items > 100000:
            export_warnings.append(
                f"Workflow has {total_items} items but export is limited to 100,000. "
                f"{total_items - 100000} items will be truncated."
            )

        # Count items by step
        items_by_step: dict[int, int] = {}
        for item in items:
            step_id = item.get('source_step_id', 0)
            items_by_step[step_id] = items_by_step.get(step_id, 0) + 1

        # Estimate size (rough calculation)
        estimated_size = self._estimate_export_size(
            workflow, steps, items, resources, planning_sessions, runs
        )

        # Scan for potential secrets
        potential_secrets = self._scan_for_secrets(workflow, resources, items)

        return ExportPreview(
            workflow_name=workflow['name'],
            workflow_namespace=workflow['namespace'],
            steps_count=len(steps),
            items_total=total_items,  # Show real count, not truncated count
            items_by_step=items_by_step,
            resources_count=len(resources),
            has_planning_session=len(planning_sessions) > 0,
            runs_count=len(runs),
            estimated_size_bytes=estimated_size,
            potential_secrets=potential_secrets,
            warnings=export_warnings,
        )

    def export_workflow(
        self,
        workflow_id: str,
        options: Optional[ExportOptions] = None,
    ) -> tuple[bytes, str]:
        """Export a workflow to ZIP archive.

        Args:
            workflow_id: ID of the workflow to export.
            options: Export options.

        Returns:
            Tuple of (zip_bytes, filename).

        Raises:
            ValueError: If workflow not found or export fails validation.
        """
        if options is None:
            options = ExportOptions()

        workflow = self.db.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow '{workflow_id}' not found")

        # Collect all data
        steps = self.db.list_workflow_steps(workflow_id)
        resources = self.db.list_workflow_resources(workflow_id)
        items, _ = self.db.list_work_items(workflow_id=workflow_id, limit=100000)
        step_resources = self._get_all_step_resources(workflow_id, steps)
        planning_sessions = self._get_planning_sessions(workflow_id) if options.include_planning else []
        runs = self.db.list_runs(workflow_id=workflow_id) if options.include_runs else []

        # Scan for secrets if not stripping
        potential_secrets = []
        if not options.strip_secrets:
            potential_secrets = self._scan_for_secrets(workflow, resources, items)

        # Build manifest
        manifest = self._build_manifest(
            workflow, steps, items, resources, planning_sessions, runs,
            potential_secrets, options
        )

        # Create ZIP archive
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Write manifest
            zf.writestr('manifest.json', json.dumps(manifest, indent=2, default=str))

            # Write workflow definition
            workflow_data = self._serialize_workflow(workflow, steps, options)
            zf.writestr('workflow.json', json.dumps(workflow_data, indent=2, default=str))

            # Write items as JSONL
            items_content = self._serialize_items_jsonl(items, options)
            zf.writestr('items.jsonl', items_content)

            # Write resources
            resources_data = self._serialize_resources(resources, options)
            zf.writestr('resources/resources.json', json.dumps(resources_data, indent=2, default=str))

            # Write step resources
            if step_resources:
                step_resources_data = self._serialize_step_resources(step_resources, options)
                zf.writestr('step-resources/step-resources.json', json.dumps(step_resources_data, indent=2, default=str))

            # Write planning sessions
            if planning_sessions and options.include_planning:
                planning_data = self._serialize_planning_sessions(
                    planning_sessions, options.include_planning_messages
                )
                zf.writestr('planning/session.json', json.dumps(planning_data, indent=2, default=str))

            # Write runs
            if runs and options.include_runs:
                runs_data = self._serialize_runs(runs)
                zf.writestr('runs/runs.json', json.dumps(runs_data, indent=2, default=str))

        # Generate filename
        timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
        namespace = workflow['namespace']
        filename = f"workflow-{namespace}-{timestamp}.ralphx.zip"

        zip_bytes = zip_buffer.getvalue()

        # Validate size
        if len(zip_bytes) > MAX_EXPORT_SIZE_MB * 1024 * 1024:
            raise ValueError(f"Export exceeds maximum size of {MAX_EXPORT_SIZE_MB}MB")

        return zip_bytes, filename

    def _get_planning_sessions(self, workflow_id: str) -> list[dict]:
        """Get planning sessions for a workflow."""
        try:
            return self.db.list_planning_sessions(workflow_id=workflow_id)
        except Exception:
            return []

    def _get_all_step_resources(self, workflow_id: str, steps: list[dict]) -> dict[int, list[dict]]:
        """Get step resources for all steps."""
        result: dict[int, list[dict]] = {}
        for step in steps:
            step_id = step['id']
            try:
                resources = self.db.list_step_resources(step_id)
                if resources:
                    result[step_id] = resources
            except Exception:
                pass
        return result

    def _estimate_export_size(
        self,
        workflow: dict,
        steps: list[dict],
        items: list[dict],
        resources: list[dict],
        planning_sessions: list[dict],
        runs: list[dict],
    ) -> int:
        """Estimate the export size in bytes."""
        size = 0

        # Workflow + steps JSON
        size += len(json.dumps(workflow, default=str))
        size += sum(len(json.dumps(s, default=str)) for s in steps)

        # Items JSONL
        size += sum(len(json.dumps(item, default=str)) for item in items)

        # Resources
        for r in resources:
            size += len(json.dumps(r, default=str))
            if r.get('content'):
                size += len(r['content'])

        # Planning sessions
        for ps in planning_sessions:
            size += len(json.dumps(ps, default=str))

        # Runs
        size += sum(len(json.dumps(r, default=str)) for r in runs)

        # Add overhead for ZIP compression (estimate 60% compression)
        return int(size * 0.6)

    def _scan_for_secrets(
        self,
        workflow: dict,
        resources: list[dict],
        items: list[dict],
    ) -> list[SecretMatch]:
        """Scan for potential secrets in exportable content."""
        matches: list[SecretMatch] = []

        # Compile patterns
        compiled_patterns = [(re.compile(p, re.IGNORECASE), name) for p, name in SECRET_PATTERNS]

        def scan_text(text: str, location: str) -> None:
            if not text:
                return
            for pattern, name in compiled_patterns:
                for match in pattern.finditer(text):
                    # Create redacted snippet
                    start = max(0, match.start() - 10)
                    end = min(len(text), match.end() + 10)
                    snippet = text[start:end]
                    # Redact the actual match
                    redacted = snippet[:match.start()-start] + '[REDACTED]' + snippet[match.end()-start:]
                    matches.append(SecretMatch(
                        pattern_name=name,
                        location=location,
                        snippet=redacted[:50] + '...' if len(redacted) > 50 else redacted,
                    ))

        # Scan workflow name and namespace (unlikely but check)
        scan_text(workflow.get('name', ''), 'workflow.name')

        # Scan resources
        for r in resources:
            location = f"resources.{r.get('name', 'unknown')}"
            scan_text(r.get('content', ''), location)
            scan_text(r.get('name', ''), location + '.name')

        # Scan items
        for item in items:
            location = f"items.{item.get('id', 'unknown')}"
            scan_text(item.get('content', ''), location)
            scan_text(item.get('title', ''), location + '.title')
            metadata = item.get('metadata')
            if metadata:
                scan_text(json.dumps(metadata, default=str), location + '.metadata')

        return matches

    def _build_manifest(
        self,
        workflow: dict,
        steps: list[dict],
        items: list[dict],
        resources: list[dict],
        planning_sessions: list[dict],
        runs: list[dict],
        potential_secrets: list[SecretMatch],
        options: ExportOptions,
    ) -> dict:
        """Build the manifest.json content."""
        return {
            'version': EXPORT_FORMAT_VERSION,
            'format': EXPORT_FORMAT_NAME,
            'exported_at': datetime.utcnow().isoformat() + 'Z',
            'ralphx_version': __version__,
            'schema_version': PROJECT_SCHEMA_VERSION,
            'workflow': {
                'id': workflow['id'],
                'name': workflow['name'],
                'namespace': workflow['namespace'],
                'template_id': workflow.get('template_id'),
            },
            'contents': {
                'steps': len(steps),
                'items_total': len(items),
                'resources': len(resources),
                'has_planning_session': len(planning_sessions) > 0,
                'has_runs': len(runs) > 0,
            },
            'template_metadata': {
                'is_template': options.as_template,
                'template_id': None,
                'template_version': None,
                'template_source': None,
            },
            'security': {
                'potential_secrets_detected': len(potential_secrets) > 0,
                'secrets_stripped': options.strip_secrets,
                'paths_sanitized': True,
            },
            'export_options': {
                'include_runs': options.include_runs,
                'include_planning': options.include_planning,
                'include_planning_messages': options.include_planning_messages,
                'include_step_artifacts': options.include_step_artifacts,
            },
        }

    def _serialize_workflow(
        self, workflow: dict, steps: list[dict], options: Optional[ExportOptions] = None
    ) -> dict:
        """Serialize workflow and steps for export.

        Args:
            workflow: The workflow dict.
            steps: List of step dicts.
            options: Export options (controls whether artifacts are included).
        """
        if options is None:
            options = ExportOptions()

        serialized_steps = []
        for s in steps:
            step_data = {
                'id': s['id'],
                'workflow_id': s['workflow_id'],
                'step_number': s['step_number'],
                'name': s['name'],
                'step_type': s['step_type'],
                'status': 'pending',  # Reset status
                'config': s.get('config'),
                'loop_name': s.get('loop_name'),
            }
            # Only include artifacts if explicitly requested (off by default)
            if options.include_step_artifacts:
                step_data['artifacts'] = s.get('artifacts')
            serialized_steps.append(step_data)

        return {
            'workflow': {
                'id': workflow['id'],
                'template_id': workflow.get('template_id'),
                'name': workflow['name'],
                'namespace': workflow['namespace'],
                'status': 'draft',  # Reset status on export
                'current_step': 1,  # Reset to beginning
                'created_at': workflow.get('created_at'),
                'updated_at': workflow.get('updated_at'),
            },
            'steps': serialized_steps,
        }

    def _serialize_items_jsonl(self, items: list[dict], options: ExportOptions) -> str:
        """Serialize items to JSONL format."""
        lines = []
        for item in items:
            item_data = {
                'id': item['id'],
                'workflow_id': item['workflow_id'],
                'source_step_id': item.get('source_step_id'),
                'content': item.get('content', ''),
                'title': item.get('title'),
                'priority': item.get('priority'),
                'status': 'pending',  # Reset status on export
                'category': item.get('category'),
                'tags': item.get('tags'),
                'metadata': item.get('metadata'),
                'item_type': item.get('item_type'),
                'dependencies': item.get('dependencies'),
                'phase': item.get('phase'),
                'duplicate_of': item.get('duplicate_of'),
                'created_at': item.get('created_at'),
            }

            # Strip secrets if requested
            if options.strip_secrets:
                item_data['content'] = self._strip_secrets(item_data.get('content', ''))
                item_data['title'] = self._strip_secrets(item_data.get('title', ''))

            lines.append(json.dumps(item_data, default=str))

        return '\n'.join(lines)

    def _serialize_resources(self, resources: list[dict], options: ExportOptions) -> list[dict]:
        """Serialize workflow resources."""
        result = []
        for r in resources:
            content = r.get('content', '')

            # If content is empty but file_path exists, read the file
            if not content and r.get('file_path'):
                try:
                    file_path = Path(r['file_path'])
                    if file_path.exists() and file_path.is_file():
                        content = file_path.read_text(encoding='utf-8')
                except Exception:
                    # If file read fails, leave content empty
                    pass

            if options.strip_secrets:
                content = self._strip_secrets(content)

            result.append({
                'id': r['id'],
                'workflow_id': r['workflow_id'],
                'resource_type': r['resource_type'],
                'name': r['name'],
                'content': content,
                'file_path': None,  # Don't export file paths, inline content instead
                'source': r.get('source'),
                'enabled': r.get('enabled', True),
            })
        return result

    def _serialize_step_resources(
        self,
        step_resources: dict[int, list[dict]],
        options: ExportOptions,
    ) -> dict:
        """Serialize step-level resources."""
        result: dict[str, list[dict]] = {}
        for step_id, resources in step_resources.items():
            serialized = []
            for r in resources:
                content = r.get('content', '')

                # If content is empty but file_path exists, read the file
                if not content and r.get('file_path'):
                    try:
                        file_path = Path(r['file_path'])
                        if file_path.exists() and file_path.is_file():
                            content = file_path.read_text(encoding='utf-8')
                    except Exception:
                        # If file read fails, leave content empty
                        pass

                if options.strip_secrets:
                    content = self._strip_secrets(content)

                serialized.append({
                    'id': r['id'],
                    'step_id': r['step_id'],
                    'workflow_resource_id': r.get('workflow_resource_id'),
                    'resource_type': r.get('resource_type'),
                    'name': r.get('name'),
                    'content': content,
                    'file_path': None,
                    'mode': r.get('mode'),
                    'enabled': r.get('enabled', True),
                    'priority': r.get('priority', 0),
                })
            result[str(step_id)] = serialized
        return result

    def _serialize_planning_sessions(
        self,
        sessions: list[dict],
        include_messages: bool,
    ) -> list[dict]:
        """Serialize planning sessions."""
        result = []
        for s in sessions:
            data = {
                'id': s['id'],
                'workflow_id': s['workflow_id'],
                'step_id': s['step_id'],
                'artifacts': s.get('artifacts'),
                'status': s.get('status'),
                'created_at': s.get('created_at'),
            }
            if include_messages:
                data['messages'] = s.get('messages', [])
            result.append(data)
        return result

    def _serialize_runs(self, runs: list[dict]) -> list[dict]:
        """Serialize run history."""
        return [
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
                'error_message': r.get('error_message'),
            }
            for r in runs
        ]

    def _strip_secrets(self, text: Optional[str]) -> str:
        """Strip potential secrets from text."""
        if not text:
            return ''

        result = text
        for pattern, _ in SECRET_PATTERNS:
            result = re.sub(pattern, '[REDACTED]', result, flags=re.IGNORECASE)

        return result
