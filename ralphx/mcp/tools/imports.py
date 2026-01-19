"""Import MCP tools.

Tools for importing data:
- ralphx_import_paste: Import pasted content
- ralphx_import_jsonl: Bulk import work items
- ralphx_list_loop_inputs: List input files
- ralphx_list_input_templates: List input templates
- ralphx_apply_input_template: Apply template
"""

import re
from pathlib import Path
from typing import Optional

from ralphx.mcp.base import (
    MCPError,
    PaginatedResult,
    ToolDefinition,
    ToolError,
    make_schema,
    prop_enum,
    prop_int,
    prop_string,
    validate_pagination,
)
from ralphx.mcp.tools.projects import get_manager


# Safe filename pattern: alphanumeric, underscores, dashes, dots (no path separators)
SAFE_FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._-]*$')

# Safe identifier pattern: alphanumeric, underscores, dashes (for loop_name, etc.)
SAFE_IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$')


def _validate_safe_filename(filename: str) -> bool:
    """Validate that a filename is safe (no path traversal).

    Args:
        filename: The filename to validate.

    Returns:
        True if safe, False if contains path traversal or invalid characters.
    """
    if not filename:
        return False
    # Reject path separators and parent directory references
    if '/' in filename or '\\' in filename or '..' in filename:
        return False
    # Must match safe pattern
    return bool(SAFE_FILENAME_PATTERN.match(filename))


def _validate_safe_identifier(identifier: str) -> bool:
    """Validate that an identifier (loop_name, etc.) is safe.

    Args:
        identifier: The identifier to validate.

    Returns:
        True if safe, False if contains path traversal or invalid characters.
    """
    if not identifier:
        return False
    # Reject path separators and parent directory references
    if '/' in identifier or '\\' in identifier or '..' in identifier:
        return False
    # Must match safe pattern
    return bool(SAFE_IDENTIFIER_PATTERN.match(identifier))


def _validate_path_within_project(file_path: str, project_path: Path) -> Path:
    """Validate that a file path resolves to within the project directory.

    Args:
        file_path: User-provided file path (absolute or relative).
        project_path: The project's root directory.

    Returns:
        Resolved Path object if valid.

    Raises:
        ToolError: If path traversal is detected or path is outside project.
    """
    file_path_obj = Path(file_path)

    # If relative, resolve relative to project
    if not file_path_obj.is_absolute():
        file_path_obj = project_path / file_path

    # Resolve to absolute path (handles .., symlinks)
    try:
        resolved = file_path_obj.resolve()
    except (OSError, ValueError) as e:
        raise ToolError.validation_error(f"Invalid file path: {e}")

    # Ensure the resolved path is within project directory
    try:
        resolved.relative_to(project_path.resolve())
    except ValueError:
        raise ToolError.validation_error(
            f"Path traversal detected: file must be within project directory",
            {"file_path": file_path},
        )

    return resolved


