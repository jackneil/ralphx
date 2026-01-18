# Design Document: Workflow-First UX Transformation

## Executive Summary

Transform RalphX from a "loop-centric" to "workflow-centric" paradigm. Workflows become the primary organizing principle, with loops as implementation details within workflow steps. This creates a clearer mental model for users and positions the platform for future workflow types (bug fixes, support tickets, refactoring, etc.).

---

## Critical Refinements (Deep Dive Findings)

### CRITICAL GAP 1: Workflow-Loop Integration Missing

**Problem:** Workflows and loops are currently **completely disconnected systems**.
- Workflows exist in `workflows` table with steps
- Loops exist in `loops` table
- **No connection between them** - `LoopExecutor` has no awareness of workflows
- Workflow steps have a `loop_name` field but nothing populates or uses it

**Solution Required:** Create a `WorkflowExecutor` that:
1. Creates loops dynamically when autonomous steps start
2. Passes planning artifacts to loop context
3. Monitors loop completion and advances steps
4. Handles step transitions (auto vs manual)

**Status:** WorkflowExecutor now exists at `ralphx/core/workflow_executor.py`. Needs enhancement to use `workflow_resources` table.

### CRITICAL GAP 2: Artifact Flow Undefined

**Problem:** Planning artifacts don't flow to implementation.
- Planning artifacts stored in `planning_sessions.artifacts`
- `complete_planning_session` saves files to `.ralphx/resources/`
- **No mechanism to inject these into loop context**

**Solution:** When creating a step loop, explicitly add workflow artifacts as resources via `ResourceManager`. Store in `workflow_resources` table.

### CRITICAL GAP 3: Planning Chat Uses Placeholders

**Problem:** `planning.py:stream_planning_response` has hardcoded placeholder text instead of calling Claude.

**Solution:** This needs real Claude integration before workflow-first UX makes sense.

### Implementation Phases Concept (from hank-rcm)

**Key Insight:** When starting on an **empty codebase**, the system should:

1. **Group foundational stories together** (Phase 1: Foundation & Infrastructure)
2. **Use dependency-aware ordering** - topological sort based on story dependencies
3. **Execute architecture-building stories first** before domain logic

**How hank-rcm does it:**
- Stories have category prefixes (FND-001, DBM-002, SEC-003)
- Categories map to phases via `PHASE_CATEGORIES.json`
- Phase 1 = FND, DBM, SEC, ARC, ADM, DAT, DEP, SYS (foundational)
- System parses story text for dependencies ("requires X model", "uses X entity")
- Topological sort ensures proper execution order

**This should be integrated into the Implementation phase:**
- Detect if codebase is "empty" (new project)
- If empty: batch foundational stories together for architecture build
- Use design doc context heavily in first batch
- After foundation built, switch to normal story-by-story processing

---

## Current State Analysis

### What Exists Today

```
PROJECT PAGE (current)
├── Header + Stats
├── Navigation Links (Workflows | Run History | Work Items)
├── "Get Started" section (only shows when empty)
├── Active Workflows (grid)
├── Loops (grid, equal prominence)
├── Resources
└── Auth
```

**Problems:**
1. **Parallel hierarchy** - Workflows and Loops shown as equals, not parent-child
2. **Loop-first mental model** - Power users think in loops, casual users confused
3. **Hidden workflows** - "Get Started" disappears when any loop exists
4. **Navigation confusion** - Where do I start? What's a workflow vs a loop?
5. **No workflow context in loops** - Loops run independently, no awareness of belonging to a workflow

---

## Target State: Workflow-First UX

### Core Principle: Everything is Workflow-Scoped

**CRITICAL ARCHITECTURE DECISION:** Resources, work items, design docs, guardrails, and all artifacts belong to workflows, not projects. A workflow is a self-contained unit with everything it needs.

```
PROJECT
├── Workflow: "Build RCM System"
│   ├── Design Doc (created in planning, used by later steps)
│   ├── Guardrails (constraints for THIS workflow)
│   ├── Other Inputs (prompts, context for THIS workflow)
│   ├── Work Items (generated/consumed within THIS workflow)
│   └── Steps (Planning → Stories → Implementation)
│
├── Workflow: "Fix Bug #123"
│   ├── Its own design doc (or reference to shared)
│   ├── Its own guardrails (or inherit from project)
│   ├── Its own work items
│   └── Its own steps
│
└── Project Settings (shared across all workflows)
    ├── Authentication (GitHub tokens, API keys)
    ├── Shared Resource Library (templates workflows can import FROM)
    └── Default Guardrails (inherited by new workflows unless overridden)
```

### What is Project-Level vs Workflow-Level

| Resource Type | Scope | Rationale |
|--------------|-------|-----------|
| Design Docs | **Workflow** | Created in planning phase, specific to that workflow's goals |
| Guardrails | **Both** | Project has defaults, workflows can override or add |
| Work Items | **Workflow** | Generated by story phase, consumed by implementation |
| Input Files | **Workflow** | Specific to that workflow's context |
| Loops | **Workflow** | Implementation detail of workflow steps |
| Runs/History | **Workflow** | Execution history for that workflow |
| Auth/Tokens | **Project** | Shared credentials for all workflows |
| Resource Templates | **Project** | Library of reusable resources workflows can import |

### Visual Architecture

```
                    ┌──────────────────────────────────┐
                    │          PROJECT                  │
                    │                                   │
                    │   ┌─────────────────────────┐    │
                    │   │    ACTIVE WORKFLOWS     │    │
                    │   │                         │    │
                    │   │   ┌─────────────────┐   │    │
                    │   │   │  Build Product  │   │    │
                    │   │   │  Phase 3 of 3   │   │    │
                    │   │   │  ████░░░ 47%    │   │    │
                    │   │   │  📄 Design Doc  │   │    │
                    │   │   │  📋 134 Stories │   │    │
                    │   │   └─────────────────┘   │    │
                    │   │                         │    │
                    │   │   ┌─────────────────┐   │    │
                    │   │   │  Fix Bug #123   │   │    │
                    │   │   │  Phase 1 of 2   │   │    │
                    │   │   │  📋 3 Stories   │   │    │
                    │   │   └─────────────────┘   │    │
                    │   │                         │    │
                    │   │   [+ Start New Workflow] │    │
                    │   └─────────────────────────┘    │
                    │                                   │
                    │   ─────────────────────────────  │
                    │   ⚙ Project Settings              │
                    │     Auth, Shared Resources        │
                    │                                   │
                    └──────────────────────────────────┘
```

### Key Paradigm Shifts

| From (Current) | To (Workflow-First) |
|----------------|----------------------|
| Loops are primary | Workflows are primary |
| Create loop → run it | Create workflow → steps execute |
| Loops shown in grid | Workflows dominate, loops hidden inside steps |
| Namespace = loop name | Namespace = workflow identifier |
| Independent loops | Loops are tasks within steps |
| "What loop?" | "What are you trying to accomplish?" |

### Terminology Clarification

**Important:** This document uses two related but distinct terms:

| Term | Meaning | Example |
|------|---------|---------|
| **Step** | A stage in a workflow's execution sequence | "Planning", "Story Generation", "Implementation" |
| **Phase** | A batch of related work items within an implementation step | "Phase 1: Foundation", "Phase 2: Core Features" |

