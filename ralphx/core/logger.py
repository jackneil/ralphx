"""Triple-write logger for RalphX.

Provides structured logging that writes to:
- stdout (for real-time terminal viewing)
- SQLite database (for UI viewing and querying)
- Rotating log file (for MCP-style tailing via API)

Usage:
    from ralphx.core.logger import auth_log, run_log, system_log

    auth_log.info("login", "User logged in", scope="global", email="user@example.com")
    run_log.error("failed", "Run failed", run_id="abc123", error="timeout")
    system_log.info("startup", "Server started", version="0.1.0")
"""

import json
import logging
import re
import sys
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import ClassVar, Optional

from ralphx.core.database import Database
from ralphx.core.workspace import get_logs_path

# Sanitize strings to prevent log injection (strip control chars)
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")

# Maximum message length to prevent memory/storage issues (64KB)
MAX_MESSAGE_LENGTH = 65536

# File logging configuration
LOG_FILE_NAME = "ralphx.log"
LOG_FILE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB max per file
LOG_FILE_BACKUP_COUNT = 3  # Keep 3 backup files (total 40 MB max)


def _get_log_file_path() -> Path:
    """Get the path to the main log file."""
    logs_dir = get_logs_path()
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / LOG_FILE_NAME


def get_log_file_path() -> Path:
    """Public interface to get the log file path for API tailing."""
    return _get_log_file_path()


def _sanitize(s: str, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    """Remove control characters and truncate to prevent issues.

    Args:
        s: String to sanitize.
        max_length: Maximum length (default 64KB). 0 = no limit.

    Returns:
        Sanitized and potentially truncated string.
    """
    if not s:
        return s
    result = _CONTROL_CHARS.sub("", s)
    if max_length > 0 and len(result) > max_length:
        result = result[:max_length] + "... [truncated]"
    return result


class RalphLogger:
    """Logger that writes to stdout, database, and rotating log file.

    - INFO/WARNING/ERROR go to stdout, DB, and file
    - DEBUG goes only to stdout (reduce DB/file noise)
    - DB/file write failures are caught and logged to stderr (never crash caller)
    """

    _db: ClassVar[Optional[Database]] = None  # Shared DB connection
    _db_lock: ClassVar[threading.Lock] = threading.Lock()  # Thread-safe init
    _file_handler: ClassVar[Optional[RotatingFileHandler]] = None  # Shared file handler
    _file_lock: ClassVar[threading.Lock] = threading.Lock()  # Thread-safe file init

    def __init__(self, category: str):
        """Create a logger for a specific category.

        Args:
            category: Event category (auth, loop, run, iteration, system)
        """
        self.category = category
        self._stdout = logging.getLogger(f"ralphx.{category}")

    @classmethod
    def _get_db(cls) -> Database:
        """Lazy-load shared database connection (thread-safe)."""
        if cls._db is None:
            with cls._db_lock:
                # Double-check pattern to avoid lock on every call
                if cls._db is None:
                    cls._db = Database()
        return cls._db

    @classmethod
    def _get_file_handler(cls) -> RotatingFileHandler:
        """Lazy-load shared rotating file handler (thread-safe)."""
        if cls._file_handler is None:
            with cls._file_lock:
                # Double-check pattern to avoid lock on every call
                if cls._file_handler is None:
                    log_path = _get_log_file_path()
                    cls._file_handler = RotatingFileHandler(
                        log_path,
                        maxBytes=LOG_FILE_MAX_BYTES,
                        backupCount=LOG_FILE_BACKUP_COUNT,
                        encoding="utf-8",
                    )
        return cls._file_handler

    def info(self, event: str, message: str, **context) -> None:
        """Log an INFO level message.

        Args:
            event: Specific event type (login, created, started, etc.)
            message: Human-readable message
            **context: Additional context (project_id, run_id, or any metadata)
        """
        self._write("INFO", event, message, context)

    def warning(self, event: str, message: str, **context) -> None:
        """Log a WARNING level message.

        Args:
            event: Specific event type
            message: Human-readable message
            **context: Additional context
        """
        self._write("WARNING", event, message, context)

    def error(self, event: str, message: str, **context) -> None:
        """Log an ERROR level message.

        Args:
            event: Specific event type
            message: Human-readable message
            **context: Additional context
        """
        self._write("ERROR", event, message, context)

    def debug(self, event: str, message: str, **context) -> None:
        """Log a DEBUG level message (stdout only, not stored in DB).

        Args:
            event: Specific event type
            message: Human-readable message
            **context: Additional context (not stored)
        """
        # Debug only goes to stdout, not DB (reduce noise)
        self._stdout.debug(f"[{_sanitize(event, max_length=100)}] {_sanitize(message)}")

    def _write(self, level: str, event: str, message: str, context: dict) -> None:
        """Write log to stdout, database, and rotating file.

        Args:
            level: Log level (INFO, WARNING, ERROR)
            event: Event type
            message: Log message
            context: Additional context dict
        """
        # Sanitize inputs to prevent log injection
        # Event names should be short identifiers (max 100 chars)
        event = _sanitize(event, max_length=100)
        message = _sanitize(message)  # Uses default MAX_MESSAGE_LENGTH

        # Stdout logging
        self._stdout.log(getattr(logging, level), f"[{event}] {message}")

        # Extract indexed fields from context, rest goes to metadata
        project_id = context.pop("project_id", None)
        run_id = context.pop("run_id", None)

        # File logging (JSON lines format for easy parsing)
        try:
            timestamp = datetime.utcnow().isoformat() + "Z"
            log_entry = {
                "timestamp": timestamp,
                "level": level,
                "category": self.category,
                "event": event,
                "message": message,
            }
            if project_id:
                log_entry["project_id"] = project_id
            if run_id:
                log_entry["run_id"] = run_id
            if context:
                log_entry["metadata"] = context

            file_handler = self._get_file_handler()
            # Use handler's acquire/release for thread safety during write
            # This ensures proper locking and rotation handling
            log_line = json.dumps(log_entry, ensure_ascii=False) + "\n"
            log_line_bytes = len(log_line.encode("utf-8"))
            file_handler.acquire()
            try:
                # Check if rotation is needed by checking current file size
                # We do this manually since we're not using emit()
                if file_handler.maxBytes > 0:
                    file_handler.stream.seek(0, 2)  # Seek to end
                    if file_handler.stream.tell() + log_line_bytes >= file_handler.maxBytes:
                        file_handler.doRollover()
                file_handler.stream.write(log_line)
                file_handler.stream.flush()
            finally:
                file_handler.release()
        except Exception as e:
            # Never let file logging failures crash the application
            print(f"[LOG FILE ERROR] {e}", file=sys.stderr)

        try:
            self._get_db().log(
                level=level,
                category=self.category,
                event=event,
                message=message,
                project_id=project_id,
                run_id=run_id,
                metadata=context if context else None,
            )
        except Exception as e:
            # Never let logging failures crash the application
            print(f"[LOG DB ERROR] {e}", file=sys.stderr)


# Pre-built loggers (shared DB connection via class variable)
auth_log = RalphLogger("auth")
loop_log = RalphLogger("loop")
run_log = RalphLogger("run")
iteration_log = RalphLogger("iteration")
system_log = RalphLogger("system")
