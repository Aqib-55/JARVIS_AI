"""Tests for the database and memory modules."""

from memory.conversation_history import ConversationHistoryManager
from memory.task_history import TaskHistoryManager


class TestDatabaseManager:

    def test_initialization(self, db):
        assert db.is_initialized is True
        assert db.db_path.exists()

    def test_tables_created(self, db):
        with db.get_connection() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            names = {row["name"] for row in tables}
            expected = {
                "conversations", "messages", "tasks",
                "task_steps", "tool_executions",
                "user_preferences", "schema_info",
            }
            assert expected.issubset(names)


class TestTaskHistory:

    def test_create_task(self, db):
        h = TaskHistoryManager(db)
        tid = h.create_task(user_request="Create a folder", total_steps=1)
        assert tid > 0

    def test_update_task(self, db):
        h = TaskHistoryManager(db)
        tid = h.create_task(user_request="Test task")
        h.update_task(tid, status="completed", completed_steps=1)
        tasks = h.get_recent_tasks(limit=1)
        assert len(tasks) == 1
        assert tasks[0]["status"] == "completed"

    def test_recent_tasks(self, db):
        h = TaskHistoryManager(db)
        for i in range(5):
            h.create_task(user_request=f"Task {i}")
        tasks = h.get_recent_tasks(limit=3)
        assert len(tasks) == 3

    def test_save_step(self, db):
        h = TaskHistoryManager(db)
        tid = h.create_task(user_request="Test")
        h.save_step(
            task_id=tid, step_number=1, tool_name="calculator",
            arguments={"expression": "2+2"}, status="completed",
            result={"answer": 4},
        )
        details = h.get_task_details(tid)
        assert details is not None
        assert len(details["steps"]) == 1


class TestConversationHistory:

    def test_start_session(self, db):
        ch = ConversationHistoryManager(db)
        cid = ch.start_session()
        assert cid > 0

    def test_save_and_retrieve(self, db):
        ch = ConversationHistoryManager(db)
        ch.start_session()
        ch.save_message("user", "Hello")
        ch.save_message("assistant", "Hi there!")
        msgs = ch.get_session_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    def test_end_session(self, db):
        ch = ConversationHistoryManager(db)
        ch.start_session()
        ch.save_message("user", "Test")
        ch.end_session()
        assert ch.current_conversation_id is None
