"""MCP server for RalphX integration with Claude Code.

This module provides backwards-compatible entry point for the MCP server.
The actual implementation is in the ralphx.mcp package.

Usage (Linux/Mac):
    claude mcp add ralphx -e PYTHONDONTWRITEBYTECODE=1 -- "$(which ralphx)" mcp
    # Mac zsh: if "which" fails, run: conda init zsh && source ~/.zshrc

Usage (Windows - find path first with: where.exe ralphx):
    claude mcp add ralphx -e PYTHONDONTWRITEBYTECODE=1 -- C:\\path\\to\\ralphx.exe mcp
"""

from ralphx.mcp import MCPServer


def main() -> None:
    """Run the MCP server."""
    server = MCPServer()
    server.run()


if __name__ == "__main__":
    main()
