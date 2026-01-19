"""Run models for RalphX."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    """Status of a loop run."""

    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    ABORTED = "aborted"


class Run(BaseModel):
    """Model for a loop execution run."""

    id: str = Field(..., description="Unique run identifier")
    project_id: str = Field(..., description="Parent project ID")
    loop_name: str = Field(..., description="Name of the loop being run")
    status: RunStatus = RunStatus.RUNNING
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    iterations_completed: int = Field(0, ge=0)
    items_generated: int = Field(0, ge=0)
    error_message: Optional[str] = None
    executor_pid: Optional[int] = Field(None, description="PID of executor process")
    last_activity_at: Optional[datetime] = Field(None, description="Last activity timestamp")

    model_config = {"from_attributes": True}

    @property
    def is_active(self) -> bool:
        """Check if run is still active."""
        return self.status == RunStatus.RUNNING

    @property
    def is_terminal(self) -> bool:
        """Check if run has ended."""
        return self.status in (
            RunStatus.COMPLETED,
            RunStatus.ERROR,
            RunStatus.ABORTED,
        )

    @property
    def duration_seconds(self) -> Optional[float]:
        """Get run duration in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return (datetime.utcnow() - self.started_at).total_seconds()

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "loop_name": self.loop_name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "iterations_completed": self.iterations_completed,
            "items_generated": self.items_generated,
            "error_message": self.error_message,
            "executor_pid": self.executor_pid,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Run":
        """Create from dictionary (e.g., database row)."""
        return cls(
            id=data["id"],
            project_id=data["project_id"],
            loop_name=data["loop_name"],
            status=RunStatus(data.get("status", "active")),
            started_at=(
                datetime.fromisoformat(data["started_at"])
                if isinstance(data.get("started_at"), str)
                else data.get("started_at", datetime.utcnow())
            ),
            completed_at=(
                datetime.fromisoformat(data["completed_at"])
                if isinstance(data.get("completed_at"), str) and data.get("completed_at")
                else None
            ),
            iterations_completed=data.get("iterations_completed", 0),
            items_generated=data.get("items_generated", 0),
            error_message=data.get("error_message"),
            executor_pid=data.get("executor_pid"),
            last_activity_at=(
                datetime.fromisoformat(data["last_activity_at"])
                if isinstance(data.get("last_activity_at"), str) and data.get("last_activity_at")
                else None
            ),
        )
