"""Project-local database for RalphX.

Each project has its own database at <project>/.ralphx/ralphx.db containing:
- Loops configuration
- Runs and sessions
- Work items (stories, tasks)
- Checkpoints
- Guardrails
- Execution logs
- Phase tracking
- Input file tracking

This makes projects portable - clone a repo with .ralphx/ and all data comes with it.
"""

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional


# Schema version for project DB
PROJECT_SCHEMA_VERSION = 16

# Project database schema - all project-specific data
PROJECT_SCHEMA_SQL = """
-- Loops table (every loop belongs to a workflow step)
CREATE TABLE IF NOT EXISTS loops (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    config_yaml TEXT NOT NULL,
    workflow_id TEXT NOT NULL,              -- Parent workflow
    step_id INTEGER NOT NULL,               -- Parent workflow step
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Runs table (every run belongs to a workflow step via its loop)
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    loop_name TEXT NOT NULL,
    status TEXT NOT NULL,
    workflow_id TEXT NOT NULL,              -- Parent workflow
    step_id INTEGER NOT NULL,               -- Parent workflow step
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    iterations_completed INTEGER DEFAULT 0,
    items_generated INTEGER DEFAULT 0,
    error_message TEXT,
    executor_pid INTEGER,                   -- PID of executor process for stale detection
    last_activity_at TIMESTAMP              -- Last activity timestamp for stale detection
);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
    iteration INTEGER NOT NULL,
    mode TEXT,
    started_at TIMESTAMP,
    duration_seconds REAL,
    status TEXT,
    items_added TEXT
);

-- Session events table (stores parsed events for history and streaming)
CREATE TABLE IF NOT EXISTS session_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,           -- text, tool_call, tool_result, error, init, complete
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    content TEXT,                       -- For text events
    tool_name TEXT,                     -- For tool events
    tool_input TEXT,                    -- JSON for tool input
    tool_result TEXT,                   -- For tool results
    error_message TEXT,                 -- For error events
    raw_data TEXT                       -- Full JSON for debugging
);

CREATE INDEX IF NOT EXISTS idx_session_events_session ON session_events(session_id);

-- Work items table (every item belongs to a workflow, created by a step)
-- Primary key is (id, workflow_id) so same item ID can exist in different workflows
CREATE TABLE IF NOT EXISTS work_items (
    id TEXT NOT NULL,                       -- Item ID (unique within workflow)
    workflow_id TEXT NOT NULL,              -- Parent workflow
    source_step_id INTEGER NOT NULL,        -- Step that created this item
    priority INTEGER,
    content TEXT NOT NULL,
    title TEXT,
    status TEXT DEFAULT 'pending',
    category TEXT,
    tags TEXT,
    metadata TEXT,
    item_type TEXT DEFAULT 'item',
    claimed_by TEXT,
    claimed_at TIMESTAMP,
    processed_at TIMESTAMP,
    implemented_commit TEXT,                -- Git commit SHA where item was implemented
    -- Phase and dependency fields
    dependencies TEXT,  -- JSON array of item IDs
    phase INTEGER,      -- Assigned phase number (for batching)
    duplicate_of TEXT,  -- Parent item ID if DUPLICATE status
    skip_reason TEXT,   -- Reason if SKIPPED status
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id, workflow_id)
);

-- Checkpoints table
CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY,
    run_id TEXT,
    loop_name TEXT,
    iteration INTEGER,
    status TEXT,
    data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Guardrails metadata table
CREATE TABLE IF NOT EXISTS guardrails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    filename TEXT NOT NULL,
    source TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_mtime REAL,
    file_size INTEGER,
    enabled BOOLEAN DEFAULT TRUE,
    loops TEXT,
    modes TEXT,
    position TEXT DEFAULT 'after_design_doc',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category, filename)
);

-- Execution logs table
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    metadata TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Run phase tracking (for Phase 1 implementation flow)
CREATE TABLE IF NOT EXISTS run_phases (
    run_id TEXT PRIMARY KEY,
    phase TEXT DEFAULT 'phase_1_pending',
    phase_1_story_ids TEXT,
    phase_1_started_at TIMESTAMP,
    phase_1_completed_at TIMESTAMP,
    analysis_output TEXT
);

-- Input file tracking
CREATE TABLE IF NOT EXISTS input_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loop_name TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    items_imported INTEGER DEFAULT 0,
    UNIQUE(loop_name, filename)
);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Project resources (design docs, architecture, coding standards, etc.)
CREATE TABLE IF NOT EXISTS resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    resource_type TEXT NOT NULL,  -- design_doc, architecture, coding_standards, domain_knowledge, custom
    file_path TEXT NOT NULL,
    injection_position TEXT DEFAULT 'after_design_doc',
    enabled BOOLEAN DEFAULT TRUE,
    inherit_default BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 100,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Loop type definitions (extensible, not hardcoded enum)
CREATE TABLE IF NOT EXISTS loop_types (
    id TEXT PRIMARY KEY,            -- 'consumer', 'generator', 'hybrid'
    label TEXT NOT NULL,            -- 'Implementation Loop'
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Requirements per loop type (checklist items)
CREATE TABLE IF NOT EXISTS loop_type_requirements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loop_type TEXT NOT NULL REFERENCES loop_types(id),
    requirement_key TEXT NOT NULL,  -- 'loop_template', 'work_items', 'auth'
    category TEXT NOT NULL,         -- 'required', 'recommended'
    label TEXT NOT NULL,
    description TEXT,
    check_type TEXT NOT NULL,       -- 'resource', 'items_count', 'auth_status'
    check_config TEXT,              -- JSON: {"resource_type": "loop_template"} or {"min": 1}
    has_default BOOLEAN DEFAULT FALSE,
    priority INTEGER DEFAULT 0,
    UNIQUE(loop_type, requirement_key)
);

-- Default templates/resources per loop type
CREATE TABLE IF NOT EXISTS loop_type_defaults (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loop_type TEXT NOT NULL REFERENCES loop_types(id),
    resource_type TEXT NOT NULL,    -- 'loop_template', 'guardrails'
    name TEXT NOT NULL,             -- 'default', 'minimal', 'comprehensive'
    content TEXT NOT NULL,          -- Actual markdown content
    description TEXT,
    is_default BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(loop_type, resource_type, name)
);

-- Import format definitions (JSONL field mappings)
CREATE TABLE IF NOT EXISTS import_formats (
    id TEXT PRIMARY KEY,            -- 'ralphx_standard', 'hank_prd'
    label TEXT NOT NULL,
    description TEXT,
    field_mapping TEXT NOT NULL,    -- JSON: {"id": "id", "story": "content", ...}
    category_mappings TEXT,         -- JSON: {"FND": "foundation", "ELG": "eligibility"}
    id_prefix_to_category BOOLEAN DEFAULT FALSE,  -- Auto-detect category from ID prefix
    sample_content TEXT,            -- Example JSONL for UI preview
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Loop resources (per-loop, not per-project)
-- Each loop can have its own loop_template, design_doc, guardrails, etc.
-- Resources can be sourced from: system defaults, project files, or other loops
CREATE TABLE IF NOT EXISTS loop_resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loop_name TEXT NOT NULL,                -- FK to loop config
    resource_type TEXT NOT NULL,            -- 'loop_template', 'design_doc', 'guardrails', 'custom'
    name TEXT NOT NULL,                     -- Display name
    injection_position TEXT NOT NULL,       -- 'template_body', 'after_design_doc', 'before_task'

    -- Source tracking (one of these will be set based on source_type)
    source_type TEXT NOT NULL,              -- 'system', 'project_file', 'loop_ref', 'project_resource', 'inline'
    source_path TEXT,                       -- For 'project_file': path relative to project
    source_loop TEXT,                       -- For 'loop_ref': source loop name
    source_resource_id INTEGER,             -- For 'loop_ref' or 'project_resource': source resource ID
    inline_content TEXT,                    -- For 'inline': actual content

    enabled BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(loop_name, resource_type, name)
);

-- Workflow templates (system-defined, user-creatable later)
CREATE TABLE IF NOT EXISTS workflow_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    phases JSON NOT NULL,                   -- Array of phase definitions
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Workflow instances (user's actual workflows)
CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY,
    template_id TEXT,                       -- Optional reference to template
    name TEXT NOT NULL,
    status TEXT DEFAULT 'draft',            -- draft, active, paused, completed
    current_step INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    archived_at TIMESTAMP                   -- NULL = active, non-NULL = archived
);

-- Workflow steps (e.g., Planning, Story Generation, Implementation)
-- Note: "step" is used for workflow structure, "phase" for implementation batching
CREATE TABLE IF NOT EXISTS workflow_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    name TEXT NOT NULL,
    step_type TEXT NOT NULL,                -- 'interactive' or 'autonomous'
    status TEXT DEFAULT 'pending',          -- pending, active, completed, skipped
    config JSON,                            -- Step-specific configuration
    loop_name TEXT,                         -- For autonomous steps: linked loop
    artifacts JSON,                         -- Outputs from this step
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    archived_at TIMESTAMP,                  -- NULL = active, non-NULL = archived (soft delete)
    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE,
    UNIQUE(workflow_id, step_number)
);

-- Planning sessions (for interactive steps)
CREATE TABLE IF NOT EXISTS planning_sessions (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    step_id INTEGER NOT NULL,
    messages JSON NOT NULL DEFAULT '[]',    -- Conversation history
    artifacts JSON,                         -- Generated design doc, guardrails
    status TEXT DEFAULT 'active',           -- active, completed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE,
    FOREIGN KEY (step_id) REFERENCES workflow_steps(id) ON DELETE CASCADE
);

-- Workflow-scoped resources (design docs, guardrails, input files)
CREATE TABLE IF NOT EXISTS workflow_resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,            -- 'design_doc', 'guardrail', 'input_file', 'prompt'
    name TEXT NOT NULL,
    content TEXT,                           -- For inline content
    file_path TEXT,                         -- For file references
    source TEXT,                            -- 'planning_step', 'manual', 'imported', 'inherited'
    source_id INTEGER,                      -- Reference to project_resources if inherited
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
);

-- Workflow resource version history (for undo/restore)
CREATE TABLE IF NOT EXISTS workflow_resource_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_resource_id INTEGER NOT NULL,
    version_number INTEGER NOT NULL,
    content TEXT,
    name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workflow_resource_id) REFERENCES workflow_resources(id) ON DELETE CASCADE
);

-- Step-level resource overrides (per-step configuration)
-- Allows steps to override, disable, or add resources beyond workflow defaults
CREATE TABLE IF NOT EXISTS workflow_step_resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    step_id INTEGER NOT NULL,
    -- For inherited resources being overridden/disabled:
    workflow_resource_id INTEGER,           -- References workflow_resources(id)
    -- For step-specific resources:
    resource_type TEXT,                     -- 'design_doc', 'guardrail', 'input_file', 'prompt'
    name TEXT,
    content TEXT,
    file_path TEXT,
    -- Control behavior:
    mode TEXT NOT NULL DEFAULT 'add',       -- 'override', 'disable', 'add'
    enabled BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (step_id) REFERENCES workflow_steps(id) ON DELETE CASCADE,
    FOREIGN KEY (workflow_resource_id) REFERENCES workflow_resources(id) ON DELETE CASCADE
);

-- Project-level shared resources (template library for inheritance)
CREATE TABLE IF NOT EXISTS project_resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_type TEXT NOT NULL,            -- 'guardrail', 'prompt_template', 'config'
    name TEXT NOT NULL,
    content TEXT,
    file_path TEXT,
    auto_inherit BOOLEAN DEFAULT FALSE,     -- If true, new workflows get this by default
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Project-level settings (singleton row per project)
CREATE TABLE IF NOT EXISTS project_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- Singleton: only one row allowed
    auto_inherit_guardrails BOOLEAN DEFAULT TRUE,
    require_design_doc BOOLEAN DEFAULT FALSE,
    architecture_first_mode BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cascade delete triggers for tables without FK constraints
-- (loops, runs, work_items have workflow_id but no FK)
CREATE TRIGGER IF NOT EXISTS cascade_delete_workflow_loops
    AFTER DELETE ON workflows
    FOR EACH ROW
    BEGIN
        DELETE FROM loops WHERE workflow_id = OLD.id;
    END;

CREATE TRIGGER IF NOT EXISTS cascade_delete_workflow_runs
    AFTER DELETE ON workflows
    FOR EACH ROW
    BEGIN
        DELETE FROM runs WHERE workflow_id = OLD.id;
    END;

CREATE TRIGGER IF NOT EXISTS cascade_delete_workflow_items
    AFTER DELETE ON workflows
    FOR EACH ROW
    BEGIN
        DELETE FROM work_items WHERE workflow_id = OLD.id;
    END;
"""

PROJECT_INDEXES_SQL = """
-- Work items indexes
CREATE INDEX IF NOT EXISTS idx_work_items_status ON work_items(status);
CREATE INDEX IF NOT EXISTS idx_work_items_category ON work_items(category);
CREATE INDEX IF NOT EXISTS idx_work_items_priority ON work_items(priority);
CREATE INDEX IF NOT EXISTS idx_work_items_created ON work_items(created_at);
CREATE INDEX IF NOT EXISTS idx_work_items_workflow ON work_items(workflow_id, source_step_id, status);
CREATE INDEX IF NOT EXISTS idx_work_items_claimed ON work_items(claimed_by, claimed_at);
CREATE INDEX IF NOT EXISTS idx_work_items_phase ON work_items(phase);

-- Loops indexes
CREATE INDEX IF NOT EXISTS idx_loops_workflow ON loops(workflow_id, step_id);

-- Runs indexes
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_workflow ON runs(workflow_id, step_id);

-- Session/log indexes
CREATE INDEX IF NOT EXISTS idx_sessions_run ON sessions(run_id);
CREATE INDEX IF NOT EXISTS idx_logs_run ON logs(run_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level, timestamp);

-- Resource indexes
CREATE INDEX IF NOT EXISTS idx_guardrails_enabled ON guardrails(enabled);
CREATE INDEX IF NOT EXISTS idx_guardrails_source ON guardrails(source);
CREATE INDEX IF NOT EXISTS idx_input_files_loop ON input_files(loop_name);
CREATE INDEX IF NOT EXISTS idx_resources_type ON resources(resource_type);
CREATE INDEX IF NOT EXISTS idx_resources_enabled ON resources(enabled);
CREATE INDEX IF NOT EXISTS idx_loop_type_requirements_type ON loop_type_requirements(loop_type);
CREATE INDEX IF NOT EXISTS idx_loop_type_defaults_type ON loop_type_defaults(loop_type, resource_type);
CREATE INDEX IF NOT EXISTS idx_loop_resources_loop ON loop_resources(loop_name, enabled);
CREATE INDEX IF NOT EXISTS idx_loop_resources_type ON loop_resources(resource_type);

-- Workflow indexes
CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_workflow ON workflow_steps(workflow_id, step_number);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_status ON workflow_steps(status);
CREATE INDEX IF NOT EXISTS idx_planning_sessions_workflow ON planning_sessions(workflow_id);
CREATE INDEX IF NOT EXISTS idx_planning_sessions_status ON planning_sessions(status);

-- Workflow resources indexes
CREATE INDEX IF NOT EXISTS idx_workflow_resources_workflow ON workflow_resources(workflow_id, resource_type);
CREATE INDEX IF NOT EXISTS idx_workflow_resources_type ON workflow_resources(resource_type, enabled);
CREATE INDEX IF NOT EXISTS idx_project_resources_type ON project_resources(resource_type, auto_inherit);
CREATE INDEX IF NOT EXISTS idx_resource_versions ON workflow_resource_versions(workflow_resource_id, version_number DESC);

-- Step resources indexes
CREATE INDEX IF NOT EXISTS idx_step_resources_step ON workflow_step_resources(step_id, mode);
CREATE INDEX IF NOT EXISTS idx_step_resources_workflow_resource ON workflow_step_resources(workflow_resource_id);
"""


def get_project_database_path(project_path: str | Path) -> Path:
    """Get path to a project's local database.

    Args:
        project_path: Path to the project directory.

    Returns:
        Path to <project>/.ralphx/ralphx.db
    """
    return Path(project_path) / ".ralphx" / "ralphx.db"


