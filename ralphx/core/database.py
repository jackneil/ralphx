"""SQLite database layer for RalphX.

Implements:
- WAL mode for concurrent reads
- Single writer, multiple readers
- All 8 tables from DESIGN.md Section 10.3
- CRUD operations for each entity
- Daily backup functionality
- Migration support
"""

import json
import os
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional

from ralphx.core.workspace import get_backups_path, get_database_path


# Schema version for migrations
# NOTE: When the initial schema is updated, also update this version and ensure
# migrations are idempotent (use IF EXISTS / IF NOT EXISTS clauses).
SCHEMA_VERSION = 9

# SQL schema
SCHEMA_SQL = """
-- Projects table
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    design_doc TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Loops table
CREATE TABLE IF NOT EXISTS loops (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    config_yaml TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, name)
);

-- Runs table
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    loop_name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    iterations_completed INTEGER DEFAULT 0,
    items_generated INTEGER DEFAULT 0,
    error_message TEXT
);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    iteration INTEGER NOT NULL,
    mode TEXT,
    started_at TIMESTAMP,
    duration_seconds REAL,
    status TEXT,
    items_added TEXT
);

-- Work items table
CREATE TABLE IF NOT EXISTS work_items (
    id TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    priority INTEGER,
    content TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    category TEXT,
    tags TEXT,
    metadata TEXT,
    namespace TEXT,  -- Renamed from source_loop: groups items by domain
    item_type TEXT DEFAULT 'item',
    claimed_by TEXT,
    claimed_at TIMESTAMP,
    processed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, id)
);

-- Checkpoints table
CREATE TABLE IF NOT EXISTS checkpoints (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    run_id TEXT,
    loop_name TEXT,
    iteration INTEGER,
    status TEXT,
    data TEXT,
    created_at TIMESTAMP
);

-- Guardrails metadata table
CREATE TABLE IF NOT EXISTS guardrails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
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
    UNIQUE(project_id, category, filename)
);

-- Execution logs table
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    run_id TEXT,  -- No FK constraint; runs exist in project databases, not here
    level TEXT NOT NULL,
    category TEXT DEFAULT 'system',
    event TEXT DEFAULT 'log',
    message TEXT NOT NULL,
    metadata TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Accounts table - stores all logged-in Claude accounts
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,  -- Primary identifier
    display_name TEXT,           -- Optional friendly name
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    expires_at INTEGER NOT NULL,  -- Unix timestamp (seconds)
    scopes TEXT,  -- JSON array of OAuth scopes
    subscription_type TEXT,  -- Claude subscription tier ("free", "pro", "max")
    rate_limit_tier TEXT,  -- API rate limit tier (e.g., "default_claude_max_20x")
    is_default BOOLEAN DEFAULT FALSE,  -- User-selected default account
    is_active BOOLEAN DEFAULT TRUE,    -- Account enabled/disabled
    is_deleted BOOLEAN DEFAULT FALSE,  -- Soft delete for safety
    last_used_at TIMESTAMP,
    -- Usage cache (avoid N API calls)
    cached_usage_5h REAL,
    cached_usage_7d REAL,
    cached_5h_resets_at TEXT,  -- ISO timestamp string
    cached_7d_resets_at TEXT,  -- ISO timestamp string
    usage_cached_at INTEGER,   -- Unix timestamp when cache was updated
    -- Error tracking
    last_error TEXT,
    last_error_at TIMESTAMP,
    consecutive_failures INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Project account assignments table - links projects to accounts
CREATE TABLE IF NOT EXISTS project_account_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,  -- RESTRICT prevents deletion while assigned
    allow_fallback BOOLEAN DEFAULT TRUE,  -- Allow falling back to other accounts on usage limit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id)  -- One account per project
);
"""

