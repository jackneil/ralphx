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

## Workflow 1: PRD Research (Story Generation)

**Source:** `ralph/ralph_rcm.sh`

### Purpose
Autonomously generates user stories from a design document, optionally with web research.

### Inputs Required
| Input | Type | Description |
|-------|------|-------------|
| Design Document | File (MD) | Full project design doc (e.g., `RCM_DESIGN.md`) |
| Existing Stories | From DB | Stories already in database (to avoid duplicates) |
| Category Info | From DB | Category stats, next ID to use |

### Loop Configuration
| Setting | Value | Notes |
|---------|-------|-------|
| Type | `generator` | Creates work items |
| Model | Sonnet (turbo) / Sonnet (deep) | Configurable |
| Timeout | 180s (turbo) / 900s (deep) | Per iteration |
| Max Iterations | 100 | Configurable |
| Tools | None (turbo) / WebSearch, WebFetch (deep) | Mode-dependent |

### Iteration Flow
1. **Select Category** - Pick random category, weighted toward underrepresented
2. **Build Prompt** - Inject design doc, existing stories, category info, next ID
3. **Execute Claude** - Generate 5-15 new stories as JSON
4. **Extract JSON** - Parse stories from Claude output
5. **Deduplicate** - Skip stories that already exist
6. **Create Work Items** - Insert new stories into `work_items` table
7. **Git Commit** - Commit the JSONL changes (if any)

### Output Format (from Claude)
```json
[
  {
    "id": "CAT-NNN",
    "priority": 1-100,
    "story": "As a [role], I can [action] so that [benefit]",
    "acceptance_criteria": ["Criterion 1", "Criterion 2"],
    "category": "CAT",
    "notes": "Optional implementation notes"
  }
]
```

### Exit Conditions
- Max iterations reached
- Max runtime exceeded
- Too many consecutive errors (5)
- Too many iterations without progress (3)

---

## Workflow 2: Feature Implementation (Consumer)

**Source:** `ralph/ralph_impl.sh`

### Purpose
Implements user stories one at a time, tracking status and handling edge cases.

### Inputs Required
| Input | Type | Description |
|-------|------|-------------|
| Work Items | From DB | Pending stories to implement |
| Design Document | File (MD) | Full project design doc |
| Implemented Summary | From DB | List of already-implemented features |
| Guardrails | File (MD) | Code style/security requirements |

### Loop Configuration
| Setting | Value | Notes |
|---------|-------|-------|
| Type | `consumer` | Processes work items from DB |
| Model | Opus | Best for implementation |
| Timeout | 1800s (30 min) | Per iteration |
| Max Iterations | 50 | Configurable |
| Tools | Read, Write, Edit, Bash, Glob, Grep | Full code access |

### Iteration Flow
1. **Claim Item** - Get next pending story (dependency/priority ordered)
2. **Build Prompt** - Inject story, design doc, implemented summary, guardrails
3. **Execute Claude** - Implement the feature
4. **Parse Status** - Extract structured result from output
5. **Update Item** - Mark item with appropriate status
6. **Git Commit** - Commit code changes (if implemented)
7. **Release/Complete** - Release claim on error, mark done on success

### Status Values (from Claude output)
| Status | Meaning | Database Update |
|--------|---------|-----------------|
| `IMPLEMENTED` | Feature completed | status=implemented, impl_notes=details |
| `EXTERNAL` | Belongs to another product | status=external, skip_reason=product |
| `DUP_OF` | Duplicate of existing story | status=duplicate, duplicate_of=id |
| `SKIPPED` | Cannot implement (reason) | status=skipped, skip_reason=reason |
| `ERROR` | Implementation failed | Release claim, retry later |

### Structured Output Format
```
###RALPH_IMPL_RESULT_7f3a9b2e###
IMPLEMENTED: Brief description of what was completed
###END_RALPH_RESULT###
```

Or for other statuses:
```
###RALPH_IMPL_RESULT_7f3a9b2e###
DUP_OF: FND-001
###END_RALPH_RESULT###
```

### Exit Conditions
- No pending items remain (SUCCESS!)
- Max iterations reached
- Max runtime exceeded

---

## Work Item Schema

The `work_items` table must support:

