"""
Task History — records and retrieves task execution history.
"""

import json
import logging
from datetime import datetime
from typing import Any

from memory.database import DatabaseManager

logger = logging.getLogger(__name__)


class TaskHistoryManager:
    """Manages task execution history in the database."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def create_task(
        self,
        user_request: str,
        conversation_id: int | None = None,
        plan_description: str = "",
        total_steps: int = 0,
    ) -> int:
        """Create a new task record and return its ID."""
        with self._db.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tasks
                    (conversation_id, user_request, status, plan_description, total_steps)
                VALUES (?, ?, 'running', ?, ?)
                """,
                (conversation_id, user_request, plan_description, total_steps),
            )
            conn.commit()
            task_id = cursor.lastrowid
            logger.info("Created task %d: %s", task_id, user_request[:50])
            return task_id

    def update_task(
        self,
        task_id: int,
        status: str,
        completed_steps: int = 0,
        error: str | None = None,
    ) -> None:
        """Update an existing task's status."""
        completed_at = (
            datetime.now().isoformat()
            if status in ("completed", "failed", "cancelled")
            else None
        )
        with self._db.get_connection() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, completed_steps = ?, error = ?, completed_at = ?
                WHERE id = ?
                """,
                (status, completed_steps, error, completed_at, task_id),
            )
            conn.commit()

    def save_step(
        self,
        task_id: int,
        step_number: int,
        tool_name: str,
        arguments: dict[str, Any],
        status: str,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        """Save a task-step execution record."""
        with self._db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO task_steps
                    (task_id, step_number, tool_name, arguments,
                     status, result, error, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    step_number,
                    tool_name,
                    json.dumps(arguments),
                    status,
                    json.dumps(result) if result is not None else None,
                    error,
                    datetime.now().isoformat()
                    if status in ("completed", "failed")
                    else None,
                ),
            )
            conn.commit()

    def log_tool_execution(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        success: bool,
        result: Any = None,
        error: str | None = None,
        task_id: int | None = None,
    ) -> None:
        """Log a tool execution in the audit log."""
        with self._db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO tool_executions
                    (task_id, tool_name, arguments, success, result, error)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    tool_name,
                    json.dumps(arguments),
                    1 if success else 0,
                    json.dumps(result) if result is not None else None,
                    error,
                ),
            )
            conn.commit()

    def get_recent_tasks(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get the most recent tasks."""
        with self._db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, user_request, status, plan_description,
                       total_steps, completed_steps, started_at, completed_at, error
                FROM tasks
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_task_details(self, task_id: int) -> dict[str, Any] | None:
        """Get detailed information about a task including its steps."""
        with self._db.get_connection() as conn:
            task_row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if task_row is None:
                return None

            task = dict(task_row)
            steps = conn.execute(
                "SELECT * FROM task_steps WHERE task_id = ? ORDER BY step_number",
                (task_id,),
            ).fetchall()
            task["steps"] = [dict(s) for s in steps]
            return task
