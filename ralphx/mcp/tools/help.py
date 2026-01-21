"""Help MCP tool.

Provides product context and guidance for using RalphX.
"""

from ralphx.mcp.base import ToolDefinition, make_schema, prop_string


RALPHX_HELP = """
# RalphX - Autonomous AI Loop Orchestration

RalphX helps you run autonomous AI workflows. Instead of manually prompting Claude over and over, you define loops that execute automatically while you monitor progress.

## Core Concepts

**Project**: A directory registered with RalphX (e.g., your codebase)
**Loop**: An autonomous workflow defined in YAML (e.g., "planning loop" generates user stories)
**Work Item**: Data generated/consumed by loops (stories, tasks, research notes)
**Workflow**: A multi-step pipeline for complex tasks (research → implement → test)
**Run**: A single execution of a loop or workflow step

## Common Workflows

### 1. Getting Started
```
1. ralphx_add_project - Register a project directory
2. ralphx_check_system_health - Verify setup is correct
3. ralphx_list_loops - See available loops
```

### 2. Running a Loop
```
1. ralphx_list_loops - Find the loop you want
2. ralphx_start_loop - Start it running
3. ralphx_list_runs - Monitor progress
4. ralphx_get_logs - View detailed logs
5. ralphx_stop_loop - Stop when done (or it stops automatically)
```

### 3. Creating a Workflow
```
1. ralphx_list_workflow_templates - See available templates
2. ralphx_create_workflow - Create from template or scratch
3. ralphx_create_workflow_step - Add steps (research, implement, test)
4. ralphx_start_workflow - Begin execution
5. ralphx_advance_workflow - Move to next step when ready
```

### 4. Managing Work Items
```
1. ralphx_list_items - View items (user stories, tasks, etc.)
2. ralphx_add_item - Add new items manually
3. ralphx_claim_item - Mark an item as being worked on
4. ralphx_complete_item - Mark as done
```

### 5. Troubleshooting
```
1. ralphx_check_system_health - System-wide health check
2. ralphx_diagnose_project - Project-specific diagnostics
3. ralphx_get_stop_reason - Why did a run fail?
4. ralphx_list_stale_runs - Find zombie runs
5. ralphx_cleanup_stale_runs - Clean them up
```

### 6. Permissions & Guardrails
```
1. ralphx_check_permissions - What tools are allowed?
2. ralphx_setup_permissions - Auto-configure based on loop needs
3. ralphx_apply_permission_preset - Quick setup (research/implementation/full)
4. ralphx_list_guardrails - See safety guardrails
```

## Tool Categories (67 tools total)

- **Projects (5)**: list, get, add, remove, update
- **Loops (7)**: list, status, start, stop, config, validate, sync
- **Items (6)**: list, get, add, update, claim, complete
- **Workflows (16)**: create, start, pause, advance, stop, steps, resources, archive
- **Monitoring (7)**: runs, logs, sessions, events
- **Diagnostics (5)**: health, diagnose, stop reason, stale runs
- **Guardrails (6)**: list, detect, validate, preview, templates
- **Permissions (3)**: check, setup, presets
- **Imports (5)**: paste, jsonl, inputs, templates
- **Resources (6)**: project resources, workflow resources

## Tips

- Always start with `ralphx_list_projects` to see what's registered
- Use `ralphx_check_system_health` if things aren't working
- Use `ralphx_get_stop_reason` to understand failures
- Workflows are for multi-step tasks; loops are for repetitive automation
"""


def get_help(topic: str = None) -> dict:
    """Get help about RalphX.

    Returns product overview and common workflows.
    For specific topics, returns focused guidance.
    """
    if topic:
        topic_lower = topic.lower()

        if "project" in topic_lower:
            return {
                "topic": "projects",
                "help": (
                    "Projects are directories registered with RalphX.\n\n"
                    "Tools:\n"
                    "- ralphx_list_projects: See all registered projects\n"
                    "- ralphx_get_project: Get details about one project\n"
                    "- ralphx_add_project: Register a new project\n"
                    "- ralphx_remove_project: Unregister a project\n"
                    "- ralphx_update_project: Update project settings\n\n"
                    "Start with: ralphx_list_projects"
                ),
            }
        elif "loop" in topic_lower:
            return {
                "topic": "loops",
                "help": (
                    "Loops are autonomous workflows defined in YAML.\n\n"
                    "Tools:\n"
                    "- ralphx_list_loops: See loops in a project\n"
                    "- ralphx_get_loop_status: Check if running\n"
                    "- ralphx_start_loop: Start execution\n"
                    "- ralphx_stop_loop: Stop execution\n"
                    "- ralphx_get_loop_config: View configuration\n"
                    "- ralphx_validate_loop: Check for config errors\n\n"
                    "Common flow: list_loops → start_loop → list_runs → stop_loop"
                ),
            }
        elif "workflow" in topic_lower:
            return {
                "topic": "workflows",
                "help": (
                    "Workflows are multi-step pipelines for complex tasks.\n\n"
                    "Tools:\n"
                    "- ralphx_list_workflows: See workflows in a project\n"
                    "- ralphx_create_workflow: Create new workflow\n"
                    "- ralphx_start_workflow: Begin execution\n"
                    "- ralphx_advance_workflow: Move to next step\n"
                    "- ralphx_create_workflow_step: Add steps\n"
                    "- ralphx_list_workflow_templates: See templates\n\n"
                    "Common flow: create_workflow → create_workflow_step (x3) → start_workflow → advance_workflow"
                ),
            }
        elif "item" in topic_lower or "work" in topic_lower:
            return {
                "topic": "work_items",
                "help": (
                    "Work items are data generated/consumed by loops (stories, tasks, etc.).\n\n"
                    "Tools:\n"
                    "- ralphx_list_items: View items with filters\n"
                    "- ralphx_add_item: Create new item\n"
                    "- ralphx_update_item: Modify item\n"
                    "- ralphx_claim_item: Mark as being worked on\n"
                    "- ralphx_complete_item: Mark as done\n\n"
                    "Filter by: status, category, phase, workflow_id"
                ),
            }
        elif "troubleshoot" in topic_lower or "debug" in topic_lower or "error" in topic_lower:
            return {
                "topic": "troubleshooting",
                "help": (
                    "Tools for diagnosing issues:\n\n"
                    "- ralphx_check_system_health: Is Python/Node/Claude CLI working?\n"
                    "- ralphx_diagnose_project: Check database, loops, workflows\n"
                    "- ralphx_get_stop_reason: Why did a run fail?\n"
                    "- ralphx_list_stale_runs: Find zombie processes\n"
                    "- ralphx_cleanup_stale_runs: Clean them up\n"
                    "- ralphx_get_logs: View detailed logs\n\n"
                    "Start with: ralphx_check_system_health"
                ),
            }

    return {
        "topic": "overview",
        "help": RALPHX_HELP,
    }


def get_help_tools() -> list[ToolDefinition]:
    """Get help tool definitions."""
    return [
        ToolDefinition(
            name="ralphx_help",
            description=(
                "Get help about RalphX. Call this FIRST to understand how to use RalphX tools. "
                "Returns product overview, common workflows, and tool categories. "
                "Optionally pass a topic: 'projects', 'loops', 'workflows', 'items', 'troubleshooting'"
            ),
            handler=get_help,
            input_schema=make_schema(
                properties={
                    "topic": prop_string(
                        "Optional topic: 'projects', 'loops', 'workflows', 'items', 'troubleshooting'"
                    ),
                },
                required=[],
            ),
        ),
    ]