| Field | Type | Description |
|-------|------|-------------|
| id | string | Unique ID (e.g., "FND-001") |
| workflow_id | string | Parent workflow |
| source_step_id | int | Step that created this item |
| priority | int | 1-100, lower = higher priority |
| content | text | Full story text |
| title | string | Short title |
| status | enum | pending, completed, processed, failed, skipped, duplicate |
| category | string | Category code (FND, SEC, etc.) |
| metadata | json | acceptance_criteria, notes, etc. |
| claimed_by | string | Loop that claimed this item |
| claimed_at | timestamp | When claimed |
| processed_at | timestamp | When completed |
| processed_by | string | Loop that processed |
| skip_reason | string | Reason if skipped |
| duplicate_of | string | Parent item if duplicate |

---

## RalphX Implementation Requirements

### REQ-1: JSONL Import via UI
**Priority:** P0 (Blocker)

User must be able to import existing JSONL file into work_items:
- Upload button in workflow UI
- Map JSONL fields to work_item fields
- Support hank_prd format (id, priority, story, acceptance_criteria, notes, status)
- Items created with status based on source (pending if not set)
- Items scoped to workflow + source_step

**API exists:** `POST /api/projects/{slug}/import-jsonl`
**UI needed:** File upload component calling this endpoint

### REQ-2: Consumer Loop Claims Items from DB
**Priority:** P0 (Blocker)

Consumer loop must:
- Query `work_items` for pending items (status=pending or status=completed from generator)
- Claim item before processing (set claimed_by, claimed_at)
- Pass claimed item to prompt template ({{ITEM_CONTENT}}, {{ITEM_TITLE}}, etc.)
- Update item status based on structured output
- Release claim on failure
- Exit when no pending items remain

**Backend exists:** `LoopExecutor._claim_source_item()`, `_mark_item_processed()`
**Issue:** WorkflowExecutor-created loops don't properly configure consume_from_step_id

### REQ-3: Structured Output Parsing (JSON Schema)
**Priority:** P1

**PREFERENCE:** Always use `claude -p --output-format stream-json --json-schema` for structured output. This guarantees parseable JSON and eliminates regex fragility.

**JSON Schema for Implementation Status:**
```json
{
  "type": "object",
  "properties": {
    "status": {
      "type": "string",
      "enum": ["implemented", "external", "duplicate", "skipped", "error"]
    },
    "details": {
      "type": "string",
      "description": "Implementation notes, product name, duplicate ID, or skip reason"
    },
    "files_changed": {
      "type": "array",
      "items": { "type": "string" },
      "description": "List of files created/modified"
    },
    "tests_passed": {
      "type": "boolean",
      "description": "Whether tests pass after implementation"
    }
  },
  "required": ["status", "details"]
}
```

**JSON Schema for Story Generation:**
```json
{
  "type": "object",
  "properties": {
    "stories": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": { "type": "string" },
          "priority": { "type": "integer" },
          "story": { "type": "string" },
          "acceptance_criteria": { "type": "array", "items": { "type": "string" } },
          "category": { "type": "string" },
          "notes": { "type": "string" }
        },
        "required": ["id", "story", "acceptance_criteria"]
      }
    }
  },
  "required": ["stories"]
}
```

**Benefits of JSON Schema:**
- Guaranteed valid JSON output
- No regex parsing needed
- Claude validates output before returning
- Easy to extend with new fields

### REQ-4: Generator Loop Creates Work Items
**Priority:** P1

Generator loop must:
- Execute Claude to generate stories (JSON array output)
- Parse JSON from output
- Create work_items in database for each story
- Deduplicate against existing items
- Git commit the changes

**Backend exists:** `LoopExecutor._create_work_items_from_output()`
**Issue:** Need to wire this to workflow step output

### REQ-5: Prompt Template Variables
**Priority:** P1

Templates must support these variables:
- `{{ITEM_ID}}` - Work item ID
- `{{ITEM_CONTENT}}` - Full content/story text
- `{{ITEM_TITLE}}` - Short title
- `{{ITEM_PRIORITY}}` - Priority number
- `{{ITEM_METADATA}}` - JSON metadata (acceptance_criteria, notes)
- `{{IMPLEMENTED_SUMMARY}}` - List of already-implemented items
- `{{DESIGN_DOC}}` - Full design document content

**Backend exists:** `LoopExecutor._build_prompt()` does variable substitution
**Issue:** Need IMPLEMENTED_SUMMARY aggregation

### REQ-6: Git Integration
**Priority:** P2

