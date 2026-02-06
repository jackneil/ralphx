# Claude Preferences for RalphX Development

## Core Philosophy: Claude Code First

RalphX is a **Claude Code-first product**. When documenting or explaining how to do things:

1. **Always provide a Claude Code prompt first** - Users should be able to copy a prompt into Claude Code to get things done
2. **Manual commands are secondary** - Only show manual bash commands as a fallback or for reference
3. **README, Wiki, and docs should lead with prompts** - e.g., "Ask Claude Code: 'Install RalphX and set it up for my project'"

Example of good documentation:
```
## Quick Start

Ask Claude Code:
> "Install RalphX using conda and register this project"

Or manually:
conda create -n ralphx python=3.11 && conda activate ralphx && pip install ralphx
```

## Python Environment

- **Always use conda (miniconda)** - Never use venv or virtualenv. We standardize on conda.
- **Use the `ralphx` conda environment**: All Python code should run in the ralphx environment.
  ```bash
  conda activate ralphx
  ```
- Always ensure you're in the correct environment before running Python scripts or tests.

## Development Server

- **Use `./dev.sh` to start the server**: Do not manually run uvicorn commands. Use the dev script which handles both backend and frontend:
  ```bash
  ./dev.sh          # Start (kills any existing processes on ports first)
  ./dev.sh          # Restart — just run it again, it auto-clears ports 16767/16768
  # Ctrl+C to stop
  ```
- The script auto-kills any existing processes on its ports before starting, so running `./dev.sh` again is effectively a restart.
- Hot-reload works for most changes, but run `./dev.sh` again when in doubt (e.g., DB migrations, new dependencies).

## Testing & Debugging

- **Use Chrome UI for testing**: When testing RalphX features, use the browser automation (Chrome) instead of curl commands. This validates the actual user experience.

## Product Philosophy

- **Import is advanced**: Importing user stories (JSONL) is an advanced feature for power users. Most users should use the default flow: describe problem → Claude generates stories → implement.

- **Multiple workflows per project**: A project can have multiple workflows (e.g., PRD Research, Feature Implementation, Bug Fixes).

## Releasing to PyPI

Publishing is automated via GitHub Actions. To release a new version:

1. **Bump version** in both `pyproject.toml` and `ralphx/__init__.py`
2. **Commit and push** to main
3. **Create a GitHub Release** using gh CLI:
   ```bash
   gh release create v0.3.0 --title "v0.3.0" --generate-notes
   ```
4. **GitHub Actions auto-publishes** to PyPI via trusted publishing (OIDC)

The workflow is defined in `.github/workflows/publish.yml` and triggers on `release: types: [published]`.

## Lessons Learned

See `lessons.md` in the project root for session-specific lessons and gotchas. Read it at the start of each session.

## Test Workflow Notes

See `.claude/TEST_WORKFLOW_NOTES.md` for current test workflow configuration.