# Indexes for common queries
INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_work_items_status ON work_items(project_id, status);
CREATE INDEX IF NOT EXISTS idx_work_items_category ON work_items(project_id, category);
CREATE INDEX IF NOT EXISTS idx_work_items_priority ON work_items(project_id, priority);
CREATE INDEX IF NOT EXISTS idx_work_items_created ON work_items(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_work_items_namespace ON work_items(project_id, namespace, status);
CREATE INDEX IF NOT EXISTS idx_work_items_claimed ON work_items(project_id, claimed_by, claimed_at);
CREATE INDEX IF NOT EXISTS idx_sessions_run ON sessions(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id, status);
CREATE INDEX IF NOT EXISTS idx_guardrails_project ON guardrails(project_id, enabled);
CREATE INDEX IF NOT EXISTS idx_guardrails_source ON guardrails(source);
CREATE INDEX IF NOT EXISTS idx_logs_run ON logs(run_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(project_id, level, timestamp);

-- Accounts indexes
CREATE INDEX IF NOT EXISTS idx_accounts_active ON accounts(is_active, is_deleted);
CREATE INDEX IF NOT EXISTS idx_accounts_email ON accounts(email);

-- Project account assignments indexes
CREATE INDEX IF NOT EXISTS idx_assignments_project ON project_account_assignments(project_id);
CREATE INDEX IF NOT EXISTS idx_assignments_account ON project_account_assignments(account_id);
"""


class Database:
    """SQLite database manager with WAL mode and connection pooling.

    Provides:
    - Single writer lock for atomic writes
    - Multiple concurrent readers via WAL mode
    - CRUD operations for all tables
    - Automatic schema creation and migration
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file. Defaults to ~/.ralphx/ralphx.db.
                     Use ":memory:" for in-memory testing.
        """
        if db_path is None:
            db_path = str(get_database_path())

        self.db_path = db_path
        self._write_lock = threading.Lock()
        self._local = threading.local()

        # Create database with proper permissions if it doesn't exist
        if db_path != ":memory:" and not Path(db_path).exists():
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            # Create file with 0600 permissions
            Path(db_path).touch(mode=0o600)

        # Initialize schema
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                check_same_thread=False,
            )
            # Enable WAL mode for concurrent reads
            conn.execute("PRAGMA journal_mode=WAL")
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys=ON")
            # Row factory for dict-like access
            conn.row_factory = sqlite3.Row
            self._local.connection = conn
        return self._local.connection

    @contextmanager
    def _writer(self) -> Iterator[sqlite3.Connection]:
        """Context manager for write operations with locking."""
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
        """Context manager for read operations (no locking needed with WAL)."""
        yield self._get_connection()

    def _init_schema(self) -> None:
        """Initialize database schema and run any pending migrations."""
        with self._writer() as conn:
            # Create tables first (IF NOT EXISTS leaves existing tables alone)
            conn.executescript(SCHEMA_SQL)

            # Check/set schema version for new databases
            cursor = conn.execute(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )

        # Run any pending migrations for existing databases
        # This adds new columns before we create indexes on them
        self.migrate()

        # Now create indexes (after migrations ensure columns exist)
        with self._writer() as conn:
            conn.executescript(INDEXES_SQL)

    def close(self) -> None:
        """Close the database connection."""
        if hasattr(self._local, "connection") and self._local.connection:
            self._local.connection.close()
            self._local.connection = None

    def _parse_metadata(self, value: Any) -> Optional[dict]:
        """Safely parse metadata that may be JSON or plain text.

        Args:
            value: Raw metadata value from database (may be JSON string, plain text, or None)

        Returns:
            Parsed dict if valid JSON, None otherwise
        """
        if not value or not isinstance(value, str) or not value.strip():
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            # Not valid JSON - return None (legacy data may have plain strings)
            return None

    # =========================================================================
    # Project Operations
    # =========================================================================

    def create_project(
        self,
        id: str,
        slug: str,
        name: str,
        path: str,
        design_doc: Optional[str] = None,
    ) -> str:
        """Create a new project.

        Returns:
            The project ID.
        """
        now = datetime.utcnow().isoformat()
        with self._writer() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, slug, name, path, design_doc, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (id, slug, name, path, design_doc, now, now),
            )
        return id

    def get_project(self, slug: str) -> Optional[dict]:
        """Get a project by slug."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM projects WHERE slug = ?", (slug,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_project_by_id(self, id: str) -> Optional[dict]:
        """Get a project by ID."""
        with self._reader() as conn:
            cursor = conn.execute("SELECT * FROM projects WHERE id = ?", (id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_projects(self) -> list[dict]:
        """List all projects."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM projects ORDER BY created_at DESC"
            )
            return [dict(row) for row in cursor.fetchall()]

    # Allowed columns for update operations (security: prevents SQL injection via column names)
    _PROJECT_UPDATE_COLS = frozenset({"name", "path", "design_doc", "updated_at"})

    def update_project(self, slug: str, **kwargs) -> bool:
        """Update a project.

        Returns:
            True if project was updated, False if not found.

        Raises:
            ValueError: If invalid column names are provided.
        """
        if not kwargs:
            return False

        # Security: validate column names against whitelist
        invalid_cols = set(kwargs.keys()) - self._PROJECT_UPDATE_COLS - {"updated_at"}
        if invalid_cols:
            raise ValueError(f"Invalid columns for project update: {invalid_cols}")

        kwargs["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [slug]

        with self._writer() as conn:
            cursor = conn.execute(
                f"UPDATE projects SET {set_clause} WHERE slug = ?", values
            )
            return cursor.rowcount > 0

    def delete_project(self, slug: str) -> bool:
        """Delete a project and all related data (CASCADE).

        Returns:
            True if project was deleted, False if not found.
        """
        with self._writer() as conn:
            cursor = conn.execute("DELETE FROM projects WHERE slug = ?", (slug,))
            return cursor.rowcount > 0

    # =========================================================================
    # Loop Operations
    # =========================================================================

    def create_loop(
        self,
        id: str,
        project_id: str,
        name: str,
        config_yaml: str,
    ) -> str:
        """Create a new loop configuration."""
        now = datetime.utcnow().isoformat()
        with self._writer() as conn:
            conn.execute(
                """
                INSERT INTO loops (id, project_id, name, config_yaml, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (id, project_id, name, config_yaml, now, now),
            )
        return id

    def get_loop(self, project_id: str, name: str) -> Optional[dict]:
        """Get a loop by project and name."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM loops WHERE project_id = ? AND name = ?",
                (project_id, name),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_loops(self, project_id: str) -> list[dict]:
        """List all loops for a project."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM loops WHERE project_id = ? ORDER BY name",
                (project_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    # Allowed columns for loop update operations
    _LOOP_UPDATE_COLS = frozenset({"config_yaml", "updated_at"})

    def update_loop(self, project_id: str, name: str, **kwargs) -> bool:
        """Update a loop configuration.

        Raises:
            ValueError: If invalid column names are provided.
        """
        if not kwargs:
            return False

        # Security: validate column names against whitelist
        invalid_cols = set(kwargs.keys()) - self._LOOP_UPDATE_COLS - {"updated_at"}
        if invalid_cols:
            raise ValueError(f"Invalid columns for loop update: {invalid_cols}")

        kwargs["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [project_id, name]

        with self._writer() as conn:
            cursor = conn.execute(
                f"UPDATE loops SET {set_clause} WHERE project_id = ? AND name = ?",
                values,
            )
            return cursor.rowcount > 0

    def delete_loop(self, project_id: str, name: str) -> bool:
        """Delete a loop."""
        with self._writer() as conn:
            cursor = conn.execute(
                "DELETE FROM loops WHERE project_id = ? AND name = ?",
                (project_id, name),
            )
            return cursor.rowcount > 0

    # =========================================================================
    # Run Operations
    # =========================================================================

    def create_run(
        self,
        id: str,
        project_id: str,
        loop_name: str,
        status: str = "active",
    ) -> str:
        """Create a new run."""
        now = datetime.utcnow().isoformat()
        with self._writer() as conn:
            conn.execute(
                """
                INSERT INTO runs (id, project_id, loop_name, status, started_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (id, project_id, loop_name, status, now),
            )
        return id

    def get_run(self, id: str) -> Optional[dict]:
        """Get a run by ID."""
        with self._reader() as conn:
            cursor = conn.execute("SELECT * FROM runs WHERE id = ?", (id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_runs(
        self, project_id: str, status: Optional[str] = None, limit: int = 100
    ) -> list[dict]:
        """List runs for a project, optionally filtered by status."""
        with self._reader() as conn:
            if status:
                cursor = conn.execute(
                    """
                    SELECT * FROM runs
                    WHERE project_id = ? AND status = ?
                    ORDER BY started_at DESC LIMIT ?
                    """,
                    (project_id, status, limit),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT * FROM runs
                    WHERE project_id = ?
                    ORDER BY started_at DESC LIMIT ?
                    """,
                    (project_id, limit),
                )
            return [dict(row) for row in cursor.fetchall()]

    # Allowed columns for run update operations
    _RUN_UPDATE_COLS = frozenset({
        "status", "completed_at", "iterations_completed",
        "items_generated", "error_message"
    })

    def update_run(self, id: str, **kwargs) -> bool:
        """Update a run.

        Raises:
            ValueError: If invalid column names are provided.
        """
        if not kwargs:
            return False

        # Security: validate column names against whitelist
        invalid_cols = set(kwargs.keys()) - self._RUN_UPDATE_COLS
        if invalid_cols:
            raise ValueError(f"Invalid columns for run update: {invalid_cols}")

        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [id]

        with self._writer() as conn:
            cursor = conn.execute(
                f"UPDATE runs SET {set_clause} WHERE id = ?", values
            )
            return cursor.rowcount > 0

    def complete_run(
        self, id: str, status: str = "completed", error_message: Optional[str] = None
    ) -> bool:
        """Mark a run as complete."""
        now = datetime.utcnow().isoformat()
        with self._writer() as conn:
            cursor = conn.execute(
                """
                UPDATE runs SET status = ?, completed_at = ?, error_message = ?
                WHERE id = ?
                """,
                (status, now, error_message, id),
            )
            return cursor.rowcount > 0

    def increment_run_counters(
        self, id: str, iterations: int = 0, items: int = 0
    ) -> bool:
        """Increment run iteration and item counters."""
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

    # =========================================================================
    # Session Operations
    # =========================================================================

    def create_session(
        self,
        session_id: str,
        project_id: str,
        iteration: int,
        run_id: Optional[str] = None,
        mode: Optional[str] = None,
        status: Optional[str] = None,
    ) -> str:
        """Create a new session record."""
        now = datetime.utcnow().isoformat()
        with self._writer() as conn:
            conn.execute(
                """
                INSERT INTO sessions
                (session_id, run_id, project_id, iteration, mode, started_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, run_id, project_id, iteration, mode, now, status),
            )
        return session_id

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get a session by ID."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_sessions(
        self,
        project_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """List sessions with optional filters.

        Args:
            project_id: Filter by project ID.
            run_id: Filter by run ID.
            limit: Max sessions to return.

        Returns:
            List of session dictionaries.
        """
        conditions = []
        params = []

        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if run_id:
            conditions.append("run_id = ?")
            params.append(run_id)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        with self._reader() as conn:
            cursor = conn.execute(
                f"SELECT * FROM sessions {where} ORDER BY started_at DESC LIMIT ?",
                params,
            )
            return [dict(row) for row in cursor.fetchall()]

    # Allowed columns for session update operations
    _SESSION_UPDATE_COLS = frozenset({
        "status", "duration_seconds", "items_added"
    })

    def update_session(self, session_id: str, **kwargs) -> bool:
        """Update a session.

        Raises:
            ValueError: If invalid column names are provided.
        """
        if not kwargs:
            return False

        # Security: validate column names against whitelist
        invalid_cols = set(kwargs.keys()) - self._SESSION_UPDATE_COLS
        if invalid_cols:
            raise ValueError(f"Invalid columns for session update: {invalid_cols}")

        # Handle items_added as JSON
        if "items_added" in kwargs and isinstance(kwargs["items_added"], list):
            kwargs["items_added"] = json.dumps(kwargs["items_added"])

        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [session_id]

        with self._writer() as conn:
            cursor = conn.execute(
                f"UPDATE sessions SET {set_clause} WHERE session_id = ?", values
            )
            return cursor.rowcount > 0

    # =========================================================================
    # Work Item Operations
    # =========================================================================

    def create_work_item(
        self,
        id: str,
        project_id: str,
        content: str,
        priority: Optional[int] = None,
        status: str = "pending",
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
        namespace: Optional[str] = None,
        item_type: Optional[str] = None,
    ) -> str:
        """Create a new work item.

        Args:
            id: Unique identifier for the item.
            project_id: Project this item belongs to.
            content: Item content.
            priority: Optional priority (lower = higher priority).
            status: Item status (pending, in_progress, completed, processed, failed).
            category: Optional category.
            tags: Optional list of tags.
            metadata: Optional metadata dictionary.
            namespace: Namespace for grouping items (typically loop name).
            item_type: Semantic type from the loop's item_types.output.singular.
        """
        now = datetime.utcnow().isoformat()
        with self._writer() as conn:
            conn.execute(
                """
                INSERT INTO work_items
                (id, project_id, priority, content, status, category, tags, metadata,
                 namespace, item_type, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    id,
                    project_id,
                    priority,
                    content,
                    status,
                    category,
                    json.dumps(tags) if tags else None,
                    json.dumps(metadata) if metadata else None,
                    namespace,
                    item_type or "item",
                    now,
                    now,
                ),
            )
        return id

    def get_work_item(self, project_id: str, id: str) -> Optional[dict]:
        """Get a work item."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM work_items WHERE project_id = ? AND id = ?",
                (project_id, id),
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                # Parse JSON fields
                if result.get("tags"):
                    result["tags"] = json.loads(result["tags"])
                if result.get("metadata"):
                    result["metadata"] = json.loads(result["metadata"])
                return result
            return None

    def list_work_items(
        self,
        project_id: str,
        status: Optional[str] = None,
        category: Optional[str] = None,
        namespace: Optional[str] = None,
        claimed_by: Optional[str] = None,
        unclaimed_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """List work items with optional filters.

        Args:
            project_id: Filter by project.
            status: Filter by status.
            category: Filter by category.
            namespace: Filter by namespace.
            claimed_by: Filter by claiming loop.
            unclaimed_only: If True, only return items where claimed_by is NULL.
            limit: Max items to return.
            offset: Pagination offset.
        """
        conditions = ["project_id = ?"]
        params: list[Any] = [project_id]

        if status:
            conditions.append("status = ?")
            params.append(status)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if namespace:
            conditions.append("namespace = ?")
            params.append(namespace)
        if claimed_by:
            conditions.append("claimed_by = ?")
            params.append(claimed_by)
        if unclaimed_only:
            conditions.append("claimed_by IS NULL")

        where_clause = " AND ".join(conditions)
        params.extend([limit, offset])

        with self._reader() as conn:
            cursor = conn.execute(
                f"""
                SELECT * FROM work_items
                WHERE {where_clause}
                ORDER BY priority ASC, created_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            )
            results = []
            for row in cursor.fetchall():
                item = dict(row)
                if item.get("tags"):
                    item["tags"] = json.loads(item["tags"])
                if item.get("metadata"):
                    item["metadata"] = json.loads(item["metadata"])
                results.append(item)
            return results

    def count_work_items(
        self,
        project_id: str,
        status: Optional[str] = None,
        category: Optional[str] = None,
        namespace: Optional[str] = None,
    ) -> int:
        """Count work items with optional filters."""
        conditions = ["project_id = ?"]
        params: list[Any] = [project_id]

        if status:
            conditions.append("status = ?")
            params.append(status)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if namespace:
            conditions.append("namespace = ?")
            params.append(namespace)

        where_clause = " AND ".join(conditions)

        with self._reader() as conn:
            cursor = conn.execute(
                f"SELECT COUNT(*) FROM work_items WHERE {where_clause}",
                params,
            )
            return cursor.fetchone()[0]

    # Allowed columns for work item update operations
    _WORK_ITEM_UPDATE_COLS = frozenset({
        "priority", "content", "status", "category", "tags", "metadata", "updated_at",
        "namespace", "item_type", "claimed_by", "claimed_at", "processed_at"
    })

    def update_work_item(self, project_id: str, id: str, **kwargs) -> bool:
        """Update a work item.

        Raises:
            ValueError: If invalid column names are provided.
        """
        if not kwargs:
            return False

        # Security: validate column names against whitelist
        invalid_cols = set(kwargs.keys()) - self._WORK_ITEM_UPDATE_COLS - {"updated_at"}
        if invalid_cols:
            raise ValueError(f"Invalid columns for work item update: {invalid_cols}")

        kwargs["updated_at"] = datetime.utcnow().isoformat()

        # Handle JSON fields
        if "tags" in kwargs and isinstance(kwargs["tags"], list):
            kwargs["tags"] = json.dumps(kwargs["tags"])
        if "metadata" in kwargs and isinstance(kwargs["metadata"], dict):
            kwargs["metadata"] = json.dumps(kwargs["metadata"])

        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [project_id, id]

        with self._writer() as conn:
            cursor = conn.execute(
                f"UPDATE work_items SET {set_clause} WHERE project_id = ? AND id = ?",
                values,
            )
            return cursor.rowcount > 0

    def delete_work_item(self, project_id: str, id: str) -> bool:
        """Delete a work item."""
        with self._writer() as conn:
            cursor = conn.execute(
                "DELETE FROM work_items WHERE project_id = ? AND id = ?",
                (project_id, id),
            )
            return cursor.rowcount > 0

    def get_work_item_stats(self, project_id: str) -> dict:
        """Get work item statistics for a project."""
        with self._reader() as conn:
            # Count by status
            cursor = conn.execute(
                """
                SELECT status, COUNT(*) as count
                FROM work_items WHERE project_id = ?
                GROUP BY status
                """,
                (project_id,),
            )
            by_status = {row["status"]: row["count"] for row in cursor.fetchall()}

            # Count by category
            cursor = conn.execute(
                """
                SELECT category, COUNT(*) as count
                FROM work_items WHERE project_id = ?
                GROUP BY category
                """,
                (project_id,),
            )
            by_category = {
                row["category"] or "uncategorized": row["count"]
                for row in cursor.fetchall()
            }

            # Total count
            cursor = conn.execute(
                "SELECT COUNT(*) FROM work_items WHERE project_id = ?",
                (project_id,),
            )
            total = cursor.fetchone()[0]

            return {
                "total": total,
                "by_status": by_status,
                "by_category": by_category,
            }

    def claim_work_item(
        self,
        project_id: str,
        id: str,
        claimed_by: str,
    ) -> bool:
        """Atomically claim a work item.

        Uses UPDATE...WHERE to prevent race conditions.

        Args:
            project_id: Project ID.
            id: Work item ID.
            claimed_by: Name of the claiming loop.

        Returns:
            True if claim succeeded, False if item doesn't exist or already claimed.
        """
        now = datetime.utcnow().isoformat()
        with self._writer() as conn:
            cursor = conn.execute(
                """
                UPDATE work_items
                SET claimed_by = ?, claimed_at = ?, updated_at = ?
                WHERE project_id = ? AND id = ? AND claimed_by IS NULL
                """,
                (claimed_by, now, now, project_id, id),
            )
            return cursor.rowcount > 0

    def release_work_item_claim(
        self,
        project_id: str,
        id: str,
        claimed_by: Optional[str] = None,
    ) -> bool:
        """Release a claim on a work item.

        Args:
            project_id: Project ID.
            id: Work item ID.
            claimed_by: If provided, only release if claimed by this loop (ownership check).

        Returns:
            True if claim was released, False otherwise.
        """
        now = datetime.utcnow().isoformat()
        with self._writer() as conn:
            if claimed_by:
                # Ownership check
                cursor = conn.execute(
                    """
                    UPDATE work_items
                    SET claimed_by = NULL, claimed_at = NULL, updated_at = ?
                    WHERE project_id = ? AND id = ? AND claimed_by = ?
                    """,
                    (now, project_id, id, claimed_by),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE work_items
                    SET claimed_by = NULL, claimed_at = NULL, updated_at = ?
                    WHERE project_id = ? AND id = ?
                    """,
                    (now, project_id, id),
                )
            return cursor.rowcount > 0

    def mark_work_item_processed(
        self,
        project_id: str,
        id: str,
        claimed_by: str,
    ) -> bool:
        """Mark a work item as processed.

        Only succeeds if the item is claimed by the specified loop.

        Args:
            project_id: Project ID.
            id: Work item ID.
            claimed_by: Name of the loop that claimed this item (ownership check).

        Returns:
            True if item was marked processed, False otherwise.
        """
        now = datetime.utcnow().isoformat()
        with self._writer() as conn:
            cursor = conn.execute(
                """
                UPDATE work_items
                SET status = 'processed', processed_at = ?, updated_at = ?
                WHERE project_id = ? AND id = ? AND claimed_by = ?
                """,
                (now, now, project_id, id, claimed_by),
            )
            return cursor.rowcount > 0

    def get_namespace_item_counts(self, project_id: str) -> dict[str, int]:
        """Get counts of completed items grouped by namespace.

        Used for dashboard to show available items per namespace.

        Returns:
            Dict mapping namespace to count of completed items.
        """
        with self._reader() as conn:
            cursor = conn.execute(
                """
                SELECT namespace, COUNT(*) as count
                FROM work_items
                WHERE project_id = ?
                  AND namespace IS NOT NULL
                  AND status = 'completed'
                  AND claimed_by IS NULL
                GROUP BY namespace
                """,
                (project_id,),
            )
            return {row["namespace"]: row["count"] for row in cursor.fetchall()}

    # Backward compatibility alias
    def get_source_item_counts(self, project_id: str) -> dict[str, int]:
        """Deprecated: Use get_namespace_item_counts instead."""
        return self.get_namespace_item_counts(project_id)

    def release_stale_claims(
        self,
        project_id: str,
        max_age_minutes: int = 30,
    ) -> int:
        """Release claims that have been held too long (likely crashed consumer).

        Args:
            project_id: Project ID.
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
                SET claimed_by = NULL, claimed_at = NULL, updated_at = ?
                WHERE project_id = ?
                  AND claimed_at < ?
                  AND claimed_by IS NOT NULL
                """,
                (now, project_id, cutoff),
            )
            return cursor.rowcount

    def release_claims_by_loop(
        self,
        project_id: str,
        loop_name: str,
    ) -> int:
        """Release all claims held by a specific loop.

        Used when deleting a loop to prevent orphaned claims.

        Args:
            project_id: Project ID.
            loop_name: Name of the loop whose claims should be released.

        Returns:
            Number of claims released.
        """
        now = datetime.utcnow().isoformat()

        with self._writer() as conn:
            cursor = conn.execute(
                """
                UPDATE work_items
                SET claimed_by = NULL, claimed_at = NULL, updated_at = ?
                WHERE project_id = ?
                  AND claimed_by = ?
                """,
                (now, project_id, loop_name),
            )
            return cursor.rowcount

    # =========================================================================
    # Checkpoint Operations
    # =========================================================================

    def save_checkpoint(
        self,
        project_id: str,
        run_id: str,
        loop_name: str,
        iteration: int,
        status: str,
        data: Optional[dict] = None,
    ) -> None:
        """Save or update a checkpoint."""
        now = datetime.utcnow().isoformat()
        with self._writer() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO checkpoints
                (project_id, run_id, loop_name, iteration, status, data, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    run_id,
                    loop_name,
                    iteration,
                    status,
                    json.dumps(data) if data else None,
                    now,
                ),
            )

    def get_checkpoint(self, project_id: str) -> Optional[dict]:
        """Get the checkpoint for a project."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM checkpoints WHERE project_id = ?", (project_id,)
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result.get("data"):
                    result["data"] = json.loads(result["data"])
                return result
            return None

    def clear_checkpoint(self, project_id: str) -> bool:
        """Clear the checkpoint for a project."""
        with self._writer() as conn:
            cursor = conn.execute(
                "DELETE FROM checkpoints WHERE project_id = ?", (project_id,)
            )
            return cursor.rowcount > 0

    # =========================================================================
    # Guardrail Operations
    # =========================================================================

    def create_guardrail(
        self,
        category: str,
        filename: str,
        source: str,
        file_path: str,
        project_id: Optional[str] = None,
        file_mtime: Optional[float] = None,
        file_size: Optional[int] = None,
        enabled: bool = True,
        loops: Optional[list[str]] = None,
        modes: Optional[list[str]] = None,
        position: str = "after_design_doc",
    ) -> int:
        """Create a guardrail metadata record."""
        with self._writer() as conn:
            cursor = conn.execute(
                """
                INSERT INTO guardrails
                (project_id, category, filename, source, file_path, file_mtime,
                 file_size, enabled, loops, modes, position)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    category,
                    filename,
                    source,
                    file_path,
                    file_mtime,
                    file_size,
                    enabled,
                    json.dumps(loops) if loops else None,
                    json.dumps(modes) if modes else None,
                    position,
                ),
            )
            return cursor.lastrowid

    def get_guardrail(self, id: int) -> Optional[dict]:
        """Get a guardrail by ID."""
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

    def list_guardrails(
        self,
        project_id: Optional[str] = None,
        category: Optional[str] = None,
        source: Optional[str] = None,
        enabled_only: bool = True,
    ) -> list[dict]:
        """List guardrails with optional filters."""
        conditions = []
        params: list[Any] = []

        if project_id is not None:
            conditions.append("(project_id = ? OR project_id IS NULL)")
            params.append(project_id)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if source:
            conditions.append("source = ?")
            params.append(source)
        if enabled_only:
            conditions.append("enabled = 1")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with self._reader() as conn:
            cursor = conn.execute(
                f"""
                SELECT * FROM guardrails
                WHERE {where_clause}
                ORDER BY category, filename
                """,
                params,
            )
            results = []
            for row in cursor.fetchall():
                item = dict(row)
                if item.get("loops"):
                    item["loops"] = json.loads(item["loops"])
                if item.get("modes"):
                    item["modes"] = json.loads(item["modes"])
                results.append(item)
            return results

    # Allowed columns for guardrail update operations
    _GUARDRAIL_UPDATE_COLS = frozenset({
        "file_mtime", "file_size", "enabled", "loops", "modes", "position"
    })

    def update_guardrail(self, id: int, **kwargs) -> bool:
        """Update a guardrail.

        Raises:
            ValueError: If invalid column names are provided.
        """
        if not kwargs:
            return False

        # Security: validate column names against whitelist
        invalid_cols = set(kwargs.keys()) - self._GUARDRAIL_UPDATE_COLS
        if invalid_cols:
            raise ValueError(f"Invalid columns for guardrail update: {invalid_cols}")

        # Handle JSON fields
        if "loops" in kwargs and isinstance(kwargs["loops"], list):
            kwargs["loops"] = json.dumps(kwargs["loops"])
        if "modes" in kwargs and isinstance(kwargs["modes"], list):
            kwargs["modes"] = json.dumps(kwargs["modes"])

        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [id]

        with self._writer() as conn:
            cursor = conn.execute(
                f"UPDATE guardrails SET {set_clause} WHERE id = ?", values
            )
            return cursor.rowcount > 0

    def delete_guardrail(self, id: int) -> bool:
        """Delete a guardrail."""
        with self._writer() as conn:
            cursor = conn.execute("DELETE FROM guardrails WHERE id = ?", (id,))
            return cursor.rowcount > 0

    # =========================================================================
    # =========================================================================
    # Account Operations (Multi-Account Authentication)
    # =========================================================================

    def create_account(
        self,
        email: str,
        access_token: str,
        expires_at: int,
        refresh_token: Optional[str] = None,
        display_name: Optional[str] = None,
        scopes: Optional[str] = None,
        subscription_type: Optional[str] = None,
        rate_limit_tier: Optional[str] = None,
    ) -> dict:
        """Create a new account or update if email already exists.

        Args:
            email: User email (unique identifier)
            access_token: OAuth access token
            expires_at: Token expiry as Unix timestamp
            refresh_token: OAuth refresh token
            display_name: Optional friendly name
            scopes: JSON string of OAuth scopes
            subscription_type: Claude subscription tier
            rate_limit_tier: API rate limit tier

        Returns:
            Account dict with all fields
        """
        now = datetime.utcnow().isoformat()

        with self._writer() as conn:
            # Check if this is the first account (make it default)
            cursor = conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE is_deleted = 0"
            )
            count = cursor.fetchone()[0]
            is_default = count == 0

            # Use INSERT OR REPLACE to handle existing accounts
            cursor = conn.execute(
                """INSERT INTO accounts (
                    email, access_token, refresh_token, expires_at, display_name,
                    scopes, subscription_type, rate_limit_tier, is_default,
                    is_active, is_deleted, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    access_token = excluded.access_token,
                    refresh_token = excluded.refresh_token,
                    expires_at = excluded.expires_at,
                    scopes = excluded.scopes,
                    subscription_type = excluded.subscription_type,
                    rate_limit_tier = excluded.rate_limit_tier,
                    is_active = 1,
                    is_deleted = 0,
                    updated_at = excluded.updated_at
                """,
                (
                    email,
                    access_token,
                    refresh_token,
                    expires_at,
                    display_name,
                    scopes,
                    subscription_type,
                    rate_limit_tier,
                    is_default,
                    now,
                    now,
                ),
            )

            # Get the account
            cursor = conn.execute(
                "SELECT * FROM accounts WHERE email = ?", (email,)
            )
            row = cursor.fetchone()
            return dict(row) if row else {}

    def get_account(self, account_id: int) -> Optional[dict]:
        """Get an account by ID.

        Args:
            account_id: Account ID

        Returns:
            Account dict or None
        """
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM accounts WHERE id = ? AND is_deleted = 0",
                (account_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_account_by_email(self, email: str) -> Optional[dict]:
        """Get an account by email.

        Args:
            email: Account email

        Returns:
            Account dict or None
        """
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM accounts WHERE email = ? AND is_deleted = 0",
                (email,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_accounts(
        self, include_inactive: bool = False, include_deleted: bool = False
    ) -> list[dict]:
        """List all accounts.

        Args:
            include_inactive: Include disabled accounts
            include_deleted: Include soft-deleted accounts

        Returns:
            List of account dicts
        """
        conditions = []
        if not include_deleted:
            conditions.append("is_deleted = 0")
        if not include_inactive:
            conditions.append("is_active = 1")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with self._reader() as conn:
            cursor = conn.execute(
                f"SELECT * FROM accounts {where} ORDER BY is_default DESC, created_at ASC"
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    # Allowed columns for account update operations
    _ACCOUNT_UPDATE_COLS = frozenset({
        "display_name", "access_token", "refresh_token", "expires_at",
        "scopes", "subscription_type", "rate_limit_tier", "is_active",
        "last_used_at", "cached_usage_5h", "cached_usage_7d",
        "cached_5h_resets_at", "cached_7d_resets_at", "usage_cached_at",
        "last_error", "last_error_at", "consecutive_failures",
    })

    def update_account(self, account_id: int, **kwargs) -> bool:
        """Update an account by ID.

        Args:
            account_id: Account ID
            **kwargs: Fields to update

        Returns:
            True if updated, False otherwise

        Raises:
            ValueError: If invalid column names are provided
        """
        if not kwargs:
            return False

        # Security: validate column names against whitelist
        invalid_cols = set(kwargs.keys()) - self._ACCOUNT_UPDATE_COLS - {"updated_at"}
        if invalid_cols:
            raise ValueError(f"Invalid columns for account update: {invalid_cols}")

        kwargs["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [account_id]

        with self._writer() as conn:
            cursor = conn.execute(
                f"UPDATE accounts SET {set_clause} WHERE id = ? AND is_deleted = 0",
                values,
            )
            return cursor.rowcount > 0

    def delete_account(self, account_id: int, hard_delete: bool = False) -> bool:
        """Delete an account (soft delete by default).

        Args:
            account_id: Account ID
            hard_delete: If True, permanently delete instead of soft delete

        Returns:
            True if deleted, False otherwise
        """
        with self._writer() as conn:
            # Check if account has project assignments (ON DELETE RESTRICT)
            cursor = conn.execute(
                "SELECT COUNT(*) FROM project_account_assignments WHERE account_id = ?",
                (account_id,),
            )
            if cursor.fetchone()[0] > 0:
                raise ValueError(
                    "Cannot delete account: still assigned to projects. "
                    "Reassign or remove project assignments first."
                )

            if hard_delete:
                cursor = conn.execute(
                    "DELETE FROM accounts WHERE id = ?", (account_id,)
                )
            else:
                cursor = conn.execute(
                    """UPDATE accounts
                       SET is_deleted = 1, is_default = 0, updated_at = ?
                       WHERE id = ?""",
                    (datetime.utcnow().isoformat(), account_id),
                )
            return cursor.rowcount > 0

    def set_default_account(self, account_id: int) -> bool:
        """Set an account as the default.

        Args:
            account_id: Account ID to set as default

        Returns:
            True if updated, False otherwise
        """
        now = datetime.utcnow().isoformat()

        with self._writer() as conn:
            # Check account exists and is active
            cursor = conn.execute(
                "SELECT is_active FROM accounts WHERE id = ? AND is_deleted = 0",
                (account_id,),
            )
            row = cursor.fetchone()
            if not row or not row["is_active"]:
                return False

            # Clear existing default
            conn.execute(
                "UPDATE accounts SET is_default = 0, updated_at = ? WHERE is_default = 1",
                (now,),
            )

            # Set new default
            cursor = conn.execute(
                "UPDATE accounts SET is_default = 1, updated_at = ? WHERE id = ?",
                (now, account_id),
            )
            return cursor.rowcount > 0

    def get_default_account(self) -> Optional[dict]:
        """Get the default account.

        Returns:
            Account dict or None
        """
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM accounts WHERE is_default = 1 AND is_active = 1 AND is_deleted = 0"
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_first_active_account(self) -> Optional[dict]:
        """Get the first active account (fallback when no default).

        Returns:
            Account dict or None
        """
        with self._reader() as conn:
            cursor = conn.execute(
                """SELECT * FROM accounts
                   WHERE is_active = 1 AND is_deleted = 0
                   ORDER BY created_at ASC LIMIT 1"""
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def count_projects_using_account(self, account_id: int) -> int:
        """Count how many projects are assigned to an account.

        Args:
            account_id: Account ID

        Returns:
            Number of projects using this account
        """
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM project_account_assignments WHERE account_id = ?",
                (account_id,),
            )
            return cursor.fetchone()[0]

    # =========================================================================
    # Project Account Assignment Operations
    # =========================================================================

    def assign_account_to_project(
        self,
        project_id: str,
        account_id: int,
        allow_fallback: bool = True,
    ) -> dict:
        """Assign an account to a project.

        Args:
            project_id: Project ID
            account_id: Account ID
            allow_fallback: Allow fallback to other accounts on rate limit

        Returns:
            Assignment dict
        """
        now = datetime.utcnow().isoformat()

        with self._writer() as conn:
            # Verify account exists and is active
            cursor = conn.execute(
                "SELECT id FROM accounts WHERE id = ? AND is_active = 1 AND is_deleted = 0",
                (account_id,),
            )
            if not cursor.fetchone():
                raise ValueError(f"Account {account_id} not found or inactive")

            # Upsert assignment
            cursor = conn.execute(
                """INSERT INTO project_account_assignments (
                    project_id, account_id, allow_fallback, created_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    account_id = excluded.account_id,
                    allow_fallback = excluded.allow_fallback
                """,
                (project_id, account_id, allow_fallback, now),
            )

            # Return the assignment
            cursor = conn.execute(
                "SELECT * FROM project_account_assignments WHERE project_id = ?",
                (project_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else {}

    def get_project_account_assignment(self, project_id: str) -> Optional[dict]:
        """Get the account assignment for a project.

        Args:
            project_id: Project ID

        Returns:
            Assignment dict or None
        """
        with self._reader() as conn:
            cursor = conn.execute(
                """SELECT paa.*, a.email, a.display_name, a.subscription_type,
                          a.is_active, a.is_default,
                          a.cached_usage_5h, a.cached_usage_7d,
                          a.cached_5h_resets_at, a.cached_7d_resets_at,
                          a.usage_cached_at, a.expires_at
                   FROM project_account_assignments paa
                   JOIN accounts a ON a.id = paa.account_id
                   WHERE paa.project_id = ? AND a.is_deleted = 0""",
                (project_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def unassign_account_from_project(self, project_id: str) -> bool:
        """Remove account assignment from a project.

        Args:
            project_id: Project ID

        Returns:
            True if removed, False if not found
        """
        with self._writer() as conn:
            cursor = conn.execute(
                "DELETE FROM project_account_assignments WHERE project_id = ?",
                (project_id,),
            )
            return cursor.rowcount > 0

    def get_effective_account(self, project_id: Optional[str] = None) -> Optional[dict]:
        """Get the effective account for a project.

        Resolution order:
        1. If project has assignment -> use that account
        2. Else -> use default account
        3. If no default -> use first active account

        Args:
            project_id: Optional project ID

        Returns:
            Account dict or None
        """
        # Check project assignment first
        if project_id:
            assignment = self.get_project_account_assignment(project_id)
            if assignment and assignment.get("is_active"):
                account = self.get_account(assignment["account_id"])
                if account:
                    return account

        # Fall back to default account
        account = self.get_default_account()
        if account:
            return account

        # Last resort: first active account
        return self.get_first_active_account()

    def get_fallback_account(
        self,
        exclude_ids: Optional[list[int]] = None,
        prefer_lowest_usage: bool = True,
    ) -> Optional[dict]:
        """Get a fallback account (for 429 rate limit handling).

        Args:
            exclude_ids: Account IDs to exclude (already failed)
            prefer_lowest_usage: Sort by lowest cached usage

        Returns:
            Account dict or None
        """
        exclude_ids = exclude_ids or []

        with self._reader() as conn:
            placeholders = ",".join("?" for _ in exclude_ids) if exclude_ids else ""
            exclude_clause = f"AND id NOT IN ({placeholders})" if exclude_ids else ""

            # Order by lowest usage (5h usage takes priority)
            order_clause = """
                ORDER BY
                    COALESCE(cached_usage_5h, 0) ASC,
                    COALESCE(cached_usage_7d, 0) ASC,
                    consecutive_failures ASC,
                    created_at ASC
            """ if prefer_lowest_usage else "ORDER BY created_at ASC"

            cursor = conn.execute(
                f"""SELECT * FROM accounts
                   WHERE is_active = 1
                     AND is_deleted = 0
                     AND consecutive_failures < 3
                     {exclude_clause}
                   {order_clause}
                   LIMIT 1""",
                exclude_ids,
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_account_usage_cache(
        self,
        account_id: int,
        five_hour: Optional[float] = None,
        seven_day: Optional[float] = None,
        five_hour_resets_at: Optional[str] = None,
        seven_day_resets_at: Optional[str] = None,
    ) -> bool:
        """Update the cached usage data for an account.

        Args:
            account_id: Account ID
            five_hour: 5-hour utilization percentage (0-100)
            seven_day: 7-day utilization percentage (0-100)
            five_hour_resets_at: ISO timestamp when 5h limit resets
            seven_day_resets_at: ISO timestamp when 7d limit resets

        Returns:
            True if updated, False otherwise
        """
        import time

        updates = {"usage_cached_at": int(time.time())}
        if five_hour is not None:
            updates["cached_usage_5h"] = five_hour
        if seven_day is not None:
            updates["cached_usage_7d"] = seven_day
        if five_hour_resets_at is not None:
            updates["cached_5h_resets_at"] = five_hour_resets_at
        if seven_day_resets_at is not None:
            updates["cached_7d_resets_at"] = seven_day_resets_at

        return self.update_account(account_id, **updates)

    def record_account_error(
        self,
        account_id: int,
        error_message: str,
        increment_failures: bool = True,
    ) -> bool:
        """Record an error for an account.

        Args:
            account_id: Account ID
            error_message: Error message
            increment_failures: Whether to increment consecutive_failures

        Returns:
            True if updated, False otherwise
        """
        now = datetime.utcnow().isoformat()

        with self._writer() as conn:
            if increment_failures:
                cursor = conn.execute(
                    """UPDATE accounts SET
                        last_error = ?,
                        last_error_at = ?,
                        consecutive_failures = consecutive_failures + 1,
                        updated_at = ?
                       WHERE id = ?""",
                    (error_message, now, now, account_id),
                )
            else:
                cursor = conn.execute(
                    """UPDATE accounts SET
                        last_error = ?,
                        last_error_at = ?,
                        updated_at = ?
                       WHERE id = ?""",
                    (error_message, now, now, account_id),
                )
            return cursor.rowcount > 0

    def clear_account_errors(self, account_id: int) -> bool:
        """Clear error state for an account (on successful use).

        Args:
            account_id: Account ID

        Returns:
            True if updated, False otherwise
        """
        now = datetime.utcnow().isoformat()

        with self._writer() as conn:
            cursor = conn.execute(
                """UPDATE accounts SET
                    last_error = NULL,
                    last_error_at = NULL,
                    consecutive_failures = 0,
                    last_used_at = ?,
                    updated_at = ?
                   WHERE id = ?""",
                (now, now, account_id),
            )
            return cursor.rowcount > 0

    # =========================================================================
    # Log Operations
    # =========================================================================

    def log(
        self,
        level: str,
        category: str,
        event: str,
        message: str,
        project_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> int:
        """Insert a log entry.

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR)
            category: Event category (auth, loop, run, iteration, system)
            event: Specific event (login, created, started, completed, failed, etc.)
            message: Human-readable log message
            project_id: Associated project ID (optional)
            run_id: Associated run ID (optional)
            metadata: Additional structured data as dict (optional)

        Returns:
            The ID of the inserted log entry
        """
        with self._writer() as conn:
            cursor = conn.execute(
                """INSERT INTO logs (level, category, event, message, project_id, run_id, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    level,
                    category,
                    event,
                    message,
                    project_id,
                    run_id,
                    json.dumps(metadata) if metadata else None,
                ),
            )
            return cursor.lastrowid

    def get_logs(
        self,
        level: Optional[str] = None,
        category: Optional[str] = None,
        event: Optional[str] = None,
        project_id: Optional[str] = None,
        run_id: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Query logs with filters. Returns newest first.

        Args:
            level: Filter by log level
            category: Filter by category
            event: Filter by event type
            project_id: Filter by project
            run_id: Filter by run
            since: Only logs after this timestamp
            until: Only logs before this timestamp
            limit: Max rows to return (default 100)
            offset: Rows to skip for pagination

        Returns:
            List of log entry dicts
        """
        conditions = []
        params: list[Any] = []

        if level:
            conditions.append("level = ?")
            params.append(level)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if event:
            conditions.append("event = ?")
            params.append(event)
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if run_id:
            conditions.append("run_id = ?")
            params.append(run_id)
        if since:
            conditions.append("timestamp >= ?")
            params.append(since.isoformat() if isinstance(since, datetime) else since)
        if until:
            conditions.append("timestamp <= ?")
            params.append(until.isoformat() if isinstance(until, datetime) else until)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.extend([limit, offset])

        with self._reader() as conn:
            cursor = conn.execute(
                f"""SELECT id, level, category, event, message, project_id, run_id,
                           metadata, timestamp
                    FROM logs
                    WHERE {where_clause}
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?""",
                params,
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "level": row[1],
                    "category": row[2],
                    "event": row[3],
                    "message": row[4],
                    "project_id": row[5],
                    "run_id": row[6],
                    "metadata": self._parse_metadata(row[7]),
                    "timestamp": row[8],
                }
                for row in rows
            ]

    def get_log_stats(self) -> dict:
        """Get log statistics.

        Returns:
            Dict with counts by level, category, and recent error count
        """
        with self._reader() as conn:
            # Count by level
            cursor = conn.execute(
                "SELECT level, COUNT(*) FROM logs GROUP BY level"
            )
            by_level = {row[0]: row[1] for row in cursor.fetchall()}

            # Count by category
            cursor = conn.execute(
                "SELECT category, COUNT(*) FROM logs GROUP BY category"
            )
            by_category = {row[0]: row[1] for row in cursor.fetchall()}

            # Recent errors (last 24 hours)
            cursor = conn.execute(
                """SELECT COUNT(*) FROM logs
                   WHERE level = 'ERROR'
                   AND timestamp >= datetime('now', '-1 day')"""
            )
            recent_errors = cursor.fetchone()[0]

            # Total count
            cursor = conn.execute("SELECT COUNT(*) FROM logs")
            total = cursor.fetchone()[0]

            return {
                "total": total,
                "by_level": by_level,
                "by_category": by_category,
                "recent_errors_24h": recent_errors,
            }

    def count_logs(
        self,
        level: Optional[str] = None,
        category: Optional[str] = None,
        event: Optional[str] = None,
        project_id: Optional[str] = None,
        run_id: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> int:
        """Count logs matching the given filters.

        Args:
            level: Filter by log level
            category: Filter by category
            event: Filter by event type
            project_id: Filter by project
            run_id: Filter by run
            since: Only logs after this timestamp
            until: Only logs before this timestamp

        Returns:
            Count of matching log entries
        """
        conditions = []
        params: list[Any] = []

        if level:
            conditions.append("level = ?")
            params.append(level)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if event:
            conditions.append("event = ?")
            params.append(event)
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if run_id:
            conditions.append("run_id = ?")
            params.append(run_id)
        if since:
            conditions.append("timestamp >= ?")
            params.append(since.isoformat() if isinstance(since, datetime) else since)
        if until:
            conditions.append("timestamp <= ?")
            params.append(until.isoformat() if isinstance(until, datetime) else until)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with self._reader() as conn:
            cursor = conn.execute(
                f"SELECT COUNT(*) FROM logs WHERE {where_clause}",
                params,
            )
            return cursor.fetchone()[0]

    def cleanup_old_logs(self, days: int = 30) -> int:
        """Delete logs older than N days.

        Args:
            days: Delete logs older than this many days (default 30)

        Returns:
            Number of rows deleted
        """
        with self._writer() as conn:
            cursor = conn.execute(
                "DELETE FROM logs WHERE timestamp < datetime('now', ?)",
                (f"-{days} days",),
            )
            return cursor.rowcount

    # =========================================================================
    # Backup Operations
    # =========================================================================

    def backup(self, backup_path: Optional[str] = None) -> Path:
        """Create a backup of the database.

        Args:
            backup_path: Custom backup path. Defaults to ~/.ralphx/backups/

        Returns:
            Path to the backup file.
        """
        if backup_path is None:
            backup_dir = get_backups_path()
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_path = str(backup_dir / f"ralphx_{timestamp}.db")

        # Use SQLite backup API for consistent backup
        with self._reader() as conn:
            backup_conn = sqlite3.connect(backup_path)
            conn.backup(backup_conn)
            backup_conn.close()

        # Set restrictive permissions on backup
        os.chmod(backup_path, 0o600)

        return Path(backup_path)

    def vacuum(self) -> None:
        """Vacuum the database to reclaim space."""
        with self._writer() as conn:
            conn.execute("VACUUM")

    # =========================================================================
    # Migration Support
    # =========================================================================

    def get_schema_version(self) -> int:
        """Get the current schema version."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
            )
            row = cursor.fetchone()
            return row[0] if row else 0

    def migrate(self) -> None:
        """Run any pending migrations."""
        current_version = self.get_schema_version()

        # Define migrations as (version, sql) tuples
        migrations: list[tuple[int, str]] = [
            # Migration to v2: Add item provenance and claiming columns
            # NOTE: For new databases (created at SCHEMA_VERSION >= 7), these columns
            # already exist in the initial schema with correct names. The migration
            # only runs for databases created before v7.
            # Indexes are idempotent (IF NOT EXISTS).
            (2, """
                CREATE INDEX IF NOT EXISTS idx_work_items_claimed
                    ON work_items(project_id, claimed_by, claimed_at);
            """),
            # Migration to v3: (Legacy - credentials table removed)
            (3, """SELECT 1;"""),
            # Migration to v4: (Legacy - credentials table removed)
            (4, """SELECT 1;"""),
            # Migration to v5: Add category and event columns to logs for structured logging
            (5, """
                -- Add category and event columns for structured logging
                ALTER TABLE logs ADD COLUMN category TEXT DEFAULT 'system';
                ALTER TABLE logs ADD COLUMN event TEXT DEFAULT 'log';
                ALTER TABLE logs ADD COLUMN project_id TEXT;

                -- Indexes for common query patterns
                CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_logs_category ON logs(category);
                CREATE INDEX IF NOT EXISTS idx_logs_project ON logs(project_id);

                -- Composite index for category+event queries (e.g., all auth.login events)
                CREATE INDEX IF NOT EXISTS idx_logs_cat_event ON logs(category, event, timestamp DESC);

                -- Composite index for run drilldown (all logs for a run, ordered)
                CREATE INDEX IF NOT EXISTS idx_logs_run_time ON logs(run_id, timestamp);
            """),
            # Migration to v6: (Legacy - credentials table removed)
            (6, """SELECT 1;"""),
            # Migration to v7: Rename source_loop to namespace for clarity
            # NOTE: For databases created after this migration was added, the column
            # is already named 'namespace' in the initial schema. This migration only
            # applies to databases created before the schema was updated.
            # We make this idempotent by just ensuring the index exists.
            (7, """
                -- Drop old index if it exists (for databases migrating from source_loop)
                DROP INDEX IF EXISTS idx_work_items_source_loop;

                -- Ensure the namespace index exists (works whether column is source_loop or namespace)
                CREATE INDEX IF NOT EXISTS idx_work_items_namespace
                    ON work_items(project_id, namespace, status);
            """),
            # Migration to v8: Remove FOREIGN KEY on run_id in logs table
            # Runs exist in project databases, not the global database, so the FK
            # constraint was causing failures when logging run events.
            (8, """
                -- Recreate logs table without FK constraint on run_id
                CREATE TABLE IF NOT EXISTS logs_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
                    run_id TEXT,
                    level TEXT NOT NULL,
                    category TEXT DEFAULT 'system',
                    event TEXT DEFAULT 'log',
                    message TEXT NOT NULL,
                    metadata TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                -- Explicitly map columns (old schema may not have all columns)
                INSERT INTO logs_new (id, project_id, run_id, level, category, event, message, metadata, timestamp)
                    SELECT id, project_id, run_id, level, category, event, message, metadata, timestamp FROM logs;
                DROP TABLE logs;
                ALTER TABLE logs_new RENAME TO logs;

                -- Recreate indexes on logs
                CREATE INDEX IF NOT EXISTS idx_logs_project ON logs(project_id);
                CREATE INDEX IF NOT EXISTS idx_logs_run ON logs(run_id);
                CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_logs_category ON logs(category);
                CREATE INDEX IF NOT EXISTS idx_logs_cat_event ON logs(category, event, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_logs_run_time ON logs(run_id, timestamp);
            """),
            # Migration to v9: Add multi-account authentication tables
            # accounts: stores all logged-in Claude accounts
            # project_account_assignments: links projects to accounts
            (9, """
                -- Create accounts table
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    expires_at INTEGER NOT NULL,
                    scopes TEXT,
                    subscription_type TEXT,
                    rate_limit_tier TEXT,
                    is_default BOOLEAN DEFAULT FALSE,
                    is_active BOOLEAN DEFAULT TRUE,
                    is_deleted BOOLEAN DEFAULT FALSE,
                    last_used_at TIMESTAMP,
                    cached_usage_5h REAL,
                    cached_usage_7d REAL,
                    cached_5h_resets_at TEXT,
                    cached_7d_resets_at TEXT,
                    usage_cached_at INTEGER,
                    last_error TEXT,
                    last_error_at TIMESTAMP,
                    consecutive_failures INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Create project account assignments table
                CREATE TABLE IF NOT EXISTS project_account_assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
                    allow_fallback BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(project_id)
                );

                -- Indexes for accounts
                CREATE INDEX IF NOT EXISTS idx_accounts_active ON accounts(is_active, is_deleted);
                CREATE INDEX IF NOT EXISTS idx_accounts_email ON accounts(email);

                -- Indexes for project account assignments
                CREATE INDEX IF NOT EXISTS idx_assignments_project ON project_account_assignments(project_id);
                CREATE INDEX IF NOT EXISTS idx_assignments_account ON project_account_assignments(account_id);

                -- Partial unique index: enforce single default account among active, non-deleted accounts
                -- SQLite supports partial indexes via WHERE clause
                CREATE UNIQUE INDEX IF NOT EXISTS idx_single_default
                    ON accounts (is_default) WHERE is_default = 1 AND is_deleted = 0;

                -- Drop legacy credentials table if it exists
                DROP TABLE IF EXISTS credentials;
            """),
        ]

        with self._writer() as conn:
            for version, sql in migrations:
                if version > current_version:
                    conn.executescript(sql)
                    conn.execute(
                        "INSERT INTO schema_version (version) VALUES (?)",
                        (version,),
                    )
