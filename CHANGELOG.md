# Changelog

All notable changes to RalphX are documented here.

## [Unreleased]

### Security
- The local API now requires an access token on every `/api` route, `/docs` and `/openapi.json` (issue #2). The token is in `~/.ralphx/api_token` (mode 0600) or `RALPHX_API_TOKEN`. The dashboard logs in with the link that `ralphx serve` prints and keeps an HttpOnly, SameSite=Strict cookie.
- The server refuses requests whose Host header is not a loopback name (DNS rebinding) and cross-origin requests. The wildcard CORS policy is removed.
- The server does not start with a token shorter than 32 characters.
- `ralphx serve` refuses a non-loopback `--host` unless `--allow-remote` is given. A wildcard address also needs `--allowed-host`.
- Removed `GET /api/auth/credentials/export`, which returned the stored Claude access and refresh tokens. `GET /api/auth/flow/{id}` no longer returns the raw OAuth token response.
- The workspace directory is now mode 0700. The server log moved from `/tmp/ralphx-server.log` to `~/.ralphx/logs/server.log` (mode 0600). Swapped Claude credential files are created with mode 0600 before any data is written. The OAuth callback no longer logs the authorization code.

### Added
- `ralphx dashboard-url` prints the dashboard login link.

## [0.4.1] - 2026-02-06

### Added
- Sidebar step navigation: 3-level tree (Project > Workflow > Steps) with status indicators, expand/collapse, and 30s auto-refresh
- Stop button reliability: checkpoint-based process tracking survives server hot-reload
- Token usage display in session events (input/output/cache tokens)
- Rate limit reset times: exact 5h/7d reset timestamps with "No active window" fallback
- Time position markers on usage progress bars showing elapsed window time
- JSONL session file tailing for streaming

### Fixed
- Session log scroll/overflow clipping in collapsed animation containers
- Grouped event rendering improvements
- Workflow items: phase column, category badges, priority display
- Consolidated loop config generation in templates

## [0.4.0] - 2026-02-05

### Added
- Event persistence pipeline: session events recorded to DB by executor, no browser tab required
- Planning iteration system: autonomous design doc refinement with SSE streaming
- Design doc file management: backup/restore, version diffing, full CRUD
- Enhanced session history UI: error banners, run metadata, status badges

### Security
- Path traversal prevention across resources, planning, and design doc endpoints
- Token refresh race condition fixes with file-based locking
- Error message sanitization, HTML comment injection prevention
- Template variable escaping against prompt injection
- Credential file permissions hardened to 0600

### Fixed
- 62 bug fixes including session event persistence, work item restore status, planning session lifecycle, double-execution guard

## [0.3.5] - 2026-01-25

### Fixed
- Re-auth scopes serialization bug: SQLite "type 'list' is not supported" error when re-authenticating with a different account
- OAuth scopes now properly JSON-serialized before storage

### Improved
- AccountsPanel with usage display and validation status
- Auth routes with better error handling

## [0.3.4] - 2026-01-21

### Added
- Multi-account authentication system
- Per-project account assignment with fallback
- Account usage tracking (5h/7d progress bars)
- v15-v16 migration with cascade delete fix and pre-migration backups

## [0.2.2] - 2026-01-20

### Fixed
- Images/GIF not displaying on PyPI: now uses absolute GitHub raw URLs

## [0.2.1] - 2026-01-20

### Added
- Non-technical install prompt: copy-paste into Claude Code for fully automated setup

## [0.2.0] - 2026-01-20

### Added
- Ralph loop terminology and branding throughout
- Hero GIF and dashboard screenshots
- Three Ralph loop types documented: Research & Design, Story Generation, Implementation
- Web-enhanced story generation mode

## [0.1.5] - 2026-01-19

### Added
- Contextual status bar with workflow-type-aware metrics
- Compact step rows with table-style layout
- Step detail page for drilling into individual steps
- Button tooltips with hover descriptions
- MCP server modular tools architecture
- SDLC Workflows design document

### Fixed
- Time formatting: hours shown until 48h threshold, "Never" for unrun steps

## [0.1.4] - 2026-01-19

### Added
- Initial workflow execution engine
- Basic dashboard UI

## [0.1.3] - 2026-01-19

### Added
- Initial release: project registration, loop orchestration, MCP server, web dashboard
