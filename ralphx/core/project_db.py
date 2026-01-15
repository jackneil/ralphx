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
PROJECT_SCHEMA_VERSION = 1

# Project database schema - all project-specific data
PROJECT_SCHEMA_SQL = """
-- Loops table
CREATE TABLE IF NOT EXISTS loops (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    config_yaml TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Runs table
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
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
    iteration INTEGER NOT NULL,
    mode TEXT,
    started_at TIMESTAMP,
    duration_seconds REAL,
    status TEXT,
    items_added TEXT
);

-- Work items table
CREATE TABLE IF NOT EXISTS work_items (
    id TEXT PRIMARY KEY,
    priority INTEGER,
    content TEXT NOT NULL,
    title TEXT,
    status TEXT DEFAULT 'pending',
    category TEXT,
    tags TEXT,
    metadata TEXT,
    source_loop TEXT,
    item_type TEXT DEFAULT 'item',
    claimed_by TEXT,
    claimed_at TIMESTAMP,
    processed_at TIMESTAMP,
    phase_1_group BOOLEAN DEFAULT FALSE,
    phase_1_order INTEGER,
    -- Phase and dependency fields
    dependencies TEXT,  -- JSON array of item IDs
    phase INTEGER,      -- Assigned phase number
    duplicate_of TEXT,  -- Parent item ID if DUPLICATE status
    skip_reason TEXT,   -- Reason if SKIPPED status
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
"""