class ProjectDatabase:
    """Project-local database for all project-specific data.

    This database is stored at <project>/.ralphx/ralphx.db and contains
    all data for a single project, making it portable.
    """

    def __init__(self, project_path: str | Path):
        """Initialize project database.

        Args:
            project_path: Path to the project directory.
                          Database will be at <project>/.ralphx/ralphx.db.
                          Use ":memory:" for in-memory testing database.
        """
        self._write_lock = threading.Lock()
        self._local = threading.local()

        # Support :memory: for testing
        if str(project_path) == ":memory:":
            self.project_path = None
            self.db_path = ":memory:"
        else:
            self.project_path = Path(project_path)
            self.db_path = get_project_database_path(project_path)
            # Create .ralphx directory and database file if needed
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            if not self.db_path.exists():
                self.db_path.touch(mode=0o600)

        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False,
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.row_factory = sqlite3.Row
            self._local.connection = conn
        return self._local.connection

    @contextmanager
    def _writer(self) -> Iterator[sqlite3.Connection]:
        """Context manager for write operations."""
        with self._write_lock:
            conn = self._get_connection()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    @contextmanager
    def _reader(self) -> Iterator[sqlite3.Connection]:
        """Context manager for read operations."""
        yield self._get_connection()

    def _init_schema(self) -> None:
        """Initialize database schema."""
        with self._writer() as conn:
            # First, check if schema_version table exists and get current version
            # This must happen BEFORE creating indexes, as old schemas may not
            # have the required columns (e.g., workflow_id)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            )
            has_version_table = cursor.fetchone() is not None

            current_version = 0
            if has_version_table:
                cursor = conn.execute(
                    "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
                )
                row = cursor.fetchone()
                current_version = row[0] if row else 0

            # For old databases (< v6), raise error before trying to create indexes
            # that reference columns that don't exist
            if current_version > 0 and current_version < 6:
                raise RuntimeError(
                    f"Database schema v{current_version} is incompatible with v6 (workflow-first). "
                    "Please delete your .ralphx/ralphx.db file and start fresh."
                )

            # Now safe to create schema and indexes
            conn.executescript(PROJECT_SCHEMA_SQL)
            conn.executescript(PROJECT_INDEXES_SQL)

            if current_version == 0:
                # Fresh database
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (PROJECT_SCHEMA_VERSION,),
                )
            elif current_version < PROJECT_SCHEMA_VERSION:
                # Run migrations (for future versions > 6)
                self._run_migrations(conn, current_version)

    def _run_migrations(self, conn: sqlite3.Connection, from_version: int) -> None:
        """Run schema migrations from a version to the latest.

        Schema v6 is a breaking change (workflow-first architecture).
        Old databases should be wiped and recreated. This is now checked
        in _init_schema before calling this method.

        Args:
            conn: Database connection.
            from_version: Current schema version (must be >= 6).
        """
        # Note: from_version < 6 check is now in _init_schema
        # This method is only called for versions >= 6

        # Migration from v6 to v7: Add workflow_resources and project_resources tables
        if from_version == 6:
            self._migrate_v6_to_v7(conn)
            from_version = 7  # Continue to next migration

        # Migration from v7 to v8: Add workflow_step_resources table
        if from_version == 7:
            self._migrate_v7_to_v8(conn)
            from_version = 8  # Continue to next migration

        # Migration from v8 to v9: Change work_items primary key to composite (id, workflow_id)
        if from_version == 8:
            self._migrate_v8_to_v9(conn)
            from_version = 9  # Continue to next migration

        # Migration from v9 to v10: Add session_events table
        if from_version == 9:
            self._migrate_v9_to_v10(conn)
            from_version = 10  # Continue to next migration

        # Migration from v10 to v11: Add stale detection fields to runs
        if from_version == 10:
            self._migrate_v10_to_v11(conn)
            from_version = 11  # Continue to next migration

        # Migration from v11 to v12: Add archived_at to workflows
        if from_version == 11:
            self._migrate_v11_to_v12(conn)
            from_version = 12  # Continue to next migration

        # Migration from v12 to v13: Add archived_at to workflow_steps
        if from_version == 12:
            self._migrate_v12_to_v13(conn)
            from_version = 13  # Continue to next migration

        # Migration from v13 to v14: Add project_settings table
        if from_version == 13:
            self._migrate_v13_to_v14(conn)
            from_version = 14  # Continue to next migration

        # Migration from v14 to v15: Add workflow_resource_versions table
        if from_version == 14:
            self._migrate_v14_to_v15(conn)
            from_version = 15  # Continue to next migration

        # Migration from v15 to v16: Remove namespace from workflows table
        if from_version == 15:
            self._migrate_v15_to_v16(conn)

        # Seed workflow templates for fresh databases
        self._seed_workflow_templates(conn)

        # Update version
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (PROJECT_SCHEMA_VERSION,),
        )

        # Seed default data if tables are empty
        self._seed_defaults(conn)

    def _migrate_v6_to_v7(self, conn: sqlite3.Connection) -> None:
        """Migrate from schema v6 to v7.

        Adds:
        - workflow_resources table for workflow-scoped resources
        - project_resources table for shared resource library
        - Cascade delete triggers for workflow cleanup
        """
        # Add workflow_resources table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                name TEXT NOT NULL,
                content TEXT,
                file_path TEXT,
                source TEXT,
                source_id INTEGER,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
            )
        """)

        # Add project_resources table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resource_type TEXT NOT NULL,
                name TEXT NOT NULL,
                content TEXT,
                file_path TEXT,
                auto_inherit BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Add cascade delete triggers
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS cascade_delete_workflow_loops
                AFTER DELETE ON workflows
                FOR EACH ROW
                BEGIN
                    DELETE FROM loops WHERE workflow_id = OLD.id;
                END
        """)

        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS cascade_delete_workflow_runs
                AFTER DELETE ON workflows
                FOR EACH ROW
                BEGIN
                    DELETE FROM runs WHERE workflow_id = OLD.id;
                END
        """)

        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS cascade_delete_workflow_items
                AFTER DELETE ON workflows
                FOR EACH ROW
                BEGIN
                    DELETE FROM work_items WHERE workflow_id = OLD.id;
                END
        """)

        # Add indexes
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflow_resources_workflow
            ON workflow_resources(workflow_id, resource_type)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_workflow_resources_type
            ON workflow_resources(resource_type, enabled)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_project_resources_type
            ON project_resources(resource_type, auto_inherit)
        """)

    def _migrate_v7_to_v8(self, conn: sqlite3.Connection) -> None:
        """Migrate from schema v7 to v8.

        Adds:
        - workflow_step_resources table for step-level resource overrides
        """
        # Add workflow_step_resources table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_step_resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                step_id INTEGER NOT NULL,
                workflow_resource_id INTEGER,
                resource_type TEXT,
                name TEXT,
                content TEXT,
                file_path TEXT,
                mode TEXT NOT NULL DEFAULT 'add',
                enabled BOOLEAN DEFAULT TRUE,
                priority INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (step_id) REFERENCES workflow_steps(id) ON DELETE CASCADE,
                FOREIGN KEY (workflow_resource_id) REFERENCES workflow_resources(id) ON DELETE CASCADE
            )
        """)

        # Add indexes
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_step_resources_step
            ON workflow_step_resources(step_id, mode)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_step_resources_workflow_resource
            ON workflow_step_resources(workflow_resource_id)
        """)

    def _migrate_v8_to_v9(self, conn: sqlite3.Connection) -> None:
        """Migrate from schema v8 to v9.

        Changes:
        - work_items primary key from (id) to composite (id, workflow_id)
          This allows same item IDs to exist in different workflows.
        - Added implemented_commit field to track which git commit implemented the item
        """
        # SQLite doesn't support ALTER TABLE to change primary key
        # We need to recreate the table with the new schema
        conn.execute("""
            CREATE TABLE IF NOT EXISTS work_items_new (
                id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                source_step_id INTEGER NOT NULL,
                priority INTEGER,
                content TEXT NOT NULL,
                title TEXT,
                status TEXT DEFAULT 'pending',
                category TEXT,
                tags TEXT,
                metadata TEXT,
                item_type TEXT DEFAULT 'item',
                claimed_by TEXT,
                claimed_at TIMESTAMP,
                processed_at TIMESTAMP,
                implemented_commit TEXT,
                dependencies TEXT,
                phase INTEGER,
                duplicate_of TEXT,
                skip_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id, workflow_id)
            )
        """)

        # Copy data from old table (dropping phase_1_* columns, adding implemented_commit)
        conn.execute("""
            INSERT OR IGNORE INTO work_items_new (
                id, workflow_id, source_step_id, priority, content, title,
                status, category, tags, metadata, item_type, claimed_by,
                claimed_at, processed_at, implemented_commit,
                dependencies, phase, duplicate_of, skip_reason,
                created_at, updated_at
            )
            SELECT
                id, workflow_id, source_step_id, priority, content, title,
                status, category, tags, metadata, item_type, claimed_by,
                claimed_at, processed_at, NULL,
                dependencies, phase, duplicate_of, skip_reason,
                created_at, updated_at
            FROM work_items
        """)

        # Drop the trigger that references work_items before dropping the table
        conn.execute("DROP TRIGGER IF EXISTS cascade_delete_workflow_items")

        # Drop old table and rename new one
        conn.execute("DROP TABLE work_items")
        conn.execute("ALTER TABLE work_items_new RENAME TO work_items")

        # Recreate indexes
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_work_items_workflow
            ON work_items(workflow_id, status)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_work_items_source_step
            ON work_items(source_step_id)
        """)

        # Recreate the trigger for the new table
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS cascade_delete_workflow_items
                AFTER DELETE ON workflows
                FOR EACH ROW
            BEGIN
                DELETE FROM work_items WHERE workflow_id = OLD.id;
            END;
        """)

    def _migrate_v9_to_v10(self, conn: sqlite3.Connection) -> None:
        """Migrate from schema v9 to v10.

        Adds:
        - session_events table for storing parsed session events for history
        """
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                event_type TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                content TEXT,
                tool_name TEXT,
                tool_input TEXT,
                tool_result TEXT,
                error_message TEXT,
                raw_data TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_events_session
            ON session_events(session_id)
        """)

    def _migrate_v10_to_v11(self, conn: sqlite3.Connection) -> None:
        """Migrate from schema v10 to v11.

        Adds:
        - executor_pid column to runs for stale process detection
        - last_activity_at column to runs for inactivity detection
        """
        conn.execute("ALTER TABLE runs ADD COLUMN executor_pid INTEGER")
        conn.execute("ALTER TABLE runs ADD COLUMN last_activity_at TIMESTAMP")

    def _migrate_v11_to_v12(self, conn: sqlite3.Connection) -> None:
        """Migrate from schema v11 to v12.

        Adds:
        - archived_at column to workflows for soft delete (archiving)
        """
        conn.execute("ALTER TABLE workflows ADD COLUMN archived_at TIMESTAMP")

    def _migrate_v12_to_v13(self, conn: sqlite3.Connection) -> None:
        """Migrate from schema v12 to v13.

        Adds:
        - archived_at column to workflow_steps for soft delete (archiving)
        """
        conn.execute("ALTER TABLE workflow_steps ADD COLUMN archived_at TIMESTAMP")

    def _migrate_v13_to_v14(self, conn: sqlite3.Connection) -> None:
        """Migrate from schema v13 to v14.

        Adds:
        - project_settings table for project-level default settings
        """
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                auto_inherit_guardrails BOOLEAN DEFAULT TRUE,
                require_design_doc BOOLEAN DEFAULT FALSE,
                architecture_first_mode BOOLEAN DEFAULT FALSE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def _migrate_v14_to_v15(self, conn: sqlite3.Connection) -> None:
        """Migrate from schema v14 to v15.

        Adds:
        - workflow_resource_versions table for resource version history
        """
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_resource_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_resource_id INTEGER NOT NULL,
                version_number INTEGER NOT NULL,
                content TEXT,
                name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (workflow_resource_id) REFERENCES workflow_resources(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_resource_versions
            ON workflow_resource_versions(workflow_resource_id, version_number DESC)
        """)

    def _migrate_v15_to_v16(self, conn: sqlite3.Connection) -> None:
        """Migrate from schema v15 to v16.

        Removes:
        - namespace column from workflows table (deprecated, replaced by workflow_id)
        - idx_workflows_namespace index

        SQLite doesn't support DROP COLUMN directly, so we recreate the table.
        """
        # 1. Create new table without namespace
        conn.execute("""
            CREATE TABLE workflows_new (
                id TEXT PRIMARY KEY,
                template_id TEXT,
                name TEXT NOT NULL,
                status TEXT DEFAULT 'draft',
                current_step INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                archived_at TIMESTAMP
            )
        """)

        # 2. Copy data (excluding namespace)
        conn.execute("""
            INSERT INTO workflows_new (id, template_id, name, status, current_step, created_at, updated_at, archived_at)
            SELECT id, template_id, name, status, current_step, created_at, updated_at, archived_at
            FROM workflows
        """)

        # 3. Drop old table and index
        conn.execute("DROP INDEX IF EXISTS idx_workflows_namespace")
        conn.execute("DROP TABLE workflows")

        # 4. Rename new table
        conn.execute("ALTER TABLE workflows_new RENAME TO workflows")

        # 5. Recreate the status index on the new table
        conn.execute("CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status)")

    # ========== Loops ==========

    def create_loop(
        self,
        id: str,
        name: str,
        config_yaml: str,
        workflow_id: Optional[str] = None,
        step_id: Optional[int] = None,
    ) -> dict:
        """Create a loop configuration.

        Args:
            id: Unique loop identifier.
            name: Loop name (must be unique).
            config_yaml: YAML configuration content.
            workflow_id: Parent workflow ID (optional for legacy standalone loops).
            step_id: Parent workflow step ID (optional for legacy standalone loops).

        Note:
            In the workflow-first architecture, loops should always be created
            with workflow_id and step_id. The None defaults are for backward
            compatibility with legacy standalone loop creation paths.
        """
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            conn.execute(
                """
                INSERT INTO loops (id, name, config_yaml, workflow_id, step_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (id, name, config_yaml, workflow_id, step_id, now, now),
            )
        return self.get_loop(name)

    def get_loop(self, name: str) -> Optional[dict]:
        """Get loop by name."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM loops WHERE name = ?",
                (name,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_loops(self) -> list[dict]:
        """List all loops."""
        with self._reader() as conn:
            cursor = conn.execute("SELECT * FROM loops ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]

    _LOOP_UPDATE_COLS = frozenset({"config_yaml", "updated_at"})

    def update_loop(self, name: str, **kwargs) -> bool:
        """Update loop configuration."""
        invalid_cols = set(kwargs.keys()) - self._LOOP_UPDATE_COLS - {"updated_at"}
        if invalid_cols:
            raise ValueError(f"Invalid columns for loop update: {invalid_cols}")

        if not kwargs:
            return False

        kwargs["updated_at"] = datetime.utcnow().isoformat()

        with self._writer() as conn:
            set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
            cursor = conn.execute(
                f"UPDATE loops SET {set_clause} WHERE name = ?",
                (*kwargs.values(), name),
            )
            return cursor.rowcount > 0

    def delete_loop(self, name: str) -> bool:
        """Delete a loop."""
        with self._writer() as conn:
            cursor = conn.execute("DELETE FROM loops WHERE name = ?", (name,))
            return cursor.rowcount > 0

    # ========== Runs ==========

    def create_run(
        self,
        id: str,
        loop_name: str,
        workflow_id: str,
        step_id: int,
    ) -> dict:
        """Create a new run.

        Args:
            id: Unique run identifier.
            loop_name: Name of the loop being run.
            workflow_id: Parent workflow ID.
            step_id: Parent workflow step ID.
        """
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            conn.execute(
                """
                INSERT INTO runs (id, loop_name, status, workflow_id, step_id, started_at)
                VALUES (?, ?, 'running', ?, ?, ?)
                """,
                (id, loop_name, workflow_id, step_id, now),
            )
        return self.get_run(id)

    def get_run(self, id: str) -> Optional[dict]:
        """Get run by ID."""
        with self._reader() as conn:
            cursor = conn.execute("SELECT * FROM runs WHERE id = ?", (id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_runs(
        self,
        loop_name: Optional[str] = None,
        status: Optional[str | list[str]] = None,
        workflow_id: Optional[str] = None,
        step_id: Optional[int] = None,
        limit: int = 100,
    ) -> list[dict]:
        """List runs with optional filters.

        Args:
            loop_name: Filter by loop name.
            status: Filter by status. Can be a single status string or a list of statuses.
            workflow_id: Filter by workflow ID.
            step_id: Filter by step ID.
            limit: Maximum number of runs to return.
        """
        with self._reader() as conn:
            query = "SELECT * FROM runs WHERE 1=1"
            params: list[Any] = []

            if loop_name:
                query += " AND loop_name = ?"
                params.append(loop_name)
            if status:
                if isinstance(status, list):
                    placeholders = ", ".join("?" * len(status))
                    query += f" AND status IN ({placeholders})"
                    params.extend(status)
                else:
                    query += " AND status = ?"
                    params.append(status)
            if workflow_id:
                query += " AND workflow_id = ?"
                params.append(workflow_id)
            if step_id:
                query += " AND step_id = ?"
                params.append(step_id)

            query += " ORDER BY started_at DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    _RUN_UPDATE_COLS = frozenset({
        "status", "completed_at", "iterations_completed",
        "items_generated", "error_message", "executor_pid", "last_activity_at"
    })

    def update_run(self, id: str, **kwargs) -> bool:
        """Update run fields."""
        invalid_cols = set(kwargs.keys()) - self._RUN_UPDATE_COLS
        if invalid_cols:
            raise ValueError(f"Invalid columns for run update: {invalid_cols}")

        if not kwargs:
            return False

        with self._writer() as conn:
            set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
            cursor = conn.execute(
                f"UPDATE runs SET {set_clause} WHERE id = ?",
                (*kwargs.values(), id),
            )
            return cursor.rowcount > 0

    def increment_run_counters(
        self,
        id: str,
        iterations: int = 0,
        items: int = 0,
    ) -> bool:
        """Atomically increment run counters."""
        with self._writer() as conn:
            cursor = conn.execute(
                """
                UPDATE runs SET
                    iterations_completed = iterations_completed + ?,
                    items_generated = items_generated + ?
                WHERE id = ?
                """,
                (iterations, items, id),
            )
            return cursor.rowcount > 0

    # ========== Sessions ==========

    def create_session(
        self,
        session_id: str,
        run_id: Optional[str],
        iteration: int,
        mode: Optional[str] = None,
        status: str = "running",
    ) -> dict:
        """Create a new session.

        Args:
            session_id: Unique session identifier.
            run_id: Associated run ID.
            iteration: Iteration number.
            mode: Mode name for this session.
            status: Session status (running, completed, error).
        """
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            conn.execute(
                """
                INSERT INTO sessions (session_id, run_id, iteration, mode, started_at, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, run_id, iteration, mode, now, status),
            )
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session by ID."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_session_status(self, session_id: str, status: str) -> bool:
        """Update session status.

        Args:
            session_id: Session to update.
            status: New status (running, completed, error).

        Returns:
            True if session was updated, False if not found.
        """
        with self._writer() as conn:
            cursor = conn.execute(
                "UPDATE sessions SET status = ? WHERE session_id = ?",
                (status, session_id),
            )
            return cursor.rowcount > 0

    def list_sessions(
        self,
        run_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """List sessions with optional filters."""
        with self._reader() as conn:
            if run_id:
                cursor = conn.execute(
                    """
                    SELECT * FROM sessions WHERE run_id = ?
                    ORDER BY iteration DESC LIMIT ?
                    """,
                    (run_id, limit),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                )
            return [dict(row) for row in cursor.fetchall()]

    _SESSION_UPDATE_COLS = frozenset({
        "duration_seconds", "status", "items_added"
    })

    def update_session(self, session_id: str, **kwargs) -> bool:
        """Update session fields."""
        invalid_cols = set(kwargs.keys()) - self._SESSION_UPDATE_COLS
        if invalid_cols:
            raise ValueError(f"Invalid columns for session update: {invalid_cols}")

        if not kwargs:
            return False

        # Serialize list fields to JSON
        if "items_added" in kwargs and isinstance(kwargs["items_added"], list):
            kwargs["items_added"] = json.dumps(kwargs["items_added"])

        with self._writer() as conn:
            set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
            cursor = conn.execute(
                f"UPDATE sessions SET {set_clause} WHERE session_id = ?",
                (*kwargs.values(), session_id),
            )
            return cursor.rowcount > 0

    # ========== Session Events ==========

    def add_session_event(
        self,
        session_id: str,
        event_type: str,
        content: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_input: Optional[dict] = None,
        tool_result: Optional[str] = None,
        error_message: Optional[str] = None,
        raw_data: Optional[dict] = None,
    ) -> int:
        """Add an event to a session.

        Args:
            session_id: Session UUID.
            event_type: Event type (text, tool_call, tool_result, error, init, complete).
            content: Text content for text events.
            tool_name: Tool name for tool events.
            tool_input: Tool input dict for tool_call events.
            tool_result: Result string for tool_result events.
            error_message: Error message for error events.
            raw_data: Full raw data dict for debugging.

        Returns:
            The ID of the created event.
        """
        with self._writer() as conn:
            cursor = conn.execute(
                """
                INSERT INTO session_events (
                    session_id, event_type, content, tool_name,
                    tool_input, tool_result, error_message, raw_data
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    event_type,
                    content,
                    tool_name,
                    json.dumps(tool_input) if tool_input else None,
                    tool_result,
                    error_message,
                    json.dumps(raw_data) if raw_data else None,
                ),
            )
            return cursor.lastrowid

    def get_session_events(
        self,
        session_id: str,
        after_id: Optional[int] = None,
        limit: int = 500,
    ) -> list[dict]:
        """Get events for a session.

        Args:
            session_id: Session UUID.
            after_id: Only return events with ID greater than this (for polling).
            limit: Maximum number of events to return.

        Returns:
            List of event dicts.
        """
        with self._reader() as conn:
            if after_id:
                cursor = conn.execute(
                    """
                    SELECT * FROM session_events
                    WHERE session_id = ? AND id > ?
                    ORDER BY id ASC LIMIT ?
                    """,
                    (session_id, after_id, limit),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT * FROM session_events
                    WHERE session_id = ?
                    ORDER BY id ASC LIMIT ?
                    """,
                    (session_id, limit),
                )

            events = []
            for row in cursor.fetchall():
                event = dict(row)
                # Parse JSON fields
                if event.get("tool_input"):
                    try:
                        event["tool_input"] = json.loads(event["tool_input"])
                    except json.JSONDecodeError:
                        pass
                if event.get("raw_data"):
                    try:
                        event["raw_data"] = json.loads(event["raw_data"])
                    except json.JSONDecodeError:
                        pass
                events.append(event)
            return events

    def get_session_event_count(self, session_id: str) -> int:
        """Get the count of events for a session.

        Args:
            session_id: Session UUID.

        Returns:
            Number of events.
        """
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM session_events WHERE session_id = ?",
                (session_id,),
            )
            return cursor.fetchone()[0]

    # ========== Work Items ==========

    def create_work_item(
        self,
        id: str,
        workflow_id: str,
        source_step_id: int,
        content: str,
        title: Optional[str] = None,
        priority: Optional[int] = None,
        category: Optional[str] = None,
        item_type: str = "item",
        metadata: Optional[dict] = None,
        dependencies: Optional[list[str]] = None,
        phase: Optional[int] = None,
        status: str = "pending",
        duplicate_of: Optional[str] = None,
        skip_reason: Optional[str] = None,
    ) -> dict:
        """Create a work item.

        Args:
            id: Unique item identifier.
            workflow_id: Parent workflow ID.
            source_step_id: Workflow step that created this item.
            content: Item content/description.
            title: Optional item title.
            priority: Optional priority (lower = higher priority).
            category: Optional category for grouping.
            item_type: Type of item (default: "item").
            metadata: Optional additional metadata dict.
            dependencies: Optional list of item IDs this depends on.
            phase: Optional phase number for implementation batching (Phase 1, etc).
            status: Initial status (default: "pending").
            duplicate_of: Parent item ID if this is a duplicate.
            skip_reason: Reason for skipping (for skipped/external status).

        Returns:
            The created work item dict.
        """
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            metadata_json = json.dumps(metadata) if metadata else None
            dependencies_json = json.dumps(dependencies) if dependencies else None
            conn.execute(
                """
                INSERT INTO work_items
                (id, workflow_id, source_step_id, content, title, priority, category,
                 item_type, metadata, dependencies, phase, status, duplicate_of,
                 skip_reason, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (id, workflow_id, source_step_id, content, title, priority, category,
                 item_type, metadata_json, dependencies_json, phase, status, duplicate_of,
                 skip_reason, now, now),
            )
        return self.get_work_item(id)

    def get_work_item(self, id: str) -> Optional[dict]:
        """Get work item by ID."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM work_items WHERE id = ?",
                (id,),
            )
            row = cursor.fetchone()
            if row:
                item = dict(row)
                if item.get("metadata"):
                    item["metadata"] = json.loads(item["metadata"])
                if item.get("tags"):
                    item["tags"] = json.loads(item["tags"])
                if item.get("dependencies"):
                    item["dependencies"] = json.loads(item["dependencies"])
                return item
            return None

    def list_work_items(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        workflow_id: Optional[str] = None,
        source_step_id: Optional[int] = None,
        phase: Optional[int] = None,
        unclaimed_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """List work items with optional filters.

        Args:
            status: Filter by status.
            category: Filter by category.
            workflow_id: Filter by parent workflow.
            source_step_id: Filter by source workflow step.
            phase: Filter by phase number (for batching).
            unclaimed_only: If True, only return items not claimed by any loop.
            limit: Maximum items to return.
            offset: Pagination offset.

        Returns:
            Tuple of (items list, total count).
        """
        with self._reader() as conn:
            # Build WHERE clause
            conditions = ["1=1"]
            params: list[Any] = []

            if status:
                conditions.append("status = ?")
                params.append(status)
            if category:
                conditions.append("category = ?")
                params.append(category)
            if workflow_id:
                conditions.append("workflow_id = ?")
                params.append(workflow_id)
            if source_step_id is not None:
                conditions.append("source_step_id = ?")
                params.append(source_step_id)
            if phase is not None:
                conditions.append("phase = ?")
                params.append(phase)
            if unclaimed_only:
                conditions.append("claimed_by IS NULL")

            where_clause = " AND ".join(conditions)

            # Get total count
            cursor = conn.execute(
                f"SELECT COUNT(*) FROM work_items WHERE {where_clause}",
                params,
            )
            total = cursor.fetchone()[0]

            # Get items
            query = f"""
                SELECT * FROM work_items WHERE {where_clause}
                ORDER BY priority ASC NULLS LAST, created_at DESC
                LIMIT ? OFFSET ?
            """
            cursor = conn.execute(query, params + [limit, offset])

            items = []
            for row in cursor.fetchall():
                item = dict(row)
                if item.get("metadata"):
                    item["metadata"] = json.loads(item["metadata"])
                if item.get("tags"):
                    item["tags"] = json.loads(item["tags"])
                if item.get("dependencies"):
                    item["dependencies"] = json.loads(item["dependencies"])
                items.append(item)

            return items, total

    _WORK_ITEM_UPDATE_COLS = frozenset({
        "content", "title", "priority", "status", "category", "tags", "metadata",
        "item_type", "claimed_by", "claimed_at", "processed_at", "implemented_commit",
        "dependencies", "phase", "duplicate_of", "skip_reason", "updated_at"
    })

    def update_work_item(self, id: str, **kwargs) -> bool:
        """Update work item fields."""
        invalid_cols = set(kwargs.keys()) - self._WORK_ITEM_UPDATE_COLS - {"updated_at"}
        if invalid_cols:
            raise ValueError(f"Invalid columns for work_item update: {invalid_cols}")

        if not kwargs:
            return False

        # Serialize JSON fields
        if "metadata" in kwargs and kwargs["metadata"] is not None:
            kwargs["metadata"] = json.dumps(kwargs["metadata"])
        if "tags" in kwargs and kwargs["tags"] is not None:
            kwargs["tags"] = json.dumps(kwargs["tags"])

        kwargs["updated_at"] = datetime.utcnow().isoformat()

        with self._writer() as conn:
            set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
            cursor = conn.execute(
                f"UPDATE work_items SET {set_clause} WHERE id = ?",
                (*kwargs.values(), id),
            )
            return cursor.rowcount > 0

    def delete_work_item(self, id: str) -> bool:
        """Delete a work item."""
        with self._writer() as conn:
            cursor = conn.execute("DELETE FROM work_items WHERE id = ?", (id,))
            return cursor.rowcount > 0

    def get_work_item_stats(self) -> dict:
        """Get statistics about work items."""
        with self._reader() as conn:
            # Total count
            cursor = conn.execute("SELECT COUNT(*) FROM work_items")
            total = cursor.fetchone()[0]

            # By status (handle NULL status as "pending")
            cursor = conn.execute(
                "SELECT COALESCE(status, 'pending') as status, COUNT(*) as count FROM work_items GROUP BY COALESCE(status, 'pending')"
            )
            by_status = {row["status"]: row["count"] for row in cursor.fetchall()}

            # By category
            cursor = conn.execute(
                """
                SELECT category, COUNT(*) as count FROM work_items
                WHERE category IS NOT NULL GROUP BY category
                """
            )
            by_category = {row["category"]: row["count"] for row in cursor.fetchall()}

            # By priority
            cursor = conn.execute(
                """
                SELECT priority, COUNT(*) as count FROM work_items
                WHERE priority IS NOT NULL GROUP BY priority ORDER BY priority
                """
            )
            by_priority = {row["priority"]: row["count"] for row in cursor.fetchall()}

            return {
                "total": total,
                "by_status": by_status,
                "by_category": by_category,
                "by_priority": by_priority,
            }

    def claim_work_item(self, id: str, claimed_by: str) -> bool:
        """Claim a work item for processing.

        Claims items that are either 'pending' (not yet processed) or 'completed'
        (generated by a producer loop and ready for consumption).

        Args:
            id: Work item ID.
            claimed_by: Name of the loop claiming this item.

        Returns:
            True if item was claimed, False if not found or already claimed.
        """
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            cursor = conn.execute(
                """
                UPDATE work_items
                SET claimed_by = ?, claimed_at = ?, status = 'claimed', updated_at = ?
                WHERE id = ? AND status IN ('pending', 'completed') AND claimed_by IS NULL
                """,
                (claimed_by, now, now, id),
            )
            return cursor.rowcount > 0

    def release_work_item(self, id: str) -> bool:
        """Release a claimed work item back to pending state."""
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            cursor = conn.execute(
                """
                UPDATE work_items
                SET claimed_by = NULL,
                    claimed_at = NULL,
                    status = 'pending',
                    updated_at = ?
                WHERE id = ? AND status = 'claimed'
                """,
                (now, id),
            )
            return cursor.rowcount > 0

    def complete_work_item(self, id: str) -> bool:
        """Mark a work item as completed."""
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            cursor = conn.execute(
                """
                UPDATE work_items
                SET status = 'completed', processed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, id),
            )
            return cursor.rowcount > 0

    def mark_work_item_processed(
        self,
        id: str,
        processed_by: str,
    ) -> bool:
        """Mark a work item as processed.

        Only succeeds if the item is claimed by the specified loop.

        Args:
            id: Work item ID.
            processed_by: Name of the loop that processed this item.

        Returns:
            True if item was marked processed, False otherwise.
        """
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            cursor = conn.execute(
                """
                UPDATE work_items
                SET status = 'processed', processed_at = ?, updated_at = ?
                WHERE id = ? AND claimed_by = ?
                """,
                (now, now, id, processed_by),
            )
            return cursor.rowcount > 0

    def update_work_item_with_status(
        self,
        id: str,
        status: str,
        processed_by: str,
        duplicate_of: Optional[str] = None,
        skip_reason: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> bool:
        """Update a work item with specific status and details.

        Used by consumer loops when Claude reports structured status output
        (implemented, duplicate, external, skipped, error).

        Only succeeds if the item is claimed by the specified loop.

        Args:
            id: Work item ID.
            status: New status (processed, duplicate, external, skipped, failed).
            processed_by: Name of the loop that processed this item.
            duplicate_of: Parent item ID if this is a duplicate.
            skip_reason: Reason for skipping (for skipped status).
            metadata: Additional metadata to merge into existing metadata.

        Returns:
            True if item was updated, False otherwise.
        """
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()

            # Get existing metadata to merge with new
            cursor = conn.execute(
                "SELECT metadata FROM work_items WHERE id = ? AND claimed_by = ?",
                (id, processed_by),
            )
            row = cursor.fetchone()
            if not row:
                return False

            # Merge metadata
            existing_metadata = {}
            if row[0]:
                try:
                    existing_metadata = json.loads(row[0])
                except (json.JSONDecodeError, TypeError):
                    pass

            if metadata:
                existing_metadata.update(metadata)

            metadata_json = json.dumps(existing_metadata) if existing_metadata else None

            # Update the item with all fields
            cursor = conn.execute(
                """
                UPDATE work_items
                SET status = ?,
                    processed_at = ?,
                    updated_at = ?,
                    duplicate_of = ?,
                    skip_reason = ?,
                    metadata = ?
                WHERE id = ? AND claimed_by = ?
                """,
                (
                    status,
                    now,
                    now,
                    duplicate_of,
                    skip_reason,
                    metadata_json,
                    id,
                    processed_by,
                ),
            )
            return cursor.rowcount > 0

    def release_stale_claims(self, max_age_minutes: int = 30) -> int:
        """Release claims that have been held too long (likely crashed consumer).

        Args:
            max_age_minutes: Claims older than this are released.

        Returns:
            Number of claims released.
        """
        from datetime import timedelta

        cutoff = (datetime.utcnow() - timedelta(minutes=max_age_minutes)).isoformat()
        now = datetime.utcnow().isoformat()

        with self._writer() as conn:
            cursor = conn.execute(
                """
                UPDATE work_items
                SET claimed_by = NULL,
                    claimed_at = NULL,
                    status = 'pending',
                    updated_at = ?
                WHERE claimed_at < ?
                  AND claimed_by IS NOT NULL
                  AND status = 'claimed'
                """,
                (now, cutoff),
            )
            return cursor.rowcount

    def release_claims_by_loop(self, loop_name: str) -> int:
        """Release all claims held by a specific loop.

        Used when deleting a loop to prevent orphaned claims.
        Released items are restored to 'pending' status so they can be
        picked up by other loops.

        Args:
            loop_name: Name of the loop whose claims should be released.

        Returns:
            Number of claims released.
        """
        now = datetime.utcnow().isoformat()

        with self._writer() as conn:
            cursor = conn.execute(
                """
                UPDATE work_items
                SET claimed_by = NULL,
                    claimed_at = NULL,
                    status = 'pending',
                    updated_at = ?
                WHERE claimed_by = ? AND status = 'claimed'
                """,
                (now, loop_name),
            )
            return cursor.rowcount

    def release_work_item_claim(self, id: str, claimed_by: str) -> bool:
        """Release a claim on a work item, verifying ownership.

        This is an atomic operation that checks ownership and releases in one step
        to prevent TOCTOU race conditions.

        Released items are restored to 'pending' status so they can be
        picked up by other loops.

        Args:
            id: Work item ID.
            claimed_by: Name of the loop that should own the claim.

        Returns:
            True if claim was released, False if item not found or not claimed by this loop.
        """
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            cursor = conn.execute(
                """
                UPDATE work_items
                SET claimed_by = NULL,
                    claimed_at = NULL,
                    status = 'pending',
                    updated_at = ?
                WHERE id = ? AND claimed_by = ? AND status = 'claimed'
                """,
                (now, id, claimed_by),
            )
            return cursor.rowcount > 0

    def get_workflow_item_counts(self, workflow_id: str) -> dict[int, dict[str, int]]:
        """Get counts of items grouped by source step and status.

        Used for dashboard to show item progress per workflow step.

        Args:
            workflow_id: The workflow to get counts for.

        Returns:
            Dictionary mapping source_step_id to {status: count}.
        """
        with self._reader() as conn:
            cursor = conn.execute(
                """
                SELECT source_step_id, status, COUNT(*) as count
                FROM work_items
                WHERE workflow_id = ?
                GROUP BY source_step_id, status
                """,
                (workflow_id,),
            )
            result: dict[int, dict[str, int]] = {}
            for row in cursor.fetchall():
                step_id = row["source_step_id"]
                if step_id not in result:
                    result[step_id] = {}
                result[step_id][row["status"]] = row["count"]
            return result

    # ========== Phase 1 Tracking ==========

    def create_run_phase(self, run_id: str) -> dict:
        """Create phase tracking for a run."""
        with self._writer() as conn:
            conn.execute(
                "INSERT INTO run_phases (run_id) VALUES (?)",
                (run_id,),
            )
        return self.get_run_phase(run_id)

    def get_run_phase(self, run_id: str) -> Optional[dict]:
        """Get phase tracking for a run."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM run_phases WHERE run_id = ?",
                (run_id,),
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result.get("phase_1_story_ids"):
                    result["phase_1_story_ids"] = json.loads(result["phase_1_story_ids"])
                if result.get("analysis_output"):
                    result["analysis_output"] = json.loads(result["analysis_output"])
                return result
            return None

    def update_run_phase(
        self,
        run_id: str,
        phase: Optional[str] = None,
        phase_1_story_ids: Optional[list[str]] = None,
        analysis_output: Optional[dict] = None,
        phase_1_started: bool = False,
        phase_1_completed: bool = False,
    ) -> bool:
        """Update phase tracking for a run."""
        with self._writer() as conn:
            updates = []
            params: list[Any] = []

            if phase:
                updates.append("phase = ?")
                params.append(phase)
            if phase_1_story_ids is not None:
                updates.append("phase_1_story_ids = ?")
                params.append(json.dumps(phase_1_story_ids))
            if analysis_output is not None:
                updates.append("analysis_output = ?")
                params.append(json.dumps(analysis_output))
            if phase_1_started:
                updates.append("phase_1_started_at = ?")
                params.append(datetime.utcnow().isoformat())
            if phase_1_completed:
                updates.append("phase_1_completed_at = ?")
                params.append(datetime.utcnow().isoformat())

            if not updates:
                return False

            params.append(run_id)
            cursor = conn.execute(
                f"UPDATE run_phases SET {', '.join(updates)} WHERE run_id = ?",
                params,
            )
            return cursor.rowcount > 0

    def set_items_phase(
        self,
        item_ids: list[str],
        workflow_id: str,
        phase: int,
    ) -> int:
        """Set the phase number for a batch of items.

        Args:
            item_ids: List of item IDs to update.
            workflow_id: Workflow the items belong to.
            phase: Phase number to assign.

        Returns:
            Number of items updated.
        """
        with self._writer() as conn:
            count = 0
            for item_id in item_ids:
                cursor = conn.execute(
                    """
                    UPDATE work_items
                    SET phase = ?, updated_at = ?
                    WHERE id = ? AND workflow_id = ?
                    """,
                    (phase, datetime.utcnow().isoformat(), item_id, workflow_id),
                )
                count += cursor.rowcount
            return count

    # ========== Input Files ==========

    def track_input_file(
        self,
        loop_name: str,
        filename: str,
        file_type: str,
        items_imported: int = 0,
    ) -> dict:
        """Track an imported input file."""
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            conn.execute(
                """
                INSERT OR REPLACE INTO input_files
                (loop_name, filename, file_type, imported_at, items_imported)
                VALUES (?, ?, ?, ?, ?)
                """,
                (loop_name, filename, file_type, now, items_imported),
            )
        return self.get_input_file(loop_name, filename)

    def get_input_file(self, loop_name: str, filename: str) -> Optional[dict]:
        """Get input file tracking info."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM input_files WHERE loop_name = ? AND filename = ?",
                (loop_name, filename),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_input_files(self, loop_name: Optional[str] = None) -> list[dict]:
        """List tracked input files."""
        with self._reader() as conn:
            if loop_name:
                cursor = conn.execute(
                    "SELECT * FROM input_files WHERE loop_name = ? ORDER BY imported_at DESC",
                    (loop_name,),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM input_files ORDER BY imported_at DESC"
                )
            return [dict(row) for row in cursor.fetchall()]

    # ========== Resources ==========

    def create_resource(
        self,
        name: str,
        resource_type: str,
        file_path: str,
        injection_position: str = "after_design_doc",
        enabled: bool = True,
        inherit_default: bool = True,
        priority: int = 100,
    ) -> dict:
        """Create a resource entry.

        Args:
            name: Unique resource name.
            resource_type: Type of resource (design_doc, architecture, coding_standards,
                          domain_knowledge, custom).
            file_path: Path to the resource file (relative to .ralphx/resources/).
            injection_position: Where to inject in prompt (before_prompt, after_design_doc,
                               before_task, after_task).
            enabled: Whether the resource is active.
            inherit_default: Whether loops should inherit this resource by default.
            priority: Ordering priority (lower = earlier injection).

        Returns:
            The created resource dict.
        """
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            conn.execute(
                """
                INSERT INTO resources
                (name, resource_type, file_path, injection_position, enabled,
                 inherit_default, priority, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (name, resource_type, file_path, injection_position, enabled,
                 inherit_default, priority, now, now),
            )
        return self.get_resource_by_name(name)

    def get_resource(self, id: int) -> Optional[dict]:
        """Get resource by ID."""
        with self._reader() as conn:
            cursor = conn.execute("SELECT * FROM resources WHERE id = ?", (id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_resource_by_name(self, name: str) -> Optional[dict]:
        """Get resource by name."""
        with self._reader() as conn:
            cursor = conn.execute("SELECT * FROM resources WHERE name = ?", (name,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_resources(
        self,
        resource_type: Optional[str] = None,
        enabled: Optional[bool] = None,
        inherit_default: Optional[bool] = None,
    ) -> list[dict]:
        """List resources with optional filters.

        Args:
            resource_type: Filter by type.
            enabled: Filter by enabled status.
            inherit_default: Filter by inherit_default flag.

        Returns:
            List of resource dicts ordered by priority, then name.
        """
        with self._reader() as conn:
            conditions = ["1=1"]
            params: list[Any] = []

            if resource_type:
                conditions.append("resource_type = ?")
                params.append(resource_type)
            if enabled is not None:
                conditions.append("enabled = ?")
                params.append(enabled)
            if inherit_default is not None:
                conditions.append("inherit_default = ?")
                params.append(inherit_default)

            cursor = conn.execute(
                f"""
                SELECT * FROM resources
                WHERE {' AND '.join(conditions)}
                ORDER BY priority, name
                """,
                params,
            )
            return [dict(row) for row in cursor.fetchall()]

    _RESOURCE_UPDATE_COLS = frozenset({
        "name", "resource_type", "file_path", "injection_position",
        "enabled", "inherit_default", "priority"
    })

    def update_resource(self, id: int, **kwargs) -> bool:
        """Update resource fields.

        Args:
            id: Resource ID.
            **kwargs: Fields to update (name, resource_type, file_path,
                     injection_position, enabled, inherit_default, priority).

        Returns:
            True if updated, False if not found.
        """
        invalid_cols = set(kwargs.keys()) - self._RESOURCE_UPDATE_COLS - {"updated_at"}
        if invalid_cols:
            raise ValueError(f"Invalid columns for resource update: {invalid_cols}")

        if not kwargs:
            return False

        kwargs["updated_at"] = datetime.utcnow().isoformat()

        with self._writer() as conn:
            set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
            cursor = conn.execute(
                f"UPDATE resources SET {set_clause} WHERE id = ?",
                (*kwargs.values(), id),
            )
            return cursor.rowcount > 0

    def delete_resource(self, id: int) -> bool:
        """Delete a resource.

        Args:
            id: Resource ID.

        Returns:
            True if deleted, False if not found.
        """
        with self._writer() as conn:
            cursor = conn.execute("DELETE FROM resources WHERE id = ?", (id,))
            return cursor.rowcount > 0

    def delete_resource_by_name(self, name: str) -> bool:
        """Delete a resource by name.

        Args:
            name: Resource name.

        Returns:
            True if deleted, False if not found.
        """
        with self._writer() as conn:
            cursor = conn.execute("DELETE FROM resources WHERE name = ?", (name,))
            return cursor.rowcount > 0

    # ========== Loop Resources (per-loop) ==========

    def create_loop_resource(
        self,
        loop_name: str,
        resource_type: str,
        name: str,
        injection_position: str,
        source_type: str,
        source_path: Optional[str] = None,
        source_loop: Optional[str] = None,
        source_resource_id: Optional[int] = None,
        inline_content: Optional[str] = None,
        enabled: bool = True,
        priority: int = 0,
    ) -> dict:
        """Create a loop-specific resource entry.

        Args:
            loop_name: Name of the loop this resource belongs to.
            resource_type: Type of resource (loop_template, design_doc, guardrails, custom).
            name: Display name for the resource.
            injection_position: Where to inject in prompt (template_body, after_design_doc, etc).
            source_type: How to load content (system, project_file, loop_ref, project_resource, inline).
            source_path: For 'project_file': path relative to project.
            source_loop: For 'loop_ref': source loop name.
            source_resource_id: For 'loop_ref' or 'project_resource': source resource ID.
            inline_content: For 'inline': actual content.
            enabled: Whether the resource is active.
            priority: Ordering priority (lower = earlier).

        Returns:
            The created loop resource dict.
        """
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            conn.execute(
                """
                INSERT INTO loop_resources
                (loop_name, resource_type, name, injection_position, source_type,
                 source_path, source_loop, source_resource_id, inline_content,
                 enabled, priority, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    loop_name, resource_type, name, injection_position, source_type,
                    source_path, source_loop, source_resource_id, inline_content,
                    enabled, priority, now, now,
                ),
            )
        return self.get_loop_resource_by_name(loop_name, resource_type, name)

    def get_loop_resource(self, id: int) -> Optional[dict]:
        """Get loop resource by ID."""
        with self._reader() as conn:
            cursor = conn.execute("SELECT * FROM loop_resources WHERE id = ?", (id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_loop_resource_by_name(
        self, loop_name: str, resource_type: str, name: str
    ) -> Optional[dict]:
        """Get loop resource by loop name, type, and resource name."""
        with self._reader() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM loop_resources
                WHERE loop_name = ? AND resource_type = ? AND name = ?
                """,
                (loop_name, resource_type, name),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_loop_resources(
        self,
        loop_name: Optional[str] = None,
        resource_type: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> list[dict]:
        """List loop resources with optional filters.

        Args:
            loop_name: Filter by loop name.
            resource_type: Filter by type.
            enabled: Filter by enabled status.

        Returns:
            List of loop resource dicts ordered by priority, then name.
        """
        with self._reader() as conn:
            conditions = ["1=1"]
            params: list[Any] = []

            if loop_name:
                conditions.append("loop_name = ?")
                params.append(loop_name)
            if resource_type:
                conditions.append("resource_type = ?")
                params.append(resource_type)
            if enabled is not None:
                conditions.append("enabled = ?")
                params.append(enabled)

            cursor = conn.execute(
                f"""
                SELECT * FROM loop_resources
                WHERE {' AND '.join(conditions)}
                ORDER BY priority, name
                """,
                params,
            )
            return [dict(row) for row in cursor.fetchall()]

    _LOOP_RESOURCE_UPDATE_COLS = frozenset({
        "name", "resource_type", "injection_position", "source_type",
        "source_path", "source_loop", "source_resource_id", "inline_content",
        "enabled", "priority",
    })

    def update_loop_resource(self, id: int, **kwargs) -> bool:
        """Update loop resource fields.

        Args:
            id: Loop resource ID.
            **kwargs: Fields to update.

        Returns:
            True if updated, False if not found.
        """
        invalid_cols = set(kwargs.keys()) - self._LOOP_RESOURCE_UPDATE_COLS - {"updated_at"}
        if invalid_cols:
            raise ValueError(f"Invalid columns for loop resource update: {invalid_cols}")

        if not kwargs:
            return False

        kwargs["updated_at"] = datetime.utcnow().isoformat()

        with self._writer() as conn:
            set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
            cursor = conn.execute(
                f"UPDATE loop_resources SET {set_clause} WHERE id = ?",
                (*kwargs.values(), id),
            )
            return cursor.rowcount > 0

    def delete_loop_resource(self, id: int) -> bool:
        """Delete a loop resource.

        Args:
            id: Loop resource ID.

        Returns:
            True if deleted, False if not found.
        """
        with self._writer() as conn:
            cursor = conn.execute("DELETE FROM loop_resources WHERE id = ?", (id,))
            return cursor.rowcount > 0

    def delete_loop_resources_for_loop(self, loop_name: str) -> int:
        """Delete all resources for a loop.

        Args:
            loop_name: Loop name.

        Returns:
            Number of resources deleted.
        """
        with self._writer() as conn:
            cursor = conn.execute(
                "DELETE FROM loop_resources WHERE loop_name = ?", (loop_name,)
            )
            return cursor.rowcount

    # ========== Guardrails ==========

    def create_guardrail(
        self,
        category: str,
        filename: str,
        source: str,
        file_path: str,
        file_mtime: Optional[float] = None,
        file_size: Optional[int] = None,
        enabled: bool = True,
        loops: Optional[list[str]] = None,
        modes: Optional[list[str]] = None,
        position: str = "after_design_doc",
    ) -> dict:
        """Create a guardrail metadata entry."""
        with self._writer() as conn:
            conn.execute(
                """
                INSERT INTO guardrails
                (category, filename, source, file_path, file_mtime, file_size,
                 enabled, loops, modes, position)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    category, filename, source, file_path, file_mtime, file_size,
                    enabled,
                    json.dumps(loops) if loops else None,
                    json.dumps(modes) if modes else None,
                    position,
                ),
            )
            return self.get_guardrail_by_filename(category, filename)

    def get_guardrail(self, id: int) -> Optional[dict]:
        """Get guardrail by ID."""
        with self._reader() as conn:
            cursor = conn.execute("SELECT * FROM guardrails WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result.get("loops"):
                    result["loops"] = json.loads(result["loops"])
                if result.get("modes"):
                    result["modes"] = json.loads(result["modes"])
                return result
            return None

    def get_guardrail_by_filename(self, category: str, filename: str) -> Optional[dict]:
        """Get guardrail by category and filename."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM guardrails WHERE category = ? AND filename = ?",
                (category, filename),
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result.get("loops"):
                    result["loops"] = json.loads(result["loops"])
                if result.get("modes"):
                    result["modes"] = json.loads(result["modes"])
                return result
            return None

    def list_guardrails(
        self,
        category: Optional[str] = None,
        source: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> list[dict]:
        """List guardrails with optional filters."""
        with self._reader() as conn:
            conditions = ["1=1"]
            params: list[Any] = []

            if category:
                conditions.append("category = ?")
                params.append(category)
            if source:
                conditions.append("source = ?")
                params.append(source)
            if enabled is not None:
                conditions.append("enabled = ?")
                params.append(enabled)

            cursor = conn.execute(
                f"""
                SELECT * FROM guardrails
                WHERE {' AND '.join(conditions)}
                ORDER BY position, category, filename
                """,
                params,
            )

            results = []
            for row in cursor.fetchall():
                result = dict(row)
                if result.get("loops"):
                    result["loops"] = json.loads(result["loops"])
                if result.get("modes"):
                    result["modes"] = json.loads(result["modes"])
                results.append(result)
            return results

    # ========== Logs ==========

    def add_log(
        self,
        level: str,
        message: str,
        run_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> int:
        """Add an execution log entry."""
        with self._writer() as conn:
            cursor = conn.execute(
                """
                INSERT INTO logs (run_id, level, message, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, level, message, json.dumps(metadata) if metadata else None),
            )
            return cursor.lastrowid

    def get_logs(
        self,
        run_id: Optional[str] = None,
        level: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Get logs with optional filters."""
        with self._reader() as conn:
            conditions = ["1=1"]
            params: list[Any] = []

            if run_id:
                conditions.append("run_id = ?")
                params.append(run_id)
            if level:
                conditions.append("level = ?")
                params.append(level)

            cursor = conn.execute(
                f"""
                SELECT * FROM logs
                WHERE {' AND '.join(conditions)}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            )

            results = []
            for row in cursor.fetchall():
                result = dict(row)
                if result.get("metadata"):
                    result["metadata"] = json.loads(result["metadata"])
                results.append(result)
            return results

    # ========== Checkpoints ==========

    def save_checkpoint(
        self,
        run_id: str,
        loop_name: str,
        iteration: int,
        status: str,
        data: Optional[dict] = None,
    ) -> None:
        """Save a checkpoint."""
        with self._writer() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints (run_id, loop_name, iteration, status, data, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id, loop_name, iteration, status,
                    json.dumps(data) if data else None,
                    datetime.utcnow().isoformat(),
                ),
            )

    def get_latest_checkpoint(self, loop_name: str) -> Optional[dict]:
        """Get the most recent checkpoint for a loop."""
        with self._reader() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM checkpoints
                WHERE loop_name = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (loop_name,),
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result.get("data"):
                    result["data"] = json.loads(result["data"])
                return result
            return None

    # ========== Loop Types ==========

    def _seed_defaults(self, conn: sqlite3.Connection) -> None:
        """Seed default loop types, requirements, and import formats.

        Called during migration to populate tables with defaults.
        Only inserts if tables are empty.
        """
        from pathlib import Path

        # Check if loop_types already seeded
        cursor = conn.execute("SELECT COUNT(*) FROM loop_types")
        if cursor.fetchone()[0] > 0:
            return

        now = datetime.utcnow().isoformat()

        # Seed loop_types
        loop_types = [
            ("consumer", "Implementation Loop", "Processes work items one by one"),
            ("generator", "Planning Loop", "Generates work items from requirements"),
            ("hybrid", "Hybrid Loop", "Both generates and implements work items"),
        ]
        for lt_id, label, description in loop_types:
            conn.execute(
                "INSERT INTO loop_types (id, label, description, created_at) VALUES (?, ?, ?, ?)",
                (lt_id, label, description, now),
            )

        # Seed loop_type_requirements
        requirements = [
            # Consumer loop requirements
            ("consumer", "loop_template", "recommended", "Loop Template", "Base prompt instructions", "resource", '{"resource_type": "loop_template"}', True, 1),
            ("consumer", "design_doc", "recommended", "Design Document", "Project design and requirements", "resource", '{"resource_type": "design_doc"}', False, 2),
            ("consumer", "work_items", "required", "Work Items", "Items to process", "items_count", '{"min": 1}', False, 3),
            ("consumer", "guardrails", "recommended", "Guardrails", "Quality rules and constraints", "resource", '{"resource_type": "guardrails"}', True, 4),
            ("consumer", "auth", "required", "Authentication", "Claude API authentication", "auth_status", '{}', False, 5),
            # Generator loop requirements
            ("generator", "loop_template", "recommended", "Loop Template", "Base prompt instructions", "resource", '{"resource_type": "loop_template"}', True, 1),
            ("generator", "design_doc", "required", "Design Document", "Project design and requirements", "resource", '{"resource_type": "design_doc"}', False, 2),
            ("generator", "guardrails", "recommended", "Guardrails", "Quality rules and constraints", "resource", '{"resource_type": "guardrails"}', True, 3),
            ("generator", "auth", "required", "Authentication", "Claude API authentication", "auth_status", '{}', False, 4),
            # Hybrid loop requirements
            ("hybrid", "loop_template", "recommended", "Loop Template", "Base prompt instructions", "resource", '{"resource_type": "loop_template"}', True, 1),
            ("hybrid", "design_doc", "recommended", "Design Document", "Project design and requirements", "resource", '{"resource_type": "design_doc"}', False, 2),
            ("hybrid", "work_items", "recommended", "Work Items", "Items to process (optional for hybrid)", "items_count", '{"min": 0}', False, 3),
            ("hybrid", "guardrails", "recommended", "Guardrails", "Quality rules and constraints", "resource", '{"resource_type": "guardrails"}', True, 4),
            ("hybrid", "auth", "required", "Authentication", "Claude API authentication", "auth_status", '{}', False, 5),
        ]
        for r in requirements:
            conn.execute(
                """INSERT INTO loop_type_requirements
                   (loop_type, requirement_key, category, label, description, check_type, check_config, has_default, priority)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                r,
            )

        # Seed loop_type_defaults from template files
        template_dir = Path(__file__).parent.parent / "templates"

        defaults = [
            ("consumer", "loop_template", "default", template_dir / "loop_templates" / "consumer.md", "Default consumer loop template"),
            ("generator", "loop_template", "default", template_dir / "loop_templates" / "generator.md", "Default generator loop template"),
            ("hybrid", "loop_template", "default", template_dir / "loop_templates" / "hybrid.md", "Default hybrid loop template"),
            ("consumer", "guardrails", "default", template_dir / "guardrails" / "default.md", "Default quality guardrails"),
            ("generator", "guardrails", "default", template_dir / "guardrails" / "default.md", "Default quality guardrails"),
            ("hybrid", "guardrails", "default", template_dir / "guardrails" / "default.md", "Default quality guardrails"),
        ]

        for loop_type, resource_type, name, path, description in defaults:
            content = ""
            if path.exists():
                content = path.read_text()
            else:
                content = f"# Default {resource_type} for {loop_type}\n\n(Template file not found)"

            conn.execute(
                """INSERT INTO loop_type_defaults
                   (loop_type, resource_type, name, content, description, is_default, created_at)
                   VALUES (?, ?, ?, ?, ?, TRUE, ?)""",
                (loop_type, resource_type, name, content, description, now),
            )

        # Seed import_formats
        import_formats = [
            (
                "ralphx_standard",
                "RalphX Standard",
                "Standard RalphX work item format",
                '{"id": "id", "title": "title", "content": "content", "category": "category", "priority": "priority"}',
                None,
                False,
                '{"id": "ITEM-001", "title": "Sample item", "content": "Item description", "category": "feature", "priority": 1}',
            ),
            (
                "hank_prd",
                "HANK PRD Format",
                "Format used by hank-rcm PRD JSONL files",
                '{"id": "id", "content": "story", "priority": "priority", "status": "status"}',
                '{"FND": "foundation", "ELG": "eligibility", "ANS": "anesthesia", "AUT": "authorization", "DAT": "data", "INT": "integration", "DOC": "documentation", "TES": "testing"}',
                True,
                '{"id": "FND-001", "priority": 1, "story": "System has Patient model...", "acceptance_criteria": ["Criteria 1"], "status": "pending"}',
            ),
        ]
        for fmt in import_formats:
            conn.execute(
                """INSERT INTO import_formats
                   (id, label, description, field_mapping, category_mappings, id_prefix_to_category, sample_content, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (*fmt, now),
            )

    def get_loop_type(self, id: str) -> Optional[dict]:
        """Get a loop type by ID."""
        with self._reader() as conn:
            cursor = conn.execute("SELECT * FROM loop_types WHERE id = ?", (id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_loop_types(self) -> list[dict]:
        """List all loop types."""
        with self._reader() as conn:
            cursor = conn.execute("SELECT * FROM loop_types ORDER BY id")
            return [dict(row) for row in cursor.fetchall()]

    def get_loop_type_requirements(self, loop_type: str) -> list[dict]:
        """Get requirements for a loop type.

        Args:
            loop_type: The loop type ID (consumer, generator, hybrid).

        Returns:
            List of requirement dicts ordered by priority.
        """
        with self._reader() as conn:
            cursor = conn.execute(
                """SELECT * FROM loop_type_requirements
                   WHERE loop_type = ?
                   ORDER BY priority""",
                (loop_type,),
            )
            results = []
            for row in cursor.fetchall():
                item = dict(row)
                if item.get("check_config"):
                    item["check_config"] = json.loads(item["check_config"])
                results.append(item)
            return results

    def get_loop_type_default(
        self,
        loop_type: str,
        resource_type: str,
        name: str = "default",
    ) -> Optional[dict]:
        """Get a default template/resource for a loop type.

        Args:
            loop_type: The loop type ID.
            resource_type: The resource type (loop_template, guardrails).
            name: The default name (usually "default").

        Returns:
            Default dict with content, or None if not found.
        """
        with self._reader() as conn:
            cursor = conn.execute(
                """SELECT * FROM loop_type_defaults
                   WHERE loop_type = ? AND resource_type = ? AND name = ?""",
                (loop_type, resource_type, name),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_loop_type_defaults(
        self,
        loop_type: Optional[str] = None,
        resource_type: Optional[str] = None,
    ) -> list[dict]:
        """List default templates/resources with optional filters.

        Args:
            loop_type: Filter by loop type.
            resource_type: Filter by resource type.

        Returns:
            List of default dicts.
        """
        with self._reader() as conn:
            conditions = ["1=1"]
            params: list[Any] = []

            if loop_type:
                conditions.append("loop_type = ?")
                params.append(loop_type)
            if resource_type:
                conditions.append("resource_type = ?")
                params.append(resource_type)

            cursor = conn.execute(
                f"""SELECT * FROM loop_type_defaults
                    WHERE {' AND '.join(conditions)}
                    ORDER BY loop_type, resource_type, name""",
                params,
            )
            return [dict(row) for row in cursor.fetchall()]

    # ========== Import Formats ==========

    def get_import_format(self, id: str) -> Optional[dict]:
        """Get an import format by ID.

        Args:
            id: Format ID (e.g., 'ralphx_standard', 'hank_prd').

        Returns:
            Import format dict with parsed JSON fields.
        """
        with self._reader() as conn:
            cursor = conn.execute("SELECT * FROM import_formats WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                item = dict(row)
                if item.get("field_mapping"):
                    item["field_mapping"] = json.loads(item["field_mapping"])
                if item.get("category_mappings"):
                    item["category_mappings"] = json.loads(item["category_mappings"])
                return item
            return None

    def list_import_formats(self) -> list[dict]:
        """List all import formats.

        Returns:
            List of import format dicts.
        """
        with self._reader() as conn:
            cursor = conn.execute("SELECT * FROM import_formats ORDER BY label")
            results = []
            for row in cursor.fetchall():
                item = dict(row)
                if item.get("field_mapping"):
                    item["field_mapping"] = json.loads(item["field_mapping"])
                if item.get("category_mappings"):
                    item["category_mappings"] = json.loads(item["category_mappings"])
                results.append(item)
            return results

    def create_import_format(
        self,
        id: str,
        label: str,
        description: str,
        field_mapping: dict,
        category_mappings: Optional[dict] = None,
        id_prefix_to_category: bool = False,
        sample_content: Optional[str] = None,
    ) -> dict:
        """Create a custom import format.

        Args:
            id: Unique format ID.
            label: Display label.
            description: Format description.
            field_mapping: Dict mapping target fields to source fields.
            category_mappings: Optional dict mapping ID prefixes to categories.
            id_prefix_to_category: Whether to auto-detect category from ID prefix.
            sample_content: Optional example JSONL for UI preview.

        Returns:
            The created import format dict.
        """
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            conn.execute(
                """INSERT INTO import_formats
                   (id, label, description, field_mapping, category_mappings,
                    id_prefix_to_category, sample_content, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    id, label, description,
                    json.dumps(field_mapping),
                    json.dumps(category_mappings) if category_mappings else None,
                    id_prefix_to_category,
                    sample_content,
                    now,
                ),
            )
        return self.get_import_format(id)

    def import_jsonl(
        self,
        file_path: str,
        format_id: str,
        workflow_id: str,
        source_step_id: int,
        loop_name: Optional[str] = None,
        import_mode: str = "pending_only",
    ) -> dict:
        """Import work items from a JSONL file.

        Args:
            file_path: Path to the JSONL file.
            format_id: Import format ID to use.
            workflow_id: Parent workflow ID for imported items.
            source_step_id: Workflow step ID that is importing these items.
            loop_name: Optional loop name for input file tracking.
            import_mode: How to handle status during import:
                - "pending_only": Only import items with pending status (skip already processed)
                - "all": Import all items, preserving their status
                - "reset": Import all items, resetting status to pending/completed

        Returns:
            Dict with import results: {imported: int, skipped: int, already_processed: int, errors: list}.

        Raises:
            ValueError: If format not found or invalid import_mode.
            FileNotFoundError: If file doesn't exist.
        """
        from pathlib import Path as P

        # Validate import_mode
        valid_modes = ("pending_only", "all", "reset")
        if import_mode not in valid_modes:
            raise ValueError(f"Invalid import_mode '{import_mode}'. Must be one of: {valid_modes}")

        # Get format
        fmt = self.get_import_format(format_id)
        if not fmt:
            raise ValueError(f"Import format '{format_id}' not found")

        path = P(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        mapping = fmt["field_mapping"]
        category_map = fmt.get("category_mappings") or {}
        auto_category = fmt.get("id_prefix_to_category", False)

        imported = 0
        skipped = 0  # Duplicates (already in DB)
        already_processed = 0  # Skipped because status != pending
        errors = []

        # Status mapping from source format to RalphX
        # Source (hank-rcm style) -> RalphX status
        STATUS_MAP = {
            "pending": "completed",      # Ready for consumer loop to process
            "implemented": "processed",  # Already done - don't reprocess
            "dup": "duplicate",          # Duplicate of another item
            "external": "skipped",       # External system handles this
            "skipped": "skipped",        # Intentionally skipped
            # RalphX native statuses pass through
            "completed": "completed",
            "processed": "processed",
            "duplicate": "duplicate",
            "failed": "failed",
        }

        with open(path, "r") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as e:
                    errors.append(f"Line {line_num}: JSON parse error: {e}")
                    continue

                # Apply field mapping
                item = {}
                for target, source in mapping.items():
                    if "." in source:
                        # Handle nested paths like "metadata.acceptance_criteria"
                        parts = source.split(".")
                        val = raw
                        for part in parts:
                            if isinstance(val, dict):
                                val = val.get(part)
                            else:
                                val = None
                                break
                        item[target] = val
                    else:
                        item[target] = raw.get(source)

                # Get ID
                item_id = item.get("id")
                if not item_id:
                    errors.append(f"Line {line_num}: Missing 'id' field")
                    continue

                # Category detection
                category = item.get("category")
                if not category and auto_category and item_id and "-" in item_id:
                    prefix = item_id.split("-")[0]
                    category = category_map.get(prefix, prefix)
                item["category"] = category

                # Get source status and map to RalphX status
                source_status = item.get("status") or raw.get("status") or "pending"
                ralphx_status = STATUS_MAP.get(source_status, "completed")

                # Handle import mode
                if import_mode == "pending_only":
                    # Only import pending items
                    if source_status not in ("pending", None, ""):
                        already_processed += 1
                        continue
                    ralphx_status = "completed"  # Ready for processing
                elif import_mode == "reset":
                    # Import all, but reset to ready-for-processing state
                    ralphx_status = "completed"
                # else: import_mode == "all" - preserve status as mapped

                item["status"] = ralphx_status

                # Extract metadata fields not in mapping
                metadata = {}
                metadata_fields = [
                    "acceptance_criteria", "impl_notes", "passes", "notes",
                    "implemented_at", "dup_of", "external_product", "skip_reason"
                ]
                for field in metadata_fields:
                    if field in raw:
                        metadata[field] = raw[field]

                # Handle special status fields
                if source_status == "dup" and raw.get("dup_of"):
                    item["duplicate_of"] = raw["dup_of"]
                if source_status == "external" and raw.get("external_product"):
                    item["skip_reason"] = f"external:{raw['external_product']}"
                if source_status == "skipped" and raw.get("skip_reason"):
                    item["skip_reason"] = raw["skip_reason"]

                if metadata:
                    item["metadata"] = metadata

                # Check if item already exists
                existing = self.get_work_item(item_id)
                if existing:
                    skipped += 1
                    continue

                # Generate title from content if not provided
                # Truncate story text to first 100 chars for title
                content = item.get("content") or ""
                title = item.get("title")
                if not title and content:
                    title = content[:100] + ("..." if len(content) > 100 else "")

                # Create work item
                try:
                    self.create_work_item(
                        id=item_id,
                        workflow_id=workflow_id,
                        source_step_id=source_step_id,
                        content=content,
                        title=title,
                        priority=item.get("priority"),
                        category=item.get("category"),
                        metadata=item.get("metadata"),
                        status=item.get("status") or "completed",
                        duplicate_of=item.get("duplicate_of"),
                        skip_reason=item.get("skip_reason"),
                    )
                    imported += 1
                except Exception as e:
                    errors.append(f"Line {line_num}: Error creating item {item_id}: {e}")

        # Track input file if loop_name provided
        if loop_name:
            self.track_input_file(
                loop_name=loop_name,
                filename=path.name,
                file_type="jsonl",
                items_imported=imported,
            )

        return {
            "imported": imported,
            "skipped": skipped,  # Duplicates already in DB
            "already_processed": already_processed,  # Skipped due to non-pending status
            "errors": errors,
            "total_lines": imported + skipped + already_processed + len(errors),
        }

    def seed_defaults_if_empty(self) -> bool:
        """Seed default data if tables are empty.

        This is a public method that can be called manually to seed defaults
        after creating a new project database.

        Returns:
            True if defaults were seeded, False if already populated.
        """
        with self._writer() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM loop_types")
            if cursor.fetchone()[0] > 0:
                return False
            self._seed_defaults(conn)
            return True

    def _seed_workflow_templates(self, conn: sqlite3.Connection) -> None:
        """Seed default workflow templates.

        Called during migration to populate workflow_templates table.
        Only inserts if table is empty.
        """
        cursor = conn.execute("SELECT COUNT(*) FROM workflow_templates")
        if cursor.fetchone()[0] > 0:
            return

        now = datetime.utcnow().isoformat()

        # Build Product workflow template
        build_product_phases = json.dumps([
            {
                "number": 1,
                "name": "Planning",
                "type": "interactive",
                "description": "Describe what you want to build. Claude will help create a design document.",
                "outputs": ["design_doc", "guardrails"],
                "skippable": True,
                "skipCondition": "User already has design doc"
            },
            {
                "number": 2,
                "name": "Story Generation",
                "type": "autonomous",
                "loopType": "generator",
                "description": "Claude generates detailed user stories from the design document.",
                "inputs": ["design_doc", "guardrails"],
                "outputs": ["stories"],
                "skippable": True,
                "skipCondition": "User already has stories"
            },
            {
                "number": 3,
                "name": "Implementation",
                "type": "autonomous",
                "loopType": "consumer",
                "description": "Claude implements each story, committing code to git.",
                "inputs": ["stories", "design_doc", "guardrails"],
                "outputs": ["code"],
                "skippable": False
            }
        ])

        conn.execute(
            """INSERT INTO workflow_templates (id, name, description, phases, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                "build-product",
                "Build Product from Scratch",
                "Design, plan, and implement a new product or feature set",
                build_product_phases,
                now,
            ),
        )

        # From Design Doc workflow - skips planning, starts with story generation
        from_design_doc_phases = json.dumps([
            {
                "number": 1,
                "name": "Story Generation",
                "type": "autonomous",
                "loopType": "generator",
                "description": "Claude generates detailed user stories from your design document.",
                "inputs": ["design_doc"],
                "outputs": ["stories"],
                "skippable": False
            },
            {
                "number": 2,
                "name": "Implementation",
                "type": "autonomous",
                "loopType": "consumer",
                "description": "Claude implements each story, committing code to git.",
                "inputs": ["stories", "design_doc"],
                "outputs": ["code"],
                "skippable": False
            }
        ])

        conn.execute(
            """INSERT INTO workflow_templates (id, name, description, phases, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                "from-design-doc",
                "Build from Design Doc",
                "Generate stories and implement from an existing design document",
                from_design_doc_phases,
                now,
            ),
        )

        # From Stories workflow - implementation only
        from_stories_phases = json.dumps([
            {
                "number": 1,
                "name": "Implementation",
                "type": "autonomous",
                "loopType": "consumer",
                "description": "Claude implements each story, committing code to git.",
                "inputs": ["stories"],
                "outputs": ["code"],
                "skippable": False
            }
        ])

        conn.execute(
            """INSERT INTO workflow_templates (id, name, description, phases, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                "from-stories",
                "Implement from Stories",
                "Implement from an existing set of user stories",
                from_stories_phases,
                now,
            ),
        )

        # Planning Only workflow - just the interactive planning step
        planning_only_phases = json.dumps([
            {
                "number": 1,
                "name": "Planning",
                "type": "interactive",
                "description": "Collaborate with Claude to create a comprehensive design document.",
                "outputs": ["design_doc", "guardrails"],
                "skippable": False
            }
        ])

        conn.execute(
            """INSERT INTO workflow_templates (id, name, description, phases, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                "planning-only",
                "Planning Session",
                "Create a design document through interactive planning with Claude",
                planning_only_phases,
                now,
            ),
        )

    def seed_workflow_templates_if_empty(self) -> bool:
        """Seed workflow templates if empty.

        Returns:
            True if templates were seeded, False if already populated.
        """
        with self._writer() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM workflow_templates")
            if cursor.fetchone()[0] > 0:
                return False
            self._seed_workflow_templates(conn)
            return True

    # ========== Workflow Templates ==========

    def get_workflow_template(self, id: str) -> Optional[dict]:
        """Get a workflow template by ID."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM workflow_templates WHERE id = ?", (id,)
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result.get("phases"):
                    result["phases"] = json.loads(result["phases"])
                return result
            return None

    def list_workflow_templates(self) -> list[dict]:
        """List all workflow templates."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM workflow_templates ORDER BY name"
            )
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                if result.get("phases"):
                    result["phases"] = json.loads(result["phases"])
                results.append(result)
            return results

    # ========== Workflows ==========

    def create_workflow(
        self,
        id: str,
        name: str,
        template_id: Optional[str] = None,
        status: str = "draft",
    ) -> dict:
        """Create a new workflow instance.

        Args:
            id: Unique workflow identifier.
            name: User-facing workflow name.
            template_id: Optional template ID this workflow is based on.
            status: Initial status (default: draft).

        Returns:
            The created workflow dict.
        """
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            conn.execute(
                """INSERT INTO workflows
                   (id, template_id, name, status, current_step, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 1, ?, ?)""",
                (id, template_id, name, status, now, now),
            )
        return self.get_workflow(id)

    def get_workflow(self, id: str) -> Optional[dict]:
        """Get workflow by ID."""
        with self._reader() as conn:
            cursor = conn.execute("SELECT * FROM workflows WHERE id = ?", (id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_workflows(
        self,
        status: Optional[str] = None,
        include_archived: bool = False,
        archived_only: bool = False,
    ) -> list[dict]:
        """List workflows with optional filters.

        Args:
            status: Filter by workflow status.
            include_archived: If True, include archived workflows.
            archived_only: If True, only return archived workflows.
        """
        with self._reader() as conn:
            conditions = ["1=1"]
            params: list[Any] = []

            if status:
                conditions.append("status = ?")
                params.append(status)

            # Handle archived filtering
            if archived_only:
                conditions.append("archived_at IS NOT NULL")
            elif not include_archived:
                conditions.append("archived_at IS NULL")

            cursor = conn.execute(
                f"""SELECT * FROM workflows
                    WHERE {' AND '.join(conditions)}
                    ORDER BY created_at DESC""",
                params,
            )
            return [dict(row) for row in cursor.fetchall()]

    def archive_workflow(self, id: str) -> bool:
        """Archive a workflow (soft delete).

        Args:
            id: Workflow ID.

        Returns:
            True if workflow was archived, False if not found.
        """
        with self._writer() as conn:
            cursor = conn.execute(
                "UPDATE workflows SET archived_at = CURRENT_TIMESTAMP WHERE id = ? AND archived_at IS NULL",
                (id,),
            )
            return cursor.rowcount > 0

    def restore_workflow(self, id: str) -> bool:
        """Restore an archived workflow.

        Args:
            id: Workflow ID.

        Returns:
            True if workflow was restored, False if not found or not archived.
        """
        with self._writer() as conn:
            cursor = conn.execute(
                "UPDATE workflows SET archived_at = NULL WHERE id = ? AND archived_at IS NOT NULL",
                (id,),
            )
            return cursor.rowcount > 0

    def is_workflow_archived(self, id: str) -> Optional[bool]:
        """Check if a workflow is archived.

        Args:
            id: Workflow ID.

        Returns:
            True if archived, False if active, None if not found.
        """
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT archived_at FROM workflows WHERE id = ?",
                (id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return row["archived_at"] is not None

    _WORKFLOW_UPDATE_COLS = frozenset({
        "name", "status", "current_step"
    })

    def update_workflow(self, id: str, **kwargs) -> bool:
        """Update workflow fields."""
        invalid_cols = set(kwargs.keys()) - self._WORKFLOW_UPDATE_COLS - {"updated_at"}
        if invalid_cols:
            raise ValueError(f"Invalid columns for workflow update: {invalid_cols}")

        if not kwargs:
            return False

        kwargs["updated_at"] = datetime.utcnow().isoformat()

        with self._writer() as conn:
            set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
            cursor = conn.execute(
                f"UPDATE workflows SET {set_clause} WHERE id = ?",
                (*kwargs.values(), id),
            )
            return cursor.rowcount > 0

    def delete_workflow(self, id: str) -> bool:
        """Delete a workflow and its steps/resources/sessions (cascade).

        Deletes in order:
        1. workflow_step_resources (step-level overrides)
        2. workflow_resources (workflow-level resources)
        3. workflow_steps
        4. workflow (the main record)
        """
        with self._writer() as conn:
            # Get all step IDs for this workflow to delete their resources
            cursor = conn.execute(
                "SELECT id FROM workflow_steps WHERE workflow_id = ?", (id,)
            )
            step_ids = [row[0] for row in cursor.fetchall()]

            # Delete step resources for all steps in this workflow
            if step_ids:
                placeholders = ",".join("?" * len(step_ids))
                conn.execute(
                    f"DELETE FROM workflow_step_resources WHERE step_id IN ({placeholders})",
                    step_ids,
                )

            # Delete workflow resources
            conn.execute(
                "DELETE FROM workflow_resources WHERE workflow_id = ?", (id,)
            )

            # Delete workflow steps
            conn.execute(
                "DELETE FROM workflow_steps WHERE workflow_id = ?", (id,)
            )

            # Delete the workflow itself
            cursor = conn.execute("DELETE FROM workflows WHERE id = ?", (id,))
            return cursor.rowcount > 0

    # ========== Workflow Resources ==========

    def create_workflow_resource(
        self,
        workflow_id: str,
        resource_type: str,
        name: str,
        content: Optional[str] = None,
        file_path: Optional[str] = None,
        source: str = "manual",
        source_id: Optional[int] = None,
        enabled: bool = True,
    ) -> dict:
        """Create a workflow-scoped resource.

        Args:
            workflow_id: Parent workflow ID.
            resource_type: Type of resource ('design_doc', 'guardrail', 'input_file', 'prompt').
            name: Resource name.
            content: Inline content (for small resources).
            file_path: Path to file (for file-based resources).
            source: How resource was created ('planning_step', 'manual', 'imported', 'inherited').
            source_id: Reference to project_resources if inherited.
            enabled: Whether resource is active.

        Returns:
            The created resource dict.
        """
        with self._writer() as conn:
            cursor = conn.execute(
                """INSERT INTO workflow_resources
                   (workflow_id, resource_type, name, content, file_path, source, source_id, enabled)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (workflow_id, resource_type, name, content, file_path, source, source_id, enabled),
            )
            return self.get_workflow_resource(cursor.lastrowid)

    def get_workflow_resource(self, id: int) -> Optional[dict]:
        """Get workflow resource by ID."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM workflow_resources WHERE id = ?", (id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_workflow_resources(
        self,
        workflow_id: str,
        resource_type: Optional[str] = None,
        enabled_only: bool = False,
    ) -> list[dict]:
        """List resources for a workflow.

        Args:
            workflow_id: Parent workflow ID.
            resource_type: Filter by type (optional).
            enabled_only: Only return enabled resources.

        Returns:
            List of resource dicts.
        """
        with self._reader() as conn:
            query = "SELECT * FROM workflow_resources WHERE workflow_id = ?"
            params: list = [workflow_id]

            if resource_type:
                query += " AND resource_type = ?"
                params.append(resource_type)

            if enabled_only:
                query += " AND enabled = TRUE"

            query += " ORDER BY created_at DESC"

            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def update_workflow_resource(
        self,
        id: int,
        name: Optional[str] = None,
        content: Optional[str] = None,
        file_path: Optional[str] = None,
        enabled: Optional[bool] = None,
        expected_updated_at: Optional[str] = None,
    ) -> dict:
        """Update a workflow resource with optimistic locking and versioning.

        Args:
            id: Resource ID to update.
            name: New name (optional).
            content: New content (optional).
            file_path: New file path (optional).
            enabled: New enabled state (optional).
            expected_updated_at: If provided, verifies the resource hasn't been
                modified since this timestamp. Returns dict with 'conflict' key
                if timestamps don't match.

        Returns:
            Updated resource dict, or {'conflict': True, 'current': <resource>}
            if optimistic locking fails.
        """
        updates = []
        params: list[Any] = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if content is not None:
            updates.append("content = ?")
            params.append(content)
        if file_path is not None:
            updates.append("file_path = ?")
            params.append(file_path)
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(enabled)

        if not updates:
            return self.get_workflow_resource(id) or {}

        with self._writer() as conn:
            # Get current state for versioning and optimistic lock check
            cursor = conn.execute(
                "SELECT * FROM workflow_resources WHERE id = ?", (id,)
            )
            current = cursor.fetchone()
            if not current:
                return {}

            current_dict = dict(current)

            # Optimistic locking check
            if expected_updated_at is not None:
                if current_dict.get("updated_at") != expected_updated_at:
                    return {"conflict": True, "current": current_dict}

            # Check if content or name is actually changing
            new_content = content if content is not None else current_dict.get("content")
            new_name = name if name is not None else current_dict.get("name")
            content_changed = new_content != current_dict.get("content")
            name_changed = new_name != current_dict.get("name")

            # Only create version if content or name actually changed
            if content_changed or name_changed:
                # Get next version number
                cursor = conn.execute(
                    """SELECT COALESCE(MAX(version_number), 0) + 1
                       FROM workflow_resource_versions
                       WHERE workflow_resource_id = ?""",
                    (id,),
                )
                next_version = cursor.fetchone()[0]

                # Create version snapshot of current state BEFORE updating
                conn.execute(
                    """INSERT INTO workflow_resource_versions
                       (workflow_resource_id, version_number, content, name)
                       VALUES (?, ?, ?, ?)""",
                    (id, next_version, current_dict.get("content"), current_dict.get("name")),
                )

            # Now update the resource with high-precision timestamp
            # Using Python datetime for microsecond precision (CURRENT_TIMESTAMP is second-only)
            from datetime import datetime
            high_precision_ts = datetime.utcnow().isoformat(timespec="microseconds")
            updates.append("updated_at = ?")
            params.append(high_precision_ts)
            params.append(id)

            conn.execute(
                f"UPDATE workflow_resources SET {', '.join(updates)} WHERE id = ?",
                params,
            )

        # Cleanup old versions (outside transaction - failure doesn't roll back edit)
        try:
            self._cleanup_old_versions(id, keep_count=50)
        except Exception:
            pass  # Cleanup failure shouldn't affect the update

        return self.get_workflow_resource(id) or {}

    def _cleanup_old_versions(self, resource_id: int, keep_count: int = 50) -> int:
        """Delete old versions beyond the retention limit.

        Args:
            resource_id: Workflow resource ID.
            keep_count: Number of recent versions to keep.

        Returns:
            Number of versions deleted.
        """
        with self._writer() as conn:
            cursor = conn.execute(
                """DELETE FROM workflow_resource_versions
                   WHERE workflow_resource_id = ?
                     AND id NOT IN (
                       SELECT id FROM workflow_resource_versions
                       WHERE workflow_resource_id = ?
                       ORDER BY version_number DESC
                       LIMIT ?
                     )""",
                (resource_id, resource_id, keep_count),
            )
            return cursor.rowcount

    def list_resource_versions(
        self,
        resource_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """List version history for a workflow resource.

        Args:
            resource_id: Workflow resource ID.
            limit: Max versions to return.
            offset: Number of versions to skip.

        Returns:
            Tuple of (list of version dicts, total count).
        """
        with self._reader() as conn:
            # Get total count
            cursor = conn.execute(
                "SELECT COUNT(*) FROM workflow_resource_versions WHERE workflow_resource_id = ?",
                (resource_id,),
            )
            total = cursor.fetchone()[0]

            # Get paginated versions (newest first)
            cursor = conn.execute(
                """SELECT * FROM workflow_resource_versions
                   WHERE workflow_resource_id = ?
                   ORDER BY version_number DESC
                   LIMIT ? OFFSET ?""",
                (resource_id, limit, offset),
            )
            versions = [dict(row) for row in cursor.fetchall()]

            return versions, total

    def get_resource_version(self, version_id: int) -> Optional[dict]:
        """Get a specific version by ID.

        Args:
            version_id: Version record ID.

        Returns:
            Version dict or None if not found.
        """
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM workflow_resource_versions WHERE id = ?",
                (version_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def restore_resource_version(self, resource_id: int, version_id: int) -> Optional[dict]:
        """Restore a workflow resource to a previous version.

        This creates a new version snapshot of the current state, then
        overwrites the resource with the old version's content and name.

        Args:
            resource_id: Workflow resource ID.
            version_id: Version ID to restore.

        Returns:
            Updated resource dict, or None if not found.
        """
        with self._writer() as conn:
            # Get the version to restore
            cursor = conn.execute(
                "SELECT * FROM workflow_resource_versions WHERE id = ? AND workflow_resource_id = ?",
                (version_id, resource_id),
            )
            version = cursor.fetchone()
            if not version:
                return None

            version_dict = dict(version)

            # Get current resource state
            cursor = conn.execute(
                "SELECT * FROM workflow_resources WHERE id = ?",
                (resource_id,),
            )
            current = cursor.fetchone()
            if not current:
                return None

            current_dict = dict(current)

            # Create version snapshot of current state BEFORE restoring
            cursor = conn.execute(
                """SELECT COALESCE(MAX(version_number), 0) + 1
                   FROM workflow_resource_versions
                   WHERE workflow_resource_id = ?""",
                (resource_id,),
            )
            next_version = cursor.fetchone()[0]

            conn.execute(
                """INSERT INTO workflow_resource_versions
                   (workflow_resource_id, version_number, content, name)
                   VALUES (?, ?, ?, ?)""",
                (resource_id, next_version, current_dict.get("content"), current_dict.get("name")),
            )

            # Restore the old version's content and name
            # Using Python datetime for microsecond precision (CURRENT_TIMESTAMP is second-only)
            from datetime import datetime
            high_precision_ts = datetime.utcnow().isoformat(timespec="microseconds")
            conn.execute(
                """UPDATE workflow_resources
                   SET content = ?, name = ?, updated_at = ?
                   WHERE id = ?""",
                (version_dict.get("content"), version_dict.get("name"), high_precision_ts, resource_id),
            )

        return self.get_workflow_resource(resource_id)

    def delete_workflow_resource(self, id: int) -> bool:
        """Delete a workflow resource and any step-level overrides referencing it."""
        with self._writer() as conn:
            # Delete step resources that reference this workflow resource
            conn.execute(
                "DELETE FROM workflow_step_resources WHERE workflow_resource_id = ?",
                (id,),
            )
            # Delete the workflow resource
            cursor = conn.execute("DELETE FROM workflow_resources WHERE id = ?", (id,))
            return cursor.rowcount > 0

    # ========== Step Resources (Per-Step Overrides) ==========

    def create_step_resource(
        self,
        step_id: int,
        mode: str,
        workflow_resource_id: Optional[int] = None,
        resource_type: Optional[str] = None,
        name: Optional[str] = None,
        content: Optional[str] = None,
        file_path: Optional[str] = None,
        enabled: bool = True,
        priority: int = 0,
    ) -> dict:
        """Create a step-level resource configuration.

        Args:
            step_id: Parent workflow step ID.
            mode: How to handle this resource:
                  - 'override': Replace workflow resource with step-specific content
                  - 'disable': Don't inject this workflow resource for this step
                  - 'add': Step-specific resource not in workflow (always injected)
            workflow_resource_id: For 'override'/'disable': which workflow resource to affect.
            resource_type: For 'add'/'override': type of resource.
            name: For 'add'/'override': resource name.
            content: Inline content.
            file_path: Path to file.
            enabled: Whether active.
            priority: Ordering priority.

        Returns:
            The created step resource dict.
        """
        if mode not in ('override', 'disable', 'add'):
            raise ValueError(f"Invalid mode: {mode}. Must be 'override', 'disable', or 'add'")

        if mode == 'disable' and not workflow_resource_id:
            raise ValueError("'disable' mode requires workflow_resource_id")
        if mode == 'override' and not name:
            raise ValueError("'override' mode requires name to match workflow resource")
        if mode == 'add' and (not name or not resource_type):
            raise ValueError("'add' mode requires name and resource_type")

        with self._writer() as conn:
            cursor = conn.execute(
                """INSERT INTO workflow_step_resources
                   (step_id, workflow_resource_id, resource_type, name, content, file_path,
                    mode, enabled, priority)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (step_id, workflow_resource_id, resource_type, name, content, file_path,
                 mode, enabled, priority),
            )
            return self.get_step_resource(cursor.lastrowid)

    def get_step_resource(self, id: int) -> Optional[dict]:
        """Get step resource by ID."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM workflow_step_resources WHERE id = ?", (id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_step_resources(self, step_id: int) -> list[dict]:
        """List all step resource configurations for a step.

        Args:
            step_id: Workflow step ID.

        Returns:
            List of step resource dicts.
        """
        with self._reader() as conn:
            cursor = conn.execute(
                """SELECT * FROM workflow_step_resources
                   WHERE step_id = ?
                   ORDER BY priority DESC, created_at ASC""",
                (step_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def update_step_resource(
        self,
        id: int,
        name: Optional[str] = None,
        content: Optional[str] = None,
        file_path: Optional[str] = None,
        enabled: Optional[bool] = None,
        priority: Optional[int] = None,
    ) -> Optional[dict]:
        """Update a step resource."""
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if content is not None:
            updates.append("content = ?")
            params.append(content)
        if file_path is not None:
            updates.append("file_path = ?")
            params.append(file_path)
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(enabled)
        if priority is not None:
            updates.append("priority = ?")
            params.append(priority)

        if not updates:
            return self.get_step_resource(id)

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(id)

        with self._writer() as conn:
            conn.execute(
                f"UPDATE workflow_step_resources SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            return self.get_step_resource(id)

    def delete_step_resource(self, id: int) -> bool:
        """Delete a step resource."""
        with self._writer() as conn:
            cursor = conn.execute("DELETE FROM workflow_step_resources WHERE id = ?", (id,))
            return cursor.rowcount > 0

    def get_step_resource_by_workflow_resource(
        self, step_id: int, workflow_resource_id: int
    ) -> Optional[dict]:
        """Get step resource for a specific workflow resource (for disable/override lookup).

        Args:
            step_id: Workflow step ID.
            workflow_resource_id: Workflow resource ID.

        Returns:
            Step resource dict if found, None otherwise.
        """
        with self._reader() as conn:
            cursor = conn.execute(
                """SELECT * FROM workflow_step_resources
                   WHERE step_id = ? AND workflow_resource_id = ?""",
                (step_id, workflow_resource_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_effective_resources_for_step(
        self, step_id: int, workflow_id: str
    ) -> list[dict]:
        """Get the effective resources for a step after merging workflow and step configs.

        This implements the merge algorithm:
        1. Start with all enabled workflow resources
        2. Apply step resource configurations:
           - 'disable': Remove the workflow resource
           - 'override': Replace workflow resource with step version
           - 'add': Add step-specific resource

        Args:
            step_id: Workflow step ID.
            workflow_id: Parent workflow ID.

        Returns:
            List of effective resource dicts to inject into the loop.
        """
        # 1. Get all enabled workflow resources
        workflow_resources = self.list_workflow_resources(workflow_id, enabled_only=True)

        # 2. Get step resource configurations
        step_resources = self.list_step_resources(step_id)

        # 3. Build final resource set (keyed by name for override/add lookup)
        final: dict[str, dict] = {}
        wr_id_to_name: dict[int, str] = {}  # Map workflow_resource_id -> name for disable mode

        for wr in workflow_resources:
            final[wr['name']] = {**wr, 'source': 'workflow'}
            wr_id_to_name[wr['id']] = wr['name']

        for sr in step_resources:
            if not sr.get('enabled', True):
                continue

            mode = sr['mode']

            if mode == 'disable':
                # Look up workflow resource by ID, then remove by name
                wr_id = sr.get('workflow_resource_id')
                if wr_id:
                    wr_name = wr_id_to_name.get(wr_id)
                    if wr_name:
                        final.pop(wr_name, None)

            elif mode == 'override':
                # Replace workflow resource with step version (matched by name)
                sr_name = sr.get('name')
                if sr_name and sr_name in final:
                    final[sr_name] = {
                        'id': sr['id'],
                        'resource_type': sr.get('resource_type') or final[sr_name]['resource_type'],
                        'name': sr_name,
                        'content': sr.get('content'),
                        'file_path': sr.get('file_path'),
                        'source': 'step_override',
                        'priority': sr.get('priority', 0),
                    }

            elif mode == 'add':
                # Add step-specific resource
                sr_name = sr.get('name')
                if sr_name:
                    final[sr_name] = {
                        'id': sr['id'],
                        'resource_type': sr.get('resource_type'),
                        'name': sr_name,
                        'content': sr.get('content'),
                        'file_path': sr.get('file_path'),
                        'source': 'step_add',
                        'priority': sr.get('priority', 0),
                    }

        return list(final.values())

    # ========== Project Resources (Shared Library) ==========

    def create_project_resource(
        self,
        resource_type: str,
        name: str,
        content: Optional[str] = None,
        file_path: Optional[str] = None,
        auto_inherit: bool = False,
    ) -> dict:
        """Create a project-level shared resource.

        Args:
            resource_type: Type of resource ('guardrail', 'prompt_template', 'config').
            name: Resource name.
            content: Inline content.
            file_path: Path to file.
            auto_inherit: If True, new workflows automatically get this resource.

        Returns:
            The created resource dict.
        """
        with self._writer() as conn:
            cursor = conn.execute(
                """INSERT INTO project_resources
                   (resource_type, name, content, file_path, auto_inherit)
                   VALUES (?, ?, ?, ?, ?)""",
                (resource_type, name, content, file_path, auto_inherit),
            )
            return self.get_project_resource(cursor.lastrowid)

    def get_project_resource(self, id: int) -> Optional[dict]:
        """Get project resource by ID."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM project_resources WHERE id = ?", (id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_project_resources(
        self,
        resource_type: Optional[str] = None,
        auto_inherit_only: bool = False,
    ) -> list[dict]:
        """List project-level resources.

        Args:
            resource_type: Filter by type (optional).
            auto_inherit_only: Only return auto-inherit resources.

        Returns:
            List of resource dicts.
        """
        with self._reader() as conn:
            query = "SELECT * FROM project_resources WHERE 1=1"
            params: list = []

            if resource_type:
                query += " AND resource_type = ?"
                params.append(resource_type)

            if auto_inherit_only:
                query += " AND auto_inherit = TRUE"

            query += " ORDER BY created_at DESC"

            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def update_project_resource(
        self,
        id: int,
        name: Optional[str] = None,
        content: Optional[str] = None,
        file_path: Optional[str] = None,
        auto_inherit: Optional[bool] = None,
    ) -> Optional[dict]:
        """Update a project resource."""
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if content is not None:
            updates.append("content = ?")
            params.append(content)
        if file_path is not None:
            updates.append("file_path = ?")
            params.append(file_path)
        if auto_inherit is not None:
            updates.append("auto_inherit = ?")
            params.append(auto_inherit)

        if not updates:
            return self.get_project_resource(id)

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(id)

        with self._writer() as conn:
            conn.execute(
                f"UPDATE project_resources SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            return self.get_project_resource(id)

    def delete_project_resource(self, id: int) -> bool:
        """Delete a project resource."""
        with self._writer() as conn:
            cursor = conn.execute("DELETE FROM project_resources WHERE id = ?", (id,))
            return cursor.rowcount > 0

    def inherit_project_resources_to_workflow(self, workflow_id: str) -> list[dict]:
        """Copy all auto-inherit project resources to a workflow.

        Called when creating a new workflow to copy shared resources.

        Args:
            workflow_id: Target workflow ID.

        Returns:
            List of created workflow resources.
        """
        auto_inherit = self.list_project_resources(auto_inherit_only=True)
        created = []

        for pr in auto_inherit:
            wr = self.create_workflow_resource(
                workflow_id=workflow_id,
                resource_type=pr["resource_type"],
                name=pr["name"],
                content=pr.get("content"),
                file_path=pr.get("file_path"),
                source="inherited",
                source_id=pr["id"],
            )
            created.append(wr)

        return created

    # ========== Project Settings ==========

    def get_project_settings(self) -> dict:
        """Get project-level default settings.

        Returns a singleton settings row. Creates with defaults if not exists.

        Returns:
            Settings dict with keys:
            - auto_inherit_guardrails: bool
            - require_design_doc: bool
            - architecture_first_mode: bool
            - updated_at: timestamp
        """
        with self._reader() as conn:
            cursor = conn.execute("SELECT * FROM project_settings WHERE id = 1")
            row = cursor.fetchone()
            if row:
                return dict(row)

        # Create default settings if not exists
        with self._writer() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO project_settings (id, auto_inherit_guardrails, require_design_doc, architecture_first_mode)
                VALUES (1, TRUE, FALSE, FALSE)
            """)

        # Re-fetch after insert
        with self._reader() as conn:
            cursor = conn.execute("SELECT * FROM project_settings WHERE id = 1")
            row = cursor.fetchone()
            return dict(row) if row else {
                "id": 1,
                "auto_inherit_guardrails": True,
                "require_design_doc": False,
                "architecture_first_mode": False,
                "updated_at": None,
            }

    def update_project_settings(
        self,
        auto_inherit_guardrails: Optional[bool] = None,
        require_design_doc: Optional[bool] = None,
        architecture_first_mode: Optional[bool] = None,
    ) -> dict:
        """Update project-level default settings.

        Args:
            auto_inherit_guardrails: Auto-inherit shared guardrails to new workflows.
            require_design_doc: Require design document before implementation steps.
            architecture_first_mode: Enable architecture-first mode for new projects.

        Returns:
            Updated settings dict.
        """
        # Ensure settings row exists
        self.get_project_settings()

        updates = []
        params = []

        if auto_inherit_guardrails is not None:
            updates.append("auto_inherit_guardrails = ?")
            params.append(auto_inherit_guardrails)
        if require_design_doc is not None:
            updates.append("require_design_doc = ?")
            params.append(require_design_doc)
        if architecture_first_mode is not None:
            updates.append("architecture_first_mode = ?")
            params.append(architecture_first_mode)

        if not updates:
            return self.get_project_settings()

        updates.append("updated_at = CURRENT_TIMESTAMP")

        with self._writer() as conn:
            conn.execute(
                f"UPDATE project_settings SET {', '.join(updates)} WHERE id = 1",
                params,
            )

        return self.get_project_settings()

    # ========== Workflow Steps ==========

    def create_workflow_step(
        self,
        workflow_id: str,
        step_number: int,
        name: str,
        step_type: str,
        config: Optional[dict] = None,
        loop_name: Optional[str] = None,
        status: str = "pending",
    ) -> dict:
        """Create a workflow step.

        Args:
            workflow_id: Parent workflow ID.
            step_number: Step number (1-indexed).
            name: Step name (e.g., "Planning", "Implementation").
            step_type: 'interactive' or 'autonomous'.
            config: Optional step-specific configuration.
            loop_name: For autonomous steps, the linked loop name.
            status: Initial status (default: pending).

        Returns:
            The created step dict.
        """
        with self._writer() as conn:
            config_json = json.dumps(config) if config else None
            cursor = conn.execute(
                """INSERT INTO workflow_steps
                   (workflow_id, step_number, name, step_type, config, loop_name, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (workflow_id, step_number, name, step_type, config_json, loop_name, status),
            )
            return self.get_workflow_step(cursor.lastrowid)

    def create_workflow_step_atomic(
        self,
        workflow_id: str,
        name: str,
        step_type: str,
        config: Optional[dict] = None,
        loop_name: Optional[str] = None,
        status: str = "pending",
    ) -> dict:
        """Create a workflow step with auto-calculated step number.

        Calculates step_number inside the transaction to prevent race conditions
        when multiple requests try to add steps concurrently.

        Args:
            workflow_id: Parent workflow ID.
            name: Step name (e.g., "Planning", "Implementation").
            step_type: 'interactive' or 'autonomous'.
            config: Optional step-specific configuration.
            loop_name: For autonomous steps, the linked loop name.
            status: Initial status (default: pending).

        Returns:
            The created step dict.
        """
        with self._writer() as conn:
            # Calculate next step number inside transaction
            cursor = conn.execute(
                """SELECT COALESCE(MAX(step_number), 0) + 1 FROM workflow_steps
                   WHERE workflow_id = ?""",
                (workflow_id,),
            )
            next_step_number = cursor.fetchone()[0]

            config_json = json.dumps(config) if config else None
            cursor = conn.execute(
                """INSERT INTO workflow_steps
                   (workflow_id, step_number, name, step_type, config, loop_name, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (workflow_id, next_step_number, name, step_type, config_json, loop_name, status),
            )
            return self.get_workflow_step(cursor.lastrowid)

    def get_workflow_step(self, id: int) -> Optional[dict]:
        """Get workflow step by ID."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM workflow_steps WHERE id = ?", (id,)
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result.get("config"):
                    result["config"] = json.loads(result["config"])
                if result.get("artifacts"):
                    result["artifacts"] = json.loads(result["artifacts"])
                return result
            return None

    def get_workflow_step_by_number(
        self, workflow_id: str, step_number: int, include_archived: bool = False
    ) -> Optional[dict]:
        """Get workflow step by workflow ID and step number.

        Args:
            workflow_id: The workflow ID.
            step_number: The step number (1-based).
            include_archived: If True, may return archived steps. Default False.

        Returns:
            Step dictionary if found, None otherwise.
        """
        with self._reader() as conn:
            if include_archived:
                query = """SELECT * FROM workflow_steps
                           WHERE workflow_id = ? AND step_number = ?"""
            else:
                query = """SELECT * FROM workflow_steps
                           WHERE workflow_id = ? AND step_number = ? AND archived_at IS NULL"""
            cursor = conn.execute(query, (workflow_id, step_number))
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result.get("config"):
                    result["config"] = json.loads(result["config"])
                if result.get("artifacts"):
                    result["artifacts"] = json.loads(result["artifacts"])
                return result
            return None

    def list_workflow_steps(
        self, workflow_id: str, include_archived: bool = False
    ) -> list[dict]:
        """List all steps for a workflow.

        Args:
            workflow_id: The workflow ID.
            include_archived: If True, include archived steps. Default is False.

        Returns:
            List of step dictionaries, ordered by step_number.
        """
        with self._reader() as conn:
            if include_archived:
                query = """SELECT * FROM workflow_steps
                           WHERE workflow_id = ?
                           ORDER BY step_number"""
            else:
                query = """SELECT * FROM workflow_steps
                           WHERE workflow_id = ? AND archived_at IS NULL
                           ORDER BY step_number"""
            cursor = conn.execute(query, (workflow_id,))
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                if result.get("config"):
                    result["config"] = json.loads(result["config"])
                if result.get("artifacts"):
                    result["artifacts"] = json.loads(result["artifacts"])
                results.append(result)
            return results

    def list_archived_steps(self, workflow_id: str) -> list[dict]:
        """List all archived steps for a workflow (for trash/recycle bin view).

        Args:
            workflow_id: The workflow ID.

        Returns:
            List of archived step dictionaries, ordered by original step_number.
        """
        with self._reader() as conn:
            cursor = conn.execute(
                """SELECT * FROM workflow_steps
                   WHERE workflow_id = ? AND archived_at IS NOT NULL
                   ORDER BY step_number""",
                (workflow_id,),
            )
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                if result.get("config"):
                    result["config"] = json.loads(result["config"])
                if result.get("artifacts"):
                    result["artifacts"] = json.loads(result["artifacts"])
                results.append(result)
            return results

    def archive_workflow_step(self, step_id: int) -> bool:
        """Archive a workflow step (soft delete).

        Does NOT renumber remaining steps - the archived step keeps its
        original step_number so it can be restored to its original position.

        Args:
            step_id: ID of the step to archive.

        Returns:
            True if step was archived, False if not found or already archived.
        """
        with self._writer() as conn:
            cursor = conn.execute(
                """UPDATE workflow_steps
                   SET archived_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND archived_at IS NULL""",
                (step_id,),
            )
            return cursor.rowcount > 0

    def restore_workflow_step(self, step_id: int) -> dict:
        """Restore an archived step to its original position.

        The step keeps its original step_number. If that position is now
        occupied by another step, raises ValueError with details.

        Args:
            step_id: ID of the step to restore.

        Returns:
            The restored step dictionary.

        Raises:
            ValueError: If step not found, not archived, or position is occupied.
        """
        with self._writer() as conn:
            # Get the archived step
            cursor = conn.execute(
                """SELECT * FROM workflow_steps
                   WHERE id = ? AND archived_at IS NOT NULL""",
                (step_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("Step not found or not archived")

            step = dict(row)

            # Check if original position is still available
            conflict = conn.execute(
                """SELECT id, name FROM workflow_steps
                   WHERE workflow_id = ? AND step_number = ? AND archived_at IS NULL""",
                (step["workflow_id"], step["step_number"]),
            ).fetchone()

            if conflict:
                raise ValueError(
                    f"Position {step['step_number']} is now occupied by step "
                    f"'{conflict['name']}'. Reorder steps first to make room."
                )

            # Restore the step
            conn.execute(
                "UPDATE workflow_steps SET archived_at = NULL WHERE id = ?",
                (step_id,),
            )

            # Return the restored step
            cursor = conn.execute(
                "SELECT * FROM workflow_steps WHERE id = ?", (step_id,)
            )
            result = dict(cursor.fetchone())
            if result.get("config"):
                result["config"] = json.loads(result["config"])
            if result.get("artifacts"):
                result["artifacts"] = json.loads(result["artifacts"])
            return result

    _STEP_UPDATE_COLS = frozenset({
        "status", "loop_name", "artifacts", "started_at", "completed_at",
        "name", "step_type", "config", "step_number"
    })

    def update_workflow_step(self, id: int, **kwargs) -> bool:
        """Update workflow step fields."""
        invalid_cols = set(kwargs.keys()) - self._STEP_UPDATE_COLS
        if invalid_cols:
            raise ValueError(f"Invalid columns for step update: {invalid_cols}")

        if not kwargs:
            return False

        # Serialize JSON fields
        if "artifacts" in kwargs and kwargs["artifacts"] is not None:
            kwargs["artifacts"] = json.dumps(kwargs["artifacts"])
        if "config" in kwargs and kwargs["config"] is not None:
            kwargs["config"] = json.dumps(kwargs["config"])

        with self._writer() as conn:
            set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
            cursor = conn.execute(
                f"UPDATE workflow_steps SET {set_clause} WHERE id = ?",
                (*kwargs.values(), id),
            )
            return cursor.rowcount > 0

    def delete_workflow_step(self, id: int) -> bool:
        """Delete a workflow step and its step resources (cascade)."""
        with self._writer() as conn:
            # Delete step resources first
            conn.execute(
                "DELETE FROM workflow_step_resources WHERE step_id = ?", (id,)
            )
            # Delete the step
            cursor = conn.execute(
                "DELETE FROM workflow_steps WHERE id = ?", (id,)
            )
            return cursor.rowcount > 0

    def delete_workflow_step_atomic(self, step_id: int, workflow_id: str) -> bool:
        """Delete a workflow step permanently.

        Note: Does NOT renumber remaining steps. This avoids UNIQUE constraint
        collisions with archived steps that retain their original step_number
        for restoration purposes. Step number gaps are acceptable.

        Args:
            step_id: ID of the step to delete.
            workflow_id: ID of the workflow containing the step.

        Returns:
            True if the step was deleted, False if not found.
        """
        with self._writer() as conn:
            # Delete step resources first (cascade)
            conn.execute(
                "DELETE FROM workflow_step_resources WHERE step_id = ?", (step_id,)
            )

            # Delete the step
            cursor = conn.execute(
                "DELETE FROM workflow_steps WHERE id = ?", (step_id,)
            )
            return cursor.rowcount > 0

    def renumber_workflow_steps(self, workflow_id: str) -> None:
        """Renumber ACTIVE steps in a workflow, skipping step numbers used by archived steps.

        Note: Archived steps keep their original step_number for restoration purposes.
        Active steps will be renumbered sequentially, skipping any step numbers
        that are occupied by archived steps.

        Example: If archived step has step_number=2, active steps will be numbered 1, 3, 4, ...
        """
        with self._writer() as conn:
            # Get step numbers used by archived steps (to skip them)
            cursor = conn.execute(
                """SELECT step_number FROM workflow_steps
                   WHERE workflow_id = ? AND archived_at IS NOT NULL""",
                (workflow_id,),
            )
            archived_numbers = {row[0] for row in cursor.fetchall()}

            # Fetch ACTIVE steps only
            cursor = conn.execute(
                """SELECT id FROM workflow_steps
                   WHERE workflow_id = ? AND archived_at IS NULL
                   ORDER BY step_number""",
                (workflow_id,),
            )
            step_ids = [row[0] for row in cursor.fetchall()]

            # Calculate new step numbers, skipping archived positions
            new_numbers = []
            next_num = 1
            for _ in step_ids:
                while next_num in archived_numbers:
                    next_num += 1
                new_numbers.append(next_num)
                next_num += 1

            # Use negative step numbers first to avoid unique constraint violations
            for i, step_id in enumerate(step_ids):
                conn.execute(
                    "UPDATE workflow_steps SET step_number = ? WHERE id = ?",
                    (-(i + 1), step_id),
                )
            # Then set to final positive values
            for step_id, new_num in zip(step_ids, new_numbers):
                conn.execute(
                    "UPDATE workflow_steps SET step_number = ? WHERE id = ?",
                    (new_num, step_id),
                )

    def reorder_workflow_steps_atomic(self, workflow_id: str, step_ids: list[int]) -> None:
        """Atomically reorder workflow steps according to the given step ID order.

        Uses negative temporary step numbers to avoid unique constraint violations
        during reordering. Skips step numbers occupied by archived steps.

        Args:
            workflow_id: The workflow ID
            step_ids: List of step IDs in their new order (must be active steps only)
        """
        with self._writer() as conn:
            # Get step numbers used by archived steps (to skip them)
            cursor = conn.execute(
                """SELECT step_number FROM workflow_steps
                   WHERE workflow_id = ? AND archived_at IS NOT NULL""",
                (workflow_id,),
            )
            archived_numbers = {row[0] for row in cursor.fetchall()}

            # Calculate new step numbers, skipping archived positions
            new_numbers = []
            next_num = 1
            for _ in step_ids:
                while next_num in archived_numbers:
                    next_num += 1
                new_numbers.append(next_num)
                next_num += 1

            # First pass: set all step numbers to negative temporaries
            for i, step_id in enumerate(step_ids, 1):
                conn.execute(
                    "UPDATE workflow_steps SET step_number = ? WHERE id = ? AND workflow_id = ?",
                    (-i, step_id, workflow_id),
                )
            # Second pass: set to final positive values, skipping archived numbers
            for step_id, new_num in zip(step_ids, new_numbers):
                conn.execute(
                    "UPDATE workflow_steps SET step_number = ? WHERE id = ? AND workflow_id = ?",
                    (new_num, step_id, workflow_id),
                )

    def start_workflow_step(self, id: int) -> bool:
        """Mark a workflow step as started."""
        now = datetime.utcnow().isoformat()
        return self.update_workflow_step(id, status="active", started_at=now)

    def complete_workflow_step(self, id: int, artifacts: Optional[dict] = None) -> bool:
        """Mark a workflow step as completed."""
        now = datetime.utcnow().isoformat()
        kwargs = {"status": "completed", "completed_at": now}
        if artifacts:
            kwargs["artifacts"] = artifacts
        return self.update_workflow_step(id, **kwargs)

    def skip_workflow_step(self, id: int) -> bool:
        """Mark a workflow step as skipped."""
        now = datetime.utcnow().isoformat()
        return self.update_workflow_step(id, status="skipped", completed_at=now)

    def advance_workflow_step_atomic(
        self,
        workflow_id: str,
        current_step_id: int,
        next_step_id: Optional[int],
        skip_current: bool = False,
        artifacts: Optional[dict] = None,
    ) -> bool:
        """Atomically advance a workflow to its next step.

        This method performs all step advancement operations in a single
        transaction to prevent race conditions from concurrent requests.

        Args:
            workflow_id: The workflow ID.
            current_step_id: The ID of the current step to complete/skip.
            next_step_id: The ID of the next step to start (None if completing workflow).
            skip_current: If True, skip the current step instead of completing it.
            artifacts: Optional artifacts to store on the current step.

        Returns:
            True if advancement succeeded, False otherwise.
        """
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()

            # Complete or skip the current step
            if skip_current:
                conn.execute(
                    "UPDATE workflow_steps SET status = 'skipped', completed_at = ? WHERE id = ?",
                    (now, current_step_id),
                )
            else:
                if artifacts:
                    conn.execute(
                        "UPDATE workflow_steps SET status = 'completed', completed_at = ?, artifacts = ? WHERE id = ?",
                        (now, json.dumps(artifacts), current_step_id),
                    )
                else:
                    conn.execute(
                        "UPDATE workflow_steps SET status = 'completed', completed_at = ? WHERE id = ?",
                        (now, current_step_id),
                    )

            if next_step_id:
                # Get next step number
                cursor = conn.execute(
                    "SELECT step_number FROM workflow_steps WHERE id = ?",
                    (next_step_id,)
                )
                row = cursor.fetchone()
                if not row:
                    return False
                next_step_num = row[0]

                # Update workflow to next step
                conn.execute(
                    "UPDATE workflows SET current_step = ?, updated_at = ? WHERE id = ?",
                    (next_step_num, now, workflow_id),
                )

                # Start the next step
                conn.execute(
                    "UPDATE workflow_steps SET status = 'active', started_at = ? WHERE id = ?",
                    (now, next_step_id),
                )
            else:
                # No more steps - mark workflow as completed
                conn.execute(
                    "UPDATE workflows SET status = 'completed', updated_at = ? WHERE id = ?",
                    (now, workflow_id),
                )

            return True

    # ========== Planning Sessions ==========

    def create_planning_session(
        self,
        id: str,
        workflow_id: str,
        step_id: int,
        messages: Optional[list] = None,
        artifacts: Optional[dict] = None,
        status: str = "active",
    ) -> dict:
        """Create a planning session for an interactive step.

        Args:
            id: Unique session identifier.
            workflow_id: Parent workflow ID.
            step_id: Parent step ID.
            messages: Initial messages (default: empty list).
            artifacts: Optional artifacts dict.
            status: Session status (default: 'active').

        Returns:
            The created session dict.
        """
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            messages_json = json.dumps(messages or [])
            artifacts_json = json.dumps(artifacts) if artifacts else None
            conn.execute(
                """INSERT INTO planning_sessions
                   (id, workflow_id, step_id, messages, artifacts, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (id, workflow_id, step_id, messages_json, artifacts_json, status, now, now),
            )
        return self.get_planning_session(id)

    def get_planning_session(self, id: str) -> Optional[dict]:
        """Get planning session by ID."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM planning_sessions WHERE id = ?", (id,)
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result.get("messages"):
                    result["messages"] = json.loads(result["messages"])
                if result.get("artifacts"):
                    result["artifacts"] = json.loads(result["artifacts"])
                return result
            return None

    def get_planning_session_by_step(self, step_id: int) -> Optional[dict]:
        """Get planning session by step ID."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM planning_sessions WHERE step_id = ?", (step_id,)
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result.get("messages"):
                    result["messages"] = json.loads(result["messages"])
                if result.get("artifacts"):
                    result["artifacts"] = json.loads(result["artifacts"])
                return result
            return None

    def get_planning_session_by_workflow(self, workflow_id: str) -> Optional[dict]:
        """Get the active planning session for a workflow."""
        with self._reader() as conn:
            cursor = conn.execute(
                """SELECT * FROM planning_sessions
                   WHERE workflow_id = ? AND status = 'active'
                   ORDER BY created_at DESC LIMIT 1""",
                (workflow_id,),
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result.get("messages"):
                    result["messages"] = json.loads(result["messages"])
                if result.get("artifacts"):
                    result["artifacts"] = json.loads(result["artifacts"])
                return result
            return None

    def list_planning_sessions(
        self,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        """List planning sessions with optional filtering.

        Args:
            workflow_id: Filter by workflow ID.
            status: Filter by status ('active', 'completed').

        Returns:
            List of planning session dicts.
        """
        with self._reader() as conn:
            conditions = []
            params: list[Any] = []

            if workflow_id:
                conditions.append("workflow_id = ?")
                params.append(workflow_id)
            if status:
                conditions.append("status = ?")
                params.append(status)

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            cursor = conn.execute(
                f"""SELECT * FROM planning_sessions
                   WHERE {where_clause}
                   ORDER BY created_at DESC""",
                params,
            )

            results = []
            for row in cursor.fetchall():
                result = dict(row)
                if result.get("messages"):
                    result["messages"] = json.loads(result["messages"])
                if result.get("artifacts"):
                    result["artifacts"] = json.loads(result["artifacts"])
                results.append(result)
            return results

    def add_planning_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> bool:
        """Add a message to a planning session.

        Args:
            session_id: Session ID.
            role: Message role ('user' or 'assistant').
            content: Message content.
            metadata: Optional message metadata.

        Returns:
            True if message was added, False if session not found.
        """
        session = self.get_planning_session(session_id)
        if not session:
            return False

        messages = session.get("messages", [])
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        }
        if metadata:
            message["metadata"] = metadata
        messages.append(message)

        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            cursor = conn.execute(
                """UPDATE planning_sessions
                   SET messages = ?, updated_at = ?
                   WHERE id = ?""",
                (json.dumps(messages), now, session_id),
            )
            return cursor.rowcount > 0

    def update_planning_session(
        self,
        id: str,
        status: Optional[str] = None,
        artifacts: Optional[dict] = None,
    ) -> bool:
        """Update planning session fields."""
        updates = []
        params: list[Any] = []

        if status:
            updates.append("status = ?")
            params.append(status)
        if artifacts is not None:
            updates.append("artifacts = ?")
            params.append(json.dumps(artifacts))

        if not updates:
            return False

        updates.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat())
        params.append(id)

        with self._writer() as conn:
            cursor = conn.execute(
                f"UPDATE planning_sessions SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            return cursor.rowcount > 0

    def complete_planning_session(
        self, id: str, artifacts: Optional[dict] = None
    ) -> bool:
        """Mark a planning session as completed."""
        return self.update_planning_session(id, status="completed", artifacts=artifacts)

    # ========== Utilities ==========

    def close(self) -> None:
        """Close database connection."""
        if hasattr(self._local, "connection") and self._local.connection:
            self._local.connection.close()
            self._local.connection = None

    def vacuum(self) -> None:
        """Reclaim unused space in database."""
        with self._writer() as conn:
            conn.execute("VACUUM")
