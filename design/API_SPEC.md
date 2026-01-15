# RalphX API Specification

Base URL: `http://localhost:8765/api`

## Authentication

For local development, no authentication required. Production deployments can enable API key authentication via the `RALPHX_API_KEY` environment variable.

```
Authorization: Bearer <api_key>
```

---

## Projects

### List All Projects

```
GET /projects
```

**Response:**
```json
{
  "projects": [
    {
      "name": "My SaaS App",
      "slug": "my-saas-app",
      "path": "/home/user/my-project",
      "design_doc": "design/DESIGN.md",
      "created_at": "2026-01-13T10:00:00Z",
      "id": "550e8400-e29b-41d4-a716-446655440000"
    }
  ]
}
```

### Add Project

```
POST /projects
```

**Request Body:**
```json
{
  "path": "/home/user/my-project",
  "name": "My SaaS App",
  "design_doc": "design/DESIGN.md"
}
```

**Response:**
```json
{
  "project": {
    "name": "My SaaS App",
    "slug": "my-saas-app",
    "path": "/home/user/my-project",
    "design_doc": "design/DESIGN.md",
    "created_at": "2026-01-13T10:00:00Z",
    "id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

### Get Project Details

```
GET /projects/{slug}
```

**Response:**
```json
{
  "project": {
    "name": "My SaaS App",
    "slug": "my-saas-app",
    "path": "/home/user/my-project",
    "design_doc": "design/DESIGN.md",
    "created_at": "2026-01-13T10:00:00Z",
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "loops": [
      {"name": "research", "status": "running"},
      {"name": "implementation", "status": "idle"}
    ]
  }
}
```

### Remove Project

```
DELETE /projects/{slug}
```

**Response:**
```json
{
  "removed": true,
  "message": "Project removed from RalphX workspace. Project files not modified."
}
```

### Get Active Run for Project

```
GET /projects/{slug}/active
```

**Response (when active):**
```json
{
  "active": true,
  "runId": "my-saas-app-20260113-143052-a1b2c3d4",
  "loopId": "research",
  "iteration": 47,
  "sessionId": "abc123-def456",
  "startedAt": "2026-01-13T14:30:52Z"
}
```

**Response (when idle):**
```json
{
  "active": false
}
```

### List Runs for Project

```
GET /projects/{slug}/runs?limit=20&offset=0
```

**Query Parameters:**
- `limit` (default: 20) - Number of runs to return
- `offset` (default: 0) - Offset for pagination
- `loop` - Filter by loop name
- `status` - Filter by status: active, completed, error

**Response:**
```json
{
  "runs": [
    {
      "run_id": "my-saas-app-20260113-143052-a1b2c3d4",
      "loop_name": "research",
      "status": "completed",
      "iterations_completed": 100,
      "items_generated": 412,
      "started_at": "2026-01-13T14:30:52Z",
      "completed_at": "2026-01-13T22:30:52Z",
      "session_count": 100
    }
  ],
  "total": 15,
  "has_more": false
}
```

### List Sessions for Run

```
GET /projects/{slug}/runs/{run_id}/sessions
```

**Response:**
```json
{
  "sessions": [
    {
      "session_id": "abc123-def456",
      "iteration": 47,
      "mode": "turbo",
      "started_at": "2026-01-13T14:35:22Z",
      "duration_seconds": 16,
      "items_added": 5,
      "status": "completed"
    }
  ]
}
```

---

## Loops

**IMPORTANT:** All loop endpoints are scoped to a project. Loops exist under `~/.ralphx/projects/{slug}/loops/`.

### List Loops for Project

```
GET /projects/{slug}/loops
```

**Response:**
```json
{
  "loops": [
    {
      "id": "prd_research",
      "display_name": "PRD Research Loop",
      "type": "generator",
      "status": "running",
      "iteration": 47,
      "items_count": 3847
    },
    {
      "id": "prd_implementation",
      "display_name": "PRD Implementation",
      "type": "consumer",
      "status": "idle",
      "iteration": 0,
      "items_count": 3847
    }
  ]
}
```

### Get Loop Details

```
GET /projects/{slug}/loops/{loop_id}
```

**Response:**
```json
{
  "id": "prd_research",
  "display_name": "PRD Research Loop",
  "description": "Discovers and generates user stories",
  "type": "generator",
  "config": {
    "modes": {
      "turbo": { "timeout": 180, "model": "sonnet", "tools": [] },
      "deep": { "timeout": 900, "model": "sonnet", "tools": ["WebSearch", "WebFetch"] }
    },
    "mode_selection": { "strategy": "weighted_random", "weights": { "turbo": 85, "deep": 15 } },
    "limits": { "max_iterations": 100, "max_runtime_seconds": 28800 }
  },
  "state": {
    "status": "running",
    "iteration": 47,
    "start_time": "2026-01-13T10:30:00Z",
    "elapsed_seconds": 8100,
    "consecutive_errors": 0,
    "no_progress_count": 0,
    "items_added": 412,
    "current_mode": "turbo",
    "current_category": "ANS"
  }
}
```

### Start Loop

```
POST /projects/{slug}/loops/{loop_id}/start
```

**Request Body (optional):**
```json
{
  "max_iterations": 50,
  "mode": "turbo",
  "category": "ANS"
}
```

**Response:**
```json
{
  "status": "starting",
  "message": "Loop prd_research is starting"
}
```

### Pause Loop

```
POST /projects/{slug}/loops/{loop_id}/pause
```

**Response:**
```json
{
  "status": "paused",
  "iteration": 47,
  "can_resume": true
}
```

### Resume Loop

```
POST /projects/{slug}/loops/{loop_id}/resume
```

**Response:**
```json
{
  "status": "running",
  "iteration": 47
}
```

### Stop Loop

```
POST /projects/{slug}/loops/{loop_id}/stop
```

**Response:**
```json
{
  "status": "stopping",
  "message": "Loop will stop after current iteration completes"
}
```

### Get Loop Logs

```
GET /projects/{slug}/loops/{loop_id}/logs?limit=100&offset=0&level=info
```

**Query Parameters:**
- `limit` (default: 100) - Number of log entries
- `offset` (default: 0) - Offset for pagination
- `level` (default: all) - Filter by level: debug, info, warning, error
- `since` - ISO timestamp to get logs after

**Response:**
```json
{
  "logs": [
    {
      "timestamp": "2026-01-13T12:34:22Z",
      "level": "info",
      "message": "Iteration 47 started",
      "metadata": { "mode": "turbo", "category": "ANS" }
    },
    {
      "timestamp": "2026-01-13T12:34:45Z",
      "level": "info",
      "message": "Extracted 8 stories",
      "metadata": { "ids": ["ANS-089", "ANS-090", "ANS-091"] }
    }
  ],
  "total": 1523,
  "has_more": true
}
```

### Stream Loop Events (SSE)

```
GET /projects/{slug}/loops/{loop_id}/stream
```

**Response:** Server-Sent Events stream

```
event: status
data: {"status": "running", "iteration": 47}

