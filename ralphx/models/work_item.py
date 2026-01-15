"""Work item models for RalphX."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class WorkItemStatus(str, Enum):
    """Status of a work item."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PROCESSED = "processed"  # Item was consumed and processed by a consumer loop
    FAILED = "failed"
    SKIPPED = "skipped"
    DUPLICATE = "duplicate"


class WorkItemCreate(BaseModel):
    """Model for creating a new work item."""

    id: str = Field(..., min_length=1, description="Unique identifier within project")
    content: str = Field(..., min_length=1, description="Main content of the work item")
    title: Optional[str] = Field(None, description="Short title for the item")
    priority: Optional[int] = Field(None, ge=0, description="Lower = higher priority")
    status: WorkItemStatus = WorkItemStatus.PENDING
    category: Optional[str] = Field(None, max_length=50)
    tags: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = None
    dependencies: Optional[list[str]] = Field(None, description="IDs of items this depends on")

    def to_work_item(self, project_id: str) -> "WorkItem":
        """Convert to full WorkItem with project ID."""
        return WorkItem(
            id=self.id,
            project_id=project_id,
            content=self.content,
            title=self.title,
            priority=self.priority,
            status=self.status,
            category=self.category,
            tags=self.tags,
            metadata=self.metadata,
            dependencies=self.dependencies,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )


class WorkItem(BaseModel):
    """Full work item model."""

    id: str = Field(..., description="Unique identifier within project")
    project_id: str = Field(..., description="Parent project ID")
    content: str = Field(..., description="Main content")
    title: Optional[str] = Field(None, description="Short title for the item")
    priority: Optional[int] = Field(None, ge=0)
    status: WorkItemStatus = WorkItemStatus.PENDING
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = None
    source_loop: Optional[str] = Field(None, description="Loop that created this item")
    item_type: Optional[str] = Field(None, description="Semantic type from output.singular")
    claimed_by: Optional[str] = Field(None, description="Loop that claimed this item for processing")
    claimed_at: Optional[datetime] = Field(None, description="When the item was claimed")
    processed_at: Optional[datetime] = Field(None, description="When the item was processed")
    # Phase and dependency fields
    dependencies: Optional[list[str]] = Field(None, description="IDs of items this depends on")
    phase: Optional[int] = Field(None, description="Assigned phase number for implementation")
    duplicate_of: Optional[str] = Field(None, description="If DUPLICATE status, the parent item ID")
    skip_reason: Optional[str] = Field(None, description="If SKIPPED status, the reason why")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "content": self.content,
            "title": self.title,
            "priority": self.priority,
            "status": self.status.value,
            "category": self.category,
            "tags": self.tags,
            "metadata": self.metadata,
            "source_loop": self.source_loop,
            "item_type": self.item_type,
            "claimed_by": self.claimed_by,
            "claimed_at": self.claimed_at.isoformat() if self.claimed_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "dependencies": self.dependencies,
            "phase": self.phase,
            "duplicate_of": self.duplicate_of,
            "skip_reason": self.skip_reason,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict, project_id: str = "") -> "WorkItem":
        """Create from dictionary (e.g., database row).

        Args:
            data: Dictionary with work item data.
            project_id: Project ID (if not in data, e.g., from ProjectDatabase).
        """
        return cls(
            id=data["id"],
            project_id=data.get("project_id", project_id),
            content=data["content"],
            title=data.get("title"),
            priority=data.get("priority"),
            status=WorkItemStatus(data.get("status", "pending")),
            category=data.get("category"),
            tags=data.get("tags"),
            metadata=data.get("metadata"),
            source_loop=data.get("source_loop"),
            item_type=data.get("item_type"),
            claimed_by=data.get("claimed_by"),
            claimed_at=(
                datetime.fromisoformat(data["claimed_at"])
                if isinstance(data.get("claimed_at"), str) and data.get("claimed_at")
                else None
            ),
            processed_at=(
                datetime.fromisoformat(data["processed_at"])
                if isinstance(data.get("processed_at"), str) and data.get("processed_at")
                else None
            ),
            dependencies=data.get("dependencies"),
            phase=data.get("phase"),
            duplicate_of=data.get("duplicate_of"),
            skip_reason=data.get("skip_reason"),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if isinstance(data.get("created_at"), str)
                else data.get("created_at", datetime.utcnow())
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if isinstance(data.get("updated_at"), str)
                else data.get("updated_at", datetime.utcnow())
            ),
        )

    def is_actionable(self) -> bool:
        """Check if work item can be worked on."""
        return self.status in (WorkItemStatus.PENDING, WorkItemStatus.IN_PROGRESS)

    def is_terminal(self) -> bool:
        """Check if work item is in a terminal state."""
        return self.status in (
            WorkItemStatus.COMPLETED,
            WorkItemStatus.PROCESSED,
            WorkItemStatus.FAILED,
            WorkItemStatus.SKIPPED,
            WorkItemStatus.DUPLICATE,
        )