- **Workflow Steps** are stored in `workflow_steps` table. A workflow has 1-N steps.
- **Implementation Phases** are a batching strategy within a single "Implementation" step. Phase 1 groups architecture stories, Phase 2+ processes remaining stories.

The UI shows both: the step timeline at the top (Planning → Stories → Implementation), and within the Implementation step, the current phase being executed.

---

## Navigation Architecture

### Proposed Route Structure

```
/projects/:slug                              → ProjectWorkflowDashboard (list workflows, quick start)
/projects/:slug/dashboard                    → ProjectDashboard (cross-workflow stats, PM view)
/projects/:slug/workflows/:id                → WorkflowDetail (full workflow view)
/projects/:slug/workflows/:id/items          → Workflow's work items
/projects/:slug/workflows/:id/resources      → Workflow's resources (design doc, guardrails, inputs)
/projects/:slug/workflows/:id/runs           → Workflow's run history
/projects/:slug/settings                     → Project settings (auth, shared resources)
```

**Key Changes:**
- No more `/advanced` route. Work items and resources are accessed **within** a workflow context.
- New `/dashboard` route provides cross-workflow visibility for project managers (total items, progress across workflows).

### Sidebar Changes

**Current:**
```
├─ Projects (list)
├─ Logs
└─ Settings
```

**Proposed:**
```
├─ Projects
│   └─ hank-rcm
│       ├─ Build Product (workflow, active)
│       │   └─ Phase 3: Implementation ▶
│       ├─ Fix API Bug (workflow, paused)
│       └─ ⚙ Settings
├─ Logs
└─ Settings
```

The sidebar becomes workflow-aware, showing active workflows and their current phase per project. No "Advanced" section - everything is accessed through workflows.

---

## Page Designs

### 1. ProjectWorkflowDashboard (Replaces ProjectDetail)

**Purpose:** Project landing page focused on workflows

```
┌─────────────────────────────────────────────────────────────────┐
│  ← Dashboard                                                     │
│                                                                  │
│  hank-rcm                                                        │
│  /home/jackmd/Github/hank-rcm                          [⚙ Setup]│
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ╭─────────────────────────────────────────────────────────────╮│
│  │                                                              ││
│  │                  What would you like to do?                  ││
│  │                                                              ││
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐ ││
│  │  │ 🏗 Build       │  │ 🐛 Fix Bugs    │  │ 📦 Import      │ ││
│  │  │ Something New  │  │                │  │ Work           │ ││
│  │  │                │  │ Find and fix   │  │                │ ││
│  │  │ Start from an  │  │ bugs in your   │  │ Bring in       │ ││
│  │  │ idea, Claude   │  │ codebase       │  │ GitHub issues, │ ││
│  │  │ helps plan     │  │                │  │ stories, etc.  │ ││
│  │  │ and implement  │  │ [Coming Soon]  │  │                │ ││
│  │  │                │  │                │  │ [Coming Soon]  │ ││
│  │  │ [Start →]      │  └────────────────┘  └────────────────┘ ││
│  │  └────────────────┘                                          ││
│  │                                                              ││
│  ╰─────────────────────────────────────────────────────────────╯│
│                                                                  │
│  ─── Active Workflows ──────────────────────────────────────────│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 🏗 Build: RCM System                          Phase 3 of 3  ││
│  │                                                              ││
│  │ Planning ──✓── Stories ──✓── Implementation ──▶ 47%         ││
│  │                                                              ││
│  │ Currently: Implementing FND-047...              [Open →]    ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ─── Completed ─────────────────────────────────────────────────│
│  │ ✓ Initial Setup (2 days ago)                    [View →]    ││
│                                                                  │
│  ─────────────────────────────────────────────────────────────  │
│  ⚙ Project Settings                                              │
│    Authentication, Shared Resource Library                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key Elements:**
- **Workflow Quick Start Cards** - Prominent entry points for each workflow type
- **Active Workflows** - Primary content, always visible, shows workflow's items/resources count
- **Completed Workflows** - Collapsed by default, expandable
- **Project Settings** - Link to auth and shared resource templates (NOT workflow data)

### 2. WorkflowDetail (Phase Execution View)

**Purpose:** Full workflow execution interface

```
┌─────────────────────────────────────────────────────────────────┐
│  ← hank-rcm                                                      │
│                                                                  │
│  Build: RCM System                           [Pause] [⚙] [···]  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────┐       │
│  │ Planning │───▶│ Stories  │───▶│   Implementation     │       │
│  │    ✓     │    │    ✓     │    │   ▶ IN PROGRESS      │       │
│  └──────────┘    └──────────┘    └──────────────────────┘       │
│                                                                  │
│  ════════════════════════════════════════════════════════════   │
│                                                                  │
│  Phase 3: Implementation                                         │
│  ──────────────────────────────────────────────────────────────  │
│                                                                  │
│  Progress: 63 of 134 stories complete                           │
│  ████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  47%    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Currently Working On:                                        ││
│  │                                                              ││
│  │ FND-047: Add patient search API endpoint                    ││
│  │ Category: API | Priority: High | Dependencies: FND-003      ││
│  │                                                              ││
│  │ ┌─────────────────────────────────────────────────────────┐ ││
│  │ │ [Live Output]                                           │ ││
│  │ │                                                         │ ││
│  │ │ > Creating src/api/patients/search.py...                │ ││
│  │ │ > Adding search parameters...                           │ ││
│  │ │ > Writing tests...                                      │ ││
│  │ │ > ▌                                                     │ ││
│  │ └─────────────────────────────────────────────────────────┘ ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ Work Items (134)│  │ Resources (3)   │  │ Run History     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Phase-Specific Content:**

| Phase Type | Content Shown |
|------------|---------------|
| Interactive | PlanningChat component (conversation + artifacts) |
| Autonomous | Progress bar, current item, live output stream |
| Completed | Summary of artifacts produced, completion stats |

### 3. Workflow Resources Page (Workflow-Scoped)

**Purpose:** View and manage resources attached to THIS workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  ← Build: RCM System                                             │
│                                                                  │
│  Resources                                          [+ Add]      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [Design Doc] [Guardrails] [Input Files] [Other]                │
│  ═══════════                                                     │
│                                                                  │
│  ─── Design Document ───────────────────────────────────────────│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 📄 RCM System Design                            [View] [⚙] ││
│  │ Created: During Planning Phase | 2,450 words                ││
│  │                                                              ││
│  │ Describes the healthcare RCM system architecture,           ││
│  │ data models, API design, and user workflows.                ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ─── Guardrails ────────────────────────────────────────────────│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 🛡 HIPAA Compliance                       [Enabled] [View]  ││
│  │ Source: Project Default | Inherited                         ││
│  └─────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 🛡 Code Style Guidelines                  [Enabled] [View]  ││
│  │ Source: Workflow-Specific | Added manually                  ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  💡 Guardrails guide Claude's behavior during implementation.   │
│     Workflow guardrails override project defaults.              │
│                                                                  │
│  [Import from Project Library →]                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4. Workflow Work Items Page (Workflow-Scoped)

