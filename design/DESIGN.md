# RalphX: Agent Loop Orchestration System

## Executive Summary

RalphX is a generic, domain-agnostic system for orchestrating autonomous AI agent loops. It provides:

- **Visual dashboard** for monitoring, controlling, and configuring loops
- **YAML-based configuration** for defining loop behavior without code changes
- **Multi-project management** from a global workspace
- **Real-time session tailing** - watch Claude's output as it runs (like `tail -f`)
- **Pluggable LLM backends** (Claude CLI primary, with API adapters)
- **Production-ready features**: crash recovery, permission management, diagnostics

---

## 1. Problem Statement

### Current State (Ralph)

Ralph is highly effective but tightly coupled to RCM domain:
- Hardcoded category maps (`ANS`, `FND`, `CLM`, etc.)
- Bash scripts with domain-specific logic
- No UI - pure CLI/terminal monitoring
- Manual log file inspection
- Domain-specific prompt templates

### Desired State (RalphX)
- **Domain-agnostic**: Define any workflow via configuration
- **Visual dashboard**: Real-time monitoring, control, and analytics
- **Declarative loops**: YAML/JSON configuration instead of bash
- **Multi-project**: Manage loops for multiple projects from one interface
- **Live session tailing**: Watch Claude's actual output in real-time
- **Pluggable backends**: Claude CLI, OpenAI, Anthropic API, local models
- **Production-ready**: Error handling, persistence, resumability, crash recovery

---

## 2. Global Workspace Model

RalphX uses a **global workspace** to manage projects centrally:

```
~/.ralphx/
├── config.yaml              # Global RalphX configuration
├── ralphx.db                # SQLite database (all data)
├── guardrails/              # GLOBAL guardrails (all projects)
│   ├── _config.yaml
│   ├── safety/
│   │   └── 00-never-do.md
│   └── compliance/
│       └── hipaa.md
├── projects/                # Per-project configs and data
│   ├── my-saas-app/
│   │   ├── project.yaml     # Project metadata
│   │   ├── loops/           # Loop configurations
│   │   │   ├── research.yaml
│   │   │   └── implementation.yaml
│   │   ├── prompts/         # Prompt templates
│   │   ├── guardrails/      # Project-level guardrails
│   │   │   ├── _config.yaml
│   │   │   ├── system/
│   │   │   ├── safety/
│   │   │   ├── domain/
│   │   │   ├── output/
│   │   │   └── custom/
│   │   └── data/            # Work items, outputs
│   └── another-project/
│       └── ...
├── templates/               # Reusable loop templates
│   └── guardrails/          # Built-in guardrail templates by project type
│       ├── web-app/
│       ├── backend-api/
│       └── healthcare/
└── logs/                    # RalphX server logs
```

### Why Global Workspace?

1. **Cross-project visibility**: Dashboard shows all projects
2. **No clutter**: Project repos stay clean (only `.claude/settings.json` added)
3. **Centralized templates**: Share loop configs across projects
4. **Single server**: One `ralphx serve` manages all projects

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     RalphX Dashboard (React)                         │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │ Project      │  │ Loop Control │  │ Live Session Tail        │   │
│  │ Selector     │  │ (start/stop) │  │ (real-time Claude output)│   │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │ Work Item    │  │ Run History  │  │ Config Editor            │   │
│  │ Browser      │  │ + Sessions   │  │                          │   │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                              │ SSE / REST
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       RalphX API (FastAPI)                           │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │ Project Manager  │  │ Loop Executor    │  │ Session Tailer    │  │
│  │ (add/list/remove)│  │ (run iterations) │  │ (tail -f for SSE) │  │
│  └──────────────────┘  └──────────────────┘  └───────────────────┘  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │ Run Manager      │  │ Work Item Store  │  │ Permission Checker│  │
│  │ (track sessions) │  │ (SQLite)         │  │                   │  │
│  └──────────────────┘  └──────────────────┘  └───────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     RalphX Core Engine (Python)                      │
├─────────────────────────────────────────────────────────────────────┤
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐ │
│  │ Loop Executor  │  │ LLM Adapters   │  │ Session Tracker        │ │
│  │                │  │ ┌────────────┐ │  │                        │ │
│  │ • Iteration    │  │ │Claude CLI  │ │  │ • Capture session_id   │ │
│  │ • Checkpoint   │  │ ├────────────┤ │  │ • Watch session logs   │ │
│  │ • Recovery     │  │ │Anthropic   │ │  │ • Run markers          │ │
│  │ • Heartbeat    │  │ ├────────────┤ │  │                        │ │
│  │                │  │ │OpenAI      │ │  └────────────────────────┘ │
│  └────────────────┘  │ └────────────┘ │                              │
│                      └────────────────┘                              │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Claude Code (CLI)                                │
├─────────────────────────────────────────────────────────────────────┤
│  Session logs: ~/.claude/projects/<project-path>/<session>.jsonl    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Core Concepts

### 4.1 Projects

A **Project** is a codebase registered with RalphX:

```yaml
# ~/.ralphx/projects/my-saas-app/project.yaml
name: "My SaaS App"
slug: "my-saas-app"
path: "/home/user/code/my-saas-app"
design_doc: "design/PRD.md"
created_at: "2026-01-13T14:00:00Z"
id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

### 4.2 Loops

A **Loop** is a reusable agent workflow definition:

```yaml
# ~/.ralphx/projects/my-saas-app/loops/research.yaml
name: research
display_name: "Research Loop"
description: "Discovers and generates work items via research"
type: generator  # generator | consumer | hybrid

modes:
  turbo:
    description: "Fast extraction from existing docs"
    timeout: 180
    model: sonnet
    tools: []
    prompt_template: prompts/research_turbo.md
  deep:
    description: "Thorough web research"
    timeout: 900
    model: sonnet
    tools: [WebSearch, WebFetch]
    prompt_template: prompts/research_deep.md

mode_selection:
  strategy: weighted_random
  weights:
    turbo: 85
    deep: 15

limits:
  max_iterations: 100
  max_runtime_seconds: 28800
  max_consecutive_errors: 5

execution:
  permission_mode: default
  permission_timeout: 30
  on_permission_block: skip
```

### 4.3 Runs

A **Run** is a specific execution of a loop with tracking:

```yaml
# ~/.ralphx/projects/my-saas-app/runs/my-saas-app-20260113-143052-a1b2c3d4.yaml
run_id: "my-saas-app-20260113-143052-a1b2c3d4"
loop: "research"
status: "active"  # active | completed | error | paused
started_at: "2026-01-13T14:30:52Z"
iterations_completed: 47
items_generated: 412
sessions:
  1: "abc123-def456"
  2: "ghi789-jkl012"
  # ... session_id for each iteration
