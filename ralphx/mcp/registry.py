"""Tool registry for MCP server.

This module handles tool registration and dispatch for all MCP tools.
Tools are registered from individual modules and dispatched by name.
"""

from typing import Any, Callable, Optional

from ralphx.mcp.base import ToolDefinition


class ToolRegistry:
    """Registry for MCP tools.

    Manages tool definitions and provides dispatch functionality.
    Tools are registered from individual modules during initialization.
    """

    def __init__(self):
        """Initialize the registry."""
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition."""
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def register_all(self, tools: list[ToolDefinition]) -> None:
        """Register multiple tools at once."""
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool by name."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def call(self, tool_name: str, **kwargs) -> Any:
        """Call a tool by name with arguments."""
        tool = self._tools.get(tool_name)
        if not tool:
            raise KeyError(f"Unknown tool: {tool_name}")
        return tool.handler(**kwargs)

    def get_definitions(self) -> list[dict]:
        """Get all tool definitions in MCP format."""
        return [tool.to_mcp_format() for tool in self._tools.values()]

    def list_names(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def __len__(self) -> int:
        """Return number of registered tools."""
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        """Check if tool is registered."""
        return name in self._tools
