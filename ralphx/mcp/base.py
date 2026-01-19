"""Base classes and patterns for MCP tools.

This module defines standard patterns used across all MCP tools:
- Pagination for list operations
- Error response format
- Sensitive data scrubbing
- Tool definition helpers
"""

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Pagination defaults
DEFAULT_LIMIT = 100
MAX_LIMIT = 500

# Sensitive data patterns to scrub
# These patterns are applied to session event content to prevent accidental exposure
SENSITIVE_PATTERNS = [
    # API Keys - various providers
    (r"sk-[a-zA-Z0-9]{20,}", "sk-***"),  # OpenAI/Anthropic API keys
    (r"sk-proj-[a-zA-Z0-9-_]{40,}", "sk-proj-***"),  # OpenAI project keys
    (r"sk-ant-[a-zA-Z0-9-_]{40,}", "sk-ant-***"),  # Anthropic API keys
    (r"xoxb-[a-zA-Z0-9-]+", "xoxb-***"),  # Slack bot tokens
    (r"xoxp-[a-zA-Z0-9-]+", "xoxp-***"),  # Slack user tokens
    # GitHub tokens
    (r"ghp_[a-zA-Z0-9]{36}", "ghp_***"),  # GitHub personal tokens
    (r"gho_[a-zA-Z0-9]{36}", "gho_***"),  # GitHub OAuth tokens
    (r"ghu_[a-zA-Z0-9]{36}", "ghu_***"),  # GitHub user tokens
    (r"ghs_[a-zA-Z0-9]{36}", "ghs_***"),  # GitHub server tokens
    (r"ghr_[a-zA-Z0-9]{36}", "ghr_***"),  # GitHub refresh tokens
    (r"github_pat_[a-zA-Z0-9_]{22,}", "github_pat_***"),  # GitHub fine-grained PAT
    # AWS credentials
    (r"AKIA[A-Z0-9]{16}", "AKIA***"),  # AWS access keys
    (r"ASIA[A-Z0-9]{16}", "ASIA***"),  # AWS temporary access keys
    # Generic secret patterns (key=value or key: value in JSON/YAML)
    (r"password[\"']?\s*[:=]\s*[\"'][^\"']+[\"']", "password: ***"),
    (r"secret[\"']?\s*[:=]\s*[\"'][^\"']+[\"']", "secret: ***"),
    (r"token[\"']?\s*[:=]\s*[\"'][^\"']+[\"']", "token: ***"),
    (r"api[_-]?key[\"']?\s*[:=]\s*[\"'][^\"']+[\"']", "api_key: ***"),
    (r"auth[_-]?token[\"']?\s*[:=]\s*[\"'][^\"']+[\"']", "auth_token: ***"),
    (r"access[_-]?token[\"']?\s*[:=]\s*[\"'][^\"']+[\"']", "access_token: ***"),
    (r"private[_-]?key[\"']?\s*[:=]\s*[\"'][^\"']+[\"']", "private_key: ***"),
    # Connection strings
    (r"postgres://[^\s]+", "postgres://***"),
    (r"mysql://[^\s]+", "mysql://***"),
    (r"mongodb://[^\s]+", "mongodb://***"),
    (r"redis://[^\s]+", "redis://***"),
]

# Max content size for session events (10KB)
MAX_EVENT_CONTENT_SIZE = 10 * 1024


@dataclass
class PaginatedResult:
    """Standard pagination response."""
    items: list[dict]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        """Check if there are more items."""
        return self.offset + len(self.items) < self.total

    def to_dict(self) -> dict:
        """Convert to response dict."""
        return {
            "items": self.items,
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
            "has_more": self.has_more,
        }


@dataclass
class MCPError(Exception):
    """MCP tool error with structured details."""
    error_code: str
    message: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to error response dict."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


