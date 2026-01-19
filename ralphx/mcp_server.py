"""MCP server for RalphX integration with Claude Code.

This module provides backwards-compatible entry point for the MCP server.
The actual implementation is in the ralphx.mcp package.

Usage:
    claude mcp add ralphx -- ralphx mcp
"""

from ralphx.mcp import MCPServer


def main() -> None:
    """Run the MCP server."""
    server = MCPServer()
    server.run()


if __name__ == "__main__":
    main()