**Purpose:** View and manage work items for THIS workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  ← Build: RCM System                                             │
│                                                                  │
│  Work Items                                    [+ Add] [Import]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  134 total │ 63 completed │ 1 in progress │ 70 pending          │
│  ████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  47%      │
│                                                                  │
│  [All] [Pending] [In Progress] [Completed] [Failed]             │
│                                                                  │
│  Search: [________________________] Category: [All ▼]            │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ ● FND-047: Add patient search API endpoint                  ││
│  │   Category: API | Priority: High | In Progress              ││
│  │   Source: Story Generation Phase                            ││
│  └─────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ ○ FND-048: Patient search results pagination                ││
│  │   Category: API | Priority: Medium | Pending                ││
│  │   Depends on: FND-047                                       ││
│  └─────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ ✓ FND-046: Patient data validation                          ││
│  │   Category: API | Priority: High | Completed                ││
│  │   Completed: 2 hours ago                                    ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 5. Project Settings Page (Project-Level Only)

**Purpose:** Manage project-wide settings that apply to ALL workflows

```
┌─────────────────────────────────────────────────────────────────┐
│  ← hank-rcm                                                      │
│                                                                  │
│  Project Settings                                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [Authentication] [Shared Resources] [Defaults]                  │
│  ════════════════                                                │
│                                                                  │
│  ─── Authentication ────────────────────────────────────────────│
│                                                                  │
│  GitHub Token                                                    │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ ✓ Connected as @jackmd                      [Reconnect]     ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  💡 Authentication is shared across all workflows in this       │
│     project. Claude uses these credentials for git operations.  │
│                                                                  │
│  ─── Shared Resource Library ───────────────────────────────────│
│                                                                  │
│  Resources here can be imported into any workflow.              │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 🛡 HIPAA Compliance Guardrail               [Used by: 2]    ││
│  │ 🛡 Code Style Guidelines                    [Used by: 1]    ││
│  │ 📄 Company API Standards                    [Used by: 0]    ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│                                        [+ Add Shared Resource]   │
│                                                                  │
│  ─── Default Settings for New Workflows ────────────────────────│
│                                                                  │
│  ☑ Auto-inherit HIPAA Compliance guardrail                      │
│  ☑ Auto-inherit Code Style Guidelines                           │
│  ☐ Require design doc before implementation                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Model Adjustments

### Current Schema (Exists)

```sql
workflows (id, template_id, name, namespace, status, current_step, ...)
workflow_steps (id, workflow_id, step_number, name, step_type, loop_name, ...)
planning_sessions (id, workflow_id, step_id, messages, artifacts, ...)
```

Note: The existing schema uses "step" terminology. This design continues that pattern.

### Proposed Schema Changes

```sql
-- ============================================================
-- WORKFLOW-SCOPED RESOURCES (New Architecture)
-- ============================================================

-- Work items MUST belong to a workflow (CASCADE delete to prevent orphans)
ALTER TABLE work_items ADD COLUMN workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE;
ALTER TABLE work_items ADD COLUMN source_step_id INTEGER REFERENCES workflow_steps(id) ON DELETE SET NULL;

-- Loops are implementation details of workflow steps (CASCADE delete)
ALTER TABLE loops ADD COLUMN workflow_id TEXT REFERENCES workflows(id) ON DELETE CASCADE;
ALTER TABLE loops ADD COLUMN step_id INTEGER REFERENCES workflow_steps(id) ON DELETE SET NULL;
ALTER TABLE loops ADD COLUMN auto_created BOOLEAN DEFAULT FALSE;

-- Runs belong to workflows (CASCADE delete)
ALTER TABLE runs ADD COLUMN workflow_id TEXT REFERENCES workflows(id) ON DELETE CASCADE;
ALTER TABLE runs ADD COLUMN step_id INTEGER REFERENCES workflow_steps(id) ON DELETE SET NULL;

-- Workflow-specific resources (design docs, guardrails, inputs)
CREATE TABLE workflow_resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    resource_type TEXT NOT NULL,  -- 'design_doc', 'guardrail', 'input_file', 'prompt'
    name TEXT NOT NULL,
    content TEXT,                  -- For inline content
    file_path TEXT,                -- For file references
    source TEXT,                   -- 'planning_phase', 'manual', 'imported', 'inherited'
    source_id TEXT,                -- Reference to project_resource if inherited
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- PROJECT-LEVEL SHARED RESOURCES (Template Library)
-- ============================================================

-- Shared resources that workflows can import FROM
CREATE TABLE project_resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_type TEXT NOT NULL,  -- 'guardrail', 'prompt_template', 'config'
    name TEXT NOT NULL,
    content TEXT,
    file_path TEXT,
    auto_inherit BOOLEAN DEFAULT FALSE,  -- If true, new workflows get this by default
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX idx_work_items_workflow ON work_items(workflow_id, status);
CREATE INDEX idx_work_items_step ON work_items(source_step_id);
CREATE INDEX idx_loops_workflow ON loops(workflow_id);
CREATE INDEX idx_runs_workflow ON runs(workflow_id);
CREATE INDEX idx_workflow_resources_workflow ON workflow_resources(workflow_id, resource_type);
CREATE INDEX idx_workflow_resources_type ON workflow_resources(resource_type, enabled);
```

### Resource Scoping Rules

| Resource | Belongs To | Can Reference |
|----------|------------|---------------|
| Work Item | Workflow (required) | Source step that created it |
| Design Doc | Workflow | Created by planning phase |
| Guardrail | Workflow or Project | Workflow inherits from project if not overridden |
| Input File | Workflow | Uploaded to or generated for workflow |
| Loop | Workflow | Auto-created by workflow step |
| Run | Workflow | Execution within workflow step |

### Namespace Strategy

**Current:** Loop name = namespace (e.g., `planning_20260115_1`)

**Proposed:** Workflow namespace is primary, all items inherit:
```
Workflow: "rcm-system-a7b3c2"
├── Work items namespace = "rcm-system-a7b3c2"
├── Phase 1: Planning → artifacts stored in workflow_resources
├── Phase 2: Stories → loop namespace = "rcm-system-a7b3c2-stories"
└── Phase 3: Impl → loop namespace = "rcm-system-a7b3c2-impl"
```

This allows:
- Items to be queried by workflow (all phases)
- Items to be queried by step (specific loop)
- Clear provenance of where items came from
- Resources to be scoped and inherited properly

---

## Phase Transition Logic

### Transition Rules

| Phase Type | Completion Trigger | Advancement |
|------------|-------------------|-------------|
| Interactive (Planning) | User clicks "Complete Planning" | Manual - user must confirm |
| Autonomous (Generator) | Loop finishes all iterations | Auto - immediately start next phase |
| Autonomous (Consumer) | All source items processed | Auto - immediately start next phase |
| Manual Review | User clicks "Approve" | Manual - user must confirm |

### Implementation Phase Special Logic

When starting the Implementation phase on a **new project** (user opts in):

1. **User checks "new project" box** - During workflow creation
2. **Identify foundation stories** - Categories: FND, DBM, SEC, ARC, architecture, foundation
3. **Batch mode activation** - Group 10-20 foundational stories
4. **Architecture build prompt** - Use design doc heavily, emphasize building coherent foundation
5. **Switch to normal mode** - After foundation batch, process stories one-by-one

### Artifact Flow

```
Planning Phase
├── User chats with Claude
├── Artifacts generated: design_doc, guardrails, architecture
└── Stored in: planning_sessions.artifacts
        ↓
        ↓ Phase Transition
        ↓
