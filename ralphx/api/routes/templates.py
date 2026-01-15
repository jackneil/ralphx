"""Template API routes.

Templates are global, read-only, and shipped with RalphX.
No authentication required - templates are public.

Includes:
- Loop templates (research, implementation, etc.)
- Loop builder templates (planning, implementation with Phase 1)
- Permission templates (planning, implementation, read_only, etc.)
"""

from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ralphx.core.templates import get_template, get_template_config, list_templates
from ralphx.core.loop_templates import (
    create_loop_from_template,
    get_loop_template,
    list_loop_templates,
)
from ralphx.core.permission_templates import (
    apply_template_to_loop,
    get_template as get_permission_template,
    list_templates as list_permission_templates,
)
from ralphx.core.project import ProjectManager

router = APIRouter()


class TemplateListItem(BaseModel):
    """Template metadata for listing."""

    name: str
    display_name: str
    description: str
    type: str
    category: str


class TemplateDetail(BaseModel):
    """Full template with config."""

    name: str
    display_name: str
    description: str
    type: str
    category: str
    config: dict
    config_yaml: str


class TemplateListResponse(BaseModel):
    """Response for listing templates."""

    templates: list[TemplateListItem]


class TemplateYamlResponse(BaseModel):
    """Response for YAML config endpoint."""

    yaml: str


@router.get("/templates", response_model=TemplateListResponse)
async def list_all_templates() -> TemplateListResponse:
    """List all available templates.

    No authentication required - templates are public.
    """
    templates = list_templates()
    return TemplateListResponse(
        templates=[TemplateListItem(**t) for t in templates]
    )


@router.get("/templates/{name}", response_model=TemplateDetail)
async def get_template_by_name(name: str) -> TemplateDetail:
    """Get a specific template by name.

    No authentication required - templates are public.

    Args:
        name: Template name (e.g., 'research', 'implementation')

    Returns:
        Full template with config and YAML representation
    """
    template = get_template(name)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{name}' not found",
        )

    config = template["config"]
    config_yaml = yaml.dump(
        config,
        indent=2,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )

    return TemplateDetail(
        name=template["name"],
        display_name=template["display_name"],
        description=template["description"],
        type=template["type"],
        category=template["category"],
        config=config,
        config_yaml=config_yaml,
    )


@router.get("/templates/{name}/yaml", response_model=TemplateYamlResponse)
async def get_template_yaml(name: str) -> TemplateYamlResponse:
    """Get just the YAML config for a template.

    Convenient endpoint for directly getting the YAML to paste into loop builder.

    Args:
        name: Template name

    Returns:
        Dict with yaml field containing the YAML string
    """
    config = get_template_config(name)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{name}' not found",
        )

    config_yaml = yaml.dump(
        config,
        indent=2,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )

    return TemplateYamlResponse(yaml=config_yaml)


# ============================================================================
# Loop Builder Templates (planning, implementation with Phase 1)
# ============================================================================


class LoopTemplateInfo(BaseModel):
    """Loop builder template information."""

    id: str
    name: str
    description: str


class LoopTemplateDetail(BaseModel):
    """Detailed loop template with config and prompts."""

    id: str
    name: str
    description: str
    config: str
    prompts: dict[str, str]
    permission_template: Optional[str] = None


class CreateFromTemplateRequest(BaseModel):
    """Request to create a loop from a template."""

    loop_name: str = Field(..., description="Name for the new loop", max_length=100)
    template_id: str = Field(..., description="Template ID to use", max_length=100)
    display_name: Optional[str] = Field(None, description="Optional custom display name", max_length=200)

    @field_validator("loop_name")
    @classmethod
    def validate_loop_name(cls, v: str) -> str:
        """Validate loop_name is safe (no path traversal)."""
        import re
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Loop name must use only letters, numbers, underscores, and hyphens")
        return v


@router.get("/loop-templates", response_model=list[LoopTemplateInfo])
async def list_loop_templates_endpoint():
    """List all available loop builder templates.

    These are specialized templates for creating loops with
    pre-configured prompts and permission settings.
    """
    templates = list_loop_templates()
    return [LoopTemplateInfo(**t) for t in templates]