def import_paste(
    slug: str,
    workflow_id: str,
    source_step_id: int,
    content: str,
    format_type: str = "auto",
    category: Optional[str] = None,
) -> dict:
    """Import work items from pasted content.

    Parses the content and creates work items. Supports:
    - Plain text (one item per line)
    - Markdown lists
    - JSON arrays
    - Numbered lists

    Args:
        slug: Project slug
        workflow_id: Target workflow
        source_step_id: Target step
        content: Content to parse and import
        format_type: Format type (auto, text, markdown, json)
        category: Optional category for imported items
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    # Verify workflow exists
    workflow = project_db.get_workflow(workflow_id)
    if not workflow:
        raise ToolError.workflow_not_found(workflow_id)

    # Verify step exists
    step = project_db.get_workflow_step(source_step_id)
    if not step:
        raise ToolError.step_not_found(source_step_id)

    try:
        from ralphx.core.import_manager import ImportManager

        im = ImportManager(project.path, project_db)
        result = im.import_paste(
            workflow_id=workflow_id,
            source_step_id=source_step_id,
            content=content,
            format_type=format_type,
            category=category,
        )

        return {
            "imported": result.get("imported", 0),
            "skipped": result.get("skipped", 0),
            "errors": result.get("errors", []),
            "items": result.get("items", [])[:10],  # Limit preview
            "message": f"Imported {result.get('imported', 0)} items",
        }
    except ImportError:
        # Fallback: basic parsing
        import uuid

        lines = content.strip().split("\n")
        items = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Remove common prefixes
            for prefix in ["- ", "* ", "• "]:
                if line.startswith(prefix):
                    line = line[len(prefix):]
                    break

            # Remove numbered list prefix
            import re
            line = re.sub(r"^\d+\.\s*", "", line)

            if line:
                item_id = str(uuid.uuid4())[:8]
                project_db.create_work_item(
                    id=item_id,
                    workflow_id=workflow_id,
                    source_step_id=source_step_id,
                    content=line,
                    category=category,
                )
                items.append({"id": item_id, "content": line[:100]})

        return {
            "imported": len(items),
            "skipped": 0,
            "errors": [],
            "items": items[:10],
            "message": f"Imported {len(items)} items",
        }
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Import failed: {e}",
            details={"workflow_id": workflow_id},
        )


def import_jsonl(
    slug: str,
    workflow_id: str,
    source_step_id: int,
    file_path: str,
    format_id: Optional[str] = None,
) -> dict:
    """Bulk import work items from JSONL file.

    Each line should be a JSON object with at least a 'content' field.
    Optional fields: title, category, priority, tags, metadata.

    Args:
        slug: Project slug
        workflow_id: Target workflow
        source_step_id: Target step
        file_path: Path to JSONL file
        format_id: Optional import format ID
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    project_db = manager.get_project_db(project.path)

    # Verify workflow exists
    workflow = project_db.get_workflow(workflow_id)
    if not workflow:
        raise ToolError.workflow_not_found(workflow_id)

    # Verify step exists
    step = project_db.get_workflow_step(source_step_id)
    if not step:
        raise ToolError.step_not_found(source_step_id)

    # SECURITY: Validate path is within project directory BEFORE any file operations
    validated_path = _validate_path_within_project(file_path, Path(project.path))

    try:
        from ralphx.core.import_manager import ImportManager

        im = ImportManager(project.path, project_db)
        result = im.import_jsonl(
            workflow_id=workflow_id,
            source_step_id=source_step_id,
            file_path=str(validated_path),  # Use validated path
            format_id=format_id,
        )

        return {
            "imported": result.get("imported", 0),
            "skipped": result.get("skipped", 0),
            "errors": result.get("errors", [])[:10],  # Limit errors
            "message": f"Imported {result.get('imported', 0)} items from {file_path}",
        }
    except ImportError:
        # Fallback: basic JSONL parsing
        import json
        import uuid

        # Path already validated above, use validated_path
        if not validated_path.exists():
            raise ToolError.validation_error(f"File not found: {file_path}")

        imported = 0
        errors = []

        with open(validated_path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    content = data.get("content")
                    if not content:
                        errors.append(f"Line {line_num}: missing 'content' field")
                        continue

                    item_id = str(uuid.uuid4())[:8]
                    project_db.create_work_item(
                        id=item_id,
                        workflow_id=workflow_id,
                        source_step_id=source_step_id,
                        content=content,
                        title=data.get("title"),
                        category=data.get("category"),
                        priority=data.get("priority", 0),
                        tags=data.get("tags"),
                        metadata=data.get("metadata"),
                    )
                    imported += 1
                except json.JSONDecodeError as e:
                    errors.append(f"Line {line_num}: invalid JSON - {e}")

        return {
            "imported": imported,
            "skipped": 0,
            "errors": errors[:10],
            "message": f"Imported {imported} items from {file_path}",
        }
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Import failed: {e}",
            details={"file_path": file_path},
        )


def list_loop_inputs(
    slug: str,
    loop_name: str,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List input files for a loop."""
    limit, offset = validate_pagination(limit, offset)

    # SECURITY: Validate loop_name to prevent path traversal
    if not _validate_safe_identifier(loop_name):
        raise ToolError.validation_error(
            "Invalid loop_name: must be alphanumeric with underscores/dashes",
            {"loop_name": loop_name},
        )

    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    try:
        from ralphx.core.import_manager import ImportManager

        project_db = manager.get_project_db(project.path)
        im = ImportManager(project.path, project_db)
        inputs = im.list_loop_inputs(loop_name=loop_name)

        total = len(inputs)
        paginated = inputs[offset : offset + limit]

        return PaginatedResult(
            items=[
                {
                    "path": i.get("path"),
                    "name": i.get("name"),
                    "format": i.get("format"),
                    "size_bytes": i.get("size_bytes"),
                    "item_count": i.get("item_count"),
                }
                for i in paginated
            ],
            total=total,
            limit=limit,
            offset=offset,
        ).to_dict()
    except ImportError:
        # Fallback: scan filesystem
        inputs_dir = Path(project.path) / ".ralphx" / "inputs" / loop_name
        inputs = []

        if inputs_dir.exists():
            for f in inputs_dir.iterdir():
                if f.is_file() and f.suffix in [".jsonl", ".json", ".txt", ".md"]:
                    inputs.append({
                        "path": str(f.relative_to(project.path)),
                        "name": f.name,
                        "format": f.suffix[1:],
                        "size_bytes": f.stat().st_size,
                    })

        total = len(inputs)
        paginated = inputs[offset : offset + limit]

        return PaginatedResult(
            items=paginated,
            total=total,
            limit=limit,
            offset=offset,
        ).to_dict()
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to list inputs: {e}",
            details={"loop_name": loop_name},
        )


def list_input_templates(slug: str) -> dict:
    """List available input file templates."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    try:
        from ralphx.core.import_manager import list_input_templates

        templates = list_input_templates()

        return {
            "templates": [
                {
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "description": t.get("description", ""),
                    "format": t.get("format"),
                    "example": t.get("example", "")[:200],
                }
                for t in templates
            ],
            "total": len(templates),
        }
    except ImportError:
        # Fallback: return built-in templates
        templates = [
            {
                "id": "user-stories",
                "name": "User Stories",
                "description": "User stories in standard format",
                "format": "jsonl",
                "example": '{"content": "As a user, I want to...", "category": "feature"}',
            },
            {
                "id": "bugs",
                "name": "Bug Reports",
                "description": "Bug report format",
                "format": "jsonl",
                "example": '{"content": "Bug description", "category": "bug", "priority": 2}',
            },
            {
                "id": "tasks",
                "name": "Tasks",
                "description": "Simple task list",
                "format": "txt",
                "example": "- Task 1\n- Task 2",
            },
        ]
        return {
            "templates": templates,
            "total": len(templates),
        }
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to list templates: {e}",
            details={"slug": slug},
        )


