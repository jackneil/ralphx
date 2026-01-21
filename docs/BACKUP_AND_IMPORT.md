# Backup and Import Guide

RalphX provides comprehensive backup and import capabilities for workflows and work items. This guide covers all export/import operations and their use cases.

---

## Quick Reference

| Operation | File Format | What's Included | Where to Find |
|-----------|-------------|-----------------|---------------|
| Export Workflow | `.ralphx.zip` | Steps, items, resources, planning sessions | Workflow Detail → "Export Workflow" |
| Import Workflow | `.ralphx.zip` | Creates new workflow from archive | Project Dashboard → "Import Workflow" |
| Import Items | `.jsonl` | Add work items (user stories) to a step | Workflow Detail → Items tab → "Import Items" |

---

## Workflow Export

Export an entire workflow as a portable `.ralphx.zip` archive for backup or sharing.

### What's Included

The export archive contains:

```
workflow-namespace-20240115-143022.ralphx.zip
├── manifest.json       # Metadata, version, contents summary
├── workflow.json       # Workflow definition + steps
├── items.jsonl         # All work items (JSONL format)
├── resources/          # Workflow-level resources (design docs, guardrails)
│   └── resources.json
├── step-resources/     # Step-level resource overrides
│   └── step-resources.json
├── planning/           # Planning session artifacts (optional)
│   └── session.json
└── runs/               # Execution history (optional)
    └── runs.json
```

### Export Options

| Option | Default | Description |
|--------|---------|-------------|
| Include Planning | Yes | Include planning session artifacts |
| Include Planning Messages | No | Include full conversation history (larger file) |
| Include Runs | No | Include execution history |
| Include Step Artifacts | No | Include step output artifacts |
| Strip Secrets | Yes | Automatically redact detected secrets |

### How to Export

**From the Dashboard:**
1. Open the workflow you want to export
2. Click **"Export Workflow"** button in the header
3. Configure options if needed
4. Download the `.ralphx.zip` file

**Via Claude Code (MCP):**
```
Ask Claude: "Export the 'my-feature' workflow from my project"
```

### Security Features

**Secret Detection**: Before export, RalphX scans content for potential secrets:
- API keys (sk-*, AKIA*, etc.)
- JWT tokens
- Database URIs with passwords
- Private keys
- Password/secret assignments in code
- Bearer tokens

**Secret Stripping**: By default, detected secrets are replaced with `[REDACTED]`. Disable this only if you're certain the export doesn't contain sensitive data.

**Export Size Limits**:
- Maximum archive size: 500 MB
- Maximum files in archive: 10,000
- Maximum items exported: 100,000

---

## Workflow Import

Import a `.ralphx.zip` archive to create a new workflow in your project.

### What Happens During Import

1. **Validation**: Archive is validated for format, security, and compatibility
2. **ID Regeneration**: All IDs are regenerated to prevent collisions
3. **Namespace Uniqueness**: If namespace exists, a suffix is added (e.g., `my-workflow-1`)
4. **Status Reset**: Workflow and items start fresh with `draft`/`pending` status
5. **File Path Removal**: Any file paths are ignored for security (content is inlined)

### How to Import

**From the Dashboard:**
1. Go to your project's workflow dashboard
2. Click **"Import Workflow"** button
3. Select a `.ralphx.zip` file
4. Review the import preview
5. Click **"Import"** to create the workflow

**Via Claude Code (MCP):**
```
Ask Claude: "Import the workflow from workflow-backup.ralphx.zip"
```

### Import Preview

Before importing, you'll see:
- Workflow name and namespace
- Number of steps, items, and resources
- Whether planning sessions or runs are included
- Compatibility notes
- Potential secrets warning (if not stripped during export)

### Compatibility

| Export Version | Import Support |
|----------------|----------------|
| 1.0 | ✓ Full support |
| Higher | May not be compatible |

Schema version differences are handled automatically with migration where possible.

### Security Validations

RalphX performs several security checks during import:

- **Zip Bomb Protection**: Rejects archives with compression ratio > 100:1
- **Path Traversal Prevention**: Rejects paths containing `..` or absolute paths
- **Symlink Rejection**: Symlinks in archives are not allowed
- **Size Limits**: Archives > 500 MB uncompressed are rejected
- **File Path Sanitization**: External file paths are never imported

---

## Items Import (JSONL)

Import work items (user stories, tasks) from a JSONL file into a specific workflow step.

### When to Use

- **Power users**: Bulk import items from external sources
- **Migration**: Move items between projects
- **Templates**: Apply predefined story sets to new workflows

> **Note**: Most users should let Claude generate stories from the design doc. JSONL import is an advanced feature.

### JSONL Format

Each line is a JSON object representing one work item:

```jsonl
{"id": "USR-001", "title": "User login", "content": "As a user, I want to log in...", "priority": "high", "category": "authentication"}
{"id": "USR-002", "title": "Password reset", "content": "As a user, I want to reset my password...", "priority": "medium", "category": "authentication"}
{"id": "USR-003", "title": "Profile settings", "content": "As a user, I want to update my profile...", "priority": "low", "category": "user-management"}
```

