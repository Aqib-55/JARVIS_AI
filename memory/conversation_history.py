"""
Conversation History — persists conversation messages to the database.
"""

import logging
import uuid
from typing import Any

from memory.database import DatabaseManager

logger = logging.getLogger(__name__)


class ConversationHistoryManager:
    """Manages persistent conversation history in the database."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db
        self._current_session_id: str | None = None
        self._current_conversation_id: int | None = None

    def start_session(self) -> int:
        """Start a new conversation session and return its database ID."""
        self._current_session_id = str(uuid.uuid4())

        with self._db.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO conversations (session_id) VALUES (?)",
                (self._current_session_id,),
            )
            conn.commit()
            self._current_conversation_id = cursor.lastrowid
            logger.info(
                "Started conversation session %d (%s…)",
                self._current_conversation_id,
                self._current_session_id[:8],
            )
            return self._current_conversation_id

    def save_message(self, role: str, content: str) -> None:
        """Save a message to the current conversation."""
        if self._current_conversation_id is None:
            self.start_session()

        with self._db.get_connection() as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
                (self._current_conversation_id, role, content),
            )
            conn.execute(
                "UPDATE conversations SET message_count = message_count + 1 WHERE id = ?",
                (self._current_conversation_id,),
            )
            conn.commit()

    def get_session_messages(
        self,
        conversation_id: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get messages from a conversation session."""
        conv_id = conversation_id or self._current_conversation_id
        if conv_id is None:
            return []

        with self._db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (conv_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def end_session(self) -> None:
        """End the current conversation session."""
        if self._current_conversation_id is None:
            return

        with self._db.get_connection() as conn:
            conn.execute(
                "UPDATE conversations SET ended_at = CURRENT_TIMESTAMP WHERE id = ?",
                (self._current_conversation_id,),
            )
            conn.commit()

        logger.info("Ended conversation session %d", self._current_conversation_id)
        self._current_conversation_id = None
        self._current_session_id = None

    @property
    def current_conversation_id(self) -> int | None:
        return self._current_conversation_id