event: log
data: {"timestamp": "2026-01-13T12:34:22Z", "level": "info", "message": "Iteration 47 started"}

event: progress
data: {"iteration": 47, "items_added": 8, "current_mode": "turbo", "current_category": "ANS"}

event: item_added
data: {"id": "ANS-089", "content": "As an anesthesiologist...", "category": "ANS"}

event: error
data: {"message": "Timeout exceeded", "recoverable": true}

event: complete
data: {"total_iterations": 100, "total_items_added": 412, "runtime_seconds": 28800}
```

### Tail Loop Session (SSE) - Live Session Monitoring

```
GET /projects/{slug}/loops/{loop_id}/tail
```

Provides real-time streaming of Claude session activity, like `tail -f` for the session log.

**Response:** Server-Sent Events stream

```
event: waiting
data: {"message": "Waiting for Claude session to start..."}

event: text
data: {"timestamp": "2026-01-13T14:35:22Z", "content": "I'll extract user stories from the design document...", "role": "assistant"}

event: tool_call
data: {"timestamp": "2026-01-13T14:35:24Z", "tool": "Read", "id": "toolu_01...", "input": "design/DESIGN.md"}

event: tool_result
data: {"timestamp": "2026-01-13T14:35:26Z", "tool_use_id": "toolu_01...", "success": true, "preview": "45,231 bytes read"}

