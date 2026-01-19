"""Guardrails MCP tools.

Tools for managing guardrails:
- ralphx_list_guardrails: List all guardrails
- ralphx_detect_guardrails: Detect AI instruction files
- ralphx_validate_guardrails: Validate configuration
- ralphx_preview_guardrails: Preview assembled guardrails
- ralphx_list_guardrail_templates: List templates
- ralphx_create_guardrail_from_template: Create from template
"""

from typing import Optional

from ralphx.mcp.base import (
    MCPError,
    ToolDefinition,
    ToolError,
    make_schema,
    prop_bool,
    prop_enum,
    prop_string,
)
from ralphx.mcp.tools.projects import get_manager


def list_guardrails(slug: str) -> dict:
    """List all guardrails configured for a project."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    try:
        from ralphx.core.guardrails import GuardrailsManager

        gm = GuardrailsManager(project.path)
        guardrails = gm.list_guardrails()

        return {
            "guardrails": [
                {
                    "name": g.get("name"),
                    "type": g.get("type"),
                    "path": g.get("path"),
                    "enabled": g.get("enabled", True),
                    "priority": g.get("priority", 0),
                }
                for g in guardrails
            ],
            "total": len(guardrails),
        }
    except ImportError:
        return {
            "guardrails": [],
            "total": 0,
            "message": "Guardrails module not available",
        }
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to list guardrails: {e}",
            details={"slug": slug},
        )


def detect_guardrails(slug: str) -> dict:
    """Detect AI instruction files in the project.

    Scans for common AI instruction file patterns:
    - CLAUDE.md, .claude/*, .cursorrules, etc.
    - Custom instruction files in .ralphx/
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    try:
        from pathlib import Path as PathLib
        from ralphx.core.guardrails import GuardrailDetector

        detector = GuardrailDetector(PathLib(project.path))
        report = detector.detect()

        detected = []
        for item in report.detected_files:
            detected.append({
                "path": str(item.path) if hasattr(item, "path") else str(item),
                "type": getattr(item, "file_type", "guardrail"),
                "source": getattr(item, "source", None),
                "size_bytes": getattr(item, "size", 0),
            })

        return {
            "detected": detected,
            "total": len(detected),
            "sources": list(set(d.get("source") for d in detected if d.get("source"))),
            "warnings": report.warnings,
            "is_cloned_repo": report.is_cloned_repo,
        }
    except ImportError:
        # Fallback: manual detection
        import os
        from pathlib import Path

        project_path = Path(project.path)
        detected = []

        # Common AI instruction files
        patterns = [
            "CLAUDE.md",
            ".claude/*",
            ".cursorrules",
            ".cursor/rules",
            ".github/copilot-instructions.md",
            "AGENTS.md",
            ".ralphx/guardrails/*",
        ]

        for pattern in patterns:
            if "*" in pattern:
                base, _ = pattern.rsplit("/", 1)
                base_path = project_path / base
                if base_path.exists():
                    for f in base_path.iterdir():
                        if f.is_file():
                            detected.append({
                                "path": str(f.relative_to(project_path)),
                                "type": "guardrail",
                                "source": base.strip("."),
                            })
            else:
                file_path = project_path / pattern
                if file_path.exists():
                    detected.append({
                        "path": pattern,
                        "type": "guardrail",
                        "source": pattern.split("/")[0].strip(".") or "root",
                    })

        return {
            "detected": detected,
            "total": len(detected),
        }
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to detect guardrails: {e}",
            details={"slug": slug},
        )


def validate_guardrails(slug: str) -> dict:
    """Validate guardrail configuration.

    Checks:
    - Syntax validity
    - Required sections
    - Circular references
    - File existence
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    try:
        from ralphx.core.guardrails import GuardrailsManager

        gm = GuardrailsManager(project.path)
        result = gm.validate()

        return {
            "valid": result.get("valid", False),
            "errors": result.get("errors", []),
            "warnings": result.get("warnings", []),
            "guardrail_count": result.get("guardrail_count", 0),
        }
    except ImportError:
        return {
            "valid": True,
            "errors": [],
            "warnings": ["Guardrails module not available for validation"],
            "guardrail_count": 0,
        }
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Validation failed: {e}",
            details={"slug": slug},
        )


def preview_guardrails(
    slug: str,
    loop_name: Optional[str] = None,
    mode: Optional[str] = None,
) -> dict:
    """Preview assembled guardrails for a loop/mode.

    Shows the final guardrails content that would be injected
    into Claude's context for a specific loop and mode.
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    try:
        from ralphx.core.guardrails import GuardrailsManager

        gm = GuardrailsManager(project.path)
        preview = gm.preview(loop_name=loop_name, mode=mode)

        # Truncate if too long
        content = preview.get("content", "")
        if len(content) > 10000:
            content = content[:10000] + "\n... [truncated]"

        return {
            "loop_name": loop_name,
            "mode": mode,
            "content": content,
            "sources": preview.get("sources", []),
            "total_length": len(preview.get("content", "")),
        }
    except ImportError:
        return {
            "content": "",
            "message": "Guardrails module not available for preview",
        }
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Preview failed: {e}",
            details={"slug": slug},
        )


def list_guardrail_templates(slug: str) -> dict:
    """List available guardrail templates."""
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    try:
        from ralphx.core.guardrails import list_templates

        templates = list_templates()

        return {
            "templates": [
                {
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "description": t.get("description", ""),
                    "category": t.get("category"),
                }
                for t in templates
            ],
            "total": len(templates),
        }
    except ImportError:
        # Fallback: return built-in templates
        templates = [
            {"id": "default", "name": "Default", "description": "Basic guardrails", "category": "general"},
            {"id": "research", "name": "Research Mode", "description": "Read-only research guardrails", "category": "mode"},
            {"id": "implementation", "name": "Implementation Mode", "description": "Code modification guardrails", "category": "mode"},
            {"id": "security", "name": "Security Focus", "description": "Security-focused guardrails", "category": "security"},
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


def create_guardrail_from_template(
    slug: str,
    template_id: str,
    name: Optional[str] = None,
    customize: bool = False,
) -> dict:
    """Create a guardrail from a template.

    Args:
        slug: Project slug
        template_id: Template ID to use
        name: Custom name for the guardrail
        customize: If True, create editable copy; if False, reference template
    """
    manager = get_manager()
    project = manager.get_project(slug)

    if not project:
        raise ToolError.project_not_found(slug)

    try:
        from ralphx.core.guardrails import GuardrailsManager

        gm = GuardrailsManager(project.path)
        result = gm.create_from_template(
            template_id=template_id,
            name=name,
            customize=customize,
        )

        return {
            "created": True,
            "name": result.get("name"),
            "path": result.get("path"),
            "customized": customize,
            "message": f"Guardrail created from template '{template_id}'",
        }
    except ImportError:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message="Guardrails module not available",
            details={"slug": slug},
        )
    except ValueError as e:
        raise ToolError.validation_error(str(e))
    except Exception as e:
        raise MCPError(
            error_code=ToolError.INTERNAL_ERROR,
            message=f"Failed to create guardrail: {e}",
            details={"template_id": template_id},
        )


def get_guardrails_tools() -> list[ToolDefinition]:
    """Get all guardrails tool definitions."""
    return [
        ToolDefinition(
            name="ralphx_list_guardrails",
            description="List all guardrails configured for a project",
            handler=list_guardrails,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_detect_guardrails",
            description="Detect AI instruction files in the project (CLAUDE.md, .cursorrules, etc.)",
            handler=detect_guardrails,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_validate_guardrails",
            description="Validate guardrail configuration for errors and warnings",
            handler=validate_guardrails,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_preview_guardrails",
            description="Preview assembled guardrails content for a specific loop/mode",
            handler=preview_guardrails,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "loop_name": prop_string("Loop name (optional)"),
                    "mode": prop_string("Mode name (optional)"),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_list_guardrail_templates",
            description="List available guardrail templates",
            handler=list_guardrail_templates,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                },
                required=["slug"],
            ),
        ),
        ToolDefinition(
            name="ralphx_create_guardrail_from_template",
            description="Create a new guardrail from a template",
            handler=create_guardrail_from_template,
            input_schema=make_schema(
                properties={
                    "slug": prop_string("Project slug"),
                    "template_id": prop_string("Template ID to use"),
                    "name": prop_string("Custom name for the guardrail"),
                    "customize": prop_bool("Create editable copy vs reference template"),
                },
                required=["slug", "template_id"],
            ),
        ),
    ]
