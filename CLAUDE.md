# Claude Preferences for RalphX Development

## Testing & Debugging

- **Use Chrome UI for testing**: When testing RalphX features, use the browser automation (Chrome) instead of curl commands. This validates the actual user experience.

## Product Philosophy

- **Import is advanced**: Importing user stories (JSONL) is an advanced feature for power users. Most users should use the default flow: describe problem → Claude generates stories → implement.

- **Multiple workflows per project**: A project can have multiple workflows (e.g., PRD Research, Feature Implementation, Bug Fixes).

## Test Workflow Notes

See `.claude/TEST_WORKFLOW_NOTES.md` for current test workflow configuration.
