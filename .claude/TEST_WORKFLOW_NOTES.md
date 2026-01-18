# Test Workflow Notes - hank-rcm

## Current Test: Feature Implementation Workflow

This is a **TEST RUN** to validate RalphX can replicate ralph_impl.sh.

### Test Configuration
- **Model**: sonnet (not opus) - faster/cheaper for testing
- **Stories**: Import small subset first (5-10 stories)
- **Goal**: Verify full flow works before running 3072 stories

### What We're Testing
1. Workflow creation via UI
2. Resource injection (design doc, guardrails)
3. JSONL import
4. Consumer loop claiming/processing items
5. Structured JSON output parsing
6. Status marking (implemented/dup/external/skipped)

### Success Criteria
- [ ] Story claimed from pending queue
- [ ] Prompt includes design doc + story content
- [ ] Claude returns valid JSON with status
- [ ] Work item marked with correct status
- [ ] Loop continues to next item
- [ ] Loop exits when queue empty

### Files to Use
- Design Doc: `/home/jackmd/Github/hank-rcm/design/RCM_DESIGN.md`
- Guardrails: `/home/jackmd/Github/hank-rcm/GUARDRAILS.md`
- Stories: `/home/jackmd/Github/hank-rcm/design/prd_RCM_software.jsonl`
