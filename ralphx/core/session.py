"""Session management for RalphX.

Implements:
- SessionManager for tracking sessions in SQLite
- SessionTailer for tail -f style watching of session files
- Session discovery and registration
"""

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from ralphx.core.project_db import ProjectDatabase
from ralphx.models.session import Session


class SessionEventType(str, Enum):
    """Types of events from session files."""

    INIT = "init"
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    COMPLETE = "complete"
    UNKNOWN = "unknown"


@dataclass
class SessionEvent:
    """Event parsed from a session file."""

    type: SessionEventType
    timestamp: datetime = field(default_factory=datetime.utcnow)
    text: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    tool_result: Optional[str] = None
    error_message: Optional[str] = None
    raw_data: dict = field(default_factory=dict)


class SessionManager:
    """Manages session tracking and lookup.

    Features:
    - Register sessions from Claude CLI stream-json output
    - Look up sessions by ID, run, or project
    - Discover sessions by timing (fallback)
    - Track session metadata

    Note: Works with ProjectDatabase (project-scoped sessions).
    """

    def __init__(self, db: ProjectDatabase):
        """Initialize the session manager.

        Args:
            db: ProjectDatabase instance for the specific project.
        """
        self.db = db

    def register_session(
        self,
        session_id: str,
        run_id: Optional[str] = None,
        iteration: int = 1,
        mode: Optional[str] = None,
        status: str = "active",
        project_id: Optional[str] = None,  # Kept for backward compatibility, but ignored
    ) -> Session:
        """Register a new session.

        Args:
            session_id: Claude session UUID.
            run_id: Parent run ID (if any).
            iteration: Iteration number.
            mode: Mode used for this iteration.
            status: Session status.
            project_id: Deprecated - ignored since db is already project-scoped.

        Returns:
            Created Session object.
        """
        self.db.create_session(
            session_id=session_id,
            run_id=run_id,
            iteration=iteration,
            mode=mode,
        )

        return Session(
            session_id=session_id,
            project_id=project_id or "",  # For backward compatibility
            run_id=run_id,
            iteration=iteration,
            mode=mode,
            status=status,
        )

    def update_session(
        self,
        session_id: str,
        status: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        items_added: Optional[list[str]] = None,
    ) -> bool:
        """Update session metadata.

        Args:
            session_id: Session to update.
            status: New status.
            duration_seconds: Total duration.
            items_added: IDs of items added.

        Returns:
            True if updated.
        """
        return self.db.update_session(
            session_id=session_id,
            status=status,
            duration_seconds=duration_seconds,
            items_added=items_added,
        )

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID.

        Args:
            session_id: Session UUID.

        Returns:
            Session or None.
        """
        data = self.db.get_session(session_id)
        if data:
            return Session.from_dict(data)
        return None

    def list_sessions(
        self,
        run_id: Optional[str] = None,
        limit: int = 100,
        project_id: Optional[str] = None,  # Kept for backward compatibility, but ignored
    ) -> list[Session]:
        """List sessions for the project or a specific run.

        Args:
            run_id: Optional run ID to filter by.
            limit: Max sessions to return.
            project_id: Deprecated - ignored since db is already project-scoped.

        Returns:
            List of Session objects.
        """
        sessions = self.db.list_sessions(
            run_id=run_id,
            limit=limit,
        )
        return [Session.from_dict(s) for s in sessions]

    def get_latest_session(
        self,
        run_id: Optional[str] = None,
        project_id: Optional[str] = None,  # Kept for backward compatibility, but ignored
    ) -> Optional[Session]:
        """Get the most recent session.

        Args:
            run_id: Optional run ID.
            project_id: Deprecated - ignored since db is already project-scoped.

        Returns:
            Latest Session or None.
        """
        sessions = self.list_sessions(run_id=run_id, limit=1)
        return sessions[0] if sessions else None

    def find_session_file(
        self,
        session_id: str,
        project_path: Path,
    ) -> Optional[Path]:
        """Find the session JSONL file.

        Searches Claude's session storage locations.

        Args:
            session_id: Session UUID.
            project_path: Project directory.

        Returns:
            Path to session file or None.
        """
        # Check Claude's default session directories
        claude_dir = Path.home() / ".claude"

        # Check projects hash directories
        projects_dir = claude_dir / "projects"
        if projects_dir.exists():
            for hash_dir in projects_dir.iterdir():
                if hash_dir.is_dir():
                    # Look for session file
                    session_file = hash_dir / f"{session_id}.jsonl"
                    if session_file.exists():
                        return session_file

        # Check project-specific .claude directory
        project_claude = project_path / ".claude"
        if project_claude.exists():
            session_file = project_claude / f"{session_id}.jsonl"
            if session_file.exists():
                return session_file

        return None

    def discover_recent_sessions(
        self,
        project_path: Path,
        since: Optional[datetime] = None,
        limit: int = 10,
    ) -> list[tuple[str, Path, datetime]]:
        """Discover recent sessions by file modification time.

        This is a fallback when session_id wasn't captured.

        Args:
            project_path: Project directory.
            since: Only find sessions modified after this time.
            limit: Max sessions to return.

        Returns:
            List of (session_id, path, mtime) tuples.
        """
        sessions = []
        claude_dir = Path.home() / ".claude"
        projects_dir = claude_dir / "projects"

        if not projects_dir.exists():
            return []

        # Collect all JSONL files
        for hash_dir in projects_dir.iterdir():
            if not hash_dir.is_dir():
                continue

            for jsonl_file in hash_dir.glob("*.jsonl"):
                try:
                    mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime)

                    if since and mtime < since:
                        continue

                    session_id = jsonl_file.stem
                    # Validate UUID format
                    if re.match(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$', session_id):
                        sessions.append((session_id, jsonl_file, mtime))
                except (OSError, ValueError):
                    continue

        # Sort by mtime descending and limit
        sessions.sort(key=lambda x: x[2], reverse=True)
        return sessions[:limit]


class SessionTailer:
    """Tail a session file for live updates.

    Implements a tail -f style watcher that:
    - Polls file for new content every 100ms
    - Parses JSONL entries into SessionEvents
    - Handles file deletion/truncation
    - Yields events as they appear
    """

    def __init__(
        self,
        session_path: Path,
        poll_interval: float = 0.1,
        from_beginning: bool = True,
    ):
        """Initialize the tailer.

        Args:
            session_path: Path to session JSONL file.
            poll_interval: Seconds between polls.
            from_beginning: Start from file beginning (vs end).
        """
        self.session_path = session_path
        self.poll_interval = poll_interval
        self.from_beginning = from_beginning
        self._position = 0
        self._running = False
        self._inode: Optional[int] = None

    @property
    def is_running(self) -> bool:
        """Check if tailer is active."""
        return self._running

    def stop(self) -> None:
        """Stop tailing."""
        self._running = False

    def _parse_line(self, line: str) -> Optional[SessionEvent]:
        """Parse a JSONL line into a SessionEvent.

        Args:
            line: Raw JSON line.

        Returns:
            SessionEvent or None if invalid.
        """
        try:
            data = json.loads(line)
            return self._parse_event(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def _parse_event(self, data: dict) -> SessionEvent:
        """Parse event data into a SessionEvent.

        Args:
            data: Parsed JSON data.

        Returns:
            SessionEvent.
        """
        msg_type = data.get("type", "")

        # Init event
        if msg_type == "init" or "session_id" in data:
            return SessionEvent(
                type=SessionEventType.INIT,
                raw_data=data,
            )

        # Text content
        if msg_type == "content_block_delta":
            delta = data.get("delta", {})
            if delta.get("type") == "text_delta":
                return SessionEvent(
                    type=SessionEventType.TEXT,
                    text=delta.get("text", ""),
                    raw_data=data,
                )

        # Tool call start
        if msg_type == "content_block_start":
            content = data.get("content_block", {})
            if content.get("type") == "tool_use":
                return SessionEvent(
                    type=SessionEventType.TOOL_CALL,
                    tool_name=content.get("name"),
                    tool_input=content.get("input", {}),
                    raw_data=data,
                )

        # Tool result
        if msg_type == "tool_result":
            return SessionEvent(
                type=SessionEventType.TOOL_RESULT,
                tool_name=data.get("name"),
                tool_result=data.get("result"),
                raw_data=data,
            )

        # Error
        if msg_type == "error":
            return SessionEvent(
                type=SessionEventType.ERROR,
                error_message=data.get("message"),
                raw_data=data,
            )

        # Message complete
        if msg_type == "message_stop":
            return SessionEvent(
                type=SessionEventType.COMPLETE,
                raw_data=data,
            )

        # Assistant message with content array
        if msg_type == "assistant" and "content" in data:
            content = data["content"]
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        return SessionEvent(
                            type=SessionEventType.TEXT,
                            text=block.get("text", ""),
                            raw_data=data,
                        )
                    if block.get("type") == "tool_use":
                        return SessionEvent(
                            type=SessionEventType.TOOL_CALL,
                            tool_name=block.get("name"),
                            tool_input=block.get("input", {}),
                            raw_data=data,
                        )

        return SessionEvent(
            type=SessionEventType.UNKNOWN,
            raw_data=data,
        )

    async def tail(self) -> AsyncIterator[SessionEvent]:
        """Tail the session file for events.

        Yields:
            SessionEvent objects as they appear.
        """
        self._running = True

        # Get initial file state
        if not self.session_path.exists():
            # Wait for file to appear
            while self._running and not self.session_path.exists():
                await asyncio.sleep(self.poll_interval)

            if not self._running:
                return

        # Initialize position
        if self.from_beginning:
            self._position = 0
        else:
            self._position = self.session_path.stat().st_size

        self._inode = self.session_path.stat().st_ino

        try:
            while self._running:
                # Check for file changes
                try:
                    stat = self.session_path.stat()
                except FileNotFoundError:
                    # File deleted
                    yield SessionEvent(
                        type=SessionEventType.ERROR,
                        error_message="Session file deleted",
                    )
                    break
                except PermissionError:
                    yield SessionEvent(
                        type=SessionEventType.ERROR,
                        error_message="Permission denied reading session file",
                    )
                    break

                # Check for file rotation (inode change)
                if stat.st_ino != self._inode:
                    self._position = 0
                    self._inode = stat.st_ino

                # Check for truncation
                if stat.st_size < self._position:
                    self._position = 0

                # Read new content
                if stat.st_size > self._position:
                    try:
                        with open(self.session_path, 'r') as f:
                            f.seek(self._position)
                            new_content = f.read()
                            self._position = f.tell()

                        # Parse lines
                        for line in new_content.strip().split('\n'):
                            if line:
                                event = self._parse_line(line)
                                if event:
                                    yield event

                                    # Stop if complete
                                    if event.type == SessionEventType.COMPLETE:
                                        self._running = False
                                        return

                    except (IOError, PermissionError) as e:
                        yield SessionEvent(
                            type=SessionEventType.ERROR,
                            error_message=str(e),
                        )
                        break

                await asyncio.sleep(self.poll_interval)

        finally:
            self._running = False

    def read_all(self) -> list[SessionEvent]:
        """Read all events from the file synchronously.

        Returns:
            List of SessionEvent objects.
        """
        events = []

        if not self.session_path.exists():
            return events

        try:
            with open(self.session_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        event = self._parse_line(line)
                        if event:
                            events.append(event)
        except (IOError, PermissionError):
            pass

        return events

    def get_text_content(self) -> str:
        """Get all text content from the session.

        Returns:
            Concatenated text from all TEXT events.
        """
        events = self.read_all()
        text_parts = []

        for event in events:
            if event.type == SessionEventType.TEXT and event.text:
                text_parts.append(event.text)

        return "".join(text_parts)

    def get_tool_calls(self) -> list[dict]:
        """Get all tool calls from the session.

        Returns:
            List of tool call dictionaries.
        """
        events = self.read_all()
        calls = []

        for event in events:
            if event.type == SessionEventType.TOOL_CALL:
                calls.append({
                    "name": event.tool_name,
                    "input": event.tool_input,
                })

        return calls
