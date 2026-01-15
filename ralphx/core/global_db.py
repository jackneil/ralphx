"""Global database for RalphX project registry.

This database stores only project discovery information:
- Project registry (path, slug, name)
- Cached stats for fast dashboard loading
- App-wide settings

All actual project data (items, runs, sessions) lives in project-local databases.
"""

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional

from ralphx.core.workspace import get_workspace_path


# Schema version for global DB
GLOBAL_SCHEMA_VERSION = 1

# Global database schema - minimal registry only
GLOBAL_SCHEMA_SQL = """
-- Project registry (minimal, just for discovery)
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    path TEXT UNIQUE NOT NULL,
    design_doc TEXT,
    last_accessed TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cached stats for fast dashboard loading
CREATE TABLE IF NOT EXISTS project_cache (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    total_items INTEGER DEFAULT 0,
    pending_items INTEGER DEFAULT 0,
    completed_items INTEGER DEFAULT 0,
    loop_count INTEGER DEFAULT 0,
    active_runs INTEGER DEFAULT 0,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- App-wide settings
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

GLOBAL_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_projects_last_accessed ON projects(last_accessed DESC);
CREATE INDEX IF NOT EXISTS idx_projects_path ON projects(path);
"""


def get_global_database_path() -> Path:
    """Get path to global RalphX database."""
    return get_workspace_path() / "ralphx.db"