class ToolError:
    """Standard error codes and factory methods."""

    # Error codes
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    WORKFLOW_NOT_FOUND = "WORKFLOW_NOT_FOUND"
    STEP_NOT_FOUND = "STEP_NOT_FOUND"
    ITEM_NOT_FOUND = "ITEM_NOT_FOUND"
    RUN_NOT_FOUND = "RUN_NOT_FOUND"
    LOOP_NOT_FOUND = "LOOP_NOT_FOUND"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    TEMPLATE_NOT_FOUND = "TEMPLATE_NOT_FOUND"
    ALREADY_RUNNING = "ALREADY_RUNNING"
    NOT_RUNNING = "NOT_RUNNING"
    INVALID_STATUS = "INVALID_STATUS"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PERMISSION_ERROR = "PERMISSION_ERROR"
    CONCURRENCY_ERROR = "CONCURRENCY_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"

    @staticmethod
    def project_not_found(slug: str) -> MCPError:
        return MCPError(
            error_code=ToolError.PROJECT_NOT_FOUND,
            message=f"Project not found: {slug}",
            details={
                "slug": slug,
                "suggestion": "Run ralphx_list_projects to see available projects",
            },
        )

    @staticmethod
    def workflow_not_found(workflow_id: str) -> MCPError:
        return MCPError(
            error_code=ToolError.WORKFLOW_NOT_FOUND,
            message=f"Workflow not found: {workflow_id}",
            details={
                "workflow_id": workflow_id,
                "suggestion": "Run ralphx_list_workflows to see available workflows",
            },
        )

    @staticmethod
    def step_not_found(step_id: Any) -> MCPError:
        return MCPError(
            error_code=ToolError.STEP_NOT_FOUND,
            message=f"Step not found: {step_id}",
            details={"step_id": str(step_id)},
        )

    @staticmethod
    def item_not_found(item_id: str) -> MCPError:
        return MCPError(
            error_code=ToolError.ITEM_NOT_FOUND,
            message=f"Work item not found: {item_id}",
            details={"item_id": item_id},
        )

    @staticmethod
    def run_not_found(run_id: str) -> MCPError:
        return MCPError(
            error_code=ToolError.RUN_NOT_FOUND,
            message=f"Run not found: {run_id}",
            details={"run_id": run_id},
        )

    @staticmethod
    def loop_not_found(loop_name: str) -> MCPError:
        return MCPError(
            error_code=ToolError.LOOP_NOT_FOUND,
            message=f"Loop not found: {loop_name}",
            details={
                "loop_name": loop_name,
                "suggestion": "Run ralphx_list_loops to see available loops",
            },
        )

    @staticmethod
    def session_not_found(session_id: str) -> MCPError:
        return MCPError(
            error_code=ToolError.SESSION_NOT_FOUND,
            message=f"Session not found: {session_id}",
            details={"session_id": session_id},
        )

    @staticmethod
    def already_running(loop_name: str, run_id: str) -> MCPError:
        return MCPError(
            error_code=ToolError.ALREADY_RUNNING,
            message=f"Loop {loop_name} is already running",
            details={
                "loop_name": loop_name,
                "run_id": run_id,
                "suggestion": "Stop the current run first or use force=true",
            },
        )

    @staticmethod
    def not_running(loop_name: str) -> MCPError:
        return MCPError(
            error_code=ToolError.NOT_RUNNING,
            message=f"Loop {loop_name} is not running",
            details={"loop_name": loop_name},
        )

    @staticmethod
    def validation_error(message: str, details: dict = None) -> MCPError:
        return MCPError(
            error_code=ToolError.VALIDATION_ERROR,
            message=message,
            details=details or {},
        )

    @staticmethod
    def concurrency_error(message: str, details: dict = None) -> MCPError:
        return MCPError(
            error_code=ToolError.CONCURRENCY_ERROR,
            message=message,
            details=details or {},
        )


def scrub_sensitive_data(text: str) -> str:
    """Scrub sensitive data patterns from text."""
    if not text:
        return text
    result = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def truncate_content(content: str, max_size: int = MAX_EVENT_CONTENT_SIZE) -> str:
    """Truncate content to max size with indicator."""
    if not content or len(content) <= max_size:
        return content
    return content[:max_size] + f"\n... [truncated, total {len(content)} bytes]"


def sanitize_event(event: dict, include_sensitive: bool = False) -> dict:
    """Sanitize a session event for safe output."""
    result = dict(event)

    # Truncate content fields
    for key in ["content", "text", "message", "result"]:
        if key in result and isinstance(result[key], str):
            result[key] = truncate_content(result[key])
            if not include_sensitive:
                result[key] = scrub_sensitive_data(result[key])

    return result


def validate_pagination(limit: Optional[int], offset: Optional[int]) -> tuple[int, int]:
    """Validate and normalize pagination parameters."""
    if limit is None:
        limit = DEFAULT_LIMIT
    if offset is None:
        offset = 0

    if limit < 1:
        limit = 1
    elif limit > MAX_LIMIT:
        limit = MAX_LIMIT

    if offset < 0:
        offset = 0

    return limit, offset


@dataclass
class ToolDefinition:
    """MCP tool definition."""
    name: str
    description: str
    handler: Callable
    input_schema: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {},
        "required": [],
    })

    def to_mcp_format(self) -> dict:
        """Convert to MCP tool definition format."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


def make_schema(
    properties: dict[str, dict],
    required: list[str] = None,
) -> dict:
    """Helper to create input schema for tools."""
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
    }


def prop_string(description: str) -> dict:
    """Helper for string property."""
    return {"type": "string", "description": description}


def prop_int(description: str, minimum: int = None, maximum: int = None) -> dict:
    """Helper for integer property."""
    result = {"type": "integer", "description": description}
    if minimum is not None:
        result["minimum"] = minimum
    if maximum is not None:
        result["maximum"] = maximum
    return result


def prop_bool(description: str) -> dict:
    """Helper for boolean property."""
    return {"type": "boolean", "description": description}


def prop_array(description: str, items: dict = None) -> dict:
    """Helper for array property."""
    result = {"type": "array", "description": description}
    if items:
        result["items"] = items
    return result


def prop_enum(description: str, values: list[str]) -> dict:
    """Helper for enum property."""
    return {"type": "string", "description": description, "enum": values}
