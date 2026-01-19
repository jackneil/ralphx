# Workflow Archive & Step Management Design Document

## Overview

This document outlines the design for two related workflow management features:
1. **Workflow Archiving** - Soft-delete workflows by archiving instead of permanent deletion
2. **Step Management** - Add and remove steps from existing workflows

## Goals

- Users should never permanently lose workflow data accidentally
- Archived workflows should be recoverable
- Users should be able to customize workflow structure after creation
- All changes should be tracked and auditable

---

## Part 1: Workflow Archiving

### Current Behavior

Currently, deleting a workflow:
- Permanently removes the workflow record from `workflows` table
- CASCADE deletes all related data (steps, sessions, resources, items, runs)
- No recovery possible

### Proposed Behavior

Instead of permanent deletion:
1. **Archive** - Mark workflow as archived (soft delete)
2. **Restore** - Unarchive a previously archived workflow
3. **Permanent Delete** - Only available for archived workflows, requires confirmation

### Database Changes

#### Schema Change

Add `archived_at` column to `workflows` table:

```sql
ALTER TABLE workflows ADD COLUMN archived_at TIMESTAMP;
```

Using a timestamp instead of boolean because:
- We can see *when* it was archived
- NULL means active, non-NULL means archived
- Supports future features like "auto-purge after 30 days"

#### Migration

Add to `_migrate_schema()` in `project_db.py`:

```python
# Migration 11 -> 12: Add workflow archiving
if current_version < 12:
    conn.execute("ALTER TABLE workflows ADD COLUMN archived_at TIMESTAMP")
```

Update `PROJECT_SCHEMA_VERSION = 12`

### API Changes

#### WorkflowResponse Model

Add field:
```python
class WorkflowResponse(BaseModel):
    # ... existing fields ...
    archived_at: Optional[str] = None
```

#### New Endpoints

```python
@router.post("/{slug}/workflows/{workflow_id}/archive")
async def archive_workflow(slug: str, workflow_id: str) -> WorkflowResponse:
    """Archive a workflow (soft delete)."""
    # Set archived_at = current timestamp
    # Return updated workflow

@router.post("/{slug}/workflows/{workflow_id}/restore")
async def restore_workflow(slug: str, workflow_id: str) -> WorkflowResponse:
    """Restore an archived workflow."""
    # Set archived_at = NULL
    # Return updated workflow

@router.delete("/{slug}/workflows/{workflow_id}")
async def delete_workflow(slug: str, workflow_id: str):
    """Permanently delete a workflow (only works if archived)."""
    # Check if archived
    # If not archived, return error "Archive first"
    # If archived, perform permanent delete
```

#### List Workflows Filter

Update list endpoint to filter by archive status:

```python
@router.get("/{slug}/workflows")
async def list_workflows(
    slug: str,
    include_archived: bool = Query(False),
    archived_only: bool = Query(False),
) -> list[WorkflowResponse]:
    """List workflows for a project."""
```

### Frontend Changes

#### WorkflowDetail.tsx

Replace delete button behavior:
- Current: `handleDelete` -> permanent delete
- New: `handleArchive` -> archive workflow

Add archive confirmation dialog:
```typescript
const handleArchive = async () => {
  const result = await Swal.fire({
    title: 'Archive Workflow?',
    text: 'This workflow will be moved to the archive. You can restore it later.',
    icon: 'info',
    showCancelButton: true,
    confirmButtonText: 'Archive',
  })
  if (result.isConfirmed) {
    await archiveWorkflow(slug, workflowId)
    navigate(`/projects/${slug}/workflows`)
  }
}
```

#### New: ArchivedWorkflowsPanel Component

Display in project settings or workflows page:

