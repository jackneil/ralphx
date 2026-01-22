"""Tests for RalphX session management."""

import asyncio
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ralphx.core.project_db import ProjectDatabase
from ralphx.core.session import (
    SessionEvent,
    SessionEventType,
    SessionManager,
    SessionTailer,
)
from ralphx.models.session import Session


@pytest.fixture
def db():
    """Create in-memory project database with workflow context."""
    database = ProjectDatabase(":memory:")

    # Create workflow context for tests that need it
    workflow_id = "wf-session-test"
    database.create_workflow(
        id=workflow_id,
        name="Session Test Workflow",
        status="active"
    )
    step = database.create_workflow_step(
        workflow_id=workflow_id,
        step_number=1,
        name="Test Step",
        step_type="autonomous",
        status="pending"
    )
    # Store workflow context for tests
    database._test_workflow_id = workflow_id
    database._test_step_id = step["id"]

    yield database
    database.close()


@pytest.fixture
def session_manager(db):
    """Create a session manager."""
    return SessionManager(db)


@pytest.fixture
def session_file():
    """Create a temporary session file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        yield Path(f.name)
    # Cleanup
    Path(f.name).unlink(missing_ok=True)


class TestSessionManager:
    """Test SessionManager functionality."""

    def test_register_session(self, session_manager, db):
        """Test registering a new session."""
        # Create run first for foreign key
        db.create_run(
            id="run-789",
            loop_name="research",
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
        )

        session = session_manager.register_session(
            session_id="abc-123-def-456",
            run_id="run-789",
            iteration=1,
            mode="turbo",
            status="active",
        )

        assert session.session_id == "abc-123-def-456"
        assert session.run_id == "run-789"
        assert session.iteration == 1
        assert session.mode == "turbo"

    def test_get_session(self, session_manager):
        """Test getting a session by ID."""
        session_manager.register_session(
            session_id="abc-123",
            iteration=1,
        )

        session = session_manager.get_session("abc-123")
        assert session is not None
        assert session.session_id == "abc-123"

    def test_get_session_not_found(self, session_manager):
        """Test getting non-existent session."""
        session = session_manager.get_session("not-exists")
        assert session is None

    def test_update_session(self, session_manager):
        """Test updating session metadata."""
        session_manager.register_session(
            session_id="abc-123",
            iteration=1,
        )

        result = session_manager.update_session(
            session_id="abc-123",
            status="completed",
            duration_seconds=45.5,
            items_added=["item-1", "item-2"],
        )

        assert result is True

        session = session_manager.get_session("abc-123")
        assert session.status == "completed"
        assert session.duration_seconds == 45.5
        assert session.items_added == ["item-1", "item-2"]

    def test_list_sessions_by_project(self, session_manager):
        """Test listing sessions."""
        # Create multiple sessions
        session_manager.register_session(
            session_id="sess-1",
            iteration=1,
        )
        session_manager.register_session(
            session_id="sess-2",
            iteration=2,
        )

        sessions = session_manager.list_sessions()
        assert len(sessions) == 2

    def test_list_sessions_by_run(self, session_manager, db):
        """Test listing sessions by run."""
        # Create run first
        db.create_run(
            id="run-123",
            loop_name="research",
            workflow_id=db._test_workflow_id,
            step_id=db._test_step_id,
        )

        # Create sessions for this run
        session_manager.register_session(
            session_id="sess-1",
            run_id="run-123",
            iteration=1,
        )
        session_manager.register_session(
            session_id="sess-2",
            run_id="run-123",
            iteration=2,
        )

        sessions = session_manager.list_sessions(
            run_id="run-123",
        )
        assert len(sessions) == 2

    def test_get_latest_session(self, session_manager):
        """Test getting the latest session."""
        session_manager.register_session(
            session_id="sess-1",
            iteration=1,
        )
        session_manager.register_session(
            session_id="sess-2",
            iteration=2,
        )

        latest = session_manager.get_latest_session()
        assert latest is not None
        # Latest by started_at (most recent first)
        assert latest.session_id in ("sess-1", "sess-2")

    def test_get_latest_session_empty(self, session_manager):
        """Test getting latest when no sessions exist."""
        latest = session_manager.get_latest_session()
        assert latest is None


class TestSessionTailer:
    """Test SessionTailer functionality."""

    def test_parse_init_event(self, session_file):
        """Test parsing init event."""
        with open(session_file, 'w') as f:
            f.write('{"type": "init", "session_id": "abc-123"}\n')

        tailer = SessionTailer(session_file)
        events = tailer.read_all()

        assert len(events) == 1
        assert events[0].type == SessionEventType.INIT

    def test_parse_text_delta(self, session_file):
        """Test parsing text delta event."""
        with open(session_file, 'w') as f:
            f.write('{"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}}\n')

        tailer = SessionTailer(session_file)
        events = tailer.read_all()

        assert len(events) == 1
        assert events[0].type == SessionEventType.TEXT
        assert events[0].text == "Hello"

    def test_parse_tool_call(self, session_file):
        """Test parsing tool call event."""
        data = {
            "type": "content_block_start",
            "content_block": {
                "type": "tool_use",
                "name": "Read",
                "input": {"file_path": "/test.py"},
            },
        }
        with open(session_file, 'w') as f:
            f.write(json.dumps(data) + '\n')

        tailer = SessionTailer(session_file)
        events = tailer.read_all()

        assert len(events) == 1
        assert events[0].type == SessionEventType.TOOL_CALL
        assert events[0].tool_name == "Read"
        assert events[0].tool_input == {"file_path": "/test.py"}

    def test_parse_tool_result(self, session_file):
        """Test parsing tool result event."""
        data = {
            "type": "tool_result",
            "name": "Read",
            "result": "file contents...",
        }
        with open(session_file, 'w') as f:
            f.write(json.dumps(data) + '\n')

        tailer = SessionTailer(session_file)
        events = tailer.read_all()

        assert len(events) == 1
        assert events[0].type == SessionEventType.TOOL_RESULT
        assert events[0].tool_name == "Read"
        assert events[0].tool_result == "file contents..."

    def test_parse_error(self, session_file):
        """Test parsing error event."""
        with open(session_file, 'w') as f:
            f.write('{"type": "error", "message": "Rate limited"}\n')

        tailer = SessionTailer(session_file)
        events = tailer.read_all()

        assert len(events) == 1
        assert events[0].type == SessionEventType.ERROR
        assert events[0].error_message == "Rate limited"

    def test_parse_complete(self, session_file):
        """Test parsing message stop event."""
        with open(session_file, 'w') as f:
            f.write('{"type": "message_stop"}\n')

        tailer = SessionTailer(session_file)
        events = tailer.read_all()

        assert len(events) == 1
        assert events[0].type == SessionEventType.COMPLETE

    def test_parse_unknown_event(self, session_file):
        """Test parsing unknown event type."""
        with open(session_file, 'w') as f:
            f.write('{"type": "unknown_type", "data": "foo"}\n')

        tailer = SessionTailer(session_file)
        events = tailer.read_all()

        assert len(events) == 1
        assert events[0].type == SessionEventType.UNKNOWN

    def test_parse_invalid_json(self, session_file):
        """Test handling invalid JSON."""
        with open(session_file, 'w') as f:
            f.write('not valid json\n')
            f.write('{"type": "init"}\n')

        tailer = SessionTailer(session_file)
        events = tailer.read_all()

        # Should skip invalid line and parse valid one
        assert len(events) == 1
        assert events[0].type == SessionEventType.INIT

    def test_get_text_content(self, session_file):
        """Test getting all text content."""
        with open(session_file, 'w') as f:
            f.write('{"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello "}}\n')
            f.write('{"type": "content_block_delta", "delta": {"type": "text_delta", "text": "World"}}\n')

        tailer = SessionTailer(session_file)
        text = tailer.get_text_content()

        assert text == "Hello World"

    def test_get_tool_calls(self, session_file):
        """Test getting all tool calls."""
        data1 = {
            "type": "content_block_start",
            "content_block": {
                "type": "tool_use",
                "name": "Read",
                "input": {"file_path": "/a.py"},
            },
        }
        data2 = {
            "type": "content_block_start",
            "content_block": {
                "type": "tool_use",
                "name": "Write",
                "input": {"file_path": "/b.py"},
            },
        }
        with open(session_file, 'w') as f:
            f.write(json.dumps(data1) + '\n')
            f.write(json.dumps(data2) + '\n')

        tailer = SessionTailer(session_file)
        calls = tailer.get_tool_calls()

        assert len(calls) == 2
        assert calls[0]["name"] == "Read"
        assert calls[1]["name"] == "Write"

    def test_read_empty_file(self, session_file):
        """Test reading empty file."""
        tailer = SessionTailer(session_file)
        events = tailer.read_all()
        assert len(events) == 0

    def test_read_nonexistent_file(self):
        """Test reading nonexistent file."""
        tailer = SessionTailer(Path("/nonexistent/file.jsonl"))
        events = tailer.read_all()
        assert len(events) == 0


class TestSessionTailerAsync:
    """Test SessionTailer async functionality."""

    @pytest.mark.asyncio
    async def test_tail_existing_file(self, session_file):
        """Test tailing an existing file."""
        # Write initial content
        with open(session_file, 'w') as f:
            f.write('{"type": "init", "session_id": "test"}\n')
            f.write('{"type": "message_stop"}\n')

        tailer = SessionTailer(session_file)
        events = []

        async for event in tailer.tail():
            events.append(event)

        assert len(events) == 2
        assert events[0].type == SessionEventType.INIT
        assert events[1].type == SessionEventType.COMPLETE

    @pytest.mark.asyncio
    async def test_tail_with_new_content(self, session_file):
        """Test tailing with content added during tailing."""
        # Write initial content
        with open(session_file, 'w') as f:
            f.write('{"type": "init"}\n')

        tailer = SessionTailer(session_file, poll_interval=0.05)
        events = []

        async def write_more():
            await asyncio.sleep(0.1)
            with open(session_file, 'a') as f:
                f.write('{"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}}\n')
            await asyncio.sleep(0.1)
            with open(session_file, 'a') as f:
                f.write('{"type": "message_stop"}\n')

        async def collect():
            async for event in tailer.tail():
                events.append(event)

        await asyncio.gather(write_more(), collect())

        assert len(events) == 3
        assert events[0].type == SessionEventType.INIT
        assert events[1].type == SessionEventType.TEXT
        assert events[2].type == SessionEventType.COMPLETE

    @pytest.mark.asyncio
    async def test_tail_stop(self, session_file):
        """Test stopping the tailer."""
        with open(session_file, 'w') as f:
            f.write('{"type": "init"}\n')

        tailer = SessionTailer(session_file, poll_interval=0.05)
        events = []

        async def stop_after_delay():
            await asyncio.sleep(0.1)
            tailer.stop()

        async def collect():
            async for event in tailer.tail():
                events.append(event)

        await asyncio.gather(stop_after_delay(), collect())

        assert tailer.is_running is False

    @pytest.mark.asyncio
    async def test_tail_from_end(self, session_file):
        """Test tailing from end of file."""
        # Write initial content
        with open(session_file, 'w') as f:
            f.write('{"type": "init"}\n')
            f.write('{"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Old"}}\n')

        tailer = SessionTailer(session_file, from_beginning=False, poll_interval=0.05)
        events = []

        async def write_more():
            await asyncio.sleep(0.1)
            with open(session_file, 'a') as f:
                f.write('{"type": "content_block_delta", "delta": {"type": "text_delta", "text": "New"}}\n')
                f.write('{"type": "message_stop"}\n')

        async def collect():
            async for event in tailer.tail():
                events.append(event)

        await asyncio.gather(write_more(), collect())

        # Should only see new content
        assert len(events) == 2
        assert events[0].text == "New"
        assert events[1].type == SessionEventType.COMPLETE


class TestSessionEvent:
    """Test SessionEvent dataclass."""

    def test_default_values(self):
        """Test default values."""
        event = SessionEvent(type=SessionEventType.TEXT)
        assert event.type == SessionEventType.TEXT
        assert event.text is None
        assert event.tool_name is None
        assert event.tool_input is None
        assert event.tool_result is None
        assert event.error_message is None
        assert event.raw_data == {}

    def test_with_values(self):
        """Test with custom values."""
        event = SessionEvent(
            type=SessionEventType.TOOL_CALL,
            tool_name="Read",
            tool_input={"file_path": "/test"},
            raw_data={"type": "tool_use"},
        )
        assert event.type == SessionEventType.TOOL_CALL
        assert event.tool_name == "Read"
        assert event.tool_input == {"file_path": "/test"}


class TestSessionEventType:
    """Test SessionEventType enum."""

    def test_all_types(self):
        """Test all event types exist."""
        assert SessionEventType.INIT.value == "init"
        assert SessionEventType.TEXT.value == "text"
        assert SessionEventType.TOOL_CALL.value == "tool_call"
        assert SessionEventType.TOOL_RESULT.value == "tool_result"
        assert SessionEventType.ERROR.value == "error"
        assert SessionEventType.COMPLETE.value == "complete"
        assert SessionEventType.UNKNOWN.value == "unknown"