```

### 4.4 Work Items

```typescript
interface WorkItem {
  id: string;              // e.g., "ANS-042" or uuid
  priority: number;        // Lower = higher priority
  content: string;         // Main content
  status: WorkItemStatus;
  category?: string;
  tags?: string[];
  created_at: string;
  updated_at: string;
  metadata?: Record<string, any>;
}

type WorkItemStatus =
  | 'pending'
  | 'in_progress'
  | 'completed'
  | 'failed'
  | 'skipped'
  | 'duplicate';
```

### 4.5 Categories & Phases

Categories provide domain-specific organization:

```yaml
# categories.yaml
categories:
  ANS:
    name: "Anesthesia"
    description: "Anesthesia-specific billing rules"
    color: "#4CAF50"
  FND:
    name: "Foundation"
    description: "Core infrastructure and data models"
    color: "#2196F3"
```

Phases organize implementation order:

```yaml
# phases.yaml
phases:
  1:
    name: "Foundation"
    categories: [FND, DBM, SEC, ARC]
  2:
    name: "Core Models"
    categories: [PAT, PRV, ENC, CLM]
    depends_on: [1]
```

---

## 5. Live Session Monitoring

### 5.1 Session Log Architecture

Claude Code stores session logs at:
```
~/.claude/projects/<project-path>/<session-uuid>.jsonl
```

Where `<project-path>` is the working directory with `/` replaced by `-`:
- `/home/user/myproject` → `-home-user-myproject`

### 5.2 Capturing Session ID

When spawning Claude CLI, use `--output-format stream-json` to capture the session ID:

```python
cmd = [
    "claude", "-p",
    "--model", model,
    "--output-format", "stream-json",  # Enables session tracking
]

proc = await asyncio.create_subprocess_exec(*cmd, ...)

# Parse first JSON message to get session_id
async for line in proc.stdout:
    msg = json.loads(line)
    if msg.get("type") == "init" or "session_id" in msg:
        session_id = msg.get("session_id")
        break
```

### 5.3 Session Tailing (tail -f Experience)

The dashboard provides a **live tail -f style view** of Claude's session:

```
┌─────────────────────────────────────────────────────────────────────┐
│ Session: my-saas-app-20260113-143052 | Iteration 47 | turbo mode   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ 14:35:22 💬 I'll extract user stories from the design document...  │
│                                                                     │
│ 14:35:24 🔧 Read(design/DESIGN.md)                                 │
│          └─ 45,231 bytes read                                       │
│                                                                     │
│ 14:35:26 💬 Based on the RCM portal design, I've identified        │
│             several user stories for the ANS category...           │
│                                                                     │
│ 14:35:28 🔧 Write(data/prd.jsonl)                                  │
│          └─ Appending 5 new stories: ANS-089 through ANS-093       │
│                                                                     │
│ ▌                                                                   │
└─────────────────────────────────────────────────────────────────────┘
  [Pause] [Clear] [Copy Log]                         Auto-scroll: ● ON
```

### 5.4 SessionTailer Implementation

```python
class SessionTailer:
    """Tail a Claude session log file like 'tail -f'."""

    def __init__(self, session_path: Path):
        self.path = session_path
        self.last_position = 0
        self.running = True

    async def tail(self) -> AsyncIterator[dict]:
        """Yield new log entries as they're written."""
        while not self.path.exists() and self.running:
            yield {"type": "waiting", "message": "Waiting for session..."}
            await asyncio.sleep(0.3)

        while self.running:
            try:
                # Handle file deletion during tailing
                if not self.path.exists():
                    yield {"type": "error", "message": "Session file was deleted"}
                    return

                current_size = self.path.stat().st_size

                # Handle file truncation (e.g., log rotation)
                if current_size < self.last_position:
                    self.last_position = 0
                    yield {"type": "warning", "message": "Session file truncated, restarting from beginning"}

                if current_size > self.last_position:
                    with open(self.path, 'r') as f:
                        f.seek(self.last_position)
                        new_content = f.read()
                        self.last_position = f.tell()

                    for line in new_content.strip().split('\n'):
                        if line:
                            try:
                                entry = json.loads(line)
                                parsed = self._parse_for_display(entry)
                                if parsed:
                                    yield parsed
                            except json.JSONDecodeError:
                                # Partial line written, will be completed on next poll
                                self.last_position -= len(line) + 1
                                break

            except FileNotFoundError:
                yield {"type": "error", "message": "Session file was deleted"}
                return
            except PermissionError:
                yield {"type": "error", "message": "Permission denied reading session file"}
                return

            await asyncio.sleep(0.1)  # 100ms polling

    def _parse_for_display(self, entry: dict) -> dict | None:
        """Parse JSONL entry into display-friendly format."""
        # Extract text, tool_use, tool_result from content blocks
        # Return structured events for dashboard
        ...
