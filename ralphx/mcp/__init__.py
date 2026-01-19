"""RalphX MCP module - Model Context Protocol server for Claude Code integration.

This module provides a modular MCP server implementation that exposes RalphX
functionality as tools that Claude Code can use.

Usage:
    claude mcp add ralphx -- ralphx mcp
"""

from ralphx.mcp.server import MCPServer

__all__ = ["MCPServer"]
