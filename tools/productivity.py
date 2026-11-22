"""
Productivity tools for JARVIS AI.

Provides notes management, reminders, todo task lists, and text summarization.
"""

import logging
import sqlite3
from datetime import datetime
from typing import Any

from config.settings import settings
from tools import PermissionLevel, ToolCategory, ToolDefinition, ToolParameter, ToolResult

logger = logging.getLogger(__name__)


def _get_db_conn() -> sqlite3.Connection:
    """Get a database connection for productivity data."""
    conn = sqlite3.connect(str(settings.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Ensure tables exist
    conn.execute("""
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        tags TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reminder_text TEXT NOT NULL,
        due_at TEXT,
        status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'completed', 'dismissed')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS todo_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_text TEXT NOT NULL,
        priority TEXT DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high')),
        status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'completed')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    )
    """)
    conn.commit()
    return conn


def manage_notes(action: str, title: str = "", content: str = "", note_id: int | None = None) -> ToolResult:
    """
    Manage user notes.

    Actions:
    - 'create': Create a new note (requires title and content).
    - 'list': List all existing notes.
    - 'read': Read a note by title or note_id.
    - 'delete': Delete a note by note_id or title.
    """
    clean_action = action.strip().lower()
    try:
        with _get_db_conn() as conn:
            if clean_action == "create":
                if not title or not content:
                    return ToolResult(success=False, error="Title and content are required to create a note.")
                cursor = conn.execute(
                    "INSERT INTO notes (title, content) VALUES (?, ?)",
                    (title.strip(), content.strip()),
                )
                conn.commit()
                return ToolResult(
                    success=True,
                    result={"message": f"Note '{title}' saved successfully.", "note_id": cursor.lastrowid},
                )

            elif clean_action == "list":
                rows = conn.execute("SELECT id, title, created_at FROM notes ORDER BY updated_at DESC").fetchall()
                notes = [dict(r) for r in rows]
                return ToolResult(success=True, result={"notes": notes, "count": len(notes)})

            elif clean_action == "read":
                if note_id:
                    row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
                elif title:
                    row = conn.execute("SELECT * FROM notes WHERE title LIKE ? LIMIT 1", (f"%{title}%",)).fetchone()
                else:
                    return ToolResult(success=False, error="Specify title or note_id to read a note.")

                if not row:
                    return ToolResult(success=False, error="Note not found.")
                return ToolResult(success=True, result=dict(row))

            elif clean_action == "delete":
                if note_id:
                    conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
                elif title:
                    conn.execute("DELETE FROM notes WHERE title = ?", (title,))
                else:
                    return ToolResult(success=False, error="Specify note_id or title to delete.")
                conn.commit()
                return ToolResult(success=True, result={"message": "Note deleted successfully."})

            else:
                return ToolResult(success=False, error=f"Unknown action: '{action}'. Use: create, list, read, delete.")
    except Exception as e:
        logger.error("Notes tool error: %s", e)
        return ToolResult(success=False, error=f"Notes error: {e}")


def manage_reminders(action: str, text: str = "", due_at: str = "", reminder_id: int | None = None) -> ToolResult:
    """
    Manage reminders.

    Actions:
    - 'add': Add a new reminder (requires text).
    - 'list': List active/pending reminders.
    - 'complete': Mark a reminder as completed by reminder_id.
    - 'delete': Delete a reminder by reminder_id.
    """
    clean_action = action.strip().lower()
    try:
        with _get_db_conn() as conn:
            if clean_action == "add":
                if not text:
                    return ToolResult(success=False, error="Reminder text is required.")
                cursor = conn.execute(
                    "INSERT INTO reminders (reminder_text, due_at) VALUES (?, ?)",
                    (text.strip(), due_at.strip() or None),
                )
                conn.commit()
                return ToolResult(
                    success=True,
                    result={"message": f"Reminder added: '{text}'", "reminder_id": cursor.lastrowid},
                )

            elif clean_action == "list":
                rows = conn.execute(
                    "SELECT id, reminder_text, due_at, status, created_at FROM reminders ORDER BY id DESC"
                ).fetchall()
                reminders = [dict(r) for r in rows]
                return ToolResult(success=True, result={"reminders": reminders, "count": len(reminders)})

            elif clean_action == "complete":
                if not reminder_id:
                    return ToolResult(success=False, error="reminder_id is required to complete a reminder.")
                conn.execute("UPDATE reminders SET status = 'completed' WHERE id = ?", (reminder_id,))
                conn.commit()
                return ToolResult(success=True, result={"message": f"Reminder {reminder_id} marked as completed."})

            elif clean_action == "delete":
                if not reminder_id:
                    return ToolResult(success=False, error="reminder_id is required to delete a reminder.")
                conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
                conn.commit()
                return ToolResult(success=True, result={"message": f"Reminder {reminder_id} deleted."})

            else:
                return ToolResult(success=False, error=f"Unknown action: '{action}'. Use: add, list, complete, delete.")
    except Exception as e:
        logger.error("Reminders tool error: %s", e)
        return ToolResult(success=False, error=f"Reminders error: {e}")


def manage_tasks(action: str, task_text: str = "", priority: str = "medium", task_id: int | None = None) -> ToolResult:
    """
    Manage personal to-do tasks.

    Actions:
    - 'add': Add a new task (requires task_text, optional priority: low, medium, high).
    - 'list': List tasks.
    - 'complete': Mark a task completed.
    - 'delete': Delete a task.
    """
    clean_action = action.strip().lower()
    try:
        with _get_db_conn() as conn:
            if clean_action == "add":
                if not task_text:
                    return ToolResult(success=False, error="task_text is required.")
                prio = priority.lower() if priority.lower() in ("low", "medium", "high") else "medium"
                cursor = conn.execute(
                    "INSERT INTO todo_items (task_text, priority) VALUES (?, ?)",
                    (task_text.strip(), prio),
                )
                conn.commit()
                return ToolResult(
                    success=True,
                    result={"message": f"Task added: '{task_text}' (Priority: {prio})", "task_id": cursor.lastrowid},
                )

            elif clean_action == "list":
                rows = conn.execute(
                    "SELECT id, task_text, priority, status, created_at FROM todo_items ORDER BY status DESC, id DESC"
                ).fetchall()
                tasks = [dict(r) for r in rows]
                return ToolResult(success=True, result={"tasks": tasks, "count": len(tasks)})

            elif clean_action == "complete":
                if not task_id:
                    return ToolResult(success=False, error="task_id is required to complete a task.")
                conn.execute(
                    "UPDATE todo_items SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (task_id,),
                )
                conn.commit()
                return ToolResult(success=True, result={"message": f"Task {task_id} marked completed."})

            elif clean_action == "delete":
                if not task_id:
                    return ToolResult(success=False, error="task_id is required to delete a task.")
                conn.execute("DELETE FROM todo_items WHERE id = ?", (task_id,))
                conn.commit()
                return ToolResult(success=True, result={"message": f"Task {task_id} deleted."})

            else:
                return ToolResult(success=False, error=f"Unknown action: '{action}'. Use: add, list, complete, delete.")
    except Exception as e:
        logger.error("Todo tool error: %s", e)
        return ToolResult(success=False, error=f"Todo error: {e}")


def summarize_text(text: str, max_points: int = 5) -> ToolResult:
    """
    Extract key sentences and structured bullet points from text.
    """
    clean_text = text.strip()
    if not clean_text:
        return ToolResult(success=False, error="Text to summarize cannot be empty.")

    try:
        # Split into sentences
        import re
        raw_sentences = re.split(r'(?<=[.!?])\s+', clean_text)
        sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 15]

        if not sentences:
            sentences = [clean_text]

        # Select representative sentences
        key_points = sentences[:max_points]
        word_count = len(clean_text.split())

        return ToolResult(
            success=True,
            result={
                "summary_points": key_points,
                "original_word_count": word_count,
                "points_count": len(key_points),
            },
        )
    except Exception as e:
        logger.error("Summarization error: %s", e)
        return ToolResult(success=False, error=f"Summarization error: {e}")


# ===================================================================
#  Tool definitions for the registry
# ===================================================================

manage_notes_definition = ToolDefinition(
    name="manage_notes",
    description="Create, list, read, or delete personal notes. Actions: 'create', 'list', 'read', 'delete'.",
    parameters=[
        ToolParameter(
            name="action",
            type="string",
            description="Action: 'create', 'list', 'read', or 'delete'.",
            enum=["create", "list", "read", "delete"],
        ),
        ToolParameter(
            name="title",
            type="string",
            description="Title of the note (required for 'create').",
            required=False,
        ),
        ToolParameter(
            name="content",
            type="string",
            description="Body text content of the note (required for 'create').",
            required=False,
        ),
        ToolParameter(
            name="note_id",
            type="integer",
            description="ID of the note (for 'read' or 'delete').",
            required=False,
        ),
    ],
    permission_level=PermissionLevel.LEVEL_1_LOW_RISK,
    category=ToolCategory.PRODUCTIVITY,
)

manage_reminders_definition = ToolDefinition(
    name="manage_reminders",
    description="Add, list, complete, or delete reminders. Actions: 'add', 'list', 'complete', 'delete'.",
    parameters=[
        ToolParameter(
            name="action",
            type="string",
            description="Action: 'add', 'list', 'complete', or 'delete'.",
            enum=["add", "list", "complete", "delete"],
        ),
        ToolParameter(
            name="text",
            type="string",
            description="Reminder message / reminder text.",
            required=False,
        ),
        ToolParameter(
            name="due_at",
            type="string",
            description="Due date or time string (e.g. 'tomorrow at 3pm').",
            required=False,
        ),
        ToolParameter(
            name="reminder_id",
            type="integer",
            description="ID of the reminder (for 'complete' or 'delete').",
            required=False,
        ),
    ],
    permission_level=PermissionLevel.LEVEL_1_LOW_RISK,
    category=ToolCategory.PRODUCTIVITY,
)

manage_tasks_definition = ToolDefinition(
    name="manage_tasks",
    description="Manage todo task items. Actions: 'add', 'list', 'complete', 'delete'.",
    parameters=[
        ToolParameter(
            name="action",
            type="string",
            description="Action: 'add', 'list', 'complete', or 'delete'.",
            enum=["add", "list", "complete", "delete"],
        ),
        ToolParameter(
            name="task_text",
            type="string",
            description="Description of the task to add.",
            required=False,
        ),
        ToolParameter(
            name="priority",
            type="string",
            description="Priority level: 'low', 'medium', or 'high'.",
            required=False,
            enum=["low", "medium", "high"],
        ),
        ToolParameter(
            name="task_id",
            type="integer",
            description="Task ID (for 'complete' or 'delete').",
            required=False,
        ),
    ],
    permission_level=PermissionLevel.LEVEL_1_LOW_RISK,
    category=ToolCategory.PRODUCTIVITY,
)

summarize_text_definition = ToolDefinition(
    name="summarize_text",
    description="Summarize text into key bullet points.",
    parameters=[
        ToolParameter(
            name="text",
            type="string",
            description="Text content to summarize.",
        ),
        ToolParameter(
            name="max_points",
            type="integer",
            description="Maximum number of key points (default: 5).",
            required=False,
        ),
    ],
    permission_level=PermissionLevel.LEVEL_0_READ_ONLY,
    category=ToolCategory.PRODUCTIVITY,
)
