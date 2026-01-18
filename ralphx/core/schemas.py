"""JSON Schemas for structured output validation.

These schemas are used with Claude CLI's --json-schema flag to get
guaranteed structured responses from implementation loops.
"""

from enum import Enum
from typing import Optional


class ItemStatus(str, Enum):
    """Valid status values for work item processing."""

    IMPLEMENTED = "implemented"
    DUPLICATE = "duplicate"
    EXTERNAL = "external"
    SKIPPED = "skipped"
    ERROR = "error"


# Schema for implementation loop status reporting
IMPLEMENTATION_STATUS_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["implemented", "duplicate", "external", "skipped", "error"],
            "description": "The outcome of processing this work item"
        },
        "summary": {
            "type": "string",
            "description": "Brief description of what was done (for implemented status)"
        },
        "duplicate_of": {
            "type": "string",
            "description": "ID of the item this is a duplicate of (for duplicate status)"
        },
        "external_system": {
            "type": "string",
            "description": "Name of external system that should handle this (for external status)"
        },
        "reason": {
            "type": "string",
            "description": "Explanation for the status (especially for skipped/external/duplicate)"
        },
        "files_changed": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of files that were modified (for implemented status)"
        },
        "tests_passed": {
            "type": "boolean",
            "description": "Whether tests passed after implementation"
        }
    },
    "required": ["status"]
}


# Schema for generator loop story output
STORY_GENERATION_SCHEMA = {
    "type": "object",
    "properties": {
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Unique story ID (e.g., 'FND-001')"
                    },
                    "title": {
                        "type": "string",
                        "description": "Short title for the story"
                    },
                    "content": {
                        "type": "string",
                        "description": "User story in 'As a... I want... So that...' format"
                    },
                    "priority": {
                        "type": "integer",
                        "description": "Priority score (1-100, lower is higher priority)"
                    },
                    "category": {
                        "type": "string",
                        "description": "Category code (e.g., 'FND', 'SEC', 'API')"
                    },
                    "acceptance_criteria": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of acceptance criteria"
                    },
                    "dependencies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IDs of stories this depends on"
                    }
                },
                "required": ["id", "content"]
            }
        },
        "total_generated": {
            "type": "integer",
            "description": "Total number of stories generated"
        }
    },
    "required": ["stories"]
}


def get_schema_for_loop_type(loop_type: str) -> Optional[dict]:
    """Get the appropriate JSON schema for a loop type.

    Args:
        loop_type: Type of loop (e.g., 'consumer', 'generator')

    Returns:
        JSON schema dict or None if no schema for this type
    """
    schemas = {
        "consumer": IMPLEMENTATION_STATUS_SCHEMA,
        "implementation": IMPLEMENTATION_STATUS_SCHEMA,
        "generator": STORY_GENERATION_SCHEMA,
        "planning": STORY_GENERATION_SCHEMA,
    }
    return schemas.get(loop_type.lower())