### Required and Optional Fields

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique identifier (e.g., "USR-001", "FEAT-123") |
| `title` | Recommended | Short title for the item |
| `content` | Recommended | Full description (user story format) |
| `priority` | No | "high", "medium", "low", or custom |
| `category` | No | Grouping category |
| `item_type` | No | "story", "task", "bug", etc. |
| `tags` | No | Array of string tags |
| `phase` | No | Development phase |
| `dependencies` | No | Array of item IDs this depends on |
| `metadata` | No | Custom JSON object |

### How to Import Items

**From the Dashboard:**
1. Open the workflow
2. Go to the **Items** tab
3. Click **"Import Items"** button
4. Select a `.jsonl` file
5. Items are added to the current step

**Via Claude Code (MCP):**
```
Ask Claude: "Import user stories from stories.jsonl into step 1 of my workflow"
```

### Conflict Handling

When importing items into a workflow that already has items:

- **Duplicate IDs are skipped**: If an item with the same ID already exists, the new item is not imported
- **No data loss**: Existing items are never modified or deleted
- **Items are added**: Non-conflicting items are added alongside existing ones

### Example JSONL Files

**Basic User Stories:**
```jsonl
{"id": "USR-001", "title": "User registration", "content": "As a new user, I want to create an account so I can access the application.", "priority": "high"}
{"id": "USR-002", "title": "Email verification", "content": "As a registered user, I want to verify my email so my account is activated.", "priority": "high"}
```

**With Dependencies:**
```jsonl
{"id": "API-001", "title": "Create user endpoint", "content": "POST /api/users - Create new user", "item_type": "task"}
{"id": "API-002", "title": "Get user endpoint", "content": "GET /api/users/:id - Retrieve user", "item_type": "task", "dependencies": ["API-001"]}
```

**With Metadata:**
```jsonl
{"id": "BUG-001", "title": "Login timeout", "content": "Users report being logged out after 5 minutes", "item_type": "bug", "priority": "critical", "metadata": {"reported_by": "support", "ticket": "SUP-1234"}}
```

---

## Advanced: Merge Into Existing Workflow

RalphX supports merging an exported workflow into an existing one (available via API/MCP).

### Conflict Resolution Options

| Mode | Behavior |
|------|----------|
| `skip` | Skip items/resources that conflict |
| `rename` | Auto-rename with unique suffix |
| `overwrite` | Replace existing with imported |

### Merge Options

- **Import items**: Yes/No
- **Import resources**: Yes/No
- **Import planning**: Yes/No
- **Selected step IDs**: Import only specific steps
- **Target step ID**: Which step to put imported items into

---

## Troubleshooting

### "Export format is newer than supported"

The archive was created with a newer version of RalphX. Update your RalphX installation:
```bash
pip install --upgrade ralphx
```

### "Archive exceeds maximum size"

The workflow has too much data. Try:
- Disable "Include Runs" and "Include Planning Messages"
- Export with fewer items (archive older workflows separately)

### "Compression ratio too high"

This is a security check. The archive may be malformed or a zip bomb. Verify the source of the file.

### "Missing manifest.json"

The file is not a valid RalphX export archive. Ensure you're importing a `.ralphx.zip` file.

### Items Not Appearing After Import

- Check that the JSONL file is valid (each line is valid JSON)
- Verify item IDs are unique
- Check for duplicate IDs that were skipped

---

## Best Practices

1. **Regular Backups**: Export important workflows before major changes
2. **Strip Secrets**: Always enable secret stripping when sharing exports
3. **Use Descriptive IDs**: In JSONL imports, use meaningful item IDs (e.g., "AUTH-001" not "1")
4. **Test Imports**: Import into a test project first to verify content
5. **Document Dependencies**: When using item dependencies, ensure all referenced items exist

---

## File Format Reference

### manifest.json

```json
{
  "version": "1.0",
  "format": "ralphx-workflow-export",
  "exported_at": "2024-01-15T14:30:22Z",
  "ralphx_version": "0.2.0",
  "schema_version": 7,
  "workflow": {
    "id": "wf-abc123",
    "name": "My Feature Workflow",
    "namespace": "my-feature",
    "template_id": "story-implementation"
  },
  "contents": {
    "steps": 3,
    "items_total": 47,
    "resources": 2,
    "has_planning_session": true,
    "has_runs": false
  },
  "security": {
    "potential_secrets_detected": false,
    "secrets_stripped": true,
    "paths_sanitized": true
  },
  "export_options": {
    "include_runs": false,
    "include_planning": true,
    "include_planning_messages": false,
    "include_step_artifacts": false
  }
}
```

### workflow.json

```json
{
  "workflow": {
    "id": "wf-abc123",
    "name": "My Feature Workflow",
    "namespace": "my-feature",
    "template_id": "story-implementation",
    "status": "draft",
    "current_step": 1
  },
  "steps": [
    {
      "id": 1,
      "workflow_id": "wf-abc123",
      "step_number": 1,
      "name": "Generate Stories",
      "step_type": "ralph_loop",
      "status": "pending",
      "config": {...},
      "loop_name": "story-generation"
    }
  ]
}
```

### items.jsonl

```jsonl
{"id":"USR-001","workflow_id":"wf-abc123","source_step_id":1,"title":"User login","content":"As a user...","priority":"high","status":"pending","category":"auth"}
{"id":"USR-002","workflow_id":"wf-abc123","source_step_id":1,"title":"User logout","content":"As a user...","priority":"medium","status":"pending","category":"auth"}
```
