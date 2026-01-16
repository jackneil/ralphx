# RalphX

**Autonomous AI Loop Orchestration for Claude Code**

[![PyPI version](https://badge.fury.io/py/ralphx.svg)](https://badge.fury.io/py/ralphx)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

RalphX lets you define autonomous AI workflows in YAML and run them with Claude Code. Instead of manually prompting your AI assistant over and over, define a loop once and let it execute autonomously while you monitor progress in a real-time dashboard.

---

## Why RalphX?

**The Problem:** Running Claude Code manually for repetitive tasks is tedious. You find yourself copy-pasting prompts, tracking progress in your head, and losing context between sessions.

**The Solution:** RalphX provides:

- **Declarative Loops** - Define workflows in YAML, not code
- **Autonomous Execution** - Let loops run while you focus on other work
- **Real-time Monitoring** - Watch progress in a web dashboard with live logs
- **Work Item Tracking** - Manage generated/consumed items with categories and phases
- **Multiple Interfaces** - Web UI for visual users, MCP for Claude Code integration, CLI for automation

### Use Cases

- **Planning Loops** - Generate user stories from design docs
- **Implementation Loops** - Build features phase by phase
- **Research Loops** - Gather and synthesize information
- **Review Loops** - Automated code review and feedback
- **Content Pipelines** - Generate documentation or content at scale

---

## Quick Start

Choose the path that fits your workflow:

### Path A: Web Dashboard (Visual Users)

The easiest way to get started. Run loops and monitor them in your browser.

```bash
# Install RalphX
pip install ralphx

# Register your project directory
ralphx add /path/to/your/project

# Start the dashboard
ralphx serve

# Open http://localhost:8765 in your browser
```

### Path B: Claude Code + MCP (Power Users)

Let Claude Code manage your loops through natural language.

```bash
# Install RalphX
pip install ralphx

# Add RalphX as an MCP server to Claude Code
claude mcp add ralphx -- ralphx mcp

# Now Claude Code can manage loops via natural language!
# Example: "List my RalphX projects" or "Start the planning loop"
```

### Path C: CLI Only (Automation)

For scripts, CI/CD, or when you prefer the command line.

```bash
# Install RalphX
pip install ralphx

# Register your project
ralphx add /path/to/your/project

# Run a loop directly
ralphx run my_loop --project my-project
```

---

## Core Concepts

| Concept | Description |
|---------|-------------|
| **Project** | A directory registered with RalphX, containing loops and work items |
| **Loop** | A YAML config defining an autonomous workflow (prompts, modes, limits) |
| **Work Item** | Generated/consumed data (stories, tasks, research notes, etc.) |
| **Mode** | An execution strategy within a loop (e.g., research mode, implementation mode) |
| **Iteration** | A single execution cycle of a loop |

---

## Creating Your First Loop

Create a file called `my_loop.yaml` in your project:

```yaml
name: research_loop
display_name: "Research Loop"
type: generator

modes:
  default:
    timeout: 300
    model: sonnet
    tools: [WebSearch, Read, Write]
    prompt_template: prompts/research.md

mode_selection:
  strategy: fixed
  fixed_mode: default

output:
  format: jsonl
  path: data/research_items.jsonl
  schema:
    required: [id, content, status]

limits:
  max_iterations: 10
  max_consecutive_errors: 3
```

### Key Fields

- **name** - Unique identifier for the loop
- **type** - `generator` (creates items) or `consumer` (processes items)
- **modes** - Different execution strategies with their own prompts and settings
- **mode_selection** - How to pick which mode runs (fixed, rotating, or conditional)
- **output** - Where generated items are stored
- **limits** - Safety limits to prevent runaway execution

Run it:

```bash
ralphx run my_loop.yaml --project my-project
```

---

## Web Dashboard

Start the dashboard with `ralphx serve` and open http://localhost:8765.

```
+----------------------------------------------------------+
|  RalphX Dashboard                              [Settings] |
+----------------------------------------------------------+
|                                                          |
|  Projects          Loops              Work Items         |
|  +--------------+  +----------------+ +----------------+ |
|  | my-project   |  | research_loop  | | 12 items       | |
|  | another-proj |  | planning_loop  | | Status: active | |
|  +--------------+  +----------------+ +----------------+ |
|                                                          |
|  Live Session Logs                                       |
|  +-----------------------------------------------------+ |
|  | [14:23:01] Starting iteration 5...                  | |
|  | [14:23:15] Generated item: user-story-042           | |
|  | [14:23:18] Iteration complete. Items: 42            | |
|  +-----------------------------------------------------+ |
|                                                          |
+----------------------------------------------------------+
```

**Features:**
- Real-time loop monitoring with SSE streaming
- Work item management (view, filter, edit)
- Session logs with timestamps
- Start/stop/pause loop controls
- Configuration editing

---

## MCP Integration (Claude Code)

[MCP (Model Context Protocol)](https://modelcontextprotocol.io/) lets Claude Code use external tools. RalphX exposes its functionality through MCP, allowing Claude to manage your loops conversationally.

### Setup

```bash
# Add RalphX as an MCP server
claude mcp add ralphx -- ralphx mcp
```

### Available Tools

Once connected, Claude Code has access to:

| Tool | Description |
|------|-------------|
| `ralphx_list_projects` | List all registered projects |
| `ralphx_get_project` | Get details about a specific project |
| `ralphx_list_loops` | List loops in a project |
| `ralphx_get_loop_status` | Check if a loop is running |
| `ralphx_start_loop` | Start a loop execution |
| `ralphx_stop_loop` | Stop a running loop |
| `ralphx_list_items` | List work items |
| `ralphx_add_item` | Add a new work item |
| `ralphx_update_item` | Update an existing item |

### Example Conversation

```
You: "What RalphX projects do I have?"
Claude: "You have 2 projects registered: 'my-app' and 'docs-site'"

You: "Start the planning loop on my-app"
Claude: "Started the planning loop. It will generate user stories from your
        design docs. I'll monitor progress - currently on iteration 1."

You: "How many items has it generated?"
Claude: "The loop has generated 8 user stories so far. Would you like me
        to show you the latest ones?"
```

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `ralphx add <path>` | Register a project directory |
| `ralphx remove <name>` | Unregister a project |
| `ralphx list` | List all registered projects |
| `ralphx show <name>` | Show project details |
| `ralphx sync` | Sync loops from project directories |
| `ralphx loops` | List all loops across projects |
| `ralphx validate <loop>` | Validate a loop configuration |
| `ralphx run <loop>` | Run a loop |
| `ralphx serve` | Start the web dashboard |
| `ralphx mcp` | Start the MCP server |
| `ralphx doctor` | Check system health |
| `ralphx diagnose <loop>` | Debug a loop configuration |
| `ralphx why <loop>` | Explain why a loop stopped |
| `ralphx permissions` | Manage loop permissions |

Use `ralphx <command> --help` for detailed options.

---

## Loop Examples

### Planning Loop

Generate user stories from a design document:

```yaml
name: planning
display_name: "Story Generator"
type: generator

modes:
  generate:
    timeout: 600
    model: sonnet
    prompt_template: prompts/generate_stories.md

mode_selection:
  strategy: fixed
  fixed_mode: generate

output:
  format: jsonl
  path: data/user_stories.jsonl
  schema:
    required: [id, title, description, acceptance_criteria]

limits:
  max_iterations: 20
```

### Implementation Loop

Build features with phase awareness:

```yaml
name: implementation
display_name: "Feature Builder"
type: consumer

input:
  path: data/user_stories.jsonl
  filter:
    status: ready

modes:
  implement:
    timeout: 900
    model: sonnet
    tools: [Read, Write, Bash]
    prompt_template: prompts/implement.md

mode_selection:
  strategy: fixed
  fixed_mode: implement

limits:
  max_iterations: 50
  max_consecutive_errors: 5
```

---

## Architecture

```
+-----------------------------------------------+
|         RalphX Dashboard (React)              |
|  Loop Control | Work Items | Live Logs        |
+-----------------------------------------------+
                    | SSE
                    v
+-----------------------------------------------+
|           RalphX API (FastAPI)                |
|  /loops  |  /items  |  /stream  |  /config    |
+-----------------------------------------------+
                    |
                    v
+-----------------------------------------------+
|           RalphX Core (Python)                |
|  Loop Executor | LLM Adapters | Item Stores   |
+-----------------------------------------------+
                    |
                    v
+-----------------------------------------------+
|              Claude Code CLI                  |
|         (or other LLM backends)               |
+-----------------------------------------------+
```

**Components:**

- **Dashboard** - React SPA with real-time updates via SSE
- **API** - FastAPI server handling REST endpoints and streaming
- **Core** - Python library with loop execution, adapters, and storage
- **Adapters** - Pluggable LLM backends (Claude CLI, Anthropic API, etc.)

---

## Documentation

- [Design Overview](design/DESIGN.md) - Full system design and architecture
- [Loop Schema](design/LOOP_SCHEMA.md) - Complete YAML configuration reference
- [API Specification](design/API_SPEC.md) - REST API documentation

---

## License

MIT