```tsx
function ArchivedWorkflowsPanel({ projectSlug }: { projectSlug: string }) {
  const [workflows, setWorkflows] = useState<Workflow[]>([])

  useEffect(() => {
    listWorkflows(projectSlug, { archivedOnly: true })
      .then(setWorkflows)
  }, [projectSlug])

  const handleRestore = async (workflowId: string) => {
    await restoreWorkflow(projectSlug, workflowId)
    // Refresh list
  }

  const handlePermanentDelete = async (workflowId: string) => {
    const result = await Swal.fire({
      title: 'Permanently Delete?',
      text: 'This cannot be undone. All workflow data will be lost.',
      icon: 'error',
      showCancelButton: true,
      confirmButtonColor: 'var(--color-rose)',
    })
    if (result.isConfirmed) {
      await deleteWorkflow(projectSlug, workflowId)
    }
  }

  return (
    <div className="card">
      <h2>Archived Workflows</h2>
      {workflows.map(wf => (
        <div key={wf.id}>
          <span>{wf.name}</span>
          <span>Archived: {formatDate(wf.archived_at)}</span>
          <button onClick={() => handleRestore(wf.id)}>Restore</button>
          <button onClick={() => handlePermanentDelete(wf.id)}>Delete Forever</button>
        </div>
      ))}
    </div>
  )
}
```

#### Where to Show Archived Workflows

Options:
1. **Project Settings page** - Add "Archived Workflows" section
2. **Workflows list page** - Add toggle "Show Archived"
3. **Both** - Settings for management, list for visibility

Recommendation: **Both**
- Workflows list shows archived with visual distinction (grayed out)
- Project settings has full archive management UI

---

## Part 2: Step Management

### Use Cases

1. **Add Step** - Insert a new step into an existing workflow
2. **Remove Step** - Delete a step (with data handling)
3. **Reorder Steps** - Change step sequence (future enhancement)

### Constraints

- Cannot remove a step that has active runs
- Cannot remove a step that generated items for downstream steps (unless cascade)
- Step numbers must remain sequential

### Database Operations

#### Add Step

```python
def add_workflow_step(
    workflow_id: str,
    step_number: int,  # Where to insert
    name: str,
    step_type: str,  # 'interactive' or 'autonomous'
    config: Optional[dict] = None,
) -> WorkflowStep:
    """Add a new step to a workflow.

    1. Shift existing steps at step_number+ up by 1
    2. Insert new step at step_number
    3. Update workflow if current_step affected
    """
    # UPDATE workflow_steps SET step_number = step_number + 1
    #   WHERE workflow_id = ? AND step_number >= ?
    # INSERT INTO workflow_steps (workflow_id, step_number, name, step_type, config)
    #   VALUES (?, ?, ?, ?, ?)
```

#### Remove Step

```python
def remove_workflow_step(
    workflow_id: str,
    step_number: int,
    cascade: bool = False,  # If true, delete generated items
) -> bool:
    """Remove a step from a workflow.

    Validation:
    1. Step must not have active runs
    2. If step has generated items and cascade=False, reject

    Actions:
    1. Delete the step and related data (loop, resources, sessions)
    2. If cascade, delete items with source_step_id = step_id
    3. Shift remaining steps down
    4. Update workflow current_step if needed
    """
```

### API Endpoints

```python
@router.post("/{slug}/workflows/{workflow_id}/steps")
async def add_step(
    slug: str,
    workflow_id: str,
    request: AddStepRequest,
) -> WorkflowStepResponse:
    """Add a new step to the workflow."""

class AddStepRequest(BaseModel):
    step_number: int  # Position to insert (1-based)
    name: str
    step_type: str  # 'interactive' or 'autonomous'
    config: Optional[dict] = None

@router.delete("/{slug}/workflows/{workflow_id}/steps/{step_number}")
async def remove_step(
    slug: str,
    workflow_id: str,
    step_number: int,
    cascade: bool = Query(False),
) -> dict:
    """Remove a step from the workflow."""
```

### Frontend Changes

#### WorkflowEditor Enhancement

Add step management to the existing workflow editor modal:

