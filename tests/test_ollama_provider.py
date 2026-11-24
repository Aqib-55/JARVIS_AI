"""
Tests for the OllamaProvider.

These tests mock the Ollama HTTP API so no live Ollama server is needed.
Live connection tests are tagged @pytest.mark.integration and require Ollama running.
"""

import json
import threading
import unittest.mock as mock

import pytest

from providers.base import FunctionCall, FunctionResponse, Message, MessageRole, ModelResponse
from providers.ollama import OllamaConnectionError, OllamaProvider


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def provider():
    """OllamaProvider pointing at test endpoint (never actually called in unit tests)."""
    p = OllamaProvider(base_url="http://127.0.0.1:11434", model="qwen3.5:4b", timeout=30)
    p._connected = True  # Bypass connect() for unit tests
    return p


def _make_ollama_response(content: str = "", tool_calls: list | None = None) -> dict:
    """Build a mock Ollama /api/chat response dictionary."""
    msg: dict = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"message": msg, "done": True}


# ---------------------------------------------------------------------------
#  _parse_response
# ---------------------------------------------------------------------------

class TestParseResponse:

    def test_plain_text_response(self, provider):
        resp = _make_ollama_response(content="Hello, I am JARVIS.")
        result = provider._parse_response(resp)
        assert result.text == "Hello, I am JARVIS."
        assert result.function_calls == []
        assert not result.is_error

    def test_thinking_field_suppressed(self, provider):
        """The 'thinking' field must NOT appear in the parsed response text."""
        resp = _make_ollama_response(content="Final answer only.")
        resp["message"]["thinking"] = "Let me reason about this..."
        result = provider._parse_response(resp)
        assert result.text == "Final answer only."
        # thinking must not leak into text
        assert "reason" not in (result.text or "")

    def test_tool_call_response(self, provider):
        tool_calls = [{"function": {"name": "get_datetime", "arguments": {}}}]
        resp = _make_ollama_response(content="", tool_calls=tool_calls)
        result = provider._parse_response(resp)
        assert result.has_function_calls
        assert result.function_calls[0].name == "get_datetime"
        assert result.text is None

    def test_tool_call_with_args(self, provider):
        args = {"operation": "add", "numbers": [1, 2]}
        tool_calls = [{"function": {"name": "calculate", "arguments": args}}]
        resp = _make_ollama_response(content="", tool_calls=tool_calls)
        result = provider._parse_response(resp)
        assert result.function_calls[0].name == "calculate"
        assert result.function_calls[0].args["operation"] == "add"

    def test_tool_call_with_string_args(self, provider):
        """Arguments as JSON strings must be parsed into dicts."""
        args_str = json.dumps({"query": "time now"})
        tool_calls = [{"function": {"name": "get_datetime", "arguments": args_str}}]
        resp = _make_ollama_response(content="", tool_calls=tool_calls)
        result = provider._parse_response(resp)
        assert isinstance(result.function_calls[0].args, dict)

    def test_empty_response(self, provider):
        resp = _make_ollama_response(content="")
        result = provider._parse_response(resp)
        assert result.text is None
        assert result.function_calls == []

    def test_provider_name(self, provider):
        assert provider.get_provider_name() == "ollama"

    def test_model_name(self, provider):
        assert provider.get_model_name() == "qwen3.5:4b"


# ---------------------------------------------------------------------------
#  _build_ollama_tools
# ---------------------------------------------------------------------------

class TestBuildOllamaTools:

    def test_wraps_declarations(self, provider):
        decls = [
            {"name": "get_datetime", "description": "Get current date/time", "parameters": {}}
        ]
        tools = provider._build_ollama_tools(decls)
        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "get_datetime"

    def test_empty_declarations(self, provider):
        assert provider._build_ollama_tools([]) == []


# ---------------------------------------------------------------------------
#  _messages_to_ollama
# ---------------------------------------------------------------------------

class TestMessagesToOllama:

    def test_system_instruction_prepended(self, provider):
        messages = [Message(role=MessageRole.USER, content="Hello")]
        result = provider._messages_to_ollama(messages, system_instruction="You are JARVIS.")
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are JARVIS."
        assert result[1]["role"] == "user"

    def test_assistant_role_mapping(self, provider):
        messages = [Message(role=MessageRole.ASSISTANT, content="Hi there")]
        result = provider._messages_to_ollama(messages)
        assert result[0]["role"] == "assistant"

    def test_user_role_mapping(self, provider):
        messages = [Message(role=MessageRole.USER, content="Help me")]
        result = provider._messages_to_ollama(messages)
        assert result[0]["role"] == "user"


# ---------------------------------------------------------------------------
#  Error handling (mocked HTTP)
# ---------------------------------------------------------------------------

class TestErrorHandling:

    def test_generate_without_connect(self):
        p = OllamaProvider(base_url="http://127.0.0.1:11434", model="qwen3.5:4b")
        # _connected defaults to False
        result = p.generate(messages=[Message(role=MessageRole.USER, content="hi")])
        assert result.is_error
        assert "not connected" in (result.error or "").lower()

    def test_generate_with_tools_without_connect(self):
        p = OllamaProvider(base_url="http://127.0.0.1:11434", model="qwen3.5:4b")
        result = p.generate_with_tools(
            messages=[Message(role=MessageRole.USER, content="hi")],
            tool_declarations=[],
        )
        assert result.is_error

    def test_connection_error_surfaced(self, provider):
        """OllamaConnectionError should be caught and returned as ModelResponse error."""
        with mock.patch.object(provider, "_http_post", side_effect=OllamaConnectionError("refused")):
            result = provider.generate(
                messages=[Message(role=MessageRole.USER, content="hi")]
            )
        assert result.is_error
        assert "refused" in (result.error or "")


# ---------------------------------------------------------------------------
#  Factory integration
# ---------------------------------------------------------------------------

class TestProviderFactory:

    def test_factory_returns_ollama(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "ollama")
        monkeypatch.setenv("LOCAL_AI_ONLY", "true")
        from providers.factory import get_provider
        p = get_provider("ollama")
        assert isinstance(p, OllamaProvider)

    def test_factory_rejects_gemini_in_local_mode(self, monkeypatch):
        monkeypatch.setenv("LOCAL_AI_ONLY", "true")
        from providers.factory import get_provider
        with pytest.raises(RuntimeError, match="LOCAL_AI_ONLY"):
            get_provider("gemini")

    def test_factory_rejects_unknown_provider(self, monkeypatch):
        monkeypatch.setenv("LOCAL_AI_ONLY", "false")
        from providers.factory import get_provider
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("openai")
