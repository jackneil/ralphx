"""Session models for RalphX."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Session(BaseModel):
    """Model for a Claude CLI session within a run."""

    session_id: str = Field(..., description="Claude session UUID")
    project_id: Optional[str] = Field(None, description="Parent project ID (optional with two-tier DB)")
    run_id: Optional[str] = Field(None, description="Parent run ID")
    iteration: int = Field(..., ge=1, description="Iteration number in the run")
    mode: Optional[str] = Field(None, description="Mode used for this iteration")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    duration_seconds: Optional[float] = Field(None, ge=0)
    status: Optional[str] = Field(None, description="Session outcome status")
    items_added: Optional[list[str]] = Field(
        None, description="IDs of work items added during this session"
    )
    account_email: Optional[str] = Field(
        None, description="Email of Claude account used for this session"
    )

    model_config = {"from_attributes": True}

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "iteration": self.iteration,
            "mode": self.mode,
            "started_at": self.started_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "status": self.status,
            "items_added": self.items_added,
            "account_email": self.account_email,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        """Create from dictionary (e.g., database row)."""
        items_added = data.get("items_added")
        # Handle JSON string from database
        if isinstance(items_added, str):
            import json
            items_added = json.loads(items_added)

        return cls(
            session_id=data["session_id"],
            project_id=data.get("project_id"),
            run_id=data.get("run_id"),
            iteration=data["iteration"],
            mode=data.get("mode"),
            started_at=(
                datetime.fromisoformat(data["started_at"])
                if isinstance(data.get("started_at"), str)
                else data.get("started_at", datetime.utcnow())
            ),
            duration_seconds=data.get("duration_seconds"),
            status=data.get("status"),
            items_added=items_added,
            account_email=data.get("account_email"),
        )
