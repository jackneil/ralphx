# Workflow UX Improvements - Design Document

## Overview

Issues and improvements identified during E2E testing of the hank-rcm workflow in RalphX.

---

## Completed Features

### 12. Resource Inline Editing & Versioning
**Status:** ✅ Implemented
**Files:** `frontend/src/components/workflow/WorkflowTimeline.tsx`, `frontend/src/pages/WorkflowDetail.tsx`, `frontend/src/api.ts`, `ralphx/core/project_db.py`, `ralphx/api/routes/workflows.py`

**Features:**
- **Inline Edit**: Click "Edit" on any resource in the viewer panel to modify content directly
- **Save Confirmation**: Modal warning that changes apply to ALL steps in the workflow
- **Auto-Versioning**: Every edit creates a version snapshot BEFORE overwriting
- **Version History**: Click "History" to view up to 50 past versions with timestamps
- **Restore**: Preview and restore any previous version (creates new version first)
- **Optimistic Locking**: Concurrent edits detected via `expected_updated_at` - second save gets 409 Conflict
- **Toast Notifications**: Feedback on save success and errors

**Database Changes:**
- Schema v14 → v15
- New table: `workflow_resource_versions` (id, workflow_resource_id, version_number, content, name, created_at)
- Microsecond-precision timestamps for reliable conflict detection

**API Endpoints:**
- `GET /workflows/{id}/resources/{resource_id}/versions` - Paginated version list
- `POST /workflows/{id}/resources/{resource_id}/versions/{version_id}/restore` - Restore old version

---

## Critical Bugs (Fixed)

### 1. JSON Extraction Regex Bug
**File:** `ralphx/core/executor.py`
**Issue:** Non-greedy regex `\[[\s\S]*?\]` found inner arrays (like `acceptance_criteria`) instead of the outer `stories` array.
**Fix:** Look for `{"stories": [...]}` pattern first, then fall back to greedy array matching.

### 2. Stream Parsing Bug
**File:** `ralphx/adapters/claude_cli.py`
**Issue:** Claude Code outputs `{"type": "assistant", "message": {"content": [...]}}` but parser looked for `data["content"]` instead of `data["message"]["content"]`.
**Fix:** Updated to check `message.content` path.

### 3. Init Event Matching All Events
**File:** `ralphx/adapters/claude_cli.py`
**Issue:** Condition `if msg_type == "init" or "session_id" in data` matched ALL events since every event has `session_id`.
**Fix:** Changed to `if msg_type in ("init", "system")`.

### 4. Loop Name Not Linked to Workflow Steps
**Issue:** Workflow steps didn't have `loop_name` populated, so SessionTail couldn't connect.
**Fix:** Need to automatically populate `loop_name` when workflow executor creates the loop.

---

## UX Improvements Needed

### 5. Live Output Component
**Status:** Partially working
**Issue:** SessionTail component added but only streams when a session is registered in DB. Sessions are registered AFTER completion, so live streaming doesn't work during active iteration.
**Solution:**
- Find active session files by scanning Claude's project directory
- Or register session_id at START of iteration, not end
- Stream from session JSONL file in real-time

### 6. Stories Per Iteration Control
**Issue:** No UX to control how many stories to generate per iteration.
**Solution:**
- Add "Stories per iteration" field to workflow step config (default: 10)
- Pass this to the prompt template as `{{stories_per_iteration}}`
- Update prompt to instruct Claude to generate that many stories

### 7. Persist Session Data for Historical Viewing
**Issue:** Users can't view past loop interactions - what Claude said, what tools it called, etc.
**Solution:**
- Store session content in database (or reference to JSONL file)
- Build UI to browse session history:
  - Collapsible iteration view
  - Show assistant messages, tool calls, results
  - Filter by session/iteration
  - Search within session content

### 8. Existing Stories Context
**Issue:** `{{existing_stories}}` shows 0 because:
- Stories from imported JSONL are in different workflow
- Stories generated this session aren't saved until extraction works
**Solution:**
- Option to pull stories from project level, not just workflow
- Or link workflows so generator feeds consumer
- Fix extraction so generated stories are immediately available

### 9. Error States and Messaging
**Issue:** When backend is down, UI shows "Internal Server Error" with no helpful message.
**Solution:**
- Add error boundary components
- Show friendly error messages: "Backend unavailable, please check server"
- Add retry button
- Show connection status indicator

### 10. Workflow Sidebar Refresh
**Issue:** New/draft workflows don't appear in sidebar until page refresh.
**Solution:**
- After workflow creation, invalidate sidebar cache
- Or use real-time updates (WebSocket/polling)

### 11. Better Logging/Debugging
**Issue:** Hard to debug why items aren't being extracted.
**Solution:**
- Add structured logging with log levels
- Log: prompt sent, output received, extraction results, save results
- Make logs accessible via UI (Activity Log page)
- Add debug mode toggle

---

## Architecture Considerations

### Guardrails Scope
**Current:** Guardrails at workflow level apply to ALL steps.
**Issue:** Story format guardrail shouldn't apply to implementation step.
**Options:**
1. Move guardrails to step level
2. Allow tagging guardrails to specific steps
3. Bake story format into template (not user-configurable)

### Story Format Standardization
The story output format should be standardized and baked into the template since downstream processing expects specific fields:
```json
{
  "id": "CAT-NNN",
  "title": "...",
  "content": "As a [role], I want...",
  "acceptance_criteria": [...],
  "priority": 1-5,
  "category": "FND|ELG|ANS|CLM|DNL|CHG|RPT|INT",
  "complexity": "small|medium|large",
  "dependencies": ["CAT-NNN", ...]
}
```

---

## Priority Order

1. **P0 - Blocking:** Fix item extraction end-to-end (adapter + executor)
2. **P0 - Blocking:** Live streaming for active sessions
3. **P1 - Important:** Stories per iteration control
4. **P1 - Important:** Error state handling
5. **P2 - Nice to have:** Session history viewing
6. **P2 - Nice to have:** Sidebar real-time updates
7. **P3 - Future:** Guardrail scoping to steps

---

## Testing Checklist

- [ ] Start workflow, verify live output streams immediately
- [ ] Complete iteration, verify stories extracted and saved
- [ ] Refresh page, verify session history is viewable
- [ ] Stop backend, verify friendly error message
- [ ] Create new workflow, verify it appears in sidebar
- [ ] Configure stories per iteration, verify Claude respects it
