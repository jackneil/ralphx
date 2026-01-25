"""RalphX MCP module - Model Context Protocol server for Claude Code integration.

This module provides a modular MCP server implementation that exposes RalphX
functionality as tools that Claude Code can use.

Usage (Linux/Mac):
    claude mcp add ralphx -e PYTHONDONTWRITEBYTECODE=1 -- "$(which ralphx)" mcp
    # Mac zsh: if "which" fails, run: conda init zsh && source ~/.zshrc

Usage (Windows - find path first with: where.exe ralphx):
    claude mcp add ralphx -e PYTHONDONTWRITEBYTECODE=1 -- C:\\path\\to\\ralphx.exe mcp
"""

from ralphx.mcp.server import MCPServer

__all__ = ["MCPServer"]