Story Generation Phase
├── Loop created with type=generator
├── Context includes: design_doc from planning (via ResourceManager)
├── Generates work_items with namespace=<workflow>-stories
└── Artifacts: none (items are the output)
        ↓
        ↓ Phase Transition
        ↓
Implementation Phase
├── Loop created with type=consumer
├── item_types.input.source = <workflow>-stories namespace
├── Context includes: design_doc, architecture (inherited)
├── If new project: batch foundational stories first
├── Processes each item → marks completed
└── Workflow complete when all items done
```

---

## Implementation Plan

### Phase 1: Backend Foundation (Prerequisites)

**1.1 Database Schema Updates**

Files: `ralphx/core/project_db.py`, `ralphx/core/database.py`

**1.2 WorkflowExecutor Class**

Note: This class already exists at `ralphx/core/workflow_executor.py`. The example below shows the key methods:

```python
class WorkflowExecutor:
    """Orchestrates multi-step workflow execution."""

    def start_step(self, workflow_id: str, step_number: int):
        """Start executing a workflow step."""
        step = self.db.get_workflow_step_by_number(workflow_id, step_number)

        if step.step_type == "interactive":
            # Just mark as started - PlanningChat handles UI
            self.db.start_workflow_step(step.id)

        elif step.step_type == "autonomous":
            # Create and start the loop for this step
            loop_config = self._create_step_loop(workflow, step)

            # Inject planning artifacts into loop context
            self._inject_artifacts(loop_config, workflow)

            # Save loop with workflow context
            self.db.save_loop(loop_config, workflow_id=workflow.id, step_id=step.id)

            # Start loop execution (async)
            executor = LoopExecutor(...)
            await executor.run()

    def on_loop_complete(self, run_id: str):
        """Handle loop completion - potentially advance step."""
        run = self.db.get_run(run_id)
        if run.workflow_id and run.step_id:
            step = self.db.get_workflow_step(run.step_id)
            if step.config.get("auto_advance", True):
                self.advance_to_next_step(run.workflow_id)

    def _inject_artifacts(self, loop_config, workflow):
        """Add planning artifacts to loop context.

        TODO: Update to save to workflow_resources table instead of
        using add_dynamic_resource (which goes to loop_resources).
        """
        session = self.db.get_planning_session_by_workflow(workflow.id)
        if session and session.artifacts:
            if session.artifacts.get("design_doc"):
                # Current: adds to loop_resources
                # Future: should save to workflow_resources
                self.resource_manager.add_dynamic_resource(
                    loop_config.name,
                    "design_doc",
                    session.artifacts["design_doc"]
                )
```

**1.3 Implementation Phases Logic**

Update `LoopExecutor` to support architecture-first mode:

```python
def _get_foundation_stories(self) -> list[WorkItem]:
    """Get foundational stories to batch together."""
    foundation_categories = ["FND", "DBM", "SEC", "ARC", "foundation", "architecture"]
    return self.db.list_items(
        categories=foundation_categories,
        status="pending",
        limit=20
    )
```

**1.4 MCP Server Workflow Tools**

Add to `ralphx/mcp_server.py`:
```python
ralphx_list_workflows(slug)
ralphx_get_workflow(slug, workflow_id)
ralphx_create_workflow(slug, template_id, name)
ralphx_start_workflow(slug, workflow_id)
ralphx_pause_workflow(slug, workflow_id)
ralphx_advance_workflow(slug, workflow_id)
```

### Phase 2: Frontend Routes & Shell

**2.1 Update Routes** (`frontend/src/App.tsx`)
```
/projects/:slug                    → ProjectWorkflowDashboard
/projects/:slug/workflows/:id      → WorkflowDetail
/projects/:slug/advanced           → AdvancedSetup
/projects/:slug/runs               → RunHistory
```

**2.2 Create Shell Pages**
- `ProjectWorkflowDashboard.tsx` (replaces ProjectDetail)
- `AdvancedSetup.tsx` (new, tabbed interface)

**2.3 Update Sidebar** (`frontend/src/components/Sidebar.tsx`)
- Show workflow hierarchy under active project
- Display current phase indicator
- Collapse other projects

### Phase 3: Workflow Quick Start

**3.1 Create Components**
- `WorkflowQuickStart.tsx` - Grid of quick start cards
- `WorkflowWizardModal.tsx` - Enhanced wizard with modular phases

**3.2 Modular Phase Selection**

### Phase 4: Active Workflow Display

**4.1 ActiveWorkflowCard Component**
- Shows phase timeline with progress
- Current phase indicator
- Quick action buttons

**4.2 Enhanced WorkflowDetail**
- Embedded `SessionTail` for autonomous steps
- Live progress updates
- Current work item display

### Phase 5: Polish & Migration

**5.1 Move Loop Management to Advanced**
- Remove loop grid from main project page
- Add to AdvancedSetup tabs

**5.2 Deprecate WorkflowHub**
- Merge functionality into ProjectWorkflowDashboard
- Redirect old routes

---

## Workflow Creation Wizard

### Modular Approach

```
┌─────────────────────────────────────────────────────────────────┐
│  Create New Workflow                                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  What do you need to do?                                        │
│                                                                  │
│  ○ Build something from scratch (Recommended)                   │
│    Planning → Story Generation → Implementation                 │
│                                                                  │
│  ○ I have a design doc, generate stories and implement          │
│    Story Generation → Implementation                            │
│    → Next step will ask you to upload your design doc           │
│                                                                  │
│  ○ I have stories, just implement them                          │
│    Implementation only                                          │
│    → Next step will let you import stories                      │
│                                                                  │
│  ○ I just want to plan / create a design doc                    │
│    Planning only                                                │
│                                                                  │
│  ○ Custom workflow                                               │
│    Pick and arrange your own phases                             │
│                                                                  │
│  ─────────────────────────────────────────────────────────────  │
│  ☑ This is a new project - build foundation first               │
│    (Groups architecture stories together for initial build)     │
│                                                                  │
│                                           [Next →]               │
└─────────────────────────────────────────────────────────────────┘
```

### Conditional Wizard Steps

When user selects **"I have a design doc"**, the next wizard step is:

```
┌─────────────────────────────────────────────────────────────────┐
│  Upload Your Design Document                              Step 2│
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Claude will use your design to generate implementation stories.│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                                                              ││
│  │  📄 Drag and drop your design doc here                      ││
│  │                                                              ││
│  │  or [Browse Files]                                          ││
│  │                                                              ││
│  │  Supported: .md, .txt, .pdf                                 ││
│  │                                                              ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  Or paste content directly:                                     │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                                                              ││
│  │  Paste your design document here...                         ││
│  │                                                              ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  💡 Include: requirements, architecture, data models, user flows│
│                                                                  │
│                                    [Back]  [Start Workflow →]   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

When user selects **"I have stories"**, the next wizard step is:

```
┌─────────────────────────────────────────────────────────────────┐
│  Import Your Stories                                      Step 2│
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Import work items from a file or paste them directly.          │
│                                                                  │
│  [Upload JSONL] [Upload CSV] [Paste JSON]                       │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Preview: 47 stories found                                   ││
│  │                                                              ││
│  │ ✓ FND-001: Core data models                                 ││
│  │ ✓ FND-002: Database schema                                  ││
│  │ ✓ FND-003: Authentication system                            ││
│  │ ... 44 more                                                 ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  💡 Stories will be processed in dependency order.              │
│                                                                  │
│                                    [Back]  [Start Workflow →]   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Files to Create/Modify Summary

### Backend (Phase 1 - Critical)

| File | Action | Notes |
|------|--------|-------|
| `ralphx/core/workflow_executor.py` | Exists | Orchestrates workflow steps, creates loops, handles transitions |
| `ralphx/core/project_db.py` | Modify | **Add `workflow_resources` table** (currently missing), add ON DELETE CASCADE to work_items |
| `ralphx/core/database.py` | Modify | Add project_resources table for shared library |
| `ralphx/core/executor.py` | Modify | Add batch architecture mode, workflow context |
| `ralphx/core/resources.py` | Modify | Support workflow-scoped resources, inheritance from project |
| `ralphx/api/routes/workflows.py` | Modify | Call WorkflowExecutor, add resource endpoints |
| `ralphx/api/routes/planning.py` | Modify | Connect completion to step advancement, save artifacts to workflow_resources |
| `ralphx/api/routes/items.py` | Keep | workflow_id optional in query params allows cross-workflow dashboard; items REQUIRE workflow_id in DB (NOT NULL) |
| `ralphx/mcp_server.py` | Modify | Add workflow tools |

**Implementation Gap:** The `workflow_resources` table defined in the schema section does not exist in the current `project_db.py`. It must be added as part of implementation. Currently, planning artifacts are stored in `planning_sessions.artifacts` and injected via `loop_resources`. The migration should:

1. Add `workflow_resources` table to schema
2. Update `WorkflowExecutor._inject_artifacts()` to write to `workflow_resources` instead of `loop_resources`
3. Add CRUD operations for workflow resources
4. Add API endpoints for workflow resource management

### Frontend (Phase 2-5)

| File | Action | Notes |
|------|--------|-------|
| `frontend/src/pages/ProjectWorkflowDashboard.tsx` | **Create** | Replaces ProjectDetail, shows workflows |
| `frontend/src/pages/WorkflowDetail.tsx` | Modify | Full workflow view with tabs for items/resources |
| `frontend/src/pages/WorkflowResources.tsx` | **Create** | Workflow-scoped resources management |
| `frontend/src/pages/WorkflowItems.tsx` | **Create** | Workflow-scoped work items list |
| `frontend/src/pages/ProjectSettings.tsx` | **Create** | Auth and shared resource library |
| `frontend/src/components/workflow/WorkflowQuickStart.tsx` | **Create** | Quick start cards |
| `frontend/src/components/workflow/ActiveWorkflowCard.tsx` | **Create** | Rich workflow card with timeline |
| `frontend/src/App.tsx` | Modify | Update routes (remove /advanced, add workflow sub-routes) |
| `frontend/src/components/Sidebar.tsx` | Modify | Add workflow hierarchy, remove Advanced link |
| `frontend/src/pages/AdvancedSetup.tsx` | **Delete** | No longer needed - resources are workflow-scoped |
| `frontend/src/pages/ProjectDetail.tsx` | Delete | Replaced by ProjectWorkflowDashboard |

---

## Design Decisions (Resolved)

1. **Multiple concurrent workflows:** Yes - users can have several workflows in progress simultaneously
2. **Resource scoping:** Resources (design docs, guardrails, work items) belong to workflows, not projects
3. **Shared resources:** Project can have a "library" of resources that workflows can import/inherit
4. **Guardrail inheritance:** New workflows auto-inherit project guardrails marked as `auto_inherit`
5. **No Advanced section:** Removed - all data is accessed through workflow context
6. **Completed workflows:** Collapsed section on project page, still accessible with all their data
7. **Phase auto-advancement:** Autonomous phases auto-advance; interactive phases require user confirmation
8. **Empty codebase detection:** Ask user during workflow creation (checkbox)
9. **Artifact storage:** Planning artifacts saved to workflow_resources table, injected into loop context
10. **Planning Chat placeholders:** Fix as part of implementation - needs real Claude integration
11. **Standalone loops:** Not supported in UI - all loops created automatically by workflow steps
12. **Workflow cascade delete:** Work items, loops, runs are deleted when parent workflow is deleted (ON DELETE CASCADE)
13. **Cross-workflow view:** Project dashboard includes summary stats across all workflows for PM visibility

---

## Access Control (Single-User MVP)

### Current Scope

This design assumes **single-user operation** per project. All workflows, resources, and items within a project are accessible to whoever has filesystem access to the project directory.

### Future RBAC Considerations

When multi-user support is added, consider:

| Resource | Read Access | Write Access | Delete Access |
|----------|-------------|--------------|---------------|
| Workflow | Project members | Workflow owner | Workflow owner + Admin |
| Work Items | Project members | Workflow owner | Workflow owner + Admin |
| Shared Resources | Project members | Project admin | Project admin |
| Project Settings | Project admin | Project admin | Project admin |

**Not in scope for MVP:** User authentication, role-based permissions, team collaboration features.

## Resolved Questions

1. **Story category detection:** Use category prefixes
   - Story generation must assign categories (FND-, ARC-, DBM-, etc.)
   - Foundation categories: FND, DBM, SEC, ARC, ADM, DAT, DEP, SYS
   - Matches how hank-rcm works with PHASE_CATEGORIES.json

2. **Batch size for architecture mode:** 10-20 stories in first batch
   - Can be tuned per project in workflow settings

3. **What defines "empty codebase"?** Ask user during workflow creation
   - Add checkbox in workflow wizard: "This is a new project, build foundation first"
   - Most explicit, gives user control
   - Avoids false positives/negatives from file detection

---

## Verification

### Workflow-First UX Working

1. **New project, no content:** Quick start cards visible, workflows prominent
2. **Existing project with workflows:** Active workflows shown with item/resource counts
3. **Click workflow card:** Goes to WorkflowDetail, phase execution visible
4. **Work items scoped:** /workflows/:id/items shows only that workflow's items
5. **Resources scoped:** /workflows/:id/resources shows only that workflow's resources
6. **Create new workflow:** Wizard opens, workflow created, lands on Phase 1

### Backend Integration Working

1. **WorkflowExecutor creates loops** when autonomous steps start
2. **Artifacts saved to workflow_resources** during planning step
3. **Artifacts injected into loop context** when steps start
4. **New project checkbox** triggers batch architecture mode
5. **Step auto-advance** works for autonomous steps
6. **MCP tools** can list/start/pause workflows
7. **Workflow deletion cascades** to work_items, loops, runs (no orphans)

### Resource Scoping Working

1. **Work items require workflow_id** - cannot exist without workflow
2. **Design docs saved to workflow_resources** after planning
3. **Guardrails inherited** from project but can be overridden per workflow
4. **Shared resource library** at project level for templates
5. **No orphaned resources** - everything belongs to a workflow or project library
6. **CASCADE DELETE on workflow_id** - work_items deleted when workflow deleted

### Navigation Clear

1. **Sidebar shows workflows** per project with current phase
2. **Breadcrumb trail** shows: Dashboard > Project > Workflow > [Items|Resources|Runs]
3. **Project Settings** link for auth and shared library only
4. **Cross-workflow dashboard** available at /projects/:slug/dashboard for PM view

### Loops Properly Subordinate

1. **No standalone loop creation** in UI
2. **Loops created automatically** when workflow steps start
3. **Loop namespace** derived from workflow namespace
4. **Loop hidden from users** - they see "steps" and "phases" instead

---

## UX Design: Two User Personas

### Persona 1: Non-Technical User (Primary)

**Characteristics:**
- May not know what "loops", "namespaces", "generators", "consumers" mean
- Just wants to build something and have Claude help
- Needs hand-holding through each step
- Should never see confusing technical jargon

**Design Principles:**
1. **Outcome-oriented language** - "What do you want to build?" not "What loop type?"
2. **Zero jargon in primary flows** - Hide technical concepts behind simple choices
3. **Guided wizard experience** - Step-by-step with explanations
4. **Sensible defaults** - Make the right choice automatic
5. **Progressive disclosure** - Advanced options hidden until needed

### Persona 2: Power User (Secondary)

**Characteristics:**
- Understands the loop system, YAML configs, CLI
- Wants direct control over configuration
- Needs clear docs on what each setting does
- Comfortable with advanced features

**Design Principles:**
1. **Direct access to configuration** - YAML editor, CLI commands visible
2. **All options available** - No artificial limitations
3. **Technical documentation** - API equivalents, performance notes
4. **Batch operations** - Import/export, templates, duplication

---

## Terminology Mapping

Replace technical jargon with outcome-oriented language:

| Technical Term | Non-Technical Alternative | When to Use Technical |
|----------------|--------------------------|----------------------|
| Loop | Process / Workflow Phase | Advanced section only |
| Generator | "Create items" / "Generate stories" | Power user tooltips |
| Consumer | "Process items" / "Implement stories" | Power user tooltips |
| Hybrid | (Hide from non-technical users) | Advanced only |
| Namespace | (Never show to users) | Internal only |
| Modes | "AI Strategies" / "Approaches" | Power user section |
| Mode Selection Strategy | "How Claude works" | Power user section |
| Weighted Random | (Hide from non-technical) | Advanced only |
| Items | "Stories" / "Tasks" / "Work" | Context-dependent |

---

## Non-Technical User Flow: Workflow Creation

### Step 1: Project Dashboard - Clear Entry Point

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  What would you like to do?                                     │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                                                              ││
│  │  🏗  BUILD SOMETHING NEW                                     ││
│  │                                                              ││
│  │  Start with an idea. Claude will help you:                  ││
│  │  1. Plan and design your project                            ││
│  │  2. Break it into buildable stories                         ││
│  │  3. Implement each story automatically                      ││
│  │                                                              ││
│  │  Perfect for: New features, new projects, rebuilds          ││
│  │                                                              ││
│  │                                    [Get Started →]           ││
│  │                                                              ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ──────────── or ─────────────                                  │
│                                                                  │
│  [I have a design doc →]  [I have stories →]  [Custom...]       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key UX Decisions:**
- **Primary card is large and inviting** - Most users want this
- **"Get Started" not "Create Workflow"** - Action-oriented, non-technical
- **Explains the 3 steps visually** - User knows what to expect
- **Secondary options below** - For users with existing artifacts
- **"Custom..." is subtle** - Power users find it, beginners don't click

### Step 2: Workflow Wizard - Guided Questions

```
┌─────────────────────────────────────────────────────────────────┐
│  Build Something New                                    Step 1/3│
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  What are you building?                                         │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Give your project a name                                    ││
│  │ ┌─────────────────────────────────────────────────────────┐ ││
│  │ │ Patient Portal Redesign                                 │ ││
│  │ └─────────────────────────────────────────────────────────┘ ││
│  │                                                              ││
│  │ 💡 This helps Claude understand your project context        ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  Is this a new project starting from scratch?                   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ ○ Yes, starting fresh                                       ││
│  │   Claude will build the foundation first, then add features ││
│  │                                                              ││
│  │ ○ No, adding to existing code                               ││
│  │   Claude will integrate with your existing codebase         ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│                                    [Back]  [Continue →]         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key UX Decisions:**
- **One question per step** - Never overwhelm
- **Plain language** - "starting fresh" not "empty codebase"
- **Inline explanation** - User understands the choice impact
- **Progress indicator** - "Step 1/3" creates confidence