PROJECT_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_work_items_status ON work_items(status);
CREATE INDEX IF NOT EXISTS idx_work_items_category ON work_items(category);
CREATE INDEX IF NOT EXISTS idx_work_items_priority ON work_items(priority);
CREATE INDEX IF NOT EXISTS idx_work_items_created ON work_items(created_at);
CREATE INDEX IF NOT EXISTS idx_work_items_source_loop ON work_items(source_loop, status);
CREATE INDEX IF NOT EXISTS idx_work_items_claimed ON work_items(claimed_by, claimed_at);
CREATE INDEX IF NOT EXISTS idx_work_items_phase_1 ON work_items(phase_1_group, phase_1_order);
CREATE INDEX IF NOT EXISTS idx_sessions_run ON sessions(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_guardrails_enabled ON guardrails(enabled);
CREATE INDEX IF NOT EXISTS idx_guardrails_source ON guardrails(source);
CREATE INDEX IF NOT EXISTS idx_logs_run ON logs(run_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level, timestamp);
CREATE INDEX IF NOT EXISTS idx_input_files_loop ON input_files(loop_name);
CREATE INDEX IF NOT EXISTS idx_resources_type ON resources(resource_type);
CREATE INDEX IF NOT EXISTS idx_resources_enabled ON resources(enabled);
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
            conn.executescript(PROJECT_SCHEMA_SQL)
            conn.executescript(PROJECT_INDEXES_SQL)

            cursor = conn.execute(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (PROJECT_SCHEMA_VERSION,),
                )

    # ========== Loops ==========

    def create_loop(self, id: str, name: str, config_yaml: str) -> dict:
        """Create a loop configuration."""
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            conn.execute(
                """
                INSERT INTO loops (id, name, config_yaml, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (id, name, config_yaml, now, now),
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

    def create_run(self, id: str, loop_name: str) -> dict:
        """Create a new run."""
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            conn.execute(
                """
                INSERT INTO runs (id, loop_name, status, started_at)
                VALUES (?, ?, 'running', ?)
                """,
                (id, loop_name, now),
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
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """List runs with optional filters."""
        with self._reader() as conn:
            query = "SELECT * FROM runs WHERE 1=1"
            params: list[Any] = []

            if loop_name:
                query += " AND loop_name = ?"
                params.append(loop_name)
            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY started_at DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    _RUN_UPDATE_COLS = frozenset({
        "status", "completed_at", "iterations_completed",
        "items_generated", "error_message"
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
    ) -> dict:
        """Create a new session."""
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            conn.execute(
                """
                INSERT INTO sessions (session_id, run_id, iteration, mode, started_at, status)
                VALUES (?, ?, ?, ?, ?, 'running')
                """,
                (session_id, run_id, iteration, mode, now),
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

    # ========== Work Items ==========

    def create_work_item(
        self,
        id: str,
        content: str,
        title: Optional[str] = None,
        priority: Optional[int] = None,
        category: Optional[str] = None,
        source_loop: Optional[str] = None,
        item_type: str = "item",
        metadata: Optional[dict] = None,
        dependencies: Optional[list[str]] = None,
        phase: Optional[int] = None,
        status: str = "pending",
    ) -> dict:
        """Create a work item."""
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            metadata_json = json.dumps(metadata) if metadata else None
            dependencies_json = json.dumps(dependencies) if dependencies else None
            conn.execute(
                """
                INSERT INTO work_items
                (id, content, title, priority, category, source_loop, item_type,
                 metadata, dependencies, phase, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (id, content, title, priority, category, source_loop, item_type,
                 metadata_json, dependencies_json, phase, status, now, now),
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
        source_loop: Optional[str] = None,
        phase_1_group: Optional[bool] = None,
        unclaimed_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """List work items with optional filters.

        Args:
            status: Filter by status.
            category: Filter by category.
            source_loop: Filter by source loop.
            phase_1_group: Filter by Phase 1 grouping.
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
            if source_loop:
                conditions.append("source_loop = ?")
                params.append(source_loop)
            if phase_1_group is not None:
                conditions.append("phase_1_group = ?")
                params.append(phase_1_group)
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
        "source_loop", "item_type", "claimed_by", "claimed_at", "processed_at",
        "phase_1_group", "phase_1_order", "dependencies", "phase", "duplicate_of",
        "skip_reason", "updated_at"
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

            # By status
            cursor = conn.execute(
                "SELECT status, COUNT(*) as count FROM work_items GROUP BY status"
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
        """Release a claimed work item back to unclaimed state.

        Items from generator loops (with source_loop set) are restored to 'completed'
        status so they can be picked up by consumer loops again.
        Items without source_loop are restored to 'pending'.
        """
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            # Use CASE to restore appropriate status based on whether item came from a generator loop
            cursor = conn.execute(
                """
                UPDATE work_items
                SET claimed_by = NULL,
                    claimed_at = NULL,
                    status = CASE WHEN source_loop IS NOT NULL THEN 'completed' ELSE 'pending' END,
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

    def release_stale_claims(self, max_age_minutes: int = 30) -> int:
        """Release claims that have been held too long (likely crashed consumer).

        Items from generator loops (with source_loop set) are restored to 'completed'
        status so they can be picked up by consumer loops again.
        Items without source_loop are restored to 'pending'.

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
                    status = CASE WHEN source_loop IS NOT NULL THEN 'completed' ELSE 'pending' END,
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
        Items from generator loops (with source_loop set) are restored to 'completed'
        status so they can be picked up by consumer loops again.
        Items without source_loop are restored to 'pending'.

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
                    status = CASE WHEN source_loop IS NOT NULL THEN 'completed' ELSE 'pending' END,
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

        Items from generator loops (with source_loop set) are restored to 'completed'
        status so they can be picked up by consumer loops again.
        Items without source_loop are restored to 'pending'.

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
                    status = CASE WHEN source_loop IS NOT NULL THEN 'completed' ELSE 'pending' END,
                    updated_at = ?
                WHERE id = ? AND claimed_by = ? AND status = 'claimed'
                """,
                (now, id, claimed_by),
            )
            return cursor.rowcount > 0

    def get_source_item_counts(self) -> dict[str, int]:
        """Get counts of completed items grouped by source_loop.

        Used for dashboard to show available items per producer loop.

        Returns:
            Dictionary mapping source_loop name to count of completed items.
        """
        with self._reader() as conn:
            cursor = conn.execute(
                """
                SELECT source_loop, COUNT(*) as count
                FROM work_items
                WHERE status = 'completed' AND source_loop IS NOT NULL
                GROUP BY source_loop
                """
            )
            return {row["source_loop"]: row["count"] for row in cursor.fetchall()}

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

    def mark_items_phase_1(self, item_ids: list[str], orders: Optional[dict[str, int]] = None) -> int:
        """Mark items as part of Phase 1 group."""
        with self._writer() as conn:
            count = 0
            for item_id in item_ids:
                order = orders.get(item_id) if orders else None
                cursor = conn.execute(
                    """
                    UPDATE work_items
                    SET phase_1_group = TRUE, phase_1_order = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (order, datetime.utcnow().isoformat(), item_id),
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
