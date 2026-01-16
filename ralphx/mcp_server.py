"""MCP server for RalphX integration with Claude Code.

This module implements the Model Context Protocol (MCP) server that allows
Claude Code to interact with RalphX projects, loops, and work items.

Usage:
    claude mcp add ralphx -- ralphx mcp
"""

import json
import sys
from typing import Any, Optional

from ralphx.core.project import ProjectManager


class MCPServer:
    """MCP protocol handler for RalphX.

    Implements the MCP stdio transport protocol to expose RalphX
    functionality as tools that Claude can use.
    """

    def __init__(self):
        """Initialize the MCP server."""
        self.manager = ProjectManager()
        self.tools = {
            "ralphx_list_projects": self._list_projects,
            "ralphx_get_project": self._get_project,
            "ralphx_list_loops": self._list_loops,
            "ralphx_get_loop_status": self._get_loop_status,
            "ralphx_start_loop": self._start_loop,
            "ralphx_stop_loop": self._stop_loop,
            "ralphx_list_items": self._list_items,
            "ralphx_add_item": self._add_item,
            "ralphx_update_item": self._update_item,
        }

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
                    "version": "0.1.1",
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
                        "version": "0.1.1",
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
                    "tools": self._get_tool_definitions(),
                },
            }

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if tool_name not in self.tools:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32601,
                        "message": f"Unknown tool: {tool_name}",
                    },
                }

            try:
                result = self.tools[tool_name](**arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, indent=2),
                            }
                        ],
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

    def _get_tool_definitions(self) -> list[dict]:
        """Get tool definitions for MCP."""
        return [
            {
                "name": "ralphx_list_projects",
                "description": "List all RalphX projects",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "ralphx_get_project",
                "description": "Get details of a specific project",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Project slug",
                        },
                    },
                    "required": ["slug"],
                },
            },
            {
                "name": "ralphx_list_loops",
                "description": "List loops configured for a project",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Project slug",
                        },
                    },
                    "required": ["slug"],
                },
            },
            {
                "name": "ralphx_get_loop_status",
                "description": "Get the current status of a loop",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Project slug",
                        },
                        "loop_name": {
                            "type": "string",
                            "description": "Loop name",
                        },
                    },
                    "required": ["slug", "loop_name"],
                },
            },
            {
                "name": "ralphx_start_loop",
                "description": "Start a loop execution",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Project slug",
                        },
                        "loop_name": {
                            "type": "string",
                            "description": "Loop name",
                        },
                        "mode": {
                            "type": "string",
                            "description": "Optional mode to use",
                        },
                        "iterations": {
                            "type": "integer",
                            "description": "Number of iterations",
                        },
                    },
                    "required": ["slug", "loop_name"],
                },
            },
            {
                "name": "ralphx_stop_loop",
                "description": "Stop a running loop",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Project slug",
                        },
                        "loop_name": {
                            "type": "string",
                            "description": "Loop name",
                        },
                    },
                    "required": ["slug", "loop_name"],
                },
            },
            {
                "name": "ralphx_list_items",
                "description": "List work items for a project",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Project slug",
                        },
                        "status": {
                            "type": "string",
                            "description": "Filter by status (pending, in_progress, completed, rejected)",
                        },
                        "category": {
                            "type": "string",
                            "description": "Filter by category",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max items to return",
                        },
                    },
                    "required": ["slug"],
                },
            },
            {
                "name": "ralphx_add_item",
                "description": "Add a new work item to a project",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Project slug",
                        },
                        "content": {
                            "type": "string",
                            "description": "Item content/description",
                        },
                        "category": {
                            "type": "string",
                            "description": "Item category",
                        },
                        "priority": {
                            "type": "integer",
                            "description": "Priority (0-10)",
                        },
                    },
                    "required": ["slug", "content"],
                },
            },
            {
                "name": "ralphx_update_item",
                "description": "Update an existing work item",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Project slug",
                        },
                        "item_id": {
                            "type": "string",
                            "description": "Item ID",
                        },
                        "content": {
                            "type": "string",
                            "description": "New content",
                        },
                        "status": {
                            "type": "string",
                            "description": "New status",
                        },
                        "category": {
                            "type": "string",
                            "description": "New category",
                        },
                        "priority": {
                            "type": "integer",
                            "description": "New priority",
                        },
                    },
                    "required": ["slug", "item_id"],
                },
            },
        ]

    # Tool implementations

    def _list_projects(self) -> list[dict]:
        """List all projects."""
        projects = self.manager.list_projects()
        return [
            {
                "slug": p.slug,
                "name": p.name,
                "path": p.path,
            }
            for p in projects
        ]

    def _get_project(self, slug: str) -> dict:
        """Get project details."""
        project = self.manager.get_project(slug)
        if not project:
            raise ValueError(f"Project not found: {slug}")

        stats = self.manager.get_project_stats(slug)
        return {
            "slug": project.slug,
            "name": project.name,
            "path": project.path,
            "design_doc": project.design_doc,
            "stats": stats,
        }

    def _list_loops(self, slug: str) -> list[dict]:
        """List loops for a project."""
        project = self.manager.get_project(slug)
        if not project:
            raise ValueError(f"Project not found: {slug}")

        loops = self.manager.list_loops(slug)
        return [
            {
                "name": loop.name,
                "display_name": loop.display_name,
                "type": loop.type,
                "modes": list(loop.modes.keys()),
            }
            for loop in loops
        ]

    def _get_loop_status(self, slug: str, loop_name: str) -> dict:
        """Get loop status."""
        project = self.manager.get_project(slug)
        if not project:
            raise ValueError(f"Project not found: {slug}")

        status = self.manager.get_loop_status(slug, loop_name)
        return {
            "loop_name": loop_name,
            "is_running": status.get("is_running", False),
            "run_id": status.get("run_id"),
            "current_iteration": status.get("current_iteration"),
            "current_mode": status.get("current_mode"),
            "status": status.get("status"),
        }

    def _start_loop(
        self,
        slug: str,
        loop_name: str,
        mode: Optional[str] = None,
        iterations: Optional[int] = None,
    ) -> dict:
        """Start a loop."""
        project = self.manager.get_project(slug)
        if not project:
            raise ValueError(f"Project not found: {slug}")

        run_id = self.manager.start_loop(
            slug=slug,
            loop_name=loop_name,
            mode=mode,
            iterations=iterations,
        )

        return {
            "message": f"Loop {loop_name} started",
            "run_id": run_id,
        }

    def _stop_loop(self, slug: str, loop_name: str) -> dict:
        """Stop a loop."""
        project = self.manager.get_project(slug)
        if not project:
            raise ValueError(f"Project not found: {slug}")

        self.manager.stop_loop(slug, loop_name)

        return {
            "message": f"Loop {loop_name} stopped",
        }

    def _list_items(
        self,
        slug: str,
        status: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> dict:
        """List work items."""
        project = self.manager.get_project(slug)
        if not project:
            raise ValueError(f"Project not found: {slug}")

        project_db = self.manager.get_project_db(project.path)
        items, total = project_db.list_work_items(
            status=status,
            category=category,
            limit=limit,
        )

        return {
            "items": [
                {
                    "id": item["id"],
                    "content": item["content"],
                    "status": item["status"],
                    "category": item.get("category"),
                    "priority": item.get("priority"),
                }
                for item in items
            ],
            "total": total,
        }

    def _add_item(
        self,
        slug: str,
        content: str,
        category: Optional[str] = None,
        priority: int = 0,
    ) -> dict:
        """Add a work item."""
        import uuid

        project = self.manager.get_project(slug)
        if not project:
            raise ValueError(f"Project not found: {slug}")

        item_id = str(uuid.uuid4())
        project_db = self.manager.get_project_db(project.path)
        project_db.create_work_item(
            id=item_id,
            content=content,
            category=category,
            priority=priority,
        )

        return {
            "id": item_id,
            "message": "Item created",
        }

    def _update_item(
        self,
        slug: str,
        item_id: str,
        content: Optional[str] = None,
        status: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> dict:
        """Update a work item."""
        project = self.manager.get_project(slug)
        if not project:
            raise ValueError(f"Project not found: {slug}")

        updates = {}
        if content is not None:
            updates["content"] = content
        if status is not None:
            updates["status"] = status
        if category is not None:
            updates["category"] = category
        if priority is not None:
            updates["priority"] = priority

        if updates:
            project_db = self.manager.get_project_db(project.path)
            project_db.update_work_item(item_id, **updates)

        return {
            "id": item_id,
            "message": "Item updated",
        }


def main() -> None:
    """Run the MCP server."""
    server = MCPServer()
    server.run()


if __name__ == "__main__":
    main()