```

### 5.5 Run Identification Markers

To track which session belongs to which run, inject a marker at the END of prompts:

```python
RUN_MARKER_TEMPLATE = """
<!-- RALPHX_TRACKING run_id="{run_id}" project="{project_slug}" iteration={iteration} mode="{mode}" ts="{started_at}" -->"""
```

This marker is:
- At the END (Claude less likely to engage with it)
- Uses XML comment syntax (typically ignored by LLMs)
- Regex-searchable for session discovery

**Important:** Avoid placing RALPHX_TRACKING patterns in design documents, as this could confuse session discovery regex matching.

### 5.6 Session Index for O(1) Lookup

To avoid scanning all JSONL files for session discovery (O(n)), maintain an index:

```json
// ~/.ralphx/projects/{slug}/session_index.json
{
  "sessions": {
    "abc123-def456": {
      "run_id": "my-saas-app-20260113-143052-a1b2c3d4",
      "iteration": 47,
      "mode": "turbo",
      "registered_at": "2026-01-13T14:35:22Z"
    }
  },
  "last_scanned": "2026-01-13T14:00:00Z"
}
```

The index is updated:
1. **Immediately** when a session_id is captured from stream-json output
2. **Incrementally** on discovery - only scan files newer than `last_scanned`

### 5.7 Fallback Session Discovery

If stream-json capture fails, use timing-based fallback:

```python
async def fallback_by_timing(self, start_time: float, timeout: float = 30) -> str | None:
    """Find session by file creation time when capture fails."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for session_file in self.claude_log_dir.glob("*.jsonl"):
            # File created after we started the iteration
            if session_file.stat().st_ctime > start_time:
                # Verify it's our session via run marker
                content = session_file.read_text()[:5000]
                if self.run_id in content:
                    return session_file.stem
        await asyncio.sleep(0.5)
    return None
```

Session lookup priority:
1. **In-memory cache** (fastest, for active run)
2. **Session index** (fast, for any run)
3. **Timing-based discovery** (slow fallback)
4. **Full log scan** (slowest, last resort)

---

## 6. Web Dashboard Design

### 6.1 Dashboard Home
```
┌─────────────────────────────────────────────────────────────────┐
│  RalphX                                          [Settings] [?] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Projects                                 Active Loops          │
│  ┌─────────────────────────────────┐      ┌─────────────────┐  │
│  │ ● Frontend App    research (42%)│      │ Work Items      │  │
│  │ ● Backend API     implement(78%)│      │ ────────────────│  │
│  │ ○ Mobile App      (idle)        │      │ Total:    3,847 │  │
│  └─────────────────────────────────┘      │ Pending:  3,102 │  │
│                                           └─────────────────┘  │
│  ┌─────────────────────────────────┐                           │
│  │ [+ Add Project] [Templates]     │                           │
│  └─────────────────────────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Loop Detail View with Live Session Tail
```
┌─────────────────────────────────────────────────────────────────┐
│  ← Back    Research Loop                    ● RUNNING          │
├─────────────────────────────────────────────────────────────────┤
│  Progress ──────────────────────────────────────────────── 47% │
│  [███████████████████░░░░░░░░░░░░░░░░░░]  47/100 iterations    │
│                                                                 │
│  ┌─────────────────────┐  ┌─────────────────────────────────┐  │
│  │ Current Iteration   │  │ Live Session Output             │  │
│  │ ─────────────────── │  │                                 │  │
│  │ Mode: turbo         │  │ 14:35:22 💬 I'll extract...     │  │
│  │ Category: ANS       │  │ 14:35:24 🔧 Read(DESIGN.md)     │  │
│  │ Elapsed: 45s        │  │          └─ 45,231 bytes        │  │
│  │ Status: ✓ NORMAL    │  │ 14:35:26 💬 Based on the...     │  │
│  │   (typical: 20-60s) │  │ 14:35:28 🔧 Write(prd.jsonl)    │  │
│  │                     │  │          └─ +5 stories          │  │
│  │ Stories this iter:  │  │                                 │  │
│  │   ANS-089 ✓         │  │ ▌                               │  │
│  │   ANS-090 ✓         │  │                                 │  │
│  └─────────────────────┘  └─────────────────────────────────┘  │
│                                                                 │
│  [Pause]  [Stop]  [View Full Session]  [Edit Config]           │
└─────────────────────────────────────────────────────────────────┘
```

### 6.3 Run History & Session Explorer
```
┌─────────────────────────────────────────────────────────────────┐
│  Run History: My SaaS App                                       │
├─────────────────────────────────────────────────────────────────┤
│  │ Run ID      │ Loop       │ Iters │ Items │ Status  │ When   │
│  ├─────────────┼────────────┼───────┼───────┼─────────┼────────┤
│  │ ...a1b2c3d4 │ research   │ 100   │ 847   │ ✓ done  │ 2h ago │
│  │ ...e5f6g7h8 │ research   │ 47    │ 412   │ ● active│ now    │
│  │ ...i9j0k1l2 │ implement  │ 23    │ 23    │ ⏸ paused│ 1d ago │
│  └─────────────────────────────────────────────────────────────┘│
│                                                                 │
│  Sessions for Run ...e5f6g7h8:                                  │
│  │ Iter │ Session ID   │ Duration │ Items │ Errors │           │
│  ├──────┼──────────────┼──────────┼───────┼────────┤           │
│  │ 47   │ abc123-def456│ 45s      │ 5     │ 0      │ [View]    │
│  │ 46   │ ghi789-jkl012│ 38s      │ 8     │ 0      │ [View]    │
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. Operational Robustness

### 7.1 Prerequisites Check (`ralphx doctor`)

```bash
$ ralphx doctor

Checking RalphX prerequisites...

✓ Python 3.11.5       OK
✓ ~/.ralphx/          writable
✓ Node.js 20.10.0     OK
✓ Claude CLI 1.0.102  OK
✓ Claude CLI auth     authenticated
✓ Linux kernel 6.8.0  OK
✓ Network access      OK (latency: 234ms)

Status: All systems operational!
```

Checks for:
- Python version (3.10+)
- Node.js (required for Claude CLI)
- Claude CLI installed and authenticated
- Linux kernel 5.15.0 warning (known hang issue)
- WSL detection + /mnt/ path warning
- Network connectivity

### 7.2 Crash Recovery & Checkpoints

```python
class LoopExecutor:
    # Checkpoints are stored in SQLite (see Section 10.3 checkpoints table)
    # Lock file remains on filesystem for cross-process coordination
    LOCK_FILE = "~/.ralphx/projects/{project}/.checkpoint.lock"

    async def _save_checkpoint(self, iteration: int, status: str):
        """Save state that survives crashes (to SQLite checkpoints table)."""
        checkpoint_data = {
            "loop": self.config.name,
            "iteration": iteration,
            "status": status,  # "in_progress" | "completed" | "error"
            "items_added": self.state.items_added,
            "last_category": self.state.current_category,
            "pid": os.getpid(),  # Track which process owns this checkpoint
        }
        try:
            # SQLite with WAL mode ensures atomic writes
            await self.db.upsert_checkpoint(
                project_id=self.project_id,
                run_id=self.run_id,
                loop_name=self.config.name,
                iteration=iteration,
                status=status,
                data=json.dumps(checkpoint_data)
            )
        except sqlite3.Error as e:
            # DB locked, disk full, etc.
            logger.error(f"Failed to save checkpoint: {e}")
            # Continue execution - checkpoint failure shouldn't stop the loop
            # but user should be notified
            self.emit("warning", f"Checkpoint save failed: {e}")

    async def _acquire_checkpoint_lock(self) -> bool:
        """Acquire exclusive lock before resuming. Returns False if already locked."""
        lock_path = self.checkpoint_path.with_suffix(".lock")
        try:
            # Create lock file with our PID
            # O_CREAT | O_EXCL ensures atomic create-if-not-exists
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            # Lock exists - check if owning process is still alive
            try:
                with open(lock_path) as f:
                    pid = int(f.read().strip())
                if not self._is_process_alive(pid):
                    # Stale lock from dead process, remove and retry
                    os.unlink(lock_path)
                    return await self._acquire_checkpoint_lock()
                return False  # Process is alive, can't acquire
            except (ValueError, OSError):
                # Corrupted lock file, remove and retry
                os.unlink(lock_path)
                return await self._acquire_checkpoint_lock()

    def _is_process_alive(self, pid: int) -> bool:
        """Cross-platform check if process is alive."""
        if sys.platform == "win32":
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        else:
            try:
                os.kill(pid, 0)
                return True
            except ProcessLookupError:
                return False

    async def _run_iteration(self, n: int):
        # Save checkpoint BEFORE (status = in_progress)
        await self._save_checkpoint(iteration=n, status="in_progress")

        try:
            result = await self.adapter.execute(...)
            # Save checkpoint AFTER (status = completed)
            await self._save_checkpoint(iteration=n, status="completed")
            return result
        except Exception as e:
            await self._save_checkpoint(iteration=n, status="error", error=str(e))
            raise
```

**Recovery Flow:**
1. Check if checkpoint exists with status="in_progress"
2. Acquire checkpoint lock (prevents two instances resuming simultaneously)
3. If lock acquired, resume from checkpoint iteration
4. If lock fails, another instance is already handling recovery

### 7.3 Heartbeat System

Real-time activity indicator so users know if stuck or just slow:

```python
MODE_TIMING_EXPECTATIONS = {
    "turbo": {"typical": (20, 60), "max": 180},
    "deep": {"typical": (60, 300), "max": 900},
}

async def heartbeat_task(self):
    while True:
        await asyncio.sleep(5)
        self.emit("heartbeat", {
            "iteration": self.state.iteration,
            "phase": self.current_phase,
            "elapsed": time.time() - self.phase_start,
            "status": get_timing_status(self.mode, elapsed),
        })
```

Dashboard shows:
```
Phase:   Calling Claude CLI... (45s)
Status:  ✓ NORMAL (typical: 20-60s, timeout: 180s)
```

### 7.4 Infinite Loop Detection

```python
def detect_infinite_loop(self, output: str) -> bool:
    # Check for repeated permission blocks
    if output.count("requires approval") >= 5:
        return True

    # Check for identical consecutive errors
    if len(self.recent_errors) >= 3:
        if len(set(self.recent_errors)) == 1:
            return True

    # Check for repeated identical tool calls
    if len(self.recent_tool_calls) >= 5:
        if len(set(self.recent_tool_calls)) == 1:
            return True

    return False
```

### 7.5 Silent Hang Detection

Claude CLI can hang silently without output. Detect via activity timeout:

```python
MODE_SILENCE_THRESHOLDS = {
    "turbo": {"warn": 45, "kill": 180},
    "deep": {"warn": 120, "kill": 600},
}

async def monitor_activity(self):
    while True:
        await asyncio.sleep(10)
        silence = time.time() - self.last_activity

        if silence > self.activity_warn_timeout:
            self.emit("warning", f"No output for {silence:.0f}s")

        if silence > self.activity_kill_timeout:
            raise StuckError(f"Unresponsive for {silence:.0f}s")
```

### 7.6 Diagnostic Commands

```bash
$ ralphx diagnose

Running diagnostics for project: My SaaS App

[1/6] Checking Claude CLI... OK (v1.0.102)
[2/6] Testing API connectivity... OK (234ms)
[3/6] Validating loop configs... OK
[4/6] Checking disk space... WARNING (2.1GB free)
[5/6] Reviewing recent errors... FOUND (3 in last hour)
[6/6] Analyzing performance... OK

$ ralphx why stopped

Loop 'research' stopped at 14:32:05 because:
→ Reached max_consecutive_errors limit (5)

Suggestions:
1. Check Anthropic status: https://status.anthropic.com
2. Increase timeout: timeout: 300
```

---

## 8. Permission Management

### 8.1 Permission Files

```
Global:           ~/.claude/settings.json
Project-specific: <project>/.claude/settings.json
Local override:   <project>/.claude/settings.local.json
```

**Critical:** Permissions load at session START. Changes require new session.

### 8.2 Permission Presets

```python
RESEARCH_PERMISSIONS = {
    "permissions": {
        "allow": [
            "Read(**)", "Glob(**)", "Grep(**)",
            "WebSearch(*)", "WebFetch(*)",
        ]
    }
}

IMPLEMENTATION_PERMISSIONS = {
    "permissions": {
        "allow": [
            "Read(**)", "Write(**)", "Edit(**)",
            "Glob(**)", "Grep(**)",
            "Bash(git *)", "Bash(python *)", "Bash(pytest *)",
            "Bash(pip *)", "Bash(npm *)", "Bash(npx *)",
        ]
    }
}
```

### 8.3 Pre-Flight Permission Check

Before starting a loop, verify permissions:

```python
def check_loop_permissions(project_path: str, loop_config: dict) -> dict:
    settings_file = Path(project_path) / ".claude" / "settings.json"

    if not settings_file.exists():
        return {"status": "missing", "hint": "Run: ralphx permissions setup"}

    # Check required tools against allowed patterns
    missing = []
    for tool in get_required_tools(loop_config):
        if not is_tool_allowed(tool, settings):
            missing.append(tool)

    if missing:
        return {"status": "insufficient", "missing": missing}

    return {"status": "ok"}
```

### 8.4 Permission Block Detection

```python
class PermissionBlockDetector:
    BLOCK_PATTERNS = [
        r"I see you haven't granted .* permissions",
        r"waiting for.*approval",
        r"I need permission to",
    ]

    def check_output(self, text: str) -> dict | None:
        for pattern in self.BLOCK_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return {"type": "permission_block", "pattern": pattern}
        return None
```

---

## 9. Guardrails System

Guardrails are markdown files injected into prompts to provide domain rules, safety constraints, and custom instructions. They allow teams to enforce coding standards, compliance requirements, and project-specific conventions across all loop iterations.

### 9.1 Directory Structure (Three Layers)

**Layer 1: Global** (`~/.ralphx/guardrails/`)
- Applies to ALL projects
- Safety rules, compliance standards

**Layer 2: Project Workspace** (`~/.ralphx/projects/{slug}/guardrails/`)
- Project-specific rules stored centrally
- Auto-detected files copied here on `ralphx add`

**Layer 3: Project Repo** (`<project>/.ralphx/guardrails/`)
- Version-controlled with project code
- Highest precedence for project rules

### 9.2 Precedence (Highest to Lowest)

1. **Mode-level overrides** (inline in loop config)
2. **Loop-level overrides** (inline in loop config)
3. **Project repo** (`.ralphx/guardrails/`) - travels with code
4. **Auto-detected files** (CLAUDE.md, .cursorrules, etc.) - copied to workspace
5. **Project workspace** (`~/.ralphx/projects/{slug}/guardrails/`)
6. **Global** (`~/.ralphx/guardrails/`)

Same filename at higher precedence **replaces** lower (no merge).

### 9.3 Categories & Injection Positions

```
┌─────────────────────────────────────────────┐
│ POSITION: start                              │
│   [Safety guardrails]                        │
├─────────────────────────────────────────────┤
│ POSITION: before_design_doc                  │
│   [System guardrails]                        │
├─────────────────────────────────────────────┤
│ {design_doc} content                         │
├─────────────────────────────────────────────┤
│ POSITION: after_design_doc                   │
│   [Domain guardrails]                        │
│   [Custom guardrails]                        │
├─────────────────────────────────────────────┤
│ [Prompt template content]                    │
├─────────────────────────────────────────────┤
│ POSITION: end                                │
│   [Output format guardrails]                 │
│   [RALPHX_TRACKING marker]                   │
└─────────────────────────────────────────────┘
```

**Categories:**
| Category | Default Position | Purpose |
|----------|-----------------|---------|
| `system` | before_design_doc | Agent identity, role definition |
| `safety` | start | Safety constraints, "never do" rules |
| `domain` | after_design_doc | Domain knowledge, terminology |
| `output` | end | Output format, schema requirements |
| `custom` | after_design_doc | Project-specific rules |

### 9.4 Auto-Detection of AI Instruction Files

When running `ralphx add`, RalphX scans for existing AI instruction files and offers to include them:

| File/Pattern | Tool Origin | Location |
|--------------|-------------|----------|
| `CLAUDE.md` | Claude Code | Root, subdirs |
| `AGENTS.md` | OpenAI Codex, Gemini CLI | Root |
| `.cursorrules` | Cursor (legacy) | Root |
| `.cursor/rules/*.md` | Cursor (current) | `.cursor/rules/` |
| `.github/copilot-instructions.md` | GitHub Copilot | `.github/` |
| `.github/instructions/*.md` | GitHub Copilot | `.github/instructions/` |
| `.continuerules` | Continue | Root |
| `.continue/rules/*.md` | Continue | `.continue/rules/` |
| `.junie/guidelines.md` | JetBrains Junie | `.junie/` |
| `.aiassistant/rules/*.md` | JetBrains AI | `.aiassistant/rules/` |
| `GEMINI.md` | Gemini CLI | Root |
| `llms.txt` | LangChain standard | Root |
| `llms-full.txt` | LangChain standard | Root |
| `AI.md`, `AI_INSTRUCTIONS.md` | Informal | Root |
| `STYLEGUIDE.md` | Informal | Root |
| `CONTRIBUTING.md` | Git standard | Root |

**Detection Flow:**
```
$ ralphx add ~/my-project --name "My App"

Scanning for existing AI instruction files...

Found 3 files:
  ✓ CLAUDE.md (2.1 KB) - Claude Code instructions
  ✓ .cursor/rules/backend.md (1.4 KB) - Cursor rules
  ✓ llms.txt (892 B) - LLM context file

Include as guardrails? [Y/n/select]
```

**CLI Flags:**
- `--no-detect` - skip auto-detection entirely
- `--detect-only` - show detected files without prompting to include

### 9.5 Security Considerations

**WARNING**: Auto-detected files come from potentially untrusted sources (cloned repos).

**Mitigations:**
1. **User confirmation required** - never auto-include without explicit approval
2. **Content preview** - show first 500 chars before including
3. **Warning for cloned repos** - if `.git/config` shows remote origin, warn: "This project was cloned from {remote}. AI instruction files may contain prompt injection."
4. **No symlink following** - refuse to include symlinked files
5. **Size limit** - reject files over 50KB at detection time

**Symlink Policy:**
```python
if file.is_symlink():
    logger.warning(f"Skipping symlink: {file}")
    continue
```

### 9.6 Template Variable Support

Guardrails can use template variables from context:
```markdown
<!-- domain/healthcare.md -->
# {domain} Rules

You are building {target_system}...
```

**Undefined variable handling:**
- If a guardrail uses `{variable}` that doesn't exist in context, **ERROR at load time**
- Error message: `Guardrail "domain/healthcare.md" uses undefined variable {target_system}`
- This is a configuration error - fail fast

**Per-mode variable scoping:**
- Variables are evaluated based on the MODE being executed, not globally
- If a guardrail is only included in certain modes (via `modes: [deep]`), variables only need to be defined for those modes
- Example: `{web_search_context}` used in `safety/web-research.md` only needs to exist in `deep` mode if that guardrail has `modes: [deep]`
- Validation (`ralphx guardrails validate`) checks ALL mode combinations to catch undefined variables early

**Validation:**
```bash
$ ralphx guardrails validate --project my-app

Validating guardrails...
✓ system/identity.md - OK (all modes)
✓ safety/web-research.md - OK (deep mode only)
✗ domain/healthcare.md - ERROR: undefined variable {target_system} in turbo mode
  Hint: Add to loop config: context.custom_context.target_system
        Or restrict guardrail to specific modes: modes: [deep]

1 error found. Fix before running loops.
```

### 9.7 Caching Strategy

**Guardrails are cached per-run:**
- On run start, all applicable guardrails are loaded and cached
- Cache key: file path + mtime
- If guardrail file is modified during run, change takes effect on NEXT run
- If guardrail file is DELETED during run, cached content is used (no error)

**Rationale:** Ensures consistent prompts within a single run. Avoids mid-run surprises.

### 9.8 Size Limits

| Limit | Value | Enforcement |
|-------|-------|-------------|
| Single guardrail file | 50 KB | At file load time |
| Single guardrail file (min) | 1 byte | At file load time (empty files rejected) |
| Total guardrails | 500 KB | At prompt assembly |
| Total prompt | 1 MB | At prompt assembly |

**When limit exceeded:**
- Single file: `ERROR: Guardrail "domain/huge.md" exceeds 50KB limit (actual: 127KB)`
- Total guardrails: `WARNING: Total guardrails (623KB) exceeds 500KB. Consider reducing.`
- Total prompt: `ERROR: Assembled prompt (1.2MB) exceeds 1MB limit. Reduce guardrails or design doc.`

**Empty file handling:**
- Empty guardrail files (0 bytes or whitespace-only) are **rejected with error**
- Error message: `ERROR: Guardrail "domain/empty.md" is empty (must have content)`
- Rationale: Empty files indicate misconfiguration, not intentional no-op

### 9.9 Guardrail Templates

RalphX includes built-in templates for common project types:

```
$ ralphx add ~/my-project --name "My App"

? What type of project is this?
  ❯ Web Application (React/Vue/Angular)
    Backend API (Python/Node/Go)
    Healthcare/HIPAA
    E-commerce
    CLI Tool
    Custom (no template)

Selected: Healthcare/HIPAA

✓ Added template guardrails:
  - guardrails/safety/hipaa-compliance.md
  - guardrails/safety/phi-protection.md
  - guardrails/domain/healthcare-terminology.md
```

**Template locations:**
```
~/.ralphx/templates/guardrails/
├── web-app/
│   ├── safety/security-best-practices.md
│   └── domain/frontend-patterns.md
├── backend-api/
│   ├── safety/api-security.md
│   └── domain/rest-conventions.md
├── healthcare/
│   ├── safety/hipaa-compliance.md
│   ├── safety/phi-protection.md
│   └── domain/healthcare-terminology.md
└── ...
```

---

## 10. SQLite Storage

### 10.1 Database Location

All RalphX data is stored in a single SQLite database:
```
~/.ralphx/ralphx.db
```

**Note:** Claude session logs remain in Claude's location (`~/.claude/projects/<path>/<session>.jsonl`) for live tailing compatibility.

### 10.2 Configuration

| Setting | Value | Purpose |
|---------|-------|---------|
| File permissions | `0600` | Owner read/write only - contains project paths and work items |
| Journal mode | WAL | Write-Ahead Logging for concurrent access |
| Connection pool | Single writer, multiple readers | Via connection pool |
| Backup | Daily automatic | `~/.ralphx/ralphx.db.bak` |

### 10.3 Schema

```sql
-- Main tables
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    design_doc TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE loops (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    config_yaml TEXT NOT NULL,  -- Full YAML stored as text
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    UNIQUE(project_id, name)
);

CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    loop_name TEXT NOT NULL,
    status TEXT NOT NULL,  -- active, completed, error, aborted
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    iterations_completed INTEGER DEFAULT 0,
    items_generated INTEGER DEFAULT 0,
    error_message TEXT
);

CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    iteration INTEGER NOT NULL,
    mode TEXT,
    started_at TIMESTAMP,
    duration_seconds REAL,
    status TEXT,
    items_added TEXT  -- JSON array of item IDs
);

CREATE TABLE work_items (
    id TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    priority INTEGER,
    content TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    category TEXT,
    tags TEXT,  -- JSON array
    metadata TEXT,  -- JSON object
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, id)
);

CREATE TABLE checkpoints (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    run_id TEXT,
    loop_name TEXT,
    iteration INTEGER,
    status TEXT,
    data TEXT,  -- JSON blob
    created_at TIMESTAMP
);

-- Guardrails metadata (content stays in files, metadata in DB)
CREATE TABLE guardrails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    category TEXT NOT NULL,        -- system, safety, domain, output, custom
    filename TEXT NOT NULL,
    source TEXT NOT NULL,          -- global, workspace, repo, auto-detected
    file_path TEXT NOT NULL,       -- actual filesystem path
    file_mtime REAL,               -- for cache invalidation
    file_size INTEGER,
    enabled BOOLEAN DEFAULT TRUE,
    loops TEXT,                    -- JSON array of loop names (null = all)
    modes TEXT,                    -- JSON array of mode names (null = all)
    position TEXT DEFAULT 'after_design_doc',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, category, filename)
);

-- Note: guardrails.project_id can be NULL for global guardrails

-- Execution logs
CREATE TABLE logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
    level TEXT NOT NULL,           -- debug, info, warning, error
    message TEXT NOT NULL,
    metadata TEXT,                 -- JSON blob for structured data
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX idx_work_items_status ON work_items(project_id, status);
CREATE INDEX idx_work_items_category ON work_items(project_id, category);
CREATE INDEX idx_work_items_priority ON work_items(project_id, priority);
CREATE INDEX idx_work_items_created ON work_items(project_id, created_at);
CREATE INDEX idx_sessions_run ON sessions(run_id);
CREATE INDEX idx_runs_project ON runs(project_id, status);
CREATE INDEX idx_guardrails_project ON guardrails(project_id, enabled);
CREATE INDEX idx_guardrails_source ON guardrails(source);  -- Filter by global/workspace/repo/auto-detected
CREATE INDEX idx_logs_run ON logs(run_id, timestamp);
CREATE INDEX idx_logs_level ON logs(project_id, level, timestamp);
```

### 10.4 Migration from Existing Data

If upgrading from a previous RalphX version with YAML/JSONL storage:
```bash
$ ralphx migrate

Migrating to SQLite...
✓ Migrated 3 projects
✓ Migrated 12 loops
✓ Migrated 8,472 work items
✓ Created indexes

Backup created: ~/.ralphx/backup-20260113/
```

---

## 11. CLI Commands

```bash
# Project management
ralphx add <path> --name "Project Name" --design-doc "design/PRD.md"
ralphx add <path> --no-detect      # Skip auto-detection of AI files
ralphx add <path> --detect-only    # Show detected files without prompting
ralphx projects                    # List all projects
ralphx remove <project>           # Remove from workspace

# Loop execution
ralphx run <loop> --project <slug> --iterations 10
ralphx run research -v            # Verbose output
ralphx run research --debug       # Full debug output
ralphx run research --dry-run     # Test without executing

# Server
ralphx serve                       # Start dashboard (default port 8765)
ralphx serve --port 9000          # Custom port

# Diagnostics
ralphx doctor                      # Check prerequisites
ralphx diagnose                    # Full diagnostics
ralphx why stopped                 # Explain why loop stopped
ralphx test                        # Quick smoke test

# Permissions
ralphx permissions setup           # Configure for project
ralphx permissions check           # Verify permissions
ralphx permissions add "Bash(*)"   # Add specific permission

# Guardrails
ralphx guardrails list --project my-app           # List all guardrails
ralphx guardrails show domain/rules.md --project my-app  # Show content
ralphx guardrails preview research --mode turbo   # Preview assembled prompt
ralphx guardrails validate --project my-app       # Validate variable usage
ralphx guardrails init --project my-app           # Initialize guardrails dir

# Templates
ralphx template export <project> <loop> --name "template-name"
ralphx template apply <project> <template-name>

# Database
ralphx migrate                     # Migrate from YAML/JSONL to SQLite

# Help
ralphx help                        # Overview
ralphx help loops                  # How loops work
ralphx help permissions            # Permission guide
ralphx help guardrails             # Guardrails guide
ralphx help debugging              # Troubleshooting
```

---

## 12. MCP Server Mode

RalphX can run as an MCP server for Claude Code integration:

```bash
# Register with Claude Code
claude mcp add ralphx -e PYTHONDONTWRITEBYTECODE=1 -- "$(which ralphx)" mcp
```

**MCP Tools Exposed:**

| Tool | Description |
|------|-------------|
| `ralphx_list_projects` | List all registered projects |
| `ralphx_list_loops` | List loops for a project |
| `ralphx_start_loop` | Start a loop running |
| `ralphx_stop_loop` | Stop a running loop |
| `ralphx_get_status` | Get loop status and progress |
| `ralphx_list_items` | List work items |
| `ralphx_add_item` | Add a new work item |

**Usage in Claude Code:**
```
User: "Start my PRD research loop for the saas-app project"
Claude: [calls ralphx_start_loop(project="saas-app", loop="research")]
        "Started research loop. Currently at iteration 0."
```

---

## 13. Directory Structure

```
ralphx/
├── pyproject.toml
├── ralphx/
│   ├── __init__.py
│   ├── cli.py                    # CLI entrypoint
│   │
│   ├── core/
│   │   ├── loop.py               # Loop config parsing
│   │   ├── executor.py           # Iteration execution
│   │   ├── project.py            # Project management
│   │   ├── run_manager.py        # Run tracking
│   │   ├── session_manager.py    # Session tracking
│   │   ├── session_watcher.py    # Session tailing
│   │   ├── checkpoint.py         # Crash recovery
│   │   ├── doctor.py             # Prerequisites check
│   │   ├── permissions.py        # Permission management
│   │   ├── project_lock.py       # Cross-platform locking
│   │   ├── guardrails.py         # Guardrails loading & caching
│   │   └── database.py           # SQLite connection & schema
│   │
│   ├── adapters/
│   │   ├── base.py
│   │   ├── claude_cli.py         # Primary adapter
│   │   ├── anthropic.py
│   │   └── openai.py
│   │
│   ├── stores/
│   │   ├── base.py
│   │   └── sqlite.py             # Primary storage backend
│   │
│   ├── api/
│   │   ├── main.py
│   │   └── routes/
│   │       ├── projects.py
│   │       ├── loops.py
│   │       ├── items.py
│   │       └── stream.py         # SSE endpoints for tailing
│   │
│   └── mcp_server.py             # MCP protocol
│
├── frontend/
│   ├── package.json
│   └── src/
│       ├── components/
│       │   ├── SessionTail.tsx   # Live session view
│       │   ├── LoopCard.tsx
│       │   ├── RunHistory.tsx
│       │   └── PermissionStatus.tsx
│       ├── stores/
│       │   └── dashboard.ts      # Zustand state
│       └── pages/
│
├── examples/
│   ├── prd_research/
│   └── code_review/
│
└── tests/
```

---

## 14. Implementation Phases

### Phase 0: Prerequisites (Do First)
- [ ] First-run workspace creation with welcome message
- [ ] `ralphx doctor` with full prerequisite checks
- [ ] Port conflict handling (auto-find available port)
- [ ] Actionable error messages with hints
- [ ] `ralphx help`, `ralphx diagnose`, `ralphx why` commands
- [ ] Design doc validation (size, format, encoding)
- [ ] Mode-aware activity timeouts

### Phase 1: Core CLI + Engine
- [ ] `pyproject.toml` with uv/pip config
- [ ] `cli.py` with all commands
- [ ] `core/loop.py` - YAML config parsing
- [ ] `core/executor.py` with:
  - [ ] Infinite loop detection
  - [ ] Permission block handling
  - [ ] Heartbeat system
  - [ ] Checkpoint/recovery
  - [ ] Exponential backoff
- [ ] `core/project.py` - Multi-project management
- [ ] `core/run_manager.py` - Run tracking with markers
- [ ] `core/session_manager.py` - Session tracking
- [ ] `adapters/claude_cli.py` with permission handling
- [ ] `stores/sqlite.py` - SQLite operations with WAL mode
- [ ] Templates for `ralphx add` wizard

### Phase 2: API Server
- [ ] FastAPI app setup
- [ ] Project CRUD endpoints
- [ ] Loop control endpoints
- [ ] Work item endpoints
- [ ] SSE streaming for session tailing
- [ ] Static file serving for frontend

### Phase 3: Dashboard MVP
- [ ] React + Vite + Tailwind setup
- [ ] Multi-project sidebar
- [ ] Loop control panel
- [ ] **Live session tail view** (SessionTail.tsx)
- [ ] Work item browser
- [ ] Run history with session links
- [ ] Real-time SSE integration

### Phase 4: Visual Config Editor
- [ ] Loop editor form
- [ ] Model selection dropdowns
- [ ] Mode weight sliders
- [ ] Category/phase editors
- [ ] Prompt template editor (Monaco)

### Phase 5: MCP Server
- [ ] MCP protocol implementation
- [ ] Tools: list_projects, list_loops, start/stop_loop
- [ ] Integration with `claude mcp add`

### Phase 6: Polish
- [ ] Loop creation wizard
- [ ] Template sharing (export/import)
- [ ] Documentation + examples
- [ ] Docker packaging

---

## 15. Technical Decisions

### Why Global Workspace?
- Cross-project visibility in single dashboard
- Project repos stay clean (no clutter)
- Centralized templates and configs
- Single server for all projects

### Why SSE over WebSockets?
- Simpler (HTTP-based)
- Auto-reconnection built-in
- Sufficient for one-way streaming
- Better proxy support

### Why YAML for Configuration?
- Human-readable and editable
- Git-friendly (line-based diffs)
- Industry standard
- Schema validation via Pydantic

### Why Claude CLI as Default?
- Battle-tested in Ralph
- Built-in tool execution
- Streaming support
- Session management
- **Session logs enable live tailing**

### Why SQLite for Storage?
- **Single file**: All data in `~/.ralphx/ralphx.db` - easy backup, migration
- **Fast queries**: Indexed queries for work items, sessions, runs
- **Atomic transactions**: Crash-safe writes, no data corruption
- **Concurrent access**: WAL mode enables multiple readers with single writer
- **Scalable**: Handles millions of work items efficiently

**Note**: Claude session logs remain in Claude's location (`~/.claude/projects/`) as JSONL files for live tailing compatibility.

### Scalability Limits

**Session Tailing (100ms polling):**
- Designed for single active session per project
- For multiple concurrent sessions, consider reducing poll frequency or using inotify/FSEvents
- Not recommended for >10 simultaneous tailing connections

**Session Discovery:**
- Session index in SQLite provides O(1) lookup for indexed sessions
- Full log scan is O(n) where n = number of session files
- Recommend periodic cleanup: `ralphx cleanup --older-than 30d`
- For projects with >1000 sessions, index rebuild may take several seconds

**Work Items (SQLite):**
- Performant up to millions of items per project
- Indexed by status, category, priority, created_at
- Query performance remains constant regardless of dataset size

**Concurrent Loops:**
- One loop per project (enforced by project lock)
- Multiple projects can run loops concurrently
- Recommended: max 5 concurrent loops to avoid API rate limits

---

## 16. Key Differentiators

### vs. LangChain/LangGraph
- **Simpler**: YAML config instead of graph DSL
- **Observable**: Built-in dashboard with live session tailing
- **Focused**: Purpose-built for autonomous loops

### vs. AutoGPT/CrewAI
- **Configurable**: Domain-agnostic via config
- **Controlled**: Phase-based execution
- **Resumable**: Crash recovery, checkpoints

### vs. Flowise
- **Code-first**: YAML configs, not drag-and-drop
- **Autonomous**: Long-running loops
- **Live visibility**: Watch Claude work in real-time

---

## 17. Testing Strategy

### 15.1 Unit Testing

**SessionTailer Testing:**
```python
# tests/test_session_tailer.py
import pytest
from unittest.mock import AsyncMock, patch
import tempfile
import json

class TestSessionTailer:
    def test_handles_file_deletion(self, tmp_path):
        """Tailer should yield error event when file is deleted."""
        session_file = tmp_path / "test.jsonl"
        session_file.write_text('{"type": "init"}\n')

        tailer = SessionTailer(session_file)
        # Start tailing, then delete file
        session_file.unlink()
        # Verify tailer yields error event, not exception

    def test_handles_truncation(self, tmp_path):
        """Tailer should reset position when file is truncated."""
        # Write, read, truncate, verify re-read from start

    def test_handles_partial_json_line(self, tmp_path):
        """Tailer should wait for complete JSON line."""
        # Write partial line, verify no parse, complete line, verify parse
```

**Claude CLI Adapter Testing:**
```python
# Mock subprocess for deterministic testing
@pytest.fixture
def mock_claude_cli():
    with patch('asyncio.create_subprocess_exec') as mock:
        proc = AsyncMock()
        proc.stdout.__aiter__ = AsyncMock(return_value=iter([
            b'{"type":"init","session_id":"test-123"}\n',
            b'{"type":"text","content":"Hello"}\n',
        ]))
        proc.returncode = 0
        mock.return_value = proc
        yield mock
```

### 15.2 Integration Testing

**Crash Recovery Test:**
```python
def test_checkpoint_recovery():
    """Simulate crash mid-iteration and verify recovery."""
    # 1. Start loop, let it save checkpoint with status="in_progress"
    # 2. Kill process (simulate crash)
    # 3. Start new instance
    # 4. Verify it resumes from checkpoint iteration
    # 5. Verify no duplicate items created
```

**Session Discovery Test:**
```python
def test_session_discovery_fallback():
    """Verify session discovery when stream-json capture fails."""
    # 1. Create session file with RALPHX_TRACKING marker
    # 2. Call fallback_by_timing()
    # 3. Verify correct session_id returned
```

### 15.3 End-to-End Testing

```bash
# tests/e2e/test_full_loop.sh
# Requires: Claude CLI installed and authenticated

# 1. Create test project
ralphx add /tmp/test-project --name "E2E Test"

# 2. Run single iteration
ralphx run research --project e2e-test --iterations 1

# 3. Verify items created
test $(ralphx items count --project e2e-test) -gt 0

# 4. Test crash recovery
ralphx run research --project e2e-test --iterations 10 &
PID=$!
sleep 5
kill -9 $PID  # Force kill

# 5. Resume and verify
ralphx run research --project e2e-test --resume
```

### 15.4 Mock Strategies

**For Claude CLI:**
- Use `--dry-run` mode that echoes prompt without calling Claude
- Environment variable `RALPHX_MOCK_CLI=1` for CI/CD
- Mock adapter that returns canned responses from fixtures

**For Session Files:**
- Create temp directory with pre-populated JSONL files
- Fixture factory for different session states (complete, partial, corrupted)

---

## 18. References

### Anthropic
- [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [Claude Code Settings](https://code.claude.com/docs/en/settings)
- [Claude Code MCP](https://code.claude.com/docs/en/mcp)
- [Claude Code Permissions](https://www.eesel.ai/blog/claude-code-permissions)

### Known Issues
- [#7091 - Sub-agent stuck indefinitely](https://github.com/anthropics/claude-code/issues/7091)
- [#208 - Windows SDK hangs](https://github.com/anthropics/claude-agent-sdk-python/issues/208)
- [#15321 - Kernel 5.15.0 hangs](https://github.com/anthropics/claude-code/issues/15321)
- [#5010 - WSL /mnt/ path issues](https://github.com/anthropics/claude-code/issues/5010)

### Session Monitoring
- [Claude Code Session Location](https://gist.github.com/BoQsc/8b392c3293107edddbd00117ada0fdd2)
- [claude-code-log Tool](https://github.com/daaain/claude-code-log)
- [Stream-JSON Chaining](https://github.com/ruvnet/claude-flow/wiki/Stream-Chaining)
- [--output-format stream-json](https://claudelog.com/faqs/what-is-output-format-in-claude-code/)

### Agent Frameworks
- [AI Agent Frameworks 2026](https://www.instaclustr.com/education/agentic-ai/agentic-ai-frameworks-top-8-options-in-2026/)
- [Agent Observability](https://opentelemetry.io/blog/2025/ai-agent-observability/)
- [Agent Debugging Platforms](https://www.getmaxim.ai/articles/the-5-best-agent-debugging-platforms-in-2026/)
