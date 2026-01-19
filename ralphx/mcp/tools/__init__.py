"""MCP tool implementations organized by category.

Tool modules:
- projects: Project management (list, get, add, remove, update)
- loops: Loop/run management
- monitoring: Logs, sessions, diagnostics, stale runs
- guardrails: Guardrail configuration
- permissions: Claude CLI permission management
- workflows: Workflow, step, and resource management
- imports: Import operations
"""

from ralphx.mcp.tools.projects import get_project_tools
from ralphx.mcp.tools.loops import get_loop_tools
from ralphx.mcp.tools.items import get_item_tools
from ralphx.mcp.tools.workflows import get_workflow_tools
from ralphx.mcp.tools.monitoring import get_monitoring_tools
from ralphx.mcp.tools.diagnostics import get_diagnostics_tools
from ralphx.mcp.tools.guardrails import get_guardrails_tools
from ralphx.mcp.tools.permissions import get_permissions_tools
from ralphx.mcp.tools.imports import get_import_tools
from ralphx.mcp.tools.resources import get_resource_tools


def get_all_tools():
    """Get all tool definitions."""
    tools = []
    tools.extend(get_project_tools())
    tools.extend(get_loop_tools())
    tools.extend(get_item_tools())
    tools.extend(get_workflow_tools())
    tools.extend(get_monitoring_tools())
    tools.extend(get_diagnostics_tools())
    tools.extend(get_guardrails_tools())
    tools.extend(get_permissions_tools())
    tools.extend(get_import_tools())
    tools.extend(get_resource_tools())
    return tools


__all__ = ["get_all_tools"]