After successful implementation:
- Stage all changes (`git add -A`)
- Commit with message including story ID
- Include Co-Authored-By line

**Backend exists:** `LoopExecutor._handle_git_commit()`

### REQ-7: Phase/Category Filtering
**Priority:** P2

Consumer loop should support:
- `--phase N` - Only process items in phase N
- `--category CAT` - Only process items with category CAT

**Backend exists:** `LoopExecutor._category_filter`, `_phase_filter`
**UI needed:** Filter options in workflow step config

### REQ-8: Dependency-Aware Ordering
**Priority:** P2

Items should be processed in dependency order:
- Items can have `dependencies: ["ITEM-001", "ITEM-002"]`
- Don't process item until dependencies are completed
- Detect cycles and warn

**Backend exists:** `LoopExecutor._build_dependency_graph()`, `DependencyGraph`

---

## UI Flow for Creating Implementation Workflow

### Step 1: Create Workflow
1. Navigate to project
2. Click "+ New Workflow"
3. Enter name: "Feature Implementation"
4. Save

### Step 2: Add Planning Step (Optional)
If user wants to select which items to implement:
1. Add Step → Interactive
2. Name: "Review Stories"
3. Description: "Review and select stories to implement"

### Step 3: Add Implementation Step
1. Add Step → Autonomous
2. Name: "Implementation"
3. Type: Consumer
4. Configure:
   - Model: Opus
   - Timeout: 1800s
   - Tools: Read, Write, Edit, Bash, Glob, Grep
   - Consume from: Step 1 (or import source)

### Step 4: Import Stories
1. Go to Resources or dedicated Import tab
2. Click "Import JSONL"
3. Select file (e.g., `prd_RCM_software.jsonl`)
4. Choose format: hank_prd
5. Confirm import → Creates work_items in DB

### Step 5: Add Resources
1. Add Design Doc resource (file: `design/RCM_DESIGN.md`)
2. Add Guardrails resource (file: `GUARDRAILS.md`)
3. Add Implementation Prompt (template with variables)

### Step 6: Start Workflow
1. Click "Start Workflow"
2. (If planning step) Complete interactive planning
3. Autonomous step begins consuming items
4. Watch progress in UI
5. Workflow completes when all items processed

---

## Current Gaps (What's Broken)

| Gap | Severity | Notes |
|-----|----------|-------|
| No JSONL import in UI | P0 | API exists, need UI button |
| Consumer loop runs forever | P0 | Doesn't exit when no items |
| Work items not created via wizard | P0 | Wizard text goes to prompt, not DB |
| consume_from_step_id not set | P1 | WorkflowExecutor doesn't configure |
| No IMPLEMENTED_SUMMARY var | P1 | Need to aggregate from DB |
| No JSON schema for structured output | P1 | Use --json-schema flag |

---

## Test Plan

### Test 1: Import JSONL
1. Create workflow with consumer step
2. Import hank-rcm's `prd_RCM_software.jsonl`
3. Verify items appear in work_items table
4. Verify items scoped to workflow

### Test 2: Consumer Loop
1. Start workflow with imported items
2. Verify loop claims first pending item
3. Verify prompt includes item content
4. Verify Claude executes
5. Verify item marked as processed
6. Verify loop claims next item
7. Verify loop exits when no items remain

### Test 3: Full E2E
1. Import 5 pending stories
2. Start implementation workflow
3. Watch Claude implement each
4. Verify git commits created
5. Verify all items marked implemented/skipped/etc.
6. Verify workflow shows completed

---

## Files Referenced

- `/home/jackmd/Github/hank-rcm/ralph/ralph_rcm.sh` - Generator workflow
- `/home/jackmd/Github/hank-rcm/ralph/ralph_impl.sh` - Consumer workflow
- `/home/jackmd/Github/hank-rcm/ralph/PROMPT_IMPL.md` - Implementation prompt
- `/home/jackmd/Github/hank-rcm/ralph/PROMPT_RCM_TURBO.md` - Generator prompt (turbo)
- `/home/jackmd/Github/hank-rcm/ralph/PROMPT_RCM_DEEP.md` - Generator prompt (deep)
- `/home/jackmd/Github/hank-rcm/design/prd_RCM_software.jsonl` - Stories database
- `/home/jackmd/Github/hank-rcm/design/RCM_DESIGN.md` - Design document