def apply_input_template(
    slug: str,
    loop_name: str,
    template_id: str,
    output_name: Optional[str] = None,
) -> dict:
    """Apply an input template to create a new input file.

    Creates a template file that can be edited and then imported.

    Args:
        slug: Project slug
        loop_name: Loop to create input for
        template_id: Template ID to use
        output_name: Optional custom output filename
    """
    # SECURITY: Validate loop_name to prevent path traversal
    if not _validate_safe_identifier(loop_name):
        raise ToolError.validation_error(
            "Invalid loop_name: must be alphanumeric with underscores/dashes",
            {"loop_name": loop_name},
        )

    # SECURITY: Validate output_name if provided
    if output_name and not _validate_safe_filename(output_name):
        raise ToolError.validation_error(
            "Invalid output_name: must be a safe filename without path separators",
            {"output_name": output_name},
        )

    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    try:
        from ralphx.core.import_manager import ImportManager

        project_db = manager.get_project_db(project.path)
        im = ImportManager(project.path, project_db)
        result = im.apply_template(
            loop_name=loop_name,
            template_id=template_id,
            output_name=output_name,
        )

        return {
            "created": True,
            "path": result.get("path"),
            "template_id": template_id,
            "message": f"Created input file from template '{template_id}'",
        }
    except ImportError:
        # Fallback: create basic template
        inputs_dir = Path(project.path) / ".ralphx" / "inputs" / loop_name
        inputs_dir.mkdir(parents=True, exist_ok=True)

        templates = {
            "user-stories": (
                "input.jsonl",
                '{"content": "As a user, I want to [action] so that [benefit]", "category": "feature"}\n'
                '{"content": "As an admin, I want to [action] so that [benefit]", "category": "feature"}\n',
            ),
            "bugs": (
                "bugs.jsonl",
                '{"content": "Bug: [description]", "category": "bug", "priority": 2}\n',
            ),
            "tasks": (
                "tasks.txt",
                "# Task List\n# One task per line\n\n- First task\n- Second task\n",
            ),
        }

        if template_id not in templates:
            raise ToolError.validation_error(f"Unknown template: {template_id}")

        default_name, content = templates[template_id]
        filename = output_name or default_name
        output_path = inputs_dir / filename

        with open(output_path, "w") as f:
            f.write(content)

        return {
            "created": True,
            "path": str(output_path.relative_to(project.path)),
            "template_id": template_id,
            "message": f"Created input file from template '{template_id}'",
        }
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to apply template: {e}",
            details={"template_id": template_id},
        )


def get_import_tools() -> list[ToolDefinition]:
    """Get all import tool definitions."""
    return [
        ToolDefinition(
            name="ralphx_import_paste",
            description="Import work items from pasted content (text, markdown, JSON)",
            handler=import_paste,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "workflow_id": prop_string("Target workflow ID"),
                    "source_step_id": prop_int("Target step ID"),
                    "content": prop_string("Content to parse and import"),
                    "format_type": prop_enum("Format type", ["auto", "text", "markdown", "json"]),
                    "category": prop_string("Category for imported items"),
                },
                required=["slug", "workflow_id", "source_step_id", "content"],
            ),
        ),
        ToolDefinition(
            name="ralphx_import_jsonl",
            description="Bulk import work items from JSONL file",
            handler=import_jsonl,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "workflow_id": prop_string("Target workflow ID"),
                    "source_step_id": prop_int("Target step ID"),
                    "file_path": prop_string("Path to JSONL file"),
                    "format_id": prop_string("Import format ID (optional)"),
                },
                required=["slug", "workflow_id", "source_step_id", "file_path"],
            ),
        ),
        ToolDefinition(
            name="ralphx_list_loop_inputs",
            description="List input files available for a loop",
            handler=list_loop_inputs,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "loop_name": prop_string("Loop name"),
                    "limit": prop_int("Max inputs to return (1-500)", minimum=1, maximum=500),
                    "offset": prop_int("Number of inputs to skip", minimum=0),
                },
                required=["slug", "loop_name"],
            ),
        ),
        ToolDefinition(
            name="ralphx_list_input_templates",
            description="List available input file templates",
            handler=list_input_templates,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_apply_input_template",
            description="Create a new input file from a template",
            handler=apply_input_template,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "loop_name": prop_string("Loop name"),
                    "template_id": prop_string("Template ID to use"),
                    "output_name": prop_string("Custom output filename"),
                },
                required=["slug", "loop_name", "template_id"],
            ),
        ),
    ]