### Step 3: Planning Phase - Conversational

```
┌─────────────────────────────────────────────────────────────────┐
│  Build: Patient Portal Redesign                      Phase 1/3  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────┐       │
│  │▶Planning │───▶│ Stories  │───▶│   Implementation     │       │
│  │  NOW     │    │          │    │                      │       │
│  └──────────┘    └──────────┘    └──────────────────────┘       │
│                                                                  │
│  ═══════════════════════════════════════════════════════════    │
│                                                                  │
│  Let's plan your project                                        │
│  ──────────────────────────────────────────────────────────     │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 💬 Tell me about what you're building. What problem      │   │
│  │    are you solving? Who will use it?                     │   │
│  │                                                          │   │
│  │ 💡 The more context you give, the better the design.     │   │
│  │    Include any requirements, constraints, or ideas.      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                                                          │   │
│  │  Type here...                                            │   │
│  │                                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ─────────────────────────────────────────────────────────────  │
│  📎 Have a design doc? [Upload or paste it →]                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key UX Decisions:**
- **Phase timeline at top** - User knows where they are in the process
- **Conversational prompt** - Natural language, not form fields
- **Helpful hints** - But not overwhelming
- **Optional upload** - Not required, just available

### Step 4: Stories Phase - Automated with Visibility

```
┌─────────────────────────────────────────────────────────────────┐
│  Build: Patient Portal Redesign                      Phase 2/3  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────┐       │
│  │ Planning │───▶│▶Stories │───▶│   Implementation     │       │
│  │    ✓     │    │  NOW     │    │                      │       │
│  └──────────┘    └──────────┘    └──────────────────────┘       │
│                                                                  │
│  ═══════════════════════════════════════════════════════════    │
│                                                                  │
│  Generating buildable stories from your design...               │
│  ──────────────────────────────────────────────────────────     │
│                                                                  │
│  ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  12 of 47   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ ✓ FND-001: Core data models                              │   │
│  │ ✓ FND-002: Database schema                               │   │
│  │ ✓ FND-003: Authentication system                         │   │
│  │ ● FND-004: User management API...                        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  💡 Claude is breaking your design into implementable pieces.   │
│     Each story is a focused unit of work.                       │
│                                                                  │
│                                    [Pause]  [View All Stories]  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key UX Decisions:**
- **Progress visible** - User sees it's working
- **Story list scrolls** - Can see what's being created
- **Explanation of what's happening** - "breaking your design into pieces"
- **Control buttons** - Can pause if needed

### Step 5: Implementation Phase - Hands-Off Magic

