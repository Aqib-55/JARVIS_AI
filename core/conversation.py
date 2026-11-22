"""
Conversation Manager — maintains the conversation context for the agent.

Manages the sliding window of messages sent to the AI provider,
respecting the configured history limit.
"""

import logging

from config.settings import settings
from providers.base import Message, MessageRole

logger = logging.getLogger(__name__)


class ConversationManager:
    """Manages conversation messages and history context."""

    def __init__(self, max_history: int | None = None) -> None:
        self._messages: list[Message] = []
        self._max_history = max_history or settings.MAX_CONVERSATION_HISTORY

    def add_message(self, role: MessageRole, content: str) -> None:
        """Add a message to the conversation."""
        self._messages.append(Message(role=role, content=content))

    def get_messages(self) -> list[Message]:
        """
        Get the conversation messages for sending to the provider.

        Returns the most recent messages up to the configured limit,
        so we don't waste tokens on old context.
        """
        if len(self._messages) <= self._max_history:
            return list(self._messages)
        return list(self._messages[-self._max_history :])

    def get_last_user_message(self) -> str | None:
        """Get the content of the most recent user message."""
        for msg in reversed(self._messages):
            if msg.role == MessageRole.USER:
                return msg.content
        return None

    def clear(self) -> None:
        """Clear all conversation messages."""
        self._messages.clear()
        logger.info("Conversation cleared.")

    @property
    def message_count(self) -> int:
        return len(self._messages)

    @property
    def all_messages(self) -> list[Message]:
        return list(self._messages)
