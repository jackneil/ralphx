# Ralph Workflow Requirements

Requirements for replicating `ralph_rcm.sh` (story generation) and `ralph_impl.sh` (implementation) workflows in RalphX via UI.

---

## Overview

Two complementary workflows that work together:

1. **PRD Research (ralph_rcm.sh)** - Generator loop that creates user stories from a design document
2. **Feature Implementation (ralph_impl.sh)** - Consumer loop that implements stories one-by-one

```
┌─────────────────────┐      ┌─────────────────────┐
│   PRD Research      │      │   Implementation    │
│   (Generator)       │      │   (Consumer)        │
│                     │      │                     │
│  Design Doc ───────►│      │  ◄─── Stories DB    │
│  Existing Stories   │      │                     │
│           │         │      │  Implement ───────► │ Code Changes
│           ▼         │      │  Mark Status        │ Git Commits
│  Generate Stories ──┼──────┼──► work_items DB    │
│  Append to DB       │      │                     │
│  Git Commit         │      │  Exit when empty    │
└─────────────────────┘      └─────────────────────┘
```

---

## Source Files in hank-rcm

### Core Scripts
| File | Purpose |
|------|---------|
| `/home/jackmd/Github/hank-rcm/ralph/ralph_rcm.sh` | Generator workflow (797 lines) |
| `/home/jackmd/Github/hank-rcm/ralph/ralph_impl.sh` | Consumer workflow (747 lines) |
| `/home/jackmd/Github/hank-rcm/ralph/prd_jsonl.py` | JSONL database manager (story CRUD, status tracking) |

### Prompt Templates
| File | Purpose |
|------|---------|
| `/home/jackmd/Github/hank-rcm/ralph/PROMPT_IMPL.md` | Implementation prompt template (276 lines) |
| `/home/jackmd/Github/hank-rcm/ralph/PROMPT_RCM_TURBO.md` | Generator prompt - turbo mode (45 lines) |
| `/home/jackmd/Github/hank-rcm/ralph/PROMPT_RCM_DEEP.md` | Generator prompt - deep mode with web research (123 lines) |

### Design & Configuration Documents
| File | Purpose |
|------|---------|
| `/home/jackmd/Github/hank-rcm/design/RCM_DESIGN.md` | Master design document (2730 lines) - **CRITICAL** |
| `/home/jackmd/Github/hank-rcm/GUARDRAILS.md` | Code style & implementation standards - **CRITICAL** |
| `/home/jackmd/Github/hank-rcm/design/EXTERNAL_PRODUCTS.md` | External product definitions for EXTERNAL status |

### Category & Phase Configuration
| File | Purpose |
|------|---------|
| `/home/jackmd/Github/hank-rcm/ralph/category_map.json` | Category definitions (code → name, description) |
| `/home/jackmd/Github/hank-rcm/ralph/PHASE_CATEGORIES.json` | Phase definitions with category ordering |
| `/home/jackmd/Github/hank-rcm/ralph/product_patterns.json` | Patterns for detecting EXTERNAL status |

### Data Files
| File | Purpose |
|------|---------|
| `/home/jackmd/Github/hank-rcm/design/prd_RCM_software.jsonl` | Stories database (3343 lines) - **SOURCE OF TRUTH** |
| `/home/jackmd/Github/hank-rcm/ralph/progress_impl.txt` | Implementation tracking log (108KB) |
| `/home/jackmd/Github/hank-rcm/ralph/progress_rcm.txt` | Research tracking log (414KB) |

### Helper Scripts
| File | Purpose |
|------|---------|
| `/home/jackmd/Github/hank-rcm/ralph/extract_json.py` | Extract JSON arrays from Claude output |
| `/home/jackmd/Github/hank-rcm/ralph/extract_section.py` | Extract sections from design doc |
| `/home/jackmd/Github/hank-rcm/ralph/parse_stream.py` | Parse stream-json output for live display |
| `/home/jackmd/Github/hank-rcm/ralph/run_with_creds.py` | Credential swapping wrapper |

