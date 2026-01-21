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

# MCP protocol version we support
PROTOCOL_VERSION = "2025-03-26"

# Server instructions for Claude - explains what RalphX is and how to use it
SERVER_INSTRUCTIONS = """RalphX is an Autonomous AI Loop Orchestration system. It helps you run autonomous AI workflows.

Key concepts:
- Project: A directory registered with RalphX (your codebase)
- Loop: An autonomous workflow defined in YAML that runs repeatedly
- Work Item: Data generated/consumed by loops (user stories, tasks, etc.)
- Workflow: A multi-step pipeline (research → implement → test)

Start with ralphx_help to see common workflows and all 67 available tools.

Quick start:
1. ralphx_list_projects - See registered projects
2. ralphx_list_loops - See available loops in a project
3. ralphx_start_loop - Run a loop
4. ralphx_list_runs - Monitor progress"""


class MCPServer:
    """MCP protocol handler for RalphX.

    Implements the MCP stdio transport protocol to expose RalphX
    functionality as tools that Claude can use.
    """

    def __init__(self):
        """Initialize the MCP server with all registered tools."""
        self.registry = ToolRegistry()
        self.registry.register_all(get_all_tools())
        self._initialized = False  # Track whether initialize handshake completed

    def run(self) -> None:
        """Run the MCP server, reading from stdin and writing to stdout."""
        # Process messages - wait for client to initiate
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

        # Per MCP spec: ping is allowed before initialization
        if method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {},
            }

        if method == "initialize":
            # Respond to client's initialize request per MCP spec
            # Client will then send notifications/initialized to signal ready
            self._initialized = True
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "serverInfo": {
                        "name": "ralphx",
                        "version": VERSION,
                    },
                    "capabilities": {
                        "tools": {
                            "listChanged": False,
                        },
                    },
                    "instructions": SERVER_INSTRUCTIONS,
                },
            }

        # Per MCP spec: most requests require initialization first
        # (ping and initialize are handled above)
        if not self._initialized and msg_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32600,
                    "message": "Server not initialized. Send 'initialize' request first.",
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
                # Per MCP spec: unknown tool is Invalid params (-32602), not Method not found
                # because tools/call method exists, the tool name is a parameter
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32602,
                        "message": f"Unknown tool: {tool_name}",
                    },
                }

            try:
                result = self.registry.call(tool_name, **arguments)

                # Format result - handle serialization errors gracefully
                try:
                    if isinstance(result, dict):
                        result_text = json.dumps(result, indent=2)
                    else:
                        result_text = str(result)
                except (TypeError, ValueError) as serialize_err:
                    # Non-JSON-serializable result - return as tool error, not protocol error
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Tool returned non-serializable result: {serialize_err}",
                                }
                            ],
                            "isError": True,
                        },
                    }

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
                # Unexpected tool execution error - return as tool error for LLM recovery
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Tool execution error: {e}",
                            }
                        ],
                        "isError": True,
                    },
                }

        if method == "notifications/initialized":
            # Client signals it's ready for normal operations
            # No response needed for notifications
            return None

        if method == "notifications/cancelled":
            # Client cancelled a request
            return None

        # Unknown method handling per JSON-RPC 2.0:
        # - If it has an id, it's a request and MUST return error
        # - If no id, it's a notification and can be silently ignored
        if msg_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            }
        # Notification we don't handle - ignore silently per JSON-RPC spec
        return None


def main() -> None:
    """Run the MCP server."""
    server = MCPServer()
    server.run()


if __name__ == "__main__":
    main()