```
┌─────────────────────────────────────────────────────────────────┐
│  Build: Patient Portal Redesign                      Phase 3/3  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────┐       │
│  │ Planning │───▶│ Stories  │───▶│▶Implementation       │       │
│  │    ✓     │    │    ✓     │    │  NOW                 │       │
│  └──────────┘    └──────────┘    └──────────────────────┘       │
│                                                                  │
│  ═══════════════════════════════════════════════════════════    │
│                                                                  │
│  Claude is implementing your stories...                         │
│  ──────────────────────────────────────────────────────────     │
│                                                                  │
│  Progress: 23 of 47 stories complete                            │
│  ████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  49%        │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Currently working on:                                    │   │
│  │                                                          │   │
│  │ FND-024: Add patient search API                          │   │
│  │ Creating src/api/patients/search.py...                   │   │
│  │                                                          │   │
│  │ ┌──────────────────────────────────────────────────────┐ │   │
│  │ │ > Adding search parameters...                        │ │   │
│  │ │ > Implementing pagination...                         │ │   │
│  │ │ > Writing tests...                                   │ │   │
│  │ │ > ▌                                                  │ │   │
│  │ └──────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  💡 You can leave this running. Claude will keep working.       │
│     Check back anytime to see progress.                         │
│                                                                  │
│                          [Pause]  [View Stories]  [View Code]   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key UX Decisions:**
- **"Hands-off magic"** - User can walk away
- **Live output visible** - Builds trust, shows it's working
- **Reassurance message** - "You can leave this running"
- **Multiple views** - Can see stories or code if curious

---

## Power User Flow: Advanced/Custom Route

### Entry Point: "Custom..." Link

```
[I have a design doc →]  [I have stories →]  [Custom...]
                                                   ↓
                                         Opens Advanced Builder
```

### Advanced Builder: Full Control

```
┌─────────────────────────────────────────────────────────────────┐
│  Custom Workflow Builder                                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [Visual Builder]  [YAML Editor]  [CLI]                         │
│  ═══════════════════════════════════════════════════════════    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Workflow Phases                          [+ Add Phase]  │    │
│  │                                                          │    │
│  │ ┌───────────────────────────────────────────────────┐   │    │
│  │ │ 1. Planning (Interactive)              [⚙] [✕]   │   │    │
│  │ │    Chat with Claude to create design doc          │   │    │
│  │ └───────────────────────────────────────────────────┘   │    │
│  │ ┌───────────────────────────────────────────────────┐   │    │
│  │ │ 2. Story Generation (Autonomous)       [⚙] [✕]   │   │    │
│  │ │    Generator loop → creates work items            │   │    │
│  │ └───────────────────────────────────────────────────┘   │    │
│  │ ┌───────────────────────────────────────────────────┐   │    │
│  │ │ 3. Implementation (Autonomous)         [⚙] [✕]   │   │    │
│  │ │    Consumer loop → processes work items           │   │    │
│  │ └───────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Available Phase Types                                   │    │
│  │                                                          │    │
│  │ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │    │
│  │ │ Interactive │ │ Generator   │ │ Consumer    │        │    │
│  │ │ (Chat)      │ │ (Create)    │ │ (Process)   │        │    │
│  │ └─────────────┘ └─────────────┘ └─────────────┘        │    │
│  │                                                          │    │
│  │ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │    │
│  │ │ Review      │ │ Analyzer    │ │ Custom      │        │    │
│  │ │ (Approve)   │ │ (Scan)      │ │ (Define)    │        │    │
│  │ └─────────────┘ └─────────────┘ └─────────────┘        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key UX Decisions:**
- **Three tabs: Visual / YAML / CLI** - Power users choose their mode
- **Drag-and-drop phases** - Visual configuration
- **Technical labels visible** - "Interactive", "Generator", "Consumer"
- **Phase type library** - All options available
- **Gear icon for settings** - Deep configuration per phase

### Phase Configuration (Power User View)

```
┌─────────────────────────────────────────────────────────────────┐
│  Configure: Story Generation Phase                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Phase Type: Generator Loop                                     │
│  ───────────────────────────────────────────────────────────    │
│                                                                  │
│  Loop Name: rcm-stories-generator                               │
│  Namespace: rcm-workflow-abc123-stories                         │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Modes                                    [+ Add Mode]   │    │
│  │                                                          │    │
│  │ ┌─────────────────────────────────────────────────────┐ │    │
│  │ │ Mode: analyze                                       │ │    │
│  │ │ Model: opus | Timeout: 1800s                        │ │    │
│  │ │ Template: .ralphx/resources/loop_template/...       │ │    │
│  │ └─────────────────────────────────────────────────────┘ │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Mode Selection Strategy                                  │    │
│  │                                                          │    │
│  │ ○ Fixed (use same mode every iteration)                 │    │
│  │ ○ Random (pick randomly)                                │    │
│  │ ○ Weighted Random (specify weights)                     │    │
│  │ ○ Phase-Aware (different modes for Phase 1)             │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Limits                                                   │    │
│  │                                                          │    │
│  │ Max Iterations: [50]     Max Runtime: [28800] seconds   │    │
│  │ Max Errors: [3]          Cooldown: [5] seconds          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ───────────────────────────────────────────────────────────    │
│  📖 Docs: Generator loops create work items from Claude output. │
│     Items are stored with namespace for the next phase.         │
│                                                                  │
│  CLI equivalent:                                                │
│  $ ralphx loops run my-project story-generator --iterations 50  │
│                                                                  │
│                                    [Cancel]  [Save Phase]       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key UX Decisions:**
- **Technical labels exposed** - "Generator Loop", "Namespace"
- **All configuration options** - Modes, strategies, limits
- **Documentation inline** - Explains what's happening
- **CLI equivalent shown** - Power users can switch to CLI

### YAML Editor Tab

```
┌─────────────────────────────────────────────────────────────────┐
│  Custom Workflow Builder                                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [Visual Builder]  [YAML Editor]  [CLI]                         │
│                    ═══════════════                               │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 1  name: rcm-workflow                                   │    │
│  │ 2  phases:                                              │    │
│  │ 3    - number: 1                                        │    │
│  │ 4      name: Planning                                   │    │
│  │ 5      type: interactive                                │    │
│  │ 6      description: Chat with Claude to design          │    │
│  │ 7    - number: 2                                        │    │
│  │ 8      name: Story Generation                           │    │
│  │ 9      type: autonomous                                 │    │
│  │10      loopType: generator                              │    │
│  │11      loopConfig:                                      │    │
│  │12        modes:                                         │    │
│  │13          analyze:                                     │    │
│  │14            model: opus                                │    │
│  │15            timeout: 1800                              │    │
│  │                                                          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ✓ Valid YAML                                                   │
│                                                                  │
│  📖 Schema Reference  |  Examples  |  Import from file          │
│                                                                  │
│                                    [Validate]  [Create]         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key UX Decisions:**
- **Full YAML editing** - Direct control
- **Real-time validation** - Immediate feedback
- **Schema reference link** - For documentation
- **Import capability** - Copy configs between projects

---

## Inline Help & Guidance System

### Help Component Patterns

**1. Contextual Tooltip (Hover)**
```
[?] ← Icon next to field label
     ↓
┌─────────────────────────────────┐
│ Mode Selection Strategy         │
│                                 │
│ Determines how Claude picks     │
│ which approach to use for each  │
│ iteration.                      │
│                                 │
│ • Fixed: Same every time        │
│ • Random: Varies each run       │
│ • Weighted: You set probability │
│                                 │
│ [Learn more →]                  │
└─────────────────────────────────┘
```

