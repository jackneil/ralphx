# RalphX

![RalphX Demo](https://raw.githubusercontent.com/jackneil/ralphx/main/docs/images/ralphx-demo.gif)

**From idea to working, tested code. Autonomously.**

RalphX is a **Ralph wrapper** for managing Ralph loops across your entire product development lifecycle. [Ralph](https://github.com/anthropics/claude-code) is the viral Claude Code looping pattern - RalphX orchestrates multiple Ralph loops together: research an idea, generate a design doc, write user stories, implement features, and test everything. Each Ralph loop runs with fresh context but memory of what's been completed.

[![PyPI version](https://badge.fury.io/py/ralphx.svg)](https://badge.fury.io/py/ralphx)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## What's New in v0.4.2

- **Sidebar step navigation** — Jump directly to any workflow step from the sidebar tree
- **Multi-account with auto-fallback** — Connect multiple Claude accounts, auto-switch on 429 rate limits with drag-to-reorder priority and per-project account assignment
- **Usage tracking** — Real-time 5h/7d progress bars with time position markers
- **Event persistence** — Full session history saved to DB, no browser tab required
- **Planning iterations** — Autonomous design doc refinement with streaming
- **Reliable stop button** — Checkpoint-based process tracking survives server hot-reload
- **Multi-account unified UX** — Streamlined account management with re-auth scope fixes
- **62 bug fixes + security hardening** — See [CHANGELOG.md](CHANGELOG.md)

---

## The Full Lifecycle

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│    Idea      │ ─▶ │ Design Doc   │ ─▶ │ User Stories │ ─▶ │ Implement    │ ─▶ │    Test      │
│              │    │ Ralph Loop   │    │ Ralph Loop   │    │ Ralph Loop   │    │ Ralph Loop   │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
       │                   │                   │                   │                   │
  "Build an app      Web search +         50-200 stories      Code for each       CLI, API, UI
   that does X"      synthesis            with criteria        story               testing
```

**Start anywhere.** Bring your own design doc, or let a Ralph loop research and create one. Jump straight to implementation if you already have stories.

---

## How It Works

Each workflow step is a **Ralph loop** - the viral Claude Code looping pattern:

1. **Fresh context** - Each iteration starts clean, no token bloat
2. **Memory of progress** - Knows what's done, what's next
3. **Recursive iterations** - Run until complete or hit limits
4. **Real-time monitoring** - Watch progress in the dashboard

```
┌─────────────────────────────────────────────────────────────────┐
│  Story Generation Ralph Loop (iteration 12 of 50)               │
│  ─────────────────────────────────────────────────────────────  │
│  ✓ 47 stories generated                                         │
│  ● Currently: Generating API authentication stories...          │
│  ○ Remaining: Payment processing, notifications                 │
└─────────────────────────────────────────────────────────────────┘
```

**Run your way:**
- Run the entire workflow end-to-end until completion
- Run individual Ralph loops one at a time
- Jump back and forth between Ralph loops as needed
- Pause, resume, or restart anytime

---

## Quick Start

**Copy and paste this into Claude Code:**

```
Install RalphX for me. RalphX is a Ralph wrapper on PyPI that manages Ralph loops
for product development. I'm not technical so please handle everything:

1. Check if I have conda/miniconda installed. If not, install miniconda for my OS.
2. Create a Python 3.11 environment called "ralphx" and activate it
3. Install RalphX from PyPI: pip install ralphx
4. Add RalphX as an MCP server using the full path to the ralphx binary in the conda env (use the right command for my OS to find it)
5. Start the RalphX dashboard: ralphx serve
6. Ask me if I want a desktop shortcut to launch the dashboard. If yes, create
   a shortcut for my OS that uses the full path to the Python executable in the
   ralphx conda env (don't use conda activate - point directly to the python binary)

Use the ask question tool if you need any info from me. Don't assume I know
how to run commands - just do everything for me and tell me when it's ready.
```

Claude will handle the entire installation. When done, tell Claude:

> "Register this project and help me build a workflow from my idea for [describe your app]"

Or if you have a design doc:

> "Register this project and create a planning workflow from my README"

Open `http://localhost:8765` to monitor progress.

![Dashboard](https://raw.githubusercontent.com/jackneil/ralphx/main/docs/images/dashboard-overview.png)

---

**Already technical?** Here's the quick setup:

```bash
# Create and activate a Python 3.10+ environment (3.11 recommended):
conda create -n ralphx python=3.11 -y && conda activate ralphx

# Install RalphX:
pip install ralphx

# Add MCP server with full path to ralphx binary:

# Linux/Mac:
claude mcp add ralphx -e PYTHONDONTWRITEBYTECODE=1 -- "$(which ralphx)" mcp

# Mac (zsh) - if "which ralphx" fails, first run: conda init zsh && source ~/.zshrc

# Windows - first find your path, then use it:
#   CMD:        where.exe ralphx
#   PowerShell: (Get-Command ralphx).Source
claude mcp add ralphx -e PYTHONDONTWRITEBYTECODE=1 -- C:\Users\YOU\miniconda3\envs\ralphx\Scripts\ralphx.exe mcp
```

---

## Supported Ralph Loop Types

### Research & Design Ralph Loop
Start from an idea. Claude searches the web, synthesizes findings, and builds out a comprehensive design document.

### Story Generation Ralph Loop
Claude extracts and generates robust user stories from your design document:
- Clear titles and descriptions
- Acceptance criteria
- Priority and categorization

Optionally enable **web-enhanced mode**: Claude uses your design doc as inspiration, then searches the web to discover related requirements and user stories you may have missed.

### Implementation Ralph Loop
Each iteration of the implementation Ralph loop:
1. **Fresh context** - Starts clean with your design doc, guardrails, and progress summary
2. **Knows what's done** - Sees all implemented stories with their git commits (can look back if needed)
3. **Detects duplicates** - Checks if a story is already implemented, marks it dup, moves on
4. **Implements ONE story** - Reads codebase, writes code that fits your patterns, adds tests
5. **Commits** - Creates a git commit after each story, then loops to the next

### Coming Soon: Testing Ralph Loops
- **CLI Testing Ralph Loop** - Run commands, verify output, loop until tests pass
- **Backend Testing Ralph Loop** - API endpoints, database operations
- **UI Testing Ralph Loop** - Chrome/Playwright automation via Claude

---

## The Dashboard

![Workflow Timeline](https://raw.githubusercontent.com/jackneil/ralphx/main/docs/images/workflow-timeline.png)

**Monitor your Ralph loops in real-time:**
- See which Ralph loop is running and iteration progress
- Watch Claude's actual output as it works
- View generated stories and implementations
- Start, pause, or stop Ralph loops anytime

---

## Workflow Step Types

Each workflow is built by combining steps. Each step uses one of these processing types:

| Step Type | What It Does |
|-----------|-------------|
| **Design Doc** | Interactive planning chat with web research to build a comprehensive design document |
| **Extract Requirements** | Extract user stories from your design doc (turbo mode for speed, deep mode for web-enhanced thoroughness) |
| **Web-Gen Requirements** | Discover requirements you missed by researching domain best practices on the web |
| **Implementation** | Implement user stories one at a time with code changes, tests, and git commits |

Build any workflow by combining these steps. For example, a full product workflow would be: Design Doc → Extract Requirements → Implementation.

Ask Claude: *"Create a workflow for my project starting from my idea for a task management app"*

---

## Coming Soon

**More Ralph Loop Types:**
- CLI/backend testing Ralph loops
- Chrome/Playwright UI testing Ralph loops
- Recursive test-fix cycles until green

**Integrations:**
- GitHub Issues - Import bugs and features directly
- Jira - Sync with existing project management
- Sentry - Turn production errors into bugs
- Slack - Notifications when workflows complete

**Triggers:**
- Scheduled workflows (cron-style)
- Webhook triggers from CI/CD
- Git push/PR triggers

**Mobile Access:**
- Mobile-friendly dashboard for monitoring on the go
- Remote access setup instructions in the wiki

---

## Multi-Account Management

Connect multiple Claude accounts and assign them per project:
- **Per-project accounts** — Each project can use a different Claude account
- **Priority ordering** — Drag-to-reorder accounts to set fallback priority
- **Auto-fallback on 429** — When one account hits rate limits (HTTP 429), automatically retry with the next account that has capacity
- **Usage tracking** — Real-time 5-hour and 7-day usage progress bars per account
- **Time markers** — Visual indicator showing where you are in each usage window

---

## Why RalphX?

| Problem | RalphX Solution |
|---------|-----------------|
| Ralph loops are powerful but manual | RalphX chains Ralph loops into full workflows |
| Claude Code loses context on long tasks | Fresh context per iteration with memory of progress |
| Hard to track what's done | Real-time dashboard shows exact progress |
| Starting from scratch is overwhelming | Research Ralph loop builds design docs from ideas |
| No visibility into AI work | Watch Claude's actual output as it works |
| Mixed billing across projects | Per-project subscription configuration |

---

## CLI Reference

**Core Commands:**
```bash
ralphx add <path>                          # Register a project
ralphx remove <slug>                       # Unregister a project
ralphx serve                               # Start dashboard (default port 8765)
ralphx run <loop> --project <slug>         # Run a loop from the CLI
ralphx doctor                              # Check system prerequisites
ralphx diagnose --project <slug>           # Run project-specific diagnostics
ralphx why --project <slug>                # Explain why the last run stopped
ralphx validate <loop.yaml>                # Validate a loop configuration file
ralphx mcp                                 # Start MCP server for Claude Code
```

**Project Management:**
```bash
ralphx projects list                       # List all registered projects
ralphx projects show <slug>                # Show project details and stats
```

**Loop Management:**
```bash
ralphx loops list --project <slug>         # List all loops for a project
ralphx loops show <name> --project <slug>  # Show loop config details
ralphx loops sync --project <slug>         # Sync loop configs from files to DB
```

**Guardrails:**
```bash
ralphx guardrails list --project <slug>              # List all guardrail files
ralphx guardrails validate --project <slug>          # Validate guardrail config
ralphx guardrails preview <loop> --project <slug>    # Preview assembled guardrails
ralphx guardrails detect --project <slug>            # Detect AI instruction files
ralphx guardrails templates                          # List guardrail templates
```

**Permissions:**
```bash
ralphx permissions check --project <slug>                     # Check current permissions
ralphx permissions setup --project <slug> --loop <name>       # Auto-configure for a loop
ralphx permissions preset --project <slug> --preset <name>    # Apply preset (research/implementation/full)
```

**Import:**
```bash
ralphx import markdown <file> --project <slug> --loop <name>  # Import markdown file
ralphx import jsonl <file> --project <slug> --loop <name>     # Import JSONL work items
ralphx import paste --project <slug> --loop <name> -f <name>  # Import from stdin
ralphx import list --project <slug> --loop <name>             # List input files
```

---

## MCP Tools (67 total)

Claude gets full access to RalphX:

| Category | What Claude Can Do |
|----------|-------------------|
| **Projects** | Register, list, configure projects |
| **Workflows** | Create, start, stop, advance steps |
| **Items** | Manage stories, tasks, bugs |
| **Monitoring** | Check progress, view logs |
| **Diagnostics** | Health checks, troubleshooting |

---

## Documentation

- [SDLC Workflows](design/SDLC_WORKFLOWS.md) - All workflow templates explained
- [Design Overview](design/DESIGN.md) - Architecture deep dive
- [Loop Schema](design/LOOP_SCHEMA.md) - Configuration reference
- [Backup & Import Guide](docs/BACKUP_AND_IMPORT.md) - Export workflows, import items

---

## License

MIT