---

## JSONL Story Schema (Source of Truth)

The `prd_RCM_software.jsonl` file contains one JSON object per line with this schema:

```json
{
  "id": "CAT-NNN",           // Unique ID: category prefix + 3-digit number
  "priority": 1-100,          // Lower = higher priority
  "story": "As a [role], I can [action] so that [benefit]",
  "acceptance_criteria": ["Criterion 1", "Criterion 2", ...],
  "notes": "Implementation notes",
  "category": "CAT",          // Category code (FND, SEC, ANS, etc.)

  // Status tracking (set by ralph_impl.sh)
  "status": "pending|implemented|dup|external|skipped",
  "passes": true|false,       // true = processed (any status except pending)

  // Status-specific fields
  "implemented_at": "2026-01-15T10:30:00",  // ISO timestamp
  "impl_notes": "What was implemented",      // For implemented
  "dup_of": "FND-001",                       // For dup status
  "external_product": "hank-os",             // For external status
  "skip_reason": "Reason for skipping"       // For skipped status
}
```

### Status Values

| Status | Meaning | Set By | Fields Updated |
|--------|---------|--------|----------------|
| `pending` | Not yet processed (default) | Import | - |
| `implemented` | Feature completed | `mark-implemented` | passes=true, impl_notes, implemented_at |
| `dup` | Duplicate of another story | `mark-dup` | passes=true, dup_of |
| `external` | Belongs to another product | `mark-external` | passes=true, external_product |
| `skipped` | Cannot implement (reason given) | `mark-skipped` | passes=true, skip_reason |

### Importing with Existing Progress

When importing JSONL, RalphX must:
1. **Preserve existing status** - Stories with `status=implemented` should NOT be re-processed
2. **Map status values** - `pending` → RalphX `completed` (ready for consumer), `implemented` → RalphX `processed`
3. **Filter by status** - Consumer loop only claims items with `status=pending` (or no status)

**Status Mapping for Import:**
```
JSONL status=pending     → work_items status=completed (ready to process)
JSONL status=implemented → work_items status=processed (already done)
JSONL status=dup         → work_items status=duplicate
JSONL status=external    → work_items status=skipped (skip_reason=external:{product})
JSONL status=skipped     → work_items status=skipped
```

---

## Category & Phase System

### Categories (from category_map.json)

Categories are 3-letter codes grouping related stories:

| Category | Name | Description |
|----------|------|-------------|
| FND | Foundation | Core infrastructure, base models |
| DBM | Database Models | Database schema, migrations |
| SEC | Security | Authentication, authorization, RBAC |
| ARC | Architecture | System design patterns |
| ANS | Anesthesia | Anesthesia billing specific |
| CLM | Claims | Claims processing |
| DNL | Denials | Denial management |
| PAY | Payments | Payment posting |
| INT | Integrations | External system integrations |
| ... | ... | (40+ categories total) |

### Phases (from PHASE_CATEGORIES.json)

Phases define implementation order:

```json
{
  "phases": {
    "1": {
      "name": "Foundation & Infrastructure",
      "description": "Core models, security, architecture, database patterns",
      "categories": ["FND", "DBM", "SEC", "ARC", "ADM", "DAT", "DEP", "SYS"]
    },
    "2": {
      "name": "Core RCM Models",
      "description": "Patient, encounter, claim, payment core domain models",
      "categories": ["RCM", "ENC", "PAT", "PRV", "PAY", "INS", "CLM", ...]
    },
    "3": {
      "name": "Integrations & Workflows",
      "categories": ["INT", "WKF", "CMP", "IMP", "GLO", "DNL", "ARF", "AUD"]
    },
    "4": {
      "name": "Specialty Modules",
      "categories": ["ANS", "CAR", "RAD", "SUR", ...]
    },
    "5": {
      "name": "Analytics, UX & Portal",
      "categories": ["KPI", "UXT", "UXA", "UXD", "PTL", "RPT", "QUA"]
    }
  }
}
```

---