class GlobalDatabase:
    """Global database for project registry and app settings.

    This is a minimal database that only tracks:
    - Which projects exist and where they are located
    - Cached stats for quick dashboard loading
    - App-wide settings

    All actual project data lives in project-local databases.
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize global database.

        Args:
            db_path: Path to database file. Defaults to ~/.ralphx/ralphx.db.
                     Use ":memory:" for testing.
        """
        if db_path is None:
            db_path = str(get_global_database_path())

        self.db_path = db_path
        self._write_lock = threading.Lock()
        self._local = threading.local()

        # Create database file if needed
        if db_path != ":memory:" and not Path(db_path).exists():
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            Path(db_path).touch(mode=0o600)

        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            conn = sqlite3.connect(
                self.db_path,
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
            conn.executescript(GLOBAL_SCHEMA_SQL)

            # Migrate existing databases: add last_accessed if missing
            cursor = conn.execute("PRAGMA table_info(projects)")
            columns = [row[1] for row in cursor.fetchall()]
            if "last_accessed" not in columns:
                conn.execute(
                    "ALTER TABLE projects ADD COLUMN last_accessed TIMESTAMP"
                )

            # Create indexes after migration (requires last_accessed column)
            conn.executescript(GLOBAL_INDEXES_SQL)

            cursor = conn.execute(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (GLOBAL_SCHEMA_VERSION,),
                )

    # ========== Project Registry ==========

    def register_project(
        self,
        id: str,
        slug: str,
        name: str,
        path: str,
        design_doc: Optional[str] = None,
    ) -> dict:
        """Register a project in the global registry.

        Args:
            id: Unique project ID.
            slug: URL-friendly project slug.
            name: Human-readable project name.
            path: Absolute path to project directory.
            design_doc: Optional path to design document (relative to project).

        Returns:
            Created project record.
        """
        with self._writer() as conn:
            now = datetime.utcnow().isoformat()
            conn.execute(
                """
                INSERT INTO projects (id, slug, name, path, design_doc, last_accessed, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (id, slug, name, path, design_doc, now, now, now),
            )

            # Initialize empty cache
            conn.execute(
                "INSERT INTO project_cache (project_id) VALUES (?)",
                (id,),
            )

        return self.get_project(slug)

    def get_project(self, slug: str) -> Optional[dict]:
        """Get project by slug."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM projects WHERE slug = ?",
                (slug,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_project_by_id(self, id: str) -> Optional[dict]:
        """Get project by ID."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM projects WHERE id = ?",
                (id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_project_by_path(self, path: str) -> Optional[dict]:
        """Get project by filesystem path."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM projects WHERE path = ?",
                (path,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_projects(self) -> list[dict]:
        """List all registered projects, sorted by last accessed."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM projects ORDER BY last_accessed DESC NULLS LAST"
            )
            return [dict(row) for row in cursor.fetchall()]

    def update_project(self, slug: str, **kwargs) -> bool:
        """Update project fields."""
        allowed_cols = frozenset({"name", "path", "design_doc", "last_accessed", "updated_at"})
        invalid_cols = set(kwargs.keys()) - allowed_cols
        if invalid_cols:
            raise ValueError(f"Invalid columns for project update: {invalid_cols}")

        # Auto-set updated_at
        if kwargs and "updated_at" not in kwargs:
            kwargs["updated_at"] = datetime.utcnow().isoformat()

        if not kwargs:
            return False

        with self._writer() as conn:
            set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
            cursor = conn.execute(
                f"UPDATE projects SET {set_clause} WHERE slug = ?",
                (*kwargs.values(), slug),
            )
            return cursor.rowcount > 0

    def touch_project(self, slug: str) -> bool:
        """Update project's last_accessed timestamp."""
        return self.update_project(slug, last_accessed=datetime.utcnow().isoformat())

    def unregister_project(self, slug: str) -> bool:
        """Remove project from registry (does not delete project data)."""
        with self._writer() as conn:
            cursor = conn.execute(
                "DELETE FROM projects WHERE slug = ?",
                (slug,),
            )
            return cursor.rowcount > 0

    # ========== Project Cache ==========

    def update_cache(
        self,
        project_id: str,
        total_items: int = 0,
        pending_items: int = 0,
        completed_items: int = 0,
        loop_count: int = 0,
        active_runs: int = 0,
    ) -> None:
        """Update cached stats for a project."""
        with self._writer() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO project_cache
                (project_id, total_items, pending_items, completed_items,
                 loop_count, active_runs, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    total_items,
                    pending_items,
                    completed_items,
                    loop_count,
                    active_runs,
                    datetime.utcnow().isoformat(),
                ),
            )

    def get_cache(self, project_id: str) -> Optional[dict]:
        """Get cached stats for a project."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT * FROM project_cache WHERE project_id = ?",
                (project_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_projects_with_cache(self) -> list[dict]:
        """Get all projects with their cached stats."""
        with self._reader() as conn:
            cursor = conn.execute(
                """
                SELECT p.*,
                       c.total_items, c.pending_items, c.completed_items,
                       c.loop_count, c.active_runs, c.cached_at
                FROM projects p
                LEFT JOIN project_cache c ON p.id = c.project_id
                ORDER BY p.last_accessed DESC NULLS LAST
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    # ========== Settings ==========

    def get_setting(self, key: str) -> Optional[str]:
        """Get an app setting."""
        with self._reader() as conn:
            cursor = conn.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            )
            row = cursor.fetchone()
            return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        """Set an app setting."""
        with self._writer() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )

    def delete_setting(self, key: str) -> bool:
        """Delete an app setting."""
        with self._writer() as conn:
            cursor = conn.execute(
                "DELETE FROM settings WHERE key = ?",
                (key,),
            )
            return cursor.rowcount > 0

    # ========== Cleanup ==========

    def cleanup_stale_projects(self, dry_run: bool = True) -> list[str]:
        """Find and optionally remove projects whose paths no longer exist.

        Args:
            dry_run: If True, only return stale slugs without deleting.

        Returns:
            List of stale project slugs.
        """
        projects = self.list_projects()
        stale_slugs = []

        for project in projects:
            if not Path(project["path"]).exists():
                stale_slugs.append(project["slug"])

        if not dry_run:
            for slug in stale_slugs:
                self.unregister_project(slug)

        return stale_slugs

    def close(self) -> None:
        """Close database connection."""
        if hasattr(self._local, "connection") and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
