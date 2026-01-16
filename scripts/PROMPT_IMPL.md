# Implement Feature: {STORY_ID}

## YOUR TASK

Implement the following user story in this codebase.

## CRITICAL RULES - READ FIRST

1. **FOLLOW THE DESIGN DOCUMENT** - The design document below is your source of truth. All implementation decisions must align with its architecture, patterns, and goals.

2. **DO NOT WRITE TO PROGRESS FILES** - The calling script handles all progress tracking. Do NOT attempt to write to progress files. Just output your status using the delimiters at the end.

3. **DO NOT BREAK EXISTING FEATURES** - Review the "Already Implemented Features" section carefully. These features are working and tested. Your implementation must NOT:
   - Remove or modify existing working code unless explicitly required
   - Change function signatures that other features depend on
   - Delete or rename existing database models/fields
   - Break existing tests

4. **CHECK FOR DUPLICATES FIRST** - Before implementing, compare this story against "Already Implemented Features". If this story's functionality is already covered by an existing implementation, mark it as a duplicate instead of reimplementing.

{GUARDRAILS}

## STORY TO IMPLEMENT

**ID:** {STORY_ID}
**Priority:** {PRIORITY}
**Category:** {CATEGORY}
**Story:** {STORY_TEXT}

## ACCEPTANCE CRITERIA

{ACCEPTANCE_CRITERIA}

## NOTES

{NOTES}

---

## ALREADY IMPLEMENTED FEATURES

**CRITICAL: Do NOT break these. Reuse this code where possible.**

If this story is essentially the same as one listed below, output `DUP_OF: [that_story_id]` instead of implementing.

{IMPLEMENTED_SUMMARY}

---

## PROJECT DESIGN DOCUMENT (SOURCE OF TRUTH)

This design document defines the project architecture, patterns, and goals.
**Your implementation MUST follow the patterns and architecture defined here.**

{DESIGN_DOC}

---

## IMPLEMENTATION CHECKLIST

Before writing code:
- [ ] Read the design document section relevant to this feature
- [ ] Review guardrails for implementation standards (if provided)
- [ ] Check if this duplicates an already-implemented feature
- [ ] Identify existing code patterns to follow

When implementing:
- [ ] Follow existing patterns from the codebase
- [ ] Reuse existing utilities and helpers
- [ ] Add unit tests for new functionality
- [ ] Do NOT modify working code unless required by this story
- [ ] Do NOT create new files unless absolutely necessary

After implementing:
- [ ] Run tests to verify nothing is broken
- [ ] Verify acceptance criteria are met

## SELF-REVIEW (MANDATORY BEFORE MARKING IMPLEMENTED)

**Before outputting `IMPLEMENTED:`, you MUST complete this review checklist:**

### Security Review
- [ ] **Input validation**: All user input validated before use?
- [ ] **No injection vectors**: SQL, command, template injection prevented?
- [ ] **Auth checks**: Protected endpoints require authentication?
- [ ] **Data isolation**: Multi-tenant data properly isolated (if applicable)?

### Code Quality Review
- [ ] **File size**: Files kept to reasonable size (<500 lines)?
- [ ] **Function size**: Functions focused and single-purpose?
- [ ] **Type hints**: Functions have type annotations (if using typed language)?
- [ ] **No magic numbers**: Constants are named and documented?

### Edge Case Review
- [ ] **Empty states**: What happens with empty lists, null values?
- [ ] **Error handling**: Errors caught and handled gracefully?
- [ ] **Validation**: Required fields enforced? Invalid input rejected?

### Test Review
- [ ] **Tests exist**: Unit tests written for new code?
- [ ] **Happy path**: Success case tested?
- [ ] **Error cases**: Validation failures, not-found tested?

**STOP CONDITION: ALL checks must pass. If ANY check fails:**
1. FIX the issue immediately
2. Re-run the ENTIRE self-review checklist from the beginning
3. Repeat until ALL checks pass with NO fixes needed
4. Only then output IMPLEMENTED

**You must loop through this review until a clean pass with zero fixes.**

---

## DUPLICATE DETECTION - IMPORTANT

If this story's core functionality is ALREADY covered by an implemented feature, mark it as a duplicate:

**How to identify duplicates:**
- Same database model or API endpoint
- Same user-facing functionality with different wording
- Subset of a broader feature already implemented
- Same business logic with minor variations

**If duplicate, output:**
```
DUP_OF: [parent_story_id]
```

The parent story ID should be the FIRST/ORIGINAL story that implemented this functionality.

**Do NOT reimplement functionality that already exists.** Just mark it as DUP_OF.

---

## OUTPUT FORMAT

When done, output your final status using these EXACT delimiters.
The unique delimiters ensure automation can detect your status even if you write code containing status-like strings.

**CRITICAL FORMATTING RULES:**
1. Use the EXACT delimiters shown below - they contain a unique ID
2. Status must be on its own line between the delimiters
3. DO NOT output these delimiters anywhere else in your response
4. A story can NEVER be `DUP_OF` itself

**Successfully implemented new functionality:**
```
###RALPH_IMPL_RESULT_7f3a9b2e###
IMPLEMENTED: Brief description of what was created
###END_RALPH_RESULT###
```

**This story duplicates existing implementation:**
```
###RALPH_IMPL_RESULT_7f3a9b2e###
DUP_OF: parent_story_id
###END_RALPH_RESULT###
```
Note: parent_story_id must be a DIFFERENT story ID, never the current story.

**Should be skipped for another reason:**
```
###RALPH_IMPL_RESULT_7f3a9b2e###
SKIPPED: reason
###END_RALPH_RESULT###
```

**Encountered unrecoverable error:**
```
###RALPH_IMPL_RESULT_7f3a9b2e###
ERROR: reason
###END_RALPH_RESULT###
```

---

## BEGIN

1. First, explore the codebase to understand existing patterns
2. Check if this duplicates an already-implemented feature
3. If not a duplicate, implement following the design document
4. Run tests to verify nothing is broken
5. Complete the self-review checklist
6. Output the appropriate status line with delimiters