## Workflow 1: PRD Research (Story Generation)

**Source:** `ralph/ralph_rcm.sh`

### Purpose
Autonomously generates user stories from a design document, optionally with web research.

### Two Modes

| Mode | Description | Timeout | Tools | Model |
|------|-------------|---------|-------|-------|
| **Turbo** | Extract from design doc only | 180s | None | Sonnet |
| **Deep** | Web research + design doc | 900s | WebSearch, WebFetch | Sonnet |

Default: Random mode (85% turbo, 15% deep)

### Iteration Flow
1. **Pick Category** - Weighted toward underrepresented categories
2. **Get Category Info** - Name, description, next available ID
3. **Get Existing Stories** - Stories in that category (for context/deduplication)
4. **Build Prompt** - Inject: category info, existing stories, FULL design doc, min/max stories
5. **Execute Claude** - Generate 5-15 new stories as JSON array
6. **Extract JSON** - Parse stories from output using `extract_json.py`
7. **Append to JSONL** - Via `prd_jsonl.py append` (deduplicates automatically)
8. **Git Commit** - Commit JSONL changes

### Prompt Variables (Turbo Mode)
```
{CATEGORY}          - Category code (e.g., "ANS")
{CATEGORY_NAME}     - Category name (e.g., "Anesthesia")
{CATEGORY_DESC}     - Category description
{NEXT_ID}           - Next available ID (e.g., "ANS-048")
{CATEGORY_STORIES}  - Existing stories in this category
{DESIGN_DOC}        - FULL design document content
{MIN_STORIES}       - Minimum stories to generate (default: 5)
{MAX_STORIES}       - Maximum stories to generate (default: 15)
```

### Exit Conditions
- Max iterations reached (default: 100)
- Max runtime exceeded (default: 8 hours)
- Too many consecutive errors (default: 5)
- Too many iterations without progress (default: 3)

---

## Workflow 2: Feature Implementation (Consumer)

**Source:** `ralph/ralph_impl.sh`

### Purpose
Implements user stories one at a time, tracking status and handling edge cases.

### Inputs Required
| Input | Source | Description |
|-------|--------|-------------|
| Next Pending Story | `prd_jsonl.py next-pending-ordered` | Filtered by phase/category |
| Design Document | `design/RCM_DESIGN.md` | Full design doc (2730 lines) |
| Implemented Summary | `prd_jsonl.py implemented-summary` | List of completed features |
| Guardrails | `GUARDRAILS.md` | Code style & implementation standards |

### Loop Configuration
| Setting | Value | Notes |
|---------|-------|-------|
| Type | `consumer` | Processes work items from DB |
| Model | Opus | Best for implementation |
| Timeout | 1800s (30 min) | Per iteration |
| Max Iterations | 50 | Configurable |
| Tools | Read, Write, Edit, Bash, Glob, Grep | Full code access |

### Iteration Flow
1. **Get Next Pending** - `prd_jsonl.py next-pending-ordered [--phase N] [--category CAT]`
2. **Build Prompt** - Inject via `PROMPT_IMPL.md` template:
   - `{STORY_ID}` - Story ID
   - `{PRIORITY}` - Priority number
   - `{STORY_TEXT}` - Full story text
   - `{NOTES}` - Implementation notes
   - `{ACCEPTANCE_CRITERIA}` - Numbered list of criteria
   - `{IMPLEMENTED_SUMMARY}` - Already-implemented features
   - `{DESIGN_DOC}` - Full design document
3. **Execute Claude** - Run with stream-json output
4. **Parse Status** - Extract from delimited output block
5. **Update JSONL** - Via `prd_jsonl.py mark-{status}`
6. **Git Commit** - If implemented, commit with story ID in message
7. **Log Progress** - Append to `progress_impl.txt`

### Structured Output Format

Claude outputs status in a delimited block:

```
###RALPH_IMPL_RESULT_7f3a9b2e###
IMPLEMENTED: Brief description of what was completed
###END_RALPH_RESULT###
```

