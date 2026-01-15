"""Project models for RalphX."""

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


def generate_slug(name: str) -> str:
    """Generate a URL-friendly slug from a project name.

    Args:
        name: Human-readable project name.

    Returns:
        Lowercase slug with only alphanumeric chars and hyphens.

    Examples:
        >>> generate_slug("My SaaS App")
        'my-saas-app'
        >>> generate_slug("Frontend (v2)")
        'frontend-v2'
    """
    # Convert to lowercase
    slug = name.lower()
    # Replace spaces and underscores with hyphens
    slug = re.sub(r"[\s_]+", "-", slug)
    # Remove non-alphanumeric characters except hyphens
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug)
    # Strip leading/trailing hyphens
    slug = slug.strip("-")
    return slug or "project"


class ProjectCreate(BaseModel):
    """Model for creating a new project."""

    name: str = Field(..., min_length=1, max_length=100)
    path: Path = Field(..., description="Absolute path to project directory")
    design_doc: Optional[str] = Field(
        None, description="Path to design document (relative to project)"
    )
    slug: Optional[str] = Field(
        None,
        description="URL-friendly identifier (auto-generated if not provided)",
        pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$",
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: Path) -> Path:
        """Validate path exists and is a directory."""
        if not v.is_absolute():
            raise ValueError("Path must be absolute")
        if not v.exists():
            raise ValueError(f"Path does not exist: {v}")
        if not v.is_dir():
            raise ValueError(f"Path is not a directory: {v}")
        return v

    @model_validator(mode="after")
    def generate_slug_if_missing(self) -> "ProjectCreate":
        """Generate slug from name if not provided."""
        if self.slug is None:
            self.slug = generate_slug(self.name)
        return self

    def to_project(self) -> "Project":
        """Convert to full Project with generated ID."""
        return Project(
            id=str(uuid.uuid4()),
            slug=self.slug,
            name=self.name,
            path=self.path,
            design_doc=self.design_doc,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )


class Project(BaseModel):
    """Full project model with all fields."""

    id: str = Field(..., description="Unique project identifier (UUID)")
    slug: str = Field(
        ...,
        description="URL-friendly identifier",
        pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$",
    )
    name: str = Field(..., min_length=1, max_length=100)
    path: Path = Field(..., description="Absolute path to project directory")
    design_doc: Optional[str] = Field(None, description="Path to design document")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}

    @property
    def design_doc_path(self) -> Optional[Path]:
        """Get absolute path to design document."""
        if self.design_doc:
            return self.path / self.design_doc
        return None

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "path": str(self.path),
            "design_doc": self.design_doc,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        """Create from dictionary (e.g., database row)."""
        return cls(
            id=data["id"],
            slug=data["slug"],
            name=data["name"],
            path=Path(data["path"]),
            design_doc=data.get("design_doc"),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if isinstance(data["created_at"], str)
                else data["created_at"]
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if isinstance(data["updated_at"], str)
                else data["updated_at"]
            ),
        )
