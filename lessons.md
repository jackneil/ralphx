# Lessons Learned

## Hot-Reload Safety
- NEVER edit source files (frontend or backend) while a loop/workflow step is running. Uvicorn hot-reload kills the worker process, which orphans or aborts the running Claude CLI subprocess. Wait for the run to complete, or stop it first.

## Scroll/Overflow in Session Logs
- Animation containers that use `overflow-hidden` for collapse/expand animations must only apply `overflow-hidden` when collapsed. When expanded, use `max-h-none` — otherwise nested content gets clipped and the parent scrollbar can't reach it.

## Prompt Size Limits
- When design docs or existing story lists are large (>50KB), use file references in the prompt ("Read the design doc at path...") instead of inlining the content into the `-p` argument. Claude CLI has prompt size limits.

## Migration Self-Healing
- SQLite migrations can partially apply (schema version bumped but column not added). Always make migrations idempotent and consider a `_verify_schema_columns()` check on startup to repair missing columns.