event: text
data: {"timestamp": "2026-01-13T14:35:28Z", "content": "Based on the RCM portal design, I've identified several user stories...", "role": "assistant"}

event: complete
data: {"message": "Session complete"}
```

**UI Display:**
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
│ ▌                                                              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Sessions

**IMPORTANT:** All session endpoints are scoped to a project. The API MUST validate that the session actually belongs to the specified project before returning data. This prevents cross-project data leakage.

### Tail Specific Session (SSE)

```
GET /projects/{slug}/sessions/{session_id}/tail
```

Tail a specific session by ID (for viewing past runs or replaying sessions).

**Security Note:** The API MUST verify that `session_id` exists in the session index for project `{slug}` or that the session file contains a RALPHX_TRACKING marker matching the project. Return 404 if session does not belong to project.

**Response:** Server-Sent Events stream (same format as `/projects/{slug}/loops/{loop_id}/tail`)

### Get Session Details

```
GET /projects/{slug}/sessions/{session_id}
```

**Response:**
```json
{
  "session_id": "abc123-def456",
  "run_id": "my-saas-app-20260113-143052-a1b2c3d4",
  "iteration": 47,
  "mode": "turbo",
  "started_at": "2026-01-13T14:35:22Z",
  "duration_seconds": 16,
  "status": "completed",
  "stats": {
    "tool_calls": 3,
    "text_blocks": 5,
    "tokens_in": 2341,
    "tokens_out": 1203
  },
  "items_added": ["ANS-089", "ANS-090", "ANS-091", "ANS-092", "ANS-093"],
  "log_path": "~/.claude/projects/-home-user-myproject/abc123-def456.jsonl"
}
```

### Get Session Log (Full)

```
GET /projects/{slug}/sessions/{session_id}/log
```

Returns the full session log for detailed analysis.

**Security Note:** Session logs may contain sensitive data from prompts. In production deployments, consider:
1. Redacting API keys or secrets that may appear in logs
2. Limiting access to session logs based on user roles
3. Auto-expiring old session logs

**Query Parameters:**
- `format` (default: "parsed") - "parsed" for structured data, "raw" for JSONL

**Response (format=parsed):**
```json
{
  "entries": [
    {
      "type": "user",
      "timestamp": "2026-01-13T14:35:22Z",
      "content": [
        {"type": "text", "text": "You are a PRD research assistant..."}
      ]
    },
    {
      "type": "assistant",
      "timestamp": "2026-01-13T14:35:24Z",
      "content": [
        {"type": "text", "text": "I'll extract user stories..."},
        {"type": "tool_use", "name": "Read", "input": {"file_path": "design/DESIGN.md"}}
      ]
    }
  ]
}
```

---

## Work Items

**IMPORTANT:** All work item endpoints are scoped to a project. Items are stored at `~/.ralphx/projects/{slug}/data/`.

### List Work Items

```
GET /projects/{slug}/items?status=pending&category=ANS&limit=25&offset=0
```

**Query Parameters:**
- `status` - Filter by status: pending, in_progress, completed, failed, skipped, duplicate, external
- `category` - Filter by category prefix
- `priority_min` / `priority_max` - Filter by priority range
- `search` - Full-text search in content
- `sort` - Sort field: id, priority, created_at, updated_at
- `order` - Sort order: asc, desc
- `limit` (default: 25)
- `offset` (default: 0)

**Response:**
```json
{
  "items": [
    {
      "id": "ANS-089",
      "priority": 15,
      "content": "As an anesthesiologist, I want to track concurrent cases...",
      "status": "pending",
      "category": "ANS",
      "tags": ["billing", "concurrency"],
      "created_at": "2026-01-13T10:45:00Z",
      "updated_at": "2026-01-13T10:45:00Z"
    }
  ],
  "total": 3102,
  "has_more": true
}
```

### Get Single Item

```
GET /projects/{slug}/items/{item_id}
```

**Response:**
```json
{
  "id": "ANS-089",
  "priority": 15,
  "content": "As an anesthesiologist, I want to track concurrent cases to ensure proper medical direction billing",
  "acceptance_criteria": [
    "System tracks concurrent anesthesia cases per provider",
    "Alerts when medical direction limits exceeded",
    "Automatically applies correct modifiers"
  ],
  "status": "pending",
  "category": "ANS",
  "tags": ["billing", "concurrency", "medical-direction"],
  "created_at": "2026-01-13T10:45:00Z",
  "updated_at": "2026-01-13T10:45:00Z",
  "metadata": {
    "source_mode": "deep",
    "source_iteration": 23
  }
}
```

### Create Item

```
POST /projects/{slug}/items
```

**Request Body:**
```json
{
  "id": "ANS-090",
  "priority": 20,
  "content": "As a billing manager, I want to view TEFRA compliance reports",
  "acceptance_criteria": [
    "Report shows all TEFRA-relevant encounters",
    "Highlights potential compliance issues"
  ],
  "category": "ANS",
  "tags": ["compliance", "reporting"]
}
```

**Response:**
```json
{
  "id": "ANS-090",
  "created": true,
  "message": "Item created successfully"
}
```

### Update Item

```
PATCH /projects/{slug}/items/{item_id}
```

**Request Body:**
```json
{
  "status": "completed",
  "metadata": {
    "implemented_at": "2026-01-13T14:30:00Z",
    "commit": "abc123"
  }
}
```

**Response:**
```json
{
  "id": "ANS-089",
  "updated": true
}
```

### Mark Item as Duplicate

```
POST /projects/{slug}/items/{item_id}/duplicate
```

**Request Body:**
```json
{
  "duplicate_of": "ANS-045"
}
```

### Mark Item as External

```
POST /projects/{slug}/items/{item_id}/external
```

**Request Body:**
```json
{
  "product": "ClaimMaker"
}
```

### Get Item Statistics

```
GET /projects/{slug}/items/stats
```

**Response:**
```json
{
  "total": 3847,
  "by_status": {
    "pending": 3102,
    "completed": 612,
    "duplicate": 89,
    "external": 34,
    "skipped": 10
  },
  "by_category": {
    "ANS": { "total": 89, "pending": 72, "completed": 15 },
    "FND": { "total": 45, "pending": 12, "completed": 33 },
    "CLM": { "total": 156, "pending": 134, "completed": 22 }
  },
  "by_phase": {
    "1": { "total": 234, "pending": 45, "completed": 189 },
    "2": { "total": 567, "pending": 423, "completed": 144 }
  }
}
```

---

## Categories

**IMPORTANT:** Categories are project-specific.

### List Categories

```
GET /projects/{slug}/categories
```

**Response:**
```json
{
  "categories": [
    {
      "prefix": "ANS",
      "name": "Anesthesia-Specific",
      "description": "Medical direction, concurrency, ASA modifiers",
      "color": "#4CAF50",
      "item_count": 89
    },
    {
      "prefix": "FND",
      "name": "Foundation",
      "description": "Core data models and system primitives",
      "color": "#2196F3",
      "item_count": 45
    }
  ]
}
```

### Get Category Details

```
GET /projects/{slug}/categories/{prefix}
```

**Response:**
```json
{
  "prefix": "ANS",
  "name": "Anesthesia-Specific",
  "description": "Medical direction, concurrency, ASA modifiers, TEFRA, time units",
  "color": "#4CAF50",
  "stats": {
    "total": 89,
    "pending": 72,
    "completed": 15,
    "duplicate": 2
  },
  "next_id": "ANS-090"
}
```

---

## Phases

**IMPORTANT:** Phases are project-specific.

### List Phases

```
GET /projects/{slug}/phases
```

**Response:**
```json
{
  "phases": [
    {
      "number": 1,
      "name": "Foundation & Infrastructure",
      "categories": ["FND", "DBM", "SEC", "ARC"],
      "stats": {
        "total": 234,
        "pending": 45,
        "completed": 189
      }
    },
    {
      "number": 2,
      "name": "Core RCM Models",
      "categories": ["PAT", "PRV", "ENC", "CLM"],
      "depends_on": [1],
      "stats": {
        "total": 567,
        "pending": 423,
        "completed": 144
      }
    }
  ]
}
```

---

## Guardrails

Guardrails are markdown files injected into prompts to provide domain rules, safety constraints, and custom instructions. See DESIGN.md Section 9 for full details.

**IMPORTANT:** All guardrail endpoints are scoped to a project.

### List All Guardrails

```
GET /projects/{slug}/guardrails
```

**Query Parameters:**
- `category` - Filter by category: system, safety, domain, output, custom
- `source` - Filter by source: global, workspace, repo, auto-detected
- `enabled` - Filter by enabled status: true, false

**Response:**
```json
{
  "guardrails": [
    {
      "category": "safety",
      "filename": "hipaa.md",
      "source": "global",
      "file_path": "~/.ralphx/guardrails/safety/hipaa.md",
      "file_size": 2134,
      "enabled": true,
      "position": "start",
      "loops": null,
      "modes": null,
      "created_at": "2026-01-13T10:00:00Z"
    },
    {
      "category": "domain",
      "filename": "healthcare-rules.md",
      "source": "workspace",
      "file_path": "~/.ralphx/projects/my-app/guardrails/domain/healthcare-rules.md",
      "file_size": 4521,
      "enabled": true,
      "position": "after_design_doc",
      "loops": ["research"],
      "modes": ["deep"],
      "created_at": "2026-01-13T11:00:00Z"
    }
  ],
  "total": 2
}
```

### Get Single Guardrail

```
GET /projects/{slug}/guardrails/{category}/{filename}
```

**Response:**
```json
{
  "category": "domain",
  "filename": "healthcare-rules.md",
  "source": "workspace",
  "file_path": "~/.ralphx/projects/my-app/guardrails/domain/healthcare-rules.md",
  "file_size": 4521,
  "enabled": true,
  "position": "after_design_doc",
  "loops": ["research"],
  "modes": ["deep"],
  "content": "# Healthcare Domain Rules\n\nWhen generating user stories for healthcare...",
  "created_at": "2026-01-13T11:00:00Z"
}
```

### Create/Update Guardrail

```
PUT /projects/{slug}/guardrails/{category}/{filename}
```

**Request Body:**
```json
{
  "content": "# Healthcare Domain Rules\n\nWhen generating user stories for healthcare...",
  "enabled": true,
  "position": "after_design_doc",
  "loops": ["research"],
  "modes": ["deep"]
}
```

**Response:**
```json
{
  "created": true,
  "file_path": "~/.ralphx/projects/my-app/guardrails/domain/healthcare-rules.md"
}
```

### Delete Guardrail

```
DELETE /projects/{slug}/guardrails/{category}/{filename}
```

**Response:**
```json
{
  "deleted": true
}
```

### Preview Assembled Prompt

Preview how guardrails will be assembled into the final prompt for a specific loop and mode.

```
POST /projects/{slug}/guardrails/preview
```

**Request Body:**
```json
{
  "loop": "research",
  "mode": "turbo",
  "include_design_doc": true
}
```

**Response:**
```json
{
  "assembled_prompt": "<!-- SAFETY GUARDRAILS -->\n\n# Never Do\n- Never expose PHI...\n\n<!-- SYSTEM GUARDRAILS -->\n...\n\n<!-- DESIGN DOC -->\n# RCM Portal Design\n...\n\n<!-- DOMAIN GUARDRAILS -->\n...\n\n<!-- OUTPUT GUARDRAILS -->\n...",
  "guardrails_included": [
    {"category": "safety", "filename": "hipaa.md", "size": 2134},
    {"category": "system", "filename": "identity.md", "size": 512},
    {"category": "domain", "filename": "healthcare-rules.md", "size": 4521},
    {"category": "output", "filename": "json-schema.md", "size": 1024}
  ],
  "total_size": 52341,
  "warnings": []
}
```

### Validate Guardrails

Validate that all guardrails have defined template variables and no issues.

```
POST /projects/{slug}/guardrails/validate
```

**Request Body:**
```json
{
  "loop": "research",
  "mode": "turbo"
}
```

**Response (success):**
```json
{
  "valid": true,
  "errors": [],
  "warnings": []
}
```

**Response (errors):**
```json
{
  "valid": false,
  "errors": [
    {
      "file": "domain/healthcare.md",
      "message": "Undefined variable {target_system}",
      "hint": "Add to loop config: context.custom_context.target_system"
    }
  ],
  "warnings": [
    {
      "file": "safety/verbose.md",
      "message": "File size (48KB) approaching 50KB limit"
    }
  ]
}
```

### Get Guardrails Configuration

```
GET /projects/{slug}/guardrails/config
```

**Response:**
```json
{
  "enabled": true,
  "inherit_global": true,
  "categories": {
    "system": {"enabled": true, "position": "before_design_doc"},
    "safety": {"enabled": true, "position": "start"},
    "domain": {"enabled": true, "position": "after_design_doc"},
    "output": {"enabled": true, "position": "end"},
    "custom": {"enabled": true, "position": "after_design_doc"}
  },
  "files": {
    "domain/anesthesia-rules.md": {
      "loops": ["research"],
      "modes": ["deep"]
    }
  }
}
```

### Update Guardrails Configuration

```
PUT /projects/{slug}/guardrails/config
```

**Request Body:**
```json
{
  "enabled": true,
  "inherit_global": true,
  "categories": {
    "safety": {"enabled": true, "position": "start"},
    "domain": {"enabled": false}
  }
}
```

**Response:**
```json
{
  "updated": true
}
```

### Detect AI Instruction Files

Scan a project directory for existing AI instruction files (CLAUDE.md, .cursorrules, etc.).

```
POST /projects/{slug}/guardrails/detect
```

**Response:**
```json
{
  "detected": [
    {
      "file": "CLAUDE.md",
      "path": "/home/user/my-project/CLAUDE.md",
      "size": 2134,
      "origin": "Claude Code",
      "preview": "# Project Rules\n\nThis project uses TypeScript and React...",
      "is_symlink": false
    },
    {
      "file": ".cursor/rules/backend.md",
      "path": "/home/user/my-project/.cursor/rules/backend.md",
      "size": 1456,
      "origin": "Cursor",
      "preview": "# Backend Rules\n\nAll API endpoints must...",
      "is_symlink": false
    }
  ],
  "warnings": [
    {
      "file": "llms.txt",
      "message": "File is a symlink and will be skipped for security"
    }
  ],
  "is_cloned_repo": true,
  "remote_origin": "git@github.com:company/project.git",
  "security_warning": "This project was cloned from git@github.com:company/project.git. AI instruction files may contain prompt injection."
}
```

### Import Detected Files

Import detected AI instruction files as guardrails.

```
POST /projects/{slug}/guardrails/import
```

**Request Body:**
```json
{
  "files": [
    {"source": "CLAUDE.md", "target_category": "system", "target_filename": "claude-instructions.md"},
    {"source": ".cursor/rules/backend.md", "target_category": "domain", "target_filename": "backend-rules.md"}
  ]
}
```

**Response:**
```json
{
  "imported": [
    {"source": "CLAUDE.md", "target": "guardrails/system/claude-instructions.md"},
    {"source": ".cursor/rules/backend.md", "target": "guardrails/domain/backend-rules.md"}
  ],
  "skipped": []
}
```

---

## Configuration

### Get Current Configuration

```
GET /config
```

**Response:**
```json
{
  "loops_directory": "loops/",
  "data_directory": "data/",
  "log_level": "info",
  "default_adapter": "claude_cli",
  "adapters": {
    "claude_cli": { "enabled": true },
    "anthropic": { "enabled": false },
    "openai": { "enabled": false }
  }
}
```

### Update Configuration

```
PATCH /config
```

**Request Body:**
```json
{
  "log_level": "debug"
}
```

### Get Loop Configuration (YAML)

```
GET /projects/{slug}/config/loops/{loop_id}
```

**Response:** Raw YAML content

### Update Loop Configuration

```
PUT /projects/{slug}/config/loops/{loop_id}
```

**Request Body:** Raw YAML content

**Response:**
```json
{
  "valid": true,
  "updated": true,
  "warnings": []
}
```

### Validate Loop Configuration

```
POST /config/validate
```

**Request Body:** Raw YAML content

**Response:**
```json
{
  "valid": true,
  "errors": [],
  "warnings": [
    "Mode 'turbo' has no tools - this is intentional for fast extraction"
  ]
}
```

---

## System

### Health Check

```
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "uptime_seconds": 3600,
  "active_loops": 1,
  "adapters": {
    "claude_cli": "available",
    "anthropic": "not_configured",
    "openai": "not_configured"
  }
}
```

### Get System Stats

```
GET /stats
```

**Response:**
```json
{
  "uptime_seconds": 3600,
  "total_iterations": 1523,
  "total_items_generated": 3847,
  "total_items_implemented": 745,
  "active_loops": 1,
  "memory_usage_mb": 256,
  "cpu_percent": 12.5
}
```

### Doctor Check (Prerequisites)

```
GET /doctor
```

**Response:**
```json
{
  "checks": [
    {"name": "python_version", "status": "ok", "message": "Python 3.11.5"},
    {"name": "node_js", "status": "ok", "message": "Node.js v20.10.0"},
    {"name": "claude_cli", "status": "ok", "message": "Claude CLI v1.0.102"},
    {"name": "claude_auth", "status": "ok", "message": "Authenticated"},
    {"name": "workspace", "status": "ok", "message": "~/.ralphx writable"},
    {"name": "network", "status": "ok", "message": "Can reach api.anthropic.com"},
    {"name": "linux_kernel", "status": "warning", "message": "Linux kernel 5.15.0 has known issues", "hint": "See github.com/anthropics/claude-code/issues/15321"}
  ],
  "overall_status": "warning",
  "issues_count": 1
}
```

### Diagnose Project

```
GET /projects/{slug}/diagnose
```

**Response:**
```json
{
  "project": "my-saas-app",
  "checks": [
    {"name": "claude_cli", "status": "ok", "message": "v1.0.102"},
    {"name": "api_connectivity", "status": "ok", "message": "latency: 234ms"},
    {"name": "loop_configs", "status": "ok", "message": "2 valid configs"},
    {"name": "disk_space", "status": "warning", "message": "2.1GB free (recommend 5GB+)"},
    {"name": "recent_errors", "status": "warning", "message": "3 errors in last hour"},
    {"name": "performance", "status": "ok", "message": "Normal"}
  ],
  "recent_issues": [
    {"type": "timeout", "count": 3, "message": "3 timeouts in last hour (normal for deep mode)"},
    {"type": "rate_limit", "count": 1, "message": "1 rate limit hit at 14:22 (auto-recovered)"}
  ],
  "recommendations": [
    "Your turbo/deep ratio of 85/15 is causing frequent API calls. Consider reducing to 90/10 if hitting rate limits."
  ]
}
```

### Why Did Loop Stop

```
GET /projects/{slug}/loops/{loop_id}/why
```

**Response:**
```json
{
  "loop": "research",
  "stopped_at": "2026-01-13T14:32:05Z",
  "reason": "Reached max_consecutive_errors limit (5)",
  "last_errors": [
    {"timestamp": "2026-01-13T14:28:12Z", "message": "Timeout after 180s (turbo mode)"},
    {"timestamp": "2026-01-13T14:29:45Z", "message": "Timeout after 180s (turbo mode)"},
    {"timestamp": "2026-01-13T14:30:18Z", "message": "Timeout after 180s (turbo mode)"},
    {"timestamp": "2026-01-13T14:31:02Z", "message": "Timeout after 180s (turbo mode)"},
    {"timestamp": "2026-01-13T14:31:49Z", "message": "Timeout after 180s (turbo mode)"}
  ],
  "likely_cause": "Claude CLI or Anthropic API is responding slowly",
  "suggestions": [
    "Check Anthropic status: https://status.anthropic.com",
    "Increase timeout in loop config: timeout: 300",
    "Wait 10-15 minutes and try again",
    "Run with verbose logging to see detailed output"
  ]
}
```

### Checkpoint Recovery

```
GET /projects/{slug}/checkpoint
```

**Response (checkpoint exists):**
```json
{
  "has_checkpoint": true,
  "checkpoint": {
    "loop": "research",
    "run_id": "my-saas-app-20260113-143052-a1b2c3d4",
    "iteration": 47,
    "status": "in_progress",
    "items_added": 412,
    "last_category": "ANS",
    "timestamp": "2026-01-13T14:31:45Z"
  }
}
```

```
POST /projects/{slug}/checkpoint/resume
```

Resume from checkpoint.

**Response:**
```json
{
  "resumed": true,
  "run_id": "my-saas-app-20260113-143052-a1b2c3d4",
  "starting_iteration": 47
}
```

```
DELETE /projects/{slug}/checkpoint
```

Discard checkpoint and start fresh.

**Response:**
```json
{
  "discarded": true
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "error": {
    "code": "LOOP_NOT_FOUND",
    "message": "Loop 'unknown_loop' does not exist",
    "details": {}
  }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `PROJECT_NOT_FOUND` | 404 | Project does not exist |
| `PROJECT_ALREADY_EXISTS` | 409 | Project with that slug already exists |
| `PROJECT_PATH_NOT_FOUND` | 400 | Project path does not exist on filesystem |
| `PROJECT_LOCKED` | 409 | Another loop is already running in this project |
| `LOOP_NOT_FOUND` | 404 | Loop does not exist |
| `LOOP_ALREADY_RUNNING` | 409 | Loop is already running |
| `LOOP_NOT_RUNNING` | 409 | Loop is not running (can't pause/stop) |
| `ITEM_NOT_FOUND` | 404 | Work item does not exist |
| `ITEM_ALREADY_EXISTS` | 409 | Work item ID already exists |
| `SESSION_NOT_FOUND` | 404 | Session does not exist |
| `RUN_NOT_FOUND` | 404 | Run does not exist |
| `INVALID_CONFIG` | 400 | Loop configuration is invalid |
| `DESIGN_DOC_NOT_FOUND` | 400 | Design document not found at configured path |
| `DESIGN_DOC_TOO_LARGE` | 400 | Design document exceeds size limit |
| `ADAPTER_ERROR` | 500 | LLM adapter failed |
| `CLAUDE_CLI_NOT_FOUND` | 500 | Claude CLI not found in PATH |
| `CLAUDE_CLI_AUTH_ERROR` | 500 | Claude CLI not authenticated |
| `PERMISSION_TIMEOUT` | 408 | Loop waiting for permission approval |
| `STUCK_DETECTED` | 408 | Loop detected as stuck (no activity) |
| `RATE_LIMITED` | 429 | API rate limit hit |
| `STORE_ERROR` | 500 | Storage backend failed |
| `SESSION_LOG_CORRUPTED` | 500 | Claude session JSONL log file is corrupted |
| `CHECKPOINT_ERROR` | 500 | Failed to save/restore checkpoint |
| `VALIDATION_ERROR` | 400 | Request validation failed |
| `GUARDRAIL_NOT_FOUND` | 404 | Guardrail file does not exist |
| `GUARDRAIL_TOO_LARGE` | 400 | Guardrail file exceeds 50KB limit |
| `GUARDRAIL_TOTAL_TOO_LARGE` | 400 | Total guardrails exceed 500KB limit |
| `GUARDRAIL_UNDEFINED_VAR` | 400 | Guardrail uses undefined template variable |
| `GUARDRAIL_SYMLINK` | 400 | Cannot import symlinked file (security) |
| `GUARDRAIL_CONFIG_INVALID` | 400 | Invalid _config.yaml in guardrails directory |
| `GUARDRAIL_PERMISSION_DENIED` | 403 | Cannot read guardrail file (permission denied) |
| `GUARDRAIL_EMPTY` | 400 | Guardrail file is empty (must have content) |
| `PROMPT_TOO_LARGE` | 400 | Assembled prompt exceeds 1MB limit |
| `DB_LOCKED` | 503 | SQLite database is locked by another process |
| `DB_CORRUPTED` | 500 | SQLite database is corrupted |

---

## WebSocket Alternative (Optional)

For bidirectional communication, a WebSocket endpoint is available:

```
WS /projects/{slug}/ws/loops/{loop_id}
```

**Client -> Server Messages:**
```json
{"type": "subscribe", "events": ["log", "progress", "item_added"]}
{"type": "unsubscribe", "events": ["log"]}
{"type": "command", "action": "pause"}
{"type": "command", "action": "resume"}
```

**Server -> Client Messages:**
```json
{"type": "log", "data": {...}}
{"type": "progress", "data": {...}}
{"type": "item_added", "data": {...}}
{"type": "status_changed", "data": {"from": "running", "to": "paused"}}
{"type": "ack", "command": "pause", "success": true}
```