@router.get("/loop-templates/{template_id}", response_model=LoopTemplateDetail)
async def get_loop_template_endpoint(template_id: str):
    """Get details for a specific loop builder template."""
    template = get_loop_template(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop template not found: {template_id}",
        )

    return LoopTemplateDetail(
        id=template_id,
        name=template["name"],
        description=template["description"],
        config=template["config"],
        prompts=template["prompts"],
        permission_template=template.get("permission_template"),
    )


@router.post("/projects/{slug}/loops/from-template")
async def create_loop_from_template_endpoint(
    slug: str, request: CreateFromTemplateRequest
):
    """Create a new loop from a builder template.

    This creates the loop directory structure with config file, prompts,
    and permission settings, then syncs to the database.
    """
    import re

    from ralphx.core.loop import LoopLoader

    # Validate loop name
    if not re.match(r"^[a-zA-Z0-9_-]+$", request.loop_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid loop name. Use only letters, numbers, underscores, and hyphens.",
        )

    # Get project
    manager = ProjectManager()
    project = manager.get_project(slug)

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )

    # Check template exists
    template = get_loop_template(request.template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Loop template not found: {request.template_id}",
        )

    # Check loop doesn't already exist
    loops_dir = Path(project.path) / ".ralphx" / "loops"
    if (loops_dir / request.loop_name).exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Loop '{request.loop_name}' already exists",
        )

    try:
        # Create loop from template
        loop_dir = create_loop_from_template(
            project_path=project.path,
            loop_name=request.loop_name,
            template_id=request.template_id,
            custom_name=request.display_name,
        )

        # Sync to database
        project_db = manager.get_project_db(project.path)
        loader = LoopLoader(db=project_db)
        loader.sync_loops(project)

        return {
            "message": f"Loop '{request.loop_name}' created from template '{request.template_id}'",
            "loop_name": request.loop_name,
            "loop_dir": str(loop_dir),
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except FileExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


# ============================================================================
# Permission Templates
# ============================================================================


class PermissionTemplateInfo(BaseModel):
    """Permission template information."""

    id: str
    name: str
    description: str


class PermissionTemplateDetail(BaseModel):
    """Detailed permission template with settings."""

    id: str
    name: str
    description: str
    settings: dict


class ApplyPermissionRequest(BaseModel):
    """Request to apply permission template to a loop."""

    template_id: str = Field(..., description="Permission template ID")


@router.get("/permission-templates", response_model=list[PermissionTemplateInfo])
async def list_permission_templates_endpoint():
    """List all available permission templates.

    Permission templates define Claude Code tool access for loops.
    """
    templates = list_permission_templates()
    return [PermissionTemplateInfo(**t) for t in templates]


@router.get("/permission-templates/{template_id}", response_model=PermissionTemplateDetail)
async def get_permission_template_endpoint(template_id: str):
    """Get details for a specific permission template."""
    template = get_permission_template(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Permission template not found: {template_id}",
        )

    return PermissionTemplateDetail(
        id=template_id,
        name=template["name"],
        description=template["description"],
        settings=template["settings"],
    )


@router.post("/projects/{slug}/loops/{loop_name}/apply-permissions")
async def apply_permission_template_endpoint(
    slug: str, loop_name: str, request: ApplyPermissionRequest
):
    """Apply a permission template to a loop.

    This creates/updates the settings.json file in the loop directory.
    """
    import re

    # Validate loop name
    if not re.match(r"^[a-zA-Z0-9_-]+$", loop_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid loop name",
        )

    # Get project
    manager = ProjectManager()
    project = manager.get_project(slug)

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {slug}",
        )

    # Check template exists
    template = get_permission_template(request.template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Permission template not found: {request.template_id}",
        )

    try:
        settings_path = apply_template_to_loop(
            project_path=project.path,
            loop_name=loop_name,
            template_id=request.template_id,
        )

        return {
            "message": f"Applied permission template '{request.template_id}' to loop '{loop_name}'",
            "settings_path": str(settings_path),
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