Or for other statuses:
```
###RALPH_IMPL_RESULT_7f3a9b2e###
EXTERNAL: hank-os
###END_RALPH_RESULT###

###RALPH_IMPL_RESULT_7f3a9b2e###
DUP_OF: FND-001
###END_RALPH_RESULT###

###RALPH_IMPL_RESULT_7f3a9b2e###
SKIPPED: Requires external API not yet available
###END_RALPH_RESULT###
```

### Status Handling

| Status | Action | JSONL Update |
|--------|--------|--------------|
| `IMPLEMENTED` | Git commit changes | `mark-implemented ID "notes"` |
| `EXTERNAL` | Log product name | `mark-external ID product` |
| `DUP_OF` | Validate target exists & is implemented | `mark-dup ID parent_id` |
| `SKIPPED` | Log reason | `mark-skipped ID "reason"` |
| `ERROR` | Increment error count, continue | (no update, retry later) |

### Validation Rules
1. Story cannot be `DUP_OF` itself
2. `DUP_OF` target must be an implemented story
3. `EXTERNAL` product must match known patterns (from `product_patterns.json`)

### Exit Conditions
- No pending items remain (SUCCESS!)
- Max iterations reached
- Max runtime exceeded

---

## Implemented Summary Generation

The `implemented-summary` command generates context for Claude:

```
## FND (12 implemented)
- FND-001: Core database models and migrations
- FND-002: Base model classes with audit fields
...

## SEC (8 implemented)
- SEC-001: JWT authentication middleware
- SEC-002: Role-based access control
...

Total implemented: 247
```

This is injected into the implementation prompt so Claude knows:
1. What features already exist (avoid reimplementing)
2. What patterns have been established (follow conventions)
3. What IDs are taken (avoid conflicts)

---

## Work Item Schema (RalphX)

The `work_items` table must support:

| Field | Type | Description |
|-------|------|-------------|
| id | string | Unique ID (e.g., "FND-001") |
| workflow_id | string | Parent workflow |
| source_step_id | int | Step that created this item |
| priority | int | 1-100, lower = higher priority |
| content | text | Full story text |
| title | string | Short title (first 100 chars of story) |
| status | enum | pending, completed, processed, failed, skipped, duplicate |
| category | string | Category code (FND, SEC, etc.) |
| metadata | json | acceptance_criteria, notes, phase, etc. |
| claimed_by | string | Loop that claimed this item |
| claimed_at | timestamp | When claimed |
| processed_at | timestamp | When completed |
| processed_by | string | Loop that processed |
| skip_reason | string | Reason if skipped/external |
| duplicate_of | string | Parent item if duplicate |

---

## RalphX Implementation Requirements

### REQ-1: JSONL Import with Status Preservation
**Priority:** P0 (Blocker)

Import must:
- Parse JSONL file line by line
- Map all fields including status
- Preserve existing progress (implemented stories stay implemented)
- Support filtering (only import pending, or all)
- Show import summary: "Imported 3072 items (2847 pending, 225 already processed)"

### REQ-2: Consumer Loop Claims Pending Items
**Priority:** P0 (Blocker)

Consumer loop must:
- Query for items with `status=completed` (ready to process) AND `unclaimed`
- Respect phase/category filters
- Respect dependency ordering
- Exit cleanly when no items remain

**FIXED:** `_is_consumer_loop()` now checks `consume_from_step_id`

### REQ-3: Structured Output Parsing (JSON Schema)
**Priority:** P0 (Blocker)

Use `claude -p --json-schema` for guaranteed parseable output:

```json
{
  "type": "object",
  "properties": {
    "status": {
      "type": "string",
      "enum": ["implemented", "duplicate", "external", "skipped", "error"]
    },
    "summary": { "type": "string" },
    "duplicate_of": { "type": "string" },
    "external_system": { "type": "string" },
    "reason": { "type": "string" },
    "files_changed": { "type": "array", "items": { "type": "string" } },
    "tests_passed": { "type": "boolean" }
  },
  "required": ["status"]
}
```

