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
            # Workflow tools
            "ralphx_list_workflows": self._list_workflows,
            "ralphx_get_workflow": self._get_workflow,
            "ralphx_create_workflow": self._create_workflow,
            "ralphx_start_workflow": self._start_workflow,
            "ralphx_pause_workflow": self._pause_workflow,
            "ralphx_advance_workflow": self._advance_workflow,
            "ralphx_list_workflow_templates": self._list_workflow_templates,
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
                    "version": "0.1.2",
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
                        "version": "0.1.2",
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
                "description": "Add a new work item to a workflow step",
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
                        "workflow_id": {
                            "type": "string",
                            "description": "Workflow ID the item belongs to",
                        },
                        "source_step_id": {
                            "type": "integer",
                            "description": "Step ID that creates/owns this item",
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
                    "required": ["slug", "content", "workflow_id", "source_step_id"],
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
            # Workflow tools
            {
                "name": "ralphx_list_workflows",
                "description": "List all workflows for a project",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Project slug",
                        },
                        "status": {
                            "type": "string",
                            "description": "Filter by status (draft, active, paused, completed)",
                        },
                    },
                    "required": ["slug"],
                },
            },
            {
                "name": "ralphx_get_workflow",
                "description": "Get workflow details including steps",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Project slug",
                        },
                        "workflow_id": {
                            "type": "string",
                            "description": "Workflow ID",
                        },
                    },
                    "required": ["slug", "workflow_id"],
                },
            },
            {
                "name": "ralphx_create_workflow",
                "description": "Create a new workflow from a template",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Project slug",
                        },
                        "name": {
                            "type": "string",
                            "description": "Workflow name",
                        },
                        "template_id": {
                            "type": "string",
                            "description": "Template ID (e.g., 'build-product')",
                        },
                    },
                    "required": ["slug", "name"],
                },
            },
            {
                "name": "ralphx_start_workflow",
                "description": "Start a workflow execution",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Project slug",
                        },
                        "workflow_id": {
                            "type": "string",
                            "description": "Workflow ID",
                        },
                    },
                    "required": ["slug", "workflow_id"],
                },
            },
            {
                "name": "ralphx_pause_workflow",
                "description": "Pause a running workflow",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Project slug",
                        },
                        "workflow_id": {
                            "type": "string",
                            "description": "Workflow ID",
                        },
                    },
                    "required": ["slug", "workflow_id"],
                },
            },
            {
                "name": "ralphx_advance_workflow",
                "description": "Advance a workflow to the next step by completing the current step",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Project slug",
                        },
                        "workflow_id": {
                            "type": "string",
                            "description": "Workflow ID",
                        },
                    },
                    "required": ["slug", "workflow_id"],
                },
            },
            {
                "name": "ralphx_list_workflow_templates",
                "description": "List available workflow templates for creating new workflows",
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
        workflow_id: str,
        source_step_id: int,
        category: Optional[str] = None,
        priority: int = 0,
    ) -> dict:
        """Add a work item to a workflow step."""
        import uuid

        project = self.manager.get_project(slug)
        if not project:
            raise ValueError(f"Project not found: {slug}")

        item_id = str(uuid.uuid4())[:8]
        project_db = self.manager.get_project_db(project.path)
        project_db.create_work_item(
            id=item_id,
            workflow_id=workflow_id,
            source_step_id=source_step_id,
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

    # Workflow implementations

    def _list_workflows(self, slug: str, status: Optional[str] = None) -> dict:
        """List workflows for a project."""
        project = self.manager.get_project(slug)
        if not project:
            raise ValueError(f"Project not found: {slug}")

        project_db = self.manager.get_project_db(project.path)
        workflows = project_db.list_workflows(status=status)

        return {
            "workflows": [
                {
                    "id": w["id"],
                    "name": w["name"],
                    "namespace": w["namespace"],
                    "status": w["status"],
                    "current_step": w["current_step"],
                    "created_at": w["created_at"],
                }
                for w in workflows
            ],
        }

    def _get_workflow(self, slug: str, workflow_id: str) -> dict:
        """Get workflow details."""
        project = self.manager.get_project(slug)
        if not project:
            raise ValueError(f"Project not found: {slug}")

        project_db = self.manager.get_project_db(project.path)
        workflow = project_db.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")

        steps = project_db.list_workflow_steps(workflow_id)

        return {
            "id": workflow["id"],
            "name": workflow["name"],
            "namespace": workflow["namespace"],
            "status": workflow["status"],
            "current_step": workflow["current_step"],
            "created_at": workflow["created_at"],
            "steps": [
                {
                    "id": s["id"],
                    "step_number": s["step_number"],
                    "name": s["name"],
                    "step_type": s["step_type"],
                    "status": s["status"],
                }
                for s in steps
            ],
        }

    def _create_workflow(
        self,
        slug: str,
        name: str,
        template_id: Optional[str] = None,
    ) -> dict:
        """Create a new workflow."""
        import uuid

        project = self.manager.get_project(slug)
        if not project:
            raise ValueError(f"Project not found: {slug}")

        project_db = self.manager.get_project_db(project.path)

        # Generate unique ID and namespace
        workflow_id = f"wf-{uuid.uuid4().hex[:12]}"
        namespace = name.lower().replace(" ", "-")[:56]
        namespace = f"{namespace}-{uuid.uuid4().hex[:7]}"

        # Get template steps if template specified
        template_steps = []
        if template_id:
            project_db.seed_workflow_templates_if_empty()
            template = project_db.get_workflow_template(template_id)
            if template:
                template_steps = template.get("phases", [])

        # Create workflow
        project_db.create_workflow(
            id=workflow_id,
            name=name,
            namespace=namespace,
            template_id=template_id,
            status="draft",
        )

        # Create steps from template
        for step_def in template_steps:
            project_db.create_workflow_step(
                workflow_id=workflow_id,
                step_number=step_def["number"],
                name=step_def["name"],
                step_type=step_def["type"],
                config={
                    "description": step_def.get("description"),
                    "loopType": step_def.get("loopType"),
                    "skippable": step_def.get("skippable", False),
                },
                status="pending",
            )

        return {
            "id": workflow_id,
            "name": name,
            "namespace": namespace,
            "message": "Workflow created",
        }

    def _start_workflow(self, slug: str, workflow_id: str) -> dict:
        """Start a workflow."""
        import asyncio
        from ralphx.core.workflow_executor import WorkflowExecutor

        project = self.manager.get_project(slug)
        if not project:
            raise ValueError(f"Project not found: {slug}")

        project_db = self.manager.get_project_db(project.path)
        executor = WorkflowExecutor(
            project=project,
            db=project_db,
            workflow_id=workflow_id,
        )

        # Run async start_workflow synchronously
        loop = asyncio.new_event_loop()
        try:
            workflow = loop.run_until_complete(executor.start_workflow())
        finally:
            loop.close()

        return {
            "id": workflow["id"],
            "status": workflow["status"],
            "current_step": workflow["current_step"],
            "message": "Workflow started",
        }

    def _pause_workflow(self, slug: str, workflow_id: str) -> dict:
        """Pause a workflow."""
        import asyncio
        from ralphx.core.workflow_executor import WorkflowExecutor

        project = self.manager.get_project(slug)
        if not project:
            raise ValueError(f"Project not found: {slug}")

        project_db = self.manager.get_project_db(project.path)
        executor = WorkflowExecutor(
            project=project,
            db=project_db,
            workflow_id=workflow_id,
        )

        # Run async pause_workflow synchronously
        loop = asyncio.new_event_loop()
        try:
            workflow = loop.run_until_complete(executor.pause_workflow())
        finally:
            loop.close()

        return {
            "id": workflow["id"],
            "status": workflow["status"],
            "message": "Workflow paused",
        }

    def _advance_workflow(self, slug: str, workflow_id: str) -> dict:
        """Advance a workflow to the next step."""
        import asyncio
        from ralphx.core.workflow_executor import WorkflowExecutor

        project = self.manager.get_project(slug)
        if not project:
            raise ValueError(f"Project not found: {slug}")

        project_db = self.manager.get_project_db(project.path)
        executor = WorkflowExecutor(
            project=project,
            db=project_db,
            workflow_id=workflow_id,
        )

        # Get current step and complete it
        workflow = project_db.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")

        current_step = project_db.get_workflow_step_by_number(
            workflow_id, workflow["current_step"]
        )
        if not current_step:
            raise ValueError("No current step found")

        # Run async complete_step synchronously
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(executor.complete_step(current_step["id"]))
        finally:
            loop.close()

        # Get updated workflow
        workflow = project_db.get_workflow(workflow_id)
        return {
            "id": workflow["id"],
            "current_step": workflow["current_step"],
            "status": workflow["status"],
            "message": f"Advanced to step {workflow['current_step']}",
        }

    def _list_workflow_templates(self, slug: str) -> dict:
        """List available workflow templates."""
        project = self.manager.get_project(slug)
        if not project:
            raise ValueError(f"Project not found: {slug}")

        project_db = self.manager.get_project_db(project.path)
        templates = project_db.list_workflow_templates()

        return {
            "templates": [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "step_count": len(t.get("phases", [])),
                }
                for t in templates
            ]
        }


def main() -> None:
    """Run the MCP server."""
    server = MCPServer()
    server.run()


if __name__ == "__main__":
    main()
