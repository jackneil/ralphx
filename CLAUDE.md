# Claude Preferences for RalphX Development

## Python Environment

- **Use the `ralphx` conda environment**: All Python code should run in the ralphx environment. We use miniconda.
  ```bash
  conda activate ralphx
  ```
- Always ensure you're in the correct environment before running Python scripts or tests.

## Development Server

- **Use `./dev.sh` to start the server**: Do not manually run uvicorn commands. Use the dev script which handles both backend and frontend:
  ```bash
  ./dev.sh
  ```
- The server hot-reloads on file changes, so no need to restart manually.

## Testing & Debugging

- **Use Chrome UI for testing**: When testing RalphX features, use the browser automation (Chrome) instead of curl commands. This validates the actual user experience.

## Product Philosophy

- **Import is advanced**: Importing user stories (JSONL) is an advanced feature for power users. Most users should use the default flow: describe problem → Claude generates stories → implement.

- **Multiple workflows per project**: A project can have multiple workflows (e.g., PRD Research, Feature Implementation, Bug Fixes).

## Releasing to PyPI

Publishing is automated via GitHub Actions. To release a new version:

1. **Bump version** in `pyproject.toml`
2. **Commit and push** to main
3. **Create a GitHub Release**:
   - Go to https://github.com/jackneil/ralphx/releases/new
   - Tag: `v0.1.3` (match pyproject.toml version)
   - Title: `v0.1.3`
   - Auto-generate release notes or write summary
   - Click "Publish release"
4. **GitHub Actions auto-publishes** to PyPI via trusted publishing (OIDC)

The workflow is defined in `.github/workflows/publish.yml` and triggers on `release: types: [published]`.

## Test Workflow Notes

See `.claude/TEST_WORKFLOW_NOTES.md` for current test workflow configuration.