### REQ-4: Implemented Summary Variable
**Priority:** P1

Template variable `{{IMPLEMENTED_SUMMARY}}` must:
- Query work_items for `status=processed`
- Group by category
- Format as markdown list
- Include count per category and total

### REQ-5: Design Doc & Guardrails Injection
**Priority:** P1

Resources must support:
- File-based resources (read from project path)
- Large content (design doc is 2730 lines)
- Injection into prompt template

### REQ-6: Git Integration
**Priority:** P2

After successful implementation:
- `git add -A`
- Commit with message: `Implement {STORY_ID}\n\n{STORY_TEXT}\n\nCo-Authored-By: Claude <noreply@anthropic.com>`

### REQ-7: Phase/Category Filtering
**Priority:** P2

Support `--phase N` and `--category CAT` filters:
- UI: Dropdown selectors in step config
- Backend: Pass to `LoopExecutor` constructor

### REQ-8: Progress Tracking
**Priority:** P3

Track and display:
- Items processed per session
- Time per item
- Status breakdown (implemented/dup/external/skipped/error)
- Remaining items

---

## UI Flow for Creating Implementation Workflow

### Step 1: Create Project
1. Register hank-rcm project in RalphX
2. Project path: `/home/jackmd/Github/hank-rcm`

### Step 2: Create Workflow
1. Click "+ New Workflow"
2. Name: "Feature Implementation"

### Step 3: Add Implementation Step
1. Add Step → Autonomous
2. Name: "Implementation"
3. Type: Consumer
4. Model: Opus
5. Timeout: 1800s
6. Tools: All

### Step 4: Add Resources
1. **Design Doc** (type: design_doc)
   - Source: File
   - Path: `design/RCM_DESIGN.md`

2. **Guardrails** (type: guardrail)
   - Source: File
   - Path: `GUARDRAILS.md`

### Step 5: Import Stories
1. Click "Import JSONL"
2. Select: `design/prd_RCM_software.jsonl`
3. Options:
   - [x] Preserve existing status
   - [x] Only import pending items
4. Confirm → Shows: "Imported 2847 pending items (225 already processed)"

### Step 6: Complete Ready Check
1. Answer pre-flight questions
2. Confirm understanding of design doc
3. Confirm codebase access

### Step 7: Start Workflow
1. Click "Start"
2. Watch progress in Live Output
3. View items completing in Items tab
4. Git commits appear automatically

---

## Test Plan

### Test 1: Import with Status Preservation
1. Import `prd_RCM_software.jsonl`
2. Verify pending items have `status=completed` (ready to process)
3. Verify implemented items have `status=processed`
4. Verify total count matches JSONL line count

### Test 2: Consumer Loop Filtering
1. Start loop with `--phase 1` filter
2. Verify only Phase 1 categories are claimed
3. Verify loop exits when Phase 1 complete

### Test 3: Status Parsing
1. Mock Claude output with each status type
2. Verify correct JSONL update for each:
   - IMPLEMENTED → mark-implemented
   - DUP_OF → mark-dup (validate target)
   - EXTERNAL → mark-external
   - SKIPPED → mark-skipped

### Test 4: Full E2E
1. Import 5 pending stories
2. Start implementation workflow
3. Watch Claude implement each
4. Verify git commits created
5. Verify JSONL updated correctly
6. Verify workflow completes when empty

---

## Current Status

### Fixed
- [x] Consumer loop detection (`_is_consumer_loop()` checks `consume_from_step_id`)
- [x] JSONL import API exists
- [x] Ready check system working
- [x] Structured output parsing with JSON schema
- [x] LoopStatus schema (run_id is string)

### Remaining Gaps
| Gap | Priority | Notes |
|-----|----------|-------|
| Status preservation on import | P0 | Need to map JSONL status to work_items status |
| Implemented summary variable | P1 | Query processed items, format as markdown |
| Phase/category UI filters | P2 | Add dropdowns to step config |
| Progress tracking UI | P3 | Show session stats |