**2. Inline Guidance (Always Visible)**
```
┌─────────────────────────────────────────────────────────────────┐
│  Design Document                                                 │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ [Browse...] No file selected                                ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  💡 Optional. If you have a PRD, spec, or design doc, add it   │
│     here. Claude will use it to understand your project.       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**3. Collapsible Deep Dive (Click to Expand)**
```
┌─────────────────────────────────────────────────────────────────┐
│  ▼ How does story generation work?                              │
│  ───────────────────────────────────────────────────────────    │
│                                                                  │
│  Claude reads your design document and breaks it into discrete  │
│  "stories" - each one a focused unit of work.                   │
│                                                                  │
│  Stories include:                                                │
│  • A clear description of what to build                         │
│  • Acceptance criteria                                          │
│  • Dependencies on other stories                                │
│  • A category (FND, API, UI, etc.)                              │
│                                                                  │
│  Example story:                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ FND-003: User authentication system                     │    │
│  │ Implement login/logout with JWT tokens                  │    │
│  │ Depends on: FND-001 (database), FND-002 (user model)    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**4. Error with Fix Suggestion**
```
┌─────────────────────────────────────────────────────────────────┐
│  Workflow Name                                                   │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ My New Workflow!                                            ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ⚠️ Names can only use lowercase letters, numbers, and dashes.  │
│     Try: "my-new-workflow" [Use this →]                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Empty States with Guidance

### No Workflows Yet

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│                     🏗                                           │
│                                                                  │
│           No workflows yet                                      │
│                                                                  │
│  Start your first workflow to build something with Claude.     │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Most popular:                                            │    │
│  │                                                          │    │
│  │ [🏗 Build from scratch]  Start with an idea, end with    │    │
│  │                           working code                    │    │
│  │                                                          │    │
│  │ [📄 From design doc]     Already have a spec? Generate   │    │
│  │                           stories and implement           │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  [View all options...]                                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Workflow Paused

```
┌─────────────────────────────────────────────────────────────────┐
│  Build: Patient Portal                           ⏸ PAUSED       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│                     ⏸                                           │
│                                                                  │
│           Workflow paused                                       │
│                                                                  │
│  Implementation was paused at 34 of 47 stories.                 │
│  Claude will pick up where it left off when you resume.         │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ What would you like to do?                               │    │
│  │                                                          │    │
│  │ [▶ Resume]     Continue implementation                   │    │
│  │                                                          │    │
│  │ [View Stories] See what's done and what's left           │    │
│  │                                                          │    │
│  │ [⚙ Settings]   Adjust implementation settings            │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Settings Guidance

### Project Settings Page

```
┌─────────────────────────────────────────────────────────────────┐
│  ← hank-rcm                                                      │
│                                                                  │
│  Project Settings                                                │
│  ───────────────────────────────────────────────────────────    │
│                                                                  │
│  ⚙ Settings that apply to all workflows in this project        │
│                                                                  │
│  [Authentication]  [Shared Resources]  [Defaults]               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Shared Resource Library

```
┌─────────────────────────────────────────────────────────────────┐
│  Shared Resource Library                               [+ Add]   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  💡 Resources here can be imported into any workflow.           │
│     Mark resources as "auto-inherit" to add them to new         │
│     workflows automatically.                                     │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 🛡 HIPAA Compliance                                      │    │
│  │   Type: Guardrail | Auto-inherit: ✓ | Used by: 2 workflows   │
│  │   [View] [Edit] [···]                                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 📄 Company API Standards                                 │    │
│  │   Type: Design Template | Auto-inherit: ☐ | Used by: 0      │
│  │   [View] [Edit] [···]                                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Workflow Resource Import

When viewing a workflow's resources, users can import from project library:

```
┌─────────────────────────────────────────────────────────────────┐
│  Import from Project Library                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Select resources to import into this workflow:                  │
│                                                                  │
│  ☑ 🛡 HIPAA Compliance (already inherited)                      │
│  ☐ 📄 Company API Standards                                     │
│  ☐ 🛡 Performance Guidelines                                    │
│                                                                  │
│  💡 Imported resources are copied to the workflow. Changes to   │
│     the project library won't affect already-imported copies.   │
│                                                                  │
│                                    [Cancel]  [Import Selected]   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Future Enhancements

### Reusable Interactive Claude Chat Component

**Goal:** Create a generic interactive chat component that can be reused for different Claude-driven conversations, not just planning sessions.

**Use Cases:**
1. **Planning Sessions** (current) - Design document creation
2. **Workflow Maker Wizard** - User describes what they want, Claude suggests/configures workflow structure
3. **Custom Step Configuration** - Claude helps configure step parameters
4. **Interactive Debugging** - Claude helps troubleshoot failed runs

**Architecture:**

```typescript
interface ClaudeConversation {
  systemPrompt: string           // What role Claude plays
  initialContext?: string        // Background info (project details, available tools, etc.)
  responseSchema?: JSONSchema    // Optional structured response format
  onStructuredResponse?: (data: StructuredResponse) => void
  onArtifacts?: (artifacts: Record<string, string>) => void
}

// Example: Workflow Maker Wizard
const workflowMakerConversation: ClaudeConversation = {
  systemPrompt: `You are a workflow configuration assistant. Help users set up
                 the right workflow for their needs. Ask clarifying questions,
                 then respond with a structured workflow configuration.`,
  initialContext: `Available workflow templates: build-product, from-design-doc,
                   from-stories, planning-only. User can also create custom workflows.`,
  responseSchema: {
    type: 'object',
    properties: {
      action: { enum: ['ask_question', 'suggest_workflow'] },
      question?: { type: 'string' },
      workflow?: {
        type: 'object',
        properties: {
          template_id: { type: 'string' },
          custom_steps: { type: 'array' },
          config: { type: 'object' }
        }
      }
    }
  },
  onStructuredResponse: (data) => {
    if (data.action === 'suggest_workflow') {
      // Create workflow from Claude's suggestion
      createWorkflow(data.workflow)
    }
  }
}
```

**Benefits:**
- Single component for all interactive Claude experiences
- Consistent UX across different conversation types
- Structured responses enable Claude to drive UI/actions
- Can evolve to support more complex multi-turn workflows

**Implementation Notes:**
- Component should handle streaming responses
- Support both freeform and structured response modes
- Allow interruption/cancellation mid-stream
- Persist conversation history for resume

### Testing Workflow Step

**Goal:** Add a "Testing" step type that can be included in workflows for automated testing, including browser-based UX testing.

**Step Types to Support:**

1. **Unit/Integration Testing**
   - Run test suites after implementation
   - Report failures back to workflow
   - Option to auto-fix failing tests

2. **Browser-Based UX Testing**
   - Use browser automation (Playwright, Puppeteer, or Claude-in-Chrome MCP)
   - Visual regression testing
   - User flow verification
   - Accessibility checks

3. **Manual Review Step**
   - Pause workflow for human review
   - Provide checklist of things to verify
   - Capture feedback for next iteration

**Workflow Template Example:**

```yaml
name: Build with Testing
steps:
  - name: Planning
    type: interactive
  - name: Story Generation
    type: autonomous
    loopType: generator
  - name: Implementation
    type: autonomous
    loopType: consumer
  - name: Testing
    type: autonomous
    loopType: tester
    config:
      run_unit_tests: true
      run_e2e_tests: true
      browser_testing:
        enabled: true
        flows:
          - login_flow
          - checkout_flow
  - name: Review
    type: interactive
    description: Human review before merge
```

**Integration Points:**
- Claude-in-Chrome MCP for browser automation
- Test framework integrations (pytest, jest, playwright)
- Screenshot/video capture for UX verification
- Failure feedback loop to implementation step
