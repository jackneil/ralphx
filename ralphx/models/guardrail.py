"""Guardrail models for RalphX."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class GuardrailCategory(str, Enum):
    """Category of guardrail for prompt positioning."""

    SYSTEM = "system"       # Before design_doc
    SAFETY = "safety"       # At start of prompt
    DOMAIN = "domain"       # After design_doc
    OUTPUT = "output"       # At end of prompt
    CUSTOM = "custom"       # After design_doc


class GuardrailSource(str, Enum):
    """Source/origin of the guardrail file."""

    GLOBAL = "global"               # ~/.ralphx/guardrails/
    WORKSPACE = "workspace"         # ~/.ralphx/projects/{slug}/guardrails/
    PROJECT = "project"             # Project repo .ralphx/guardrails/
    LOOP = "loop"                   # Loop/mode-level overrides
    REPO = "repo"                   # Alias for PROJECT (deprecated)
    AUTO_DETECTED = "auto-detected" # Detected AI instruction files


class GuardrailPosition(str, Enum):
    """Position in the assembled prompt."""

    BEFORE_DESIGN_DOC = "before_design_doc"
    AFTER_DESIGN_DOC = "after_design_doc"
    START_OF_PROMPT = "start_of_prompt"
    END_OF_PROMPT = "end_of_prompt"


class Guardrail(BaseModel):
    """Model for guardrail metadata."""

    id: Optional[int] = Field(None, description="Database ID")
    project_id: Optional[str] = Field(
        None, description="Project ID (null for global guardrails)"
    )
    category: GuardrailCategory = Field(..., description="Guardrail category")
    filename: str = Field(..., min_length=1, description="Filename (e.g., 'never-do.md')")
    source: GuardrailSource = Field(..., description="Where the guardrail came from")
    file_path: str = Field(..., description="Absolute filesystem path")
    file_mtime: Optional[float] = Field(None, description="File modification time")
    file_size: Optional[int] = Field(None, ge=0, description="File size in bytes")
    enabled: bool = Field(True, description="Whether this guardrail is active")
    loops: Optional[list[str]] = Field(
        None, description="Loops this applies to (null = all)"
    )
    modes: Optional[list[str]] = Field(
        None, description="Modes this applies to (null = all)"
    )
    position: str = Field(
        "after_design_doc", description="Position in assembled prompt"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}

    def applies_to_loop(self, loop_name: str) -> bool:
        """Check if this guardrail applies to a specific loop."""
        if self.loops is None:
            return True
        return loop_name in self.loops

    def applies_to_mode(self, mode_name: str) -> bool:
        """Check if this guardrail applies to a specific mode."""
        if self.modes is None:
            return True
        return mode_name in self.modes

    def is_valid(self) -> bool:
        """Check if the guardrail file exists and is within size limits."""
        from pathlib import Path

        path = Path(self.file_path)
        if not path.exists():
            return False
        if path.is_symlink():
            return False  # Symlinks not allowed for security
        if self.file_size is not None and self.file_size > 50 * 1024:  # 50KB limit
            return False
        if self.file_size is not None and self.file_size < 1:  # Must have content
            return False
        return True

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "category": self.category.value,
            "filename": self.filename,
            "source": self.source.value,
            "file_path": self.file_path,
            "file_mtime": self.file_mtime,
            "file_size": self.file_size,
            "enabled": self.enabled,
            "loops": self.loops,
            "modes": self.modes,
            "position": self.position,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Guardrail":
        """Create from dictionary (e.g., database row)."""
        loops = data.get("loops")
        modes = data.get("modes")

        # Handle JSON strings from database
        if isinstance(loops, str):
            import json
            loops = json.loads(loops)
        if isinstance(modes, str):
            import json
            modes = json.loads(modes)

        return cls(
            id=data.get("id"),
            project_id=data.get("project_id"),
            category=GuardrailCategory(data["category"]),
            filename=data["filename"],
            source=GuardrailSource(data["source"]),
            file_path=data["file_path"],
            file_mtime=data.get("file_mtime"),
            file_size=data.get("file_size"),
            enabled=data.get("enabled", True),
            loops=loops,
            modes=modes,
            position=data.get("position", "after_design_doc"),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if isinstance(data.get("created_at"), str)
                else data.get("created_at", datetime.utcnow())
            ),
        )
