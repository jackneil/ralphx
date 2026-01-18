# Plan: Run hank-rcm Implementation Loop via RalphX UI

## Goal
Replicate exactly what `ralph_impl.sh` does, but via the RalphX web UI.

## What ralph_impl.sh Does

1. **Source**: `design/prd_RCM_software.jsonl` (3072 pending stories)
2. **Design Doc**: `design/RCM_DESIGN.md` injected into every prompt
3. **Per Story**:
   - Build prompt with: story content, acceptance criteria, design doc, implemented summary
   - Run Claude (opus, 30min timeout)
   - Parse structured output: IMPLEMENTED, EXTERNAL, DUP_OF, SKIPPED, ERROR
   - Mark story status in JSONL
   - Git commit if implemented
4. **Loop**: Until all done or max iterations

## RalphX UI Steps

### Step 1: Create Workflow
- Navigate to: http://localhost:5173/projects/hank-rcm/workflows
- Click "+ New Workflow"
- Name: "Feature Implementation"
- Save

### Step 2: Add Implementation Step
- Click "Add Step"
- Type: Autonomous
- Name: "Implement Stories"
- Loop Type: consumer
- Model: opus (or sonnet for testing)
- Timeout: 1800 seconds
- Tools: Read, Write, Edit, Bash, Glob, Grep
- Save

### Step 3: Add Design Doc Resource
- Go to Resources tab
- Add Resource:
  - Type: design_doc
  - Name: "RCM Design Document"
  - Content: Copy from `/home/jackmd/Github/hank-rcm/design/RCM_DESIGN.md`
- This gets injected into every prompt

### Step 4: Import Stories from JSONL
- Click "Import" button on workflow page
- Select file: `design/prd_RCM_software.jsonl`
- Format: HANK PRD Format
- Target Step: "Implement Stories"
- Click Import
- Should see: "Imported 3072 items"

### Step 5: Start Workflow
- Click "Start Workflow"
- Consumer loop begins:
  - Claims first pending story
  - Builds prompt with: story + design doc + implemented_summary
  - Runs Claude
  - Parses structured JSON output
  - Marks story with status
  - Claims next story
  - Repeats until all done

## Verification Checklist

- [ ] Workflow created with 1 autonomous consumer step
- [ ] Design doc added as resource
- [ ] 3072 stories imported
- [ ] Workflow starts and claims first story
- [ ] Claude receives story content + acceptance criteria
- [ ] Claude returns structured JSON status
- [ ] Story marked in DB with correct status
- [ ] Loop continues to next story
- [ ] Can pause/resume workflow

## Files Referenced

- `/home/jackmd/Github/hank-rcm/design/prd_RCM_software.jsonl` - Stories to import
- `/home/jackmd/Github/hank-rcm/design/RCM_DESIGN.md` - Design doc to inject
- `/home/jackmd/Github/hank-rcm/ralph/PROMPT_IMPL.md` - Reference for prompt format
