# RalphX

![RalphX Demo](https://raw.githubusercontent.com/jackneil/ralphx/main/docs/images/ralphx-demo.gif)

**From idea to working, tested code. Autonomously.**

RalphX is a **Ralph wrapper** for managing Ralph loops across your entire product development lifecycle. [Ralph](https://github.com/anthropics/claude-code) is the viral Claude Code looping pattern - RalphX orchestrates multiple Ralph loops together: research an idea, generate a design doc, write user stories, implement features, and test everything. Each Ralph loop runs with fresh context but memory of what's been completed.

[![PyPI version](https://badge.fury.io/py/ralphx.svg)](https://badge.fury.io/py/ralphx)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

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
4. Add RalphX as an MCP server so you can control it: claude mcp add ralphx -- ralphx mcp
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

Open `http://localhost:16768` to monitor progress.

![Dashboard](https://raw.githubusercontent.com/jackneil/ralphx/main/docs/images/dashboard-overview.png)

---

**Already technical?** Here's the one-liner:

```bash
pip install ralphx && claude mcp add ralphx -- ralphx mcp
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

## Workflow Templates

Pre-built workflows that chain Ralph loops together:

| Template | Ralph Loops |
|----------|-------------|
| **New Product** | Research → Design Doc → Stories → Implement → Test |
| **From PRD** | Stories → Implement → Test |
| **Feature Add** | Impact Analysis → Tasks → Implement → Test |
| **Bug Fix** | Import Issues → Triage → Root Cause → Fix → Verify |
| **Security Audit** | Scan → Prioritize → Remediate → Verify |

Ask Claude: *"Set up a new-product workflow starting from my idea for a task management app"*

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

**Subscription Management:**
- Auto-switch to backup subscription when usage limits hit

**Mobile Access:**
- Mobile-friendly dashboard for monitoring on the go
- Remote access setup instructions in the wiki

---

## Manual Installation

For those who prefer to do it themselves:

```bash
# If you don't have conda, install miniconda first:
# https://docs.conda.io/en/latest/miniconda.html

# Create environment and install
conda create -n ralphx python=3.11 -y
conda activate ralphx
pip install ralphx

# Set up MCP so Claude can control RalphX
claude mcp add ralphx -- ralphx mcp

# Start the dashboard
ralphx serve
# Open http://localhost:16768
```

---

## Per-Project Subscriptions

Configure different Claude subscriptions per project. Great for:
- Separating personal vs work usage
- Managing team billing
- Tracking costs per project

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

```bash
ralphx add <path>           # Register a project
ralphx serve                # Start dashboard
ralphx doctor               # Check prerequisites
ralphx why <workflow>       # Explain why something stopped
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

---

## License

MIT
