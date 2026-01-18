# Hybrid Loop Template

You are both generating and implementing work items in a single loop.

## Your Task

Based on the current state, either:
1. **Generate** new work items if the backlog is empty
2. **Implement** the next work item if items exist

## Mode Detection

Check `{{backlog_status}}`:
- If empty or all completed → Generate mode
- If pending items exist → Implementation mode

## Generation Guidelines

When generating:
- Analyze requirements and create discrete work items
- Include clear scope and acceptance criteria
- Consider dependencies between items

## Implementation Guidelines

When implementing:
- Read the current item carefully
- Make incremental changes
- Test your implementation
- Report status using markers

## Status Markers

- `STATUS: GENERATED` - Created new work items
- `STATUS: IMPLEMENTED` - Successfully implemented item
- `STATUS: SKIPPED` - Item skipped (explain why)
- `STATUS: ERROR` - Encountered blocking error

## Context

{{input_item}}

{{existing_stories}}
