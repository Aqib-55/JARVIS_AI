"""
Abstract base class for AI model providers.

All providers (Gemini, OpenAI, etc.) must implement this interface.
This ensures the rest of the application is provider-independent.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass
class FunctionCall:
    """Represents a function/tool call requested by the AI model."""
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class FunctionResponse:
    """Represents the result of executing a function/tool call."""
    name: str
    response: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelResponse:
    """Standardized response from any AI model provider."""
    text: str | None = None
    function_calls: list[FunctionCall] = field(default_factory=list)
    error: str | None = None
    provider: str = ""
    model: str = ""

    @property
    def has_function_calls(self) -> bool:
        return len(self.function_calls) > 0

    @property
    def is_error(self) -> bool:
        return self.error is not None


class MessageRole(str, Enum):
    """Roles for conversation messages."""
    USER = "user"
    ASSISTANT = "model"
    SYSTEM = "system"


@dataclass
class Message:
    """A single message in a conversation."""
    role: MessageRole
    content: str


class BaseProvider(ABC):
    """
    Abstract base class that all AI providers must implement.

    To add a new provider (e.g. OpenAI):
      1. Create providers/openai.py with a class that inherits BaseProvider.
      2. Implement all abstract methods.
      3. Register it in providers/factory.py.
    """

    @abstractmethod
    def connect(self) -> bool:
        """
        Initialize the connection to the provider.
        Returns True if successful, False otherwise.
        """
        ...

    @abstractmethod
    def generate(
        self,
        messages: list[Message],
        system_instruction: str | None = None,
    ) -> ModelResponse:
        """Generate a response without tool-calling capability."""
        ...

    @abstractmethod
    def generate_with_tools(
        self,
        messages: list[Message],
        tool_declarations: list[dict[str, Any]],
        system_instruction: str | None = None,
    ) -> ModelResponse:
        """
        Generate a response with tool-calling capability.
        The model may respond with text, function calls, or both.
        """
        ...

    @abstractmethod
    def send_function_results(
        self,
        messages: list[Message],
        function_calls: list[FunctionCall],
        function_responses: list[FunctionResponse],
        tool_declarations: list[dict[str, Any]],
        system_instruction: str | None = None,
    ) -> ModelResponse:
        """Send function execution results back to the model for a final response."""
        ...

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the name of this provider (e.g. 'gemini')."""
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model identifier being used (e.g. 'gemini-2.5-flash')."""
        ...
