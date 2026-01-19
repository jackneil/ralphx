"""MCP server core protocol handling.

This module implements the MCP stdio transport protocol and dispatches
tool calls to the registered handlers.
"""

import json
import sys
from typing import Any, Optional

from ralphx.mcp.base import MCPError
from ralphx.mcp.registry import ToolRegistry
from ralphx.mcp.tools import get_all_tools


# Version from pyproject.toml
VERSION = "0.1.5"


class MCPServer:
    """MCP protocol handler for RalphX.

    Implements the MCP stdio transport protocol to expose RalphX
    functionality as tools that Claude can use.
    """

    def __init__(self):
        """Initialize the MCP server with all registered tools."""
        self.registry = ToolRegistry()
        self.registry.register_all(get_all_tools())

    def run(self) -> None:
        """Run the MCP server, reading from stdin and writing to stdout."""
        # Send initialization message
        self._send_init()

        # Process messages
        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue

                try:
                    message = json.loads(line)
                    response = self._handle_message(message)
                    if response:
                        self._send(response)
                except json.JSONDecodeError:
                    self._send_error(-32700, "Parse error")
                except Exception as e:
                    self._send_error(-32603, str(e))
        except EOFError:
            # stdin was closed (e.g., in test environment or client disconnected)
            # Exit gracefully
            pass

    def _send_init(self) -> None:
        """Send MCP initialization message."""
        self._send({
            "jsonrpc": "2.0",
            "method": "initialized",
            "params": {
                "serverInfo": {
                    "name": "ralphx",
                    "version": VERSION,
                },
                "capabilities": {
                    "tools": True,
                },
            },
        })

    def _send(self, message: dict) -> None:
        """Send a JSON-RPC message to stdout."""
        print(json.dumps(message), flush=True)

    def _send_error(self, code: int, message: str, id: Any = None) -> None:
        """Send a JSON-RPC error response."""
        self._send({
            "jsonrpc": "2.0",
            "id": id,
            "error": {
                "code": code,
                "message": message,
            },
        })

    def _handle_message(self, message: dict) -> Optional[dict]:
        """Handle an incoming JSON-RPC message."""
        method = message.get("method")
        params = message.get("params", {})
        msg_id = message.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "serverInfo": {
                        "name": "ralphx",
                        "version": VERSION,
                    },
                    "capabilities": {
                        "tools": {
                            "listChanged": False,
                        },
                    },
                },
            }

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": self.registry.get_definitions(),
                },
            }

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if not self.registry.has(tool_name):
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32601,
                        "message": f"Unknown tool: {tool_name}",
                    },
                }

            try:
                result = self.registry.call(tool_name, **arguments)

                # Format result
                if isinstance(result, dict):
                    result_text = json.dumps(result, indent=2)
                else:
                    result_text = str(result)

                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": result_text,
                            }
                        ],
                    },
                }
            except MCPError as e:
                # Return structured error as result content
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(e.to_dict(), indent=2),
                            }
                        ],
                        "isError": True,
                    },
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32603,
                        "message": str(e),
                    },
                }

        if method == "notifications/cancelled":
            return None

        return None


def main() -> None:
    """Run the MCP server."""
    server = MCPServer()
    server.run()


if __name__ == "__main__":
    main()