```tsx
function WorkflowEditor({ workflow, projectSlug, onClose, onSave }) {
  const [steps, setSteps] = useState(workflow.steps)

  const handleAddStep = async (afterStepNumber: number) => {
    const result = await Swal.fire({
      title: 'Add Step',
      html: `
        <input id="step-name" placeholder="Step name">
        <select id="step-type">
          <option value="interactive">Interactive (Chat)</option>
          <option value="autonomous">Autonomous (Loop)</option>
        </select>
      `,
      confirmButtonText: 'Add',
      preConfirm: () => ({
        name: document.getElementById('step-name').value,
        step_type: document.getElementById('step-type').value,
      }),
    })

    if (result.isConfirmed) {
      await addWorkflowStep(projectSlug, workflow.id, {
        step_number: afterStepNumber + 1,
        name: result.value.name,
        step_type: result.value.step_type,
      })
      onSave()
    }
  }

  const handleRemoveStep = async (stepNumber: number) => {
    const step = steps.find(s => s.step_number === stepNumber)

    // Check if step has data
    const hasData = step.iterations_completed > 0 || step.items_generated > 0

    if (hasData) {
      const result = await Swal.fire({
        title: 'Step Has Data',
        text: 'This step has generated data. Delete the data too?',
        icon: 'warning',
        showCancelButton: true,
        showDenyButton: true,
        confirmButtonText: 'Delete Step & Data',
        denyButtonText: 'Keep Data',
        cancelButtonText: 'Cancel',
      })

      if (result.isConfirmed) {
        await removeWorkflowStep(projectSlug, workflow.id, stepNumber, true)
        onSave()
      }
    } else {
      const result = await Swal.fire({
        title: 'Remove Step?',
        text: `Remove "${step.name}" from this workflow?`,
        icon: 'question',
        showCancelButton: true,
      })

      if (result.isConfirmed) {
        await removeWorkflowStep(projectSlug, workflow.id, stepNumber, false)
        onSave()
      }
    }
  }

  return (
    <div className="modal">
      {steps.map((step, idx) => (
        <div key={step.id} className="step-row">
          <span>{step.step_number}. {step.name}</span>
          <button onClick={() => handleRemoveStep(step.step_number)}>
            Remove
          </button>
          <button onClick={() => handleAddStep(step.step_number)}>
            + Add After
          </button>
        </div>
      ))}
      <button onClick={() => handleAddStep(0)}>
        + Add First Step
      </button>
    </div>
  )
}
```

---

## Implementation Order

### Phase 1: Archiving (Simpler)
1. Database migration for `archived_at`
2. Update WorkflowResponse model
3. Add archive/restore endpoints
4. Update delete endpoint (require archived)
5. Frontend: Archive button replaces delete
6. Frontend: Archived workflows panel

### Phase 2: Step Management
1. Add step database operation
2. Remove step database operation
3. API endpoints
4. Frontend: WorkflowEditor enhancement

---

## Data Safety Considerations

### Archive Safety
- Archive is always safe (no data loss)
- Permanent delete requires double confirmation
- Consider auto-purge policy (e.g., archive > 90 days)

### Step Removal Safety
- Block removal of steps with active runs
- Warn about cascade delete
- Consider "orphan" handling for items whose source step is removed

---

## Testing Plan

### Archive Tests
1. Archive active workflow -> should succeed
2. List workflows -> archived not shown by default
3. List workflows with include_archived -> shows all
4. Restore archived workflow -> should succeed
5. Delete non-archived workflow -> should fail
6. Delete archived workflow -> should succeed

### Step Management Tests
1. Add step at beginning -> step numbers shift
2. Add step in middle -> step numbers shift
3. Add step at end -> just appends
4. Remove step with no data -> succeeds
5. Remove step with data, no cascade -> fails
6. Remove step with data, cascade=true -> succeeds
7. Remove step with active run -> fails

---

## Future Enhancements

1. **Step Reordering** - Drag and drop to change order
2. **Step Cloning** - Duplicate a step configuration
3. **Archive Auto-Purge** - Delete after X days
4. **Bulk Archive** - Archive multiple workflows at once
5. **Archive Search** - Search within archived workflows
