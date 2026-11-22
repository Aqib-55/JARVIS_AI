"""
Memory Manager — manages facts, user preferences, tool usage metrics,
cross-domain memory search, and contextual retrieval.
"""

import logging
from typing import Any

from memory.database import DatabaseManager

logger = logging.getLogger(__name__)


class MemoryManager:
    """Provides high-level memory operations for JARVIS AI."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    # ------------------------------------------------------------------
    #  Important Facts (Long-term Knowledge)
    # ------------------------------------------------------------------

    def add_fact(self, category: str, fact: str, source: str = "user") -> int:
        """Store an important fact in long-term memory."""
        clean_fact = fact.strip()
        clean_cat = category.strip().lower() or "general"
        with self._db.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO important_facts (category, fact, source) VALUES (?, ?, ?)",
                (clean_cat, clean_fact, source),
            )
            conn.commit()
            fact_id = cursor.lastrowid
            logger.info("Recorded fact #%d [%s]: %s", fact_id, clean_cat, clean_fact[:40])
            return fact_id

    def get_facts(self, category: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve stored facts, optionally filtered by category."""
        with self._db.get_connection() as conn:
            if category:
                rows = conn.execute(
                    "SELECT id, category, fact, source, created_at FROM important_facts WHERE category = ? ORDER BY id DESC LIMIT ?",
                    (category.strip().lower(), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, category, fact, source, created_at FROM important_facts ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def delete_fact(self, fact_id: int) -> bool:
        """Delete a fact by ID."""
        with self._db.get_connection() as conn:
            cursor = conn.execute("DELETE FROM important_facts WHERE id = ?", (fact_id,))
            conn.commit()
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    #  User Preferences
    # ------------------------------------------------------------------

    def set_preference(self, key: str, value: str) -> None:
        """Set a persistent user preference."""
        with self._db.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_preferences (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (key.strip(), value.strip()),
            )
            conn.commit()
            logger.info("Updated preference: %s", key)

    def get_preference(self, key: str, default: str | None = None) -> str | None:
        """Get a persistent user preference."""
        with self._db.get_connection() as conn:
            row = conn.execute("SELECT value FROM user_preferences WHERE key = ?", (key.strip(),)).fetchone()
            if row:
                return row["value"]
            return default

    def get_all_preferences(self) -> dict[str, str]:
        """Return all user preferences as a dictionary."""
        with self._db.get_connection() as conn:
            rows = conn.execute("SELECT key, value FROM user_preferences").fetchall()
            return {r["key"]: r["value"] for r in rows}

    def delete_preference(self, key: str) -> bool:
        """Delete a user preference."""
        with self._db.get_connection() as conn:
            cursor = conn.execute("DELETE FROM user_preferences WHERE key = ?", (key.strip(),))
            conn.commit()
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    #  Tool Usage Metrics
    # ------------------------------------------------------------------

    def record_tool_usage(self, tool_name: str, success: bool) -> None:
        """Record an execution in tool metrics."""
        with self._db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO tool_usage_metrics (tool_name, call_count, success_count, failure_count, last_used_at)
                VALUES (?, 1, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(tool_name) DO UPDATE SET
                    call_count = call_count + 1,
                    success_count = success_count + excluded.success_count,
                    failure_count = failure_count + excluded.failure_count,
                    last_used_at = CURRENT_TIMESTAMP
                """,
                (tool_name, 1 if success else 0, 0 if success else 1),
            )
            conn.commit()

    def get_frequently_used_tools(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return most frequently used tools."""
        with self._db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT tool_name, call_count, success_count, failure_count, last_used_at
                FROM tool_usage_metrics
                ORDER BY call_count DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    #  Cross-Domain Memory Search
    # ------------------------------------------------------------------

    def search_memory(self, query: str, limit: int = 10) -> dict[str, list[dict[str, Any]]]:
        """
        Search across facts, notes, tasks, and previous messages.
        """
        clean_q = f"%{query.strip()}%"
        results: dict[str, list[dict[str, Any]]] = {
            "facts": [],
            "notes": [],
            "tasks": [],
            "messages": [],
        }

        with self._db.get_connection() as conn:
            # Facts
            fact_rows = conn.execute(
                "SELECT id, category, fact, created_at FROM important_facts WHERE fact LIKE ? OR category LIKE ? LIMIT ?",
                (clean_q, clean_q, limit),
            ).fetchall()
            results["facts"] = [dict(r) for r in fact_rows]

            # Notes
            note_rows = conn.execute(
                "SELECT id, title, content, created_at FROM notes WHERE title LIKE ? OR content LIKE ? LIMIT ?",
                (clean_q, clean_q, limit),
            ).fetchall()
            results["notes"] = [dict(r) for r in note_rows]

            # Tasks
            task_rows = conn.execute(
                "SELECT id, user_request, status, started_at FROM tasks WHERE user_request LIKE ? LIMIT ?",
                (clean_q, limit),
            ).fetchall()
            results["tasks"] = [dict(r) for r in task_rows]

            # Messages
            msg_rows = conn.execute(
                "SELECT role, content, created_at FROM messages WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
                (clean_q, limit),
            ).fetchall()
            results["messages"] = [dict(r) for r in msg_rows]

        return results

    # ------------------------------------------------------------------
    #  Context Retrieval for Prompt Augmentation
    # ------------------------------------------------------------------

    def get_relevant_context(self, user_query: str) -> str:
        """
        Retrieve relevant facts and user preferences to concisely augment system instructions.
        """
        context_parts = []

        # 1. User preferences
        prefs = self.get_all_preferences()
        if prefs:
            pref_lines = [f"- {k}: {v}" for k, v in prefs.items()]
            context_parts.append("User Preferences:\n" + "\n".join(pref_lines))

        # 2. Keyword-relevant facts
        search_hits = self.search_memory(user_query, limit=3)
        relevant_facts = search_hits.get("facts", [])
        if relevant_facts:
            fact_lines = [f"- [{f['category']}] {f['fact']}" for f in relevant_facts]
            context_parts.append("Relevant Known Facts:\n" + "\n".join(fact_lines))

        return "\n\n".join(context_parts)

    # ------------------------------------------------------------------
    #  Memory Deletion & Privacy Controls
    # ------------------------------------------------------------------

    def clear_all_memory(self, confirm: bool = False) -> bool:
        """Clear all conversation history and facts (keeps schema)."""
        if not confirm:
            return False
        with self._db.get_connection() as conn:
            conn.execute("DELETE FROM messages")
            conn.execute("DELETE FROM conversations")
            conn.execute("DELETE FROM task_steps")
            conn.execute("DELETE FROM tool_executions")
            conn.execute("DELETE FROM tasks")
            conn.execute("DELETE FROM important_facts")
            conn.commit()
            logger.warning("All conversational and task memory has been erased.")
            return True
