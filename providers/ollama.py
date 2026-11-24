"""
Ollama AI provider for JARVIS — the sole active AI backend.

Uses the Ollama local HTTP API (POST /api/chat) with:
- Native structured tool/function calling.
- Conversation history with multi-turn support.
- System instructions.
- Thinking-trace suppression (content vs thinking separation).
- Connection health checks.
- Configurable timeouts.
- Maximum tool-call loop guard.

Official docs: https://docs.ollama.com/api
Tool calling:  https://docs.ollama.com/capabilities/tool-calling
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from config.settings import settings
from providers.base import (
    BaseProvider,
    FunctionCall,
    FunctionResponse,
    Message,
    MessageRole,
    ModelResponse,
)

logger = logging.getLogger(__name__)

# Ollama API endpoints
_CHAT_PATH = "/api/chat"
_TAGS_PATH = "/api/tags"


class OllamaProvider(BaseProvider):
    """
    Local Ollama AI provider using the native /api/chat endpoint.

    Supports:
    - Streaming disabled (stream=false) for structured responses.
    - Native tool definitions via the 'tools' parameter.
    - tool_calls parsing from message.tool_calls.
    - Thinking-trace suppression: message.thinking is ignored; only message.content is used.
    - Multi-turn conversation history.
    """

    def __init__(
        self,
        base_url: str = "",
        model: str = "",
        timeout: int = 0,
    ) -> None:
        self._base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self._model = model or settings.OLLAMA_MODEL
        self._timeout = timeout or settings.OLLAMA_TIMEOUT
        self._connected = False

    # ------------------------------------------------------------------
    #  Connection / Health
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """
        Verify that the Ollama service is reachable and the target model exists.
        Returns True only if both checks pass.
        """
        # 1. Ping the tags endpoint
        try:
            tags_data = self._http_get(_TAGS_PATH)
        except OllamaConnectionError as e:
            logger.error("Ollama service unreachable at %s — %s", self._base_url, e)
            logger.error(
                "Please ensure Ollama is running. Start it with: ollama serve"
            )
            return False

        # 2. Verify model is available locally
        models_available = [m.get("name", "") for m in tags_data.get("models", [])]
        # Ollama may suffix with ':latest'; normalise for comparison
        def _norm(name: str) -> str:
            return name.split(":")[0].lower()

        target = _norm(self._model)
        found = any(_norm(m) == target for m in models_available)
        if not found:
            logger.error(
                "Model '%s' not found in local Ollama. Available: %s",
                self._model,
                models_available or "(none)",
            )
            logger.error(
                "Install it with: ollama pull %s", self._model
            )
            return False

        # 3. Quick sanity generation
        try:
            payload = {
                "model": self._model,
                "messages": [{"role": "user", "content": "Reply with the single word: OK"}],
                "stream": False,
                "think": False,
            }
            resp = self._http_post(_CHAT_PATH, payload)
            content = resp.get("message", {}).get("content", "")
            if not content:
                logger.warning("Ollama health-check returned empty content; assuming connected.")
        except OllamaConnectionError as e:
            logger.error("Ollama health-check failed: %s", e)
            return False

        self._connected = True
        logger.info(
            "Ollama connected — model: %s, endpoint: %s", self._model, self._base_url
        )
        return True

    # ------------------------------------------------------------------
    #  Generation — no tools
    # ------------------------------------------------------------------

    def generate(
        self,
        messages: list[Message],
        system_instruction: str | None = None,
    ) -> ModelResponse:
        """Generate a plain text response without tool definitions."""
        if not self._connected:
            return ModelResponse(error="Ollama provider not connected. Call connect() first.")

        payload = self._build_payload(
            messages=messages,
            system_instruction=system_instruction,
            tools=None,
        )
        try:
            resp = self._http_post(_CHAT_PATH, payload)
            return self._parse_response(resp)
        except OllamaConnectionError as e:
            return ModelResponse(error=str(e))
        except Exception as e:
            logger.exception("Unexpected error during Ollama generate()")
            return ModelResponse(error=f"Ollama error: {e}")

    # ------------------------------------------------------------------
    #  Generation — with tools
    # ------------------------------------------------------------------

    def generate_with_tools(
        self,
        messages: list[Message],
        tool_declarations: list[dict[str, Any]],
        system_instruction: str | None = None,
    ) -> ModelResponse:
        """
        Generate a response with native tool-call capability.

        Tool definitions are wrapped in Ollama's expected format:
            {"type": "function", "function": {name, description, parameters}}
        """
        if not self._connected:
            return ModelResponse(error="Ollama provider not connected. Call connect() first.")

        ollama_tools = self._build_ollama_tools(tool_declarations)
        payload = self._build_payload(
            messages=messages,
            system_instruction=system_instruction,
            tools=ollama_tools,
        )
        try:
            resp = self._http_post(_CHAT_PATH, payload)
            return self._parse_response(resp)
        except OllamaConnectionError as e:
            return ModelResponse(error=str(e))
        except Exception as e:
            logger.exception("Unexpected error during Ollama generate_with_tools()")
            return ModelResponse(error=f"Ollama error: {e}")

    # ------------------------------------------------------------------
    #  Send tool results back to model
    # ------------------------------------------------------------------

    def send_function_results(
        self,
        messages: list[Message],
        function_calls: list[FunctionCall],
        function_responses: list[FunctionResponse],
        tool_declarations: list[dict[str, Any]],
        system_instruction: str | None = None,
    ) -> ModelResponse:
        """
        Build a conversation that includes:
          - prior messages
          - assistant's tool-call message (required by Ollama API)
          - tool result messages (role=tool)
        Then request the model's final answer.

        Ollama expects the conversation to include the assistant's tool_calls
        message verbatim before the tool result messages.
        """
        if not self._connected:
            return ModelResponse(error="Ollama provider not connected. Call connect() first.")

        ollama_msgs = self._messages_to_ollama(messages, system_instruction)

        # Append the assistant's tool_calls turn (required by Ollama)
        tool_calls_body = [
            {
                "function": {
                    "name": fc.name,
                    "arguments": fc.args,
                }
            }
            for fc in function_calls
        ]
        ollama_msgs.append({
            "role": "assistant",
            "content": "",
            "tool_calls": tool_calls_body,
        })

        # Append tool result messages
        for fc, fr in zip(function_calls, function_responses):
            result_str = (
                json.dumps(fr.response)
                if isinstance(fr.response, dict)
                else str(fr.response)
            )
            ollama_msgs.append({
                "role": "tool",
                "content": result_str,
                "name": fr.name,
            })

        ollama_tools = self._build_ollama_tools(tool_declarations)
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": ollama_msgs,
            "stream": False,
            "think": False,
        }
        if ollama_tools:
            payload["tools"] = ollama_tools

        try:
            resp = self._http_post(_CHAT_PATH, payload)
            return self._parse_response(resp)
        except OllamaConnectionError as e:
            return ModelResponse(error=str(e))
        except Exception as e:
            logger.exception("Unexpected error during Ollama send_function_results()")
            return ModelResponse(error=f"Ollama error: {e}")

    # ------------------------------------------------------------------
    #  Private helpers
    # ------------------------------------------------------------------

    def _build_payload(
        self,
        messages: list[Message],
        system_instruction: str | None,
        tools: list[dict] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": self._messages_to_ollama(messages, system_instruction),
            "stream": False,
            "think": False,  # Suppress internal thinking from response
        }
        if tools:
            payload["tools"] = tools
        return payload

    def _messages_to_ollama(
        self,
        messages: list[Message],
        system_instruction: str | None = None,
    ) -> list[dict[str, Any]]:
        """Convert internal Message objects to Ollama API message format."""
        ollama_msgs: list[dict[str, Any]] = []

        if system_instruction:
            ollama_msgs.append({"role": "system", "content": system_instruction})

        for msg in messages:
            role = "assistant" if msg.role == MessageRole.ASSISTANT else "user"
            ollama_msgs.append({"role": role, "content": msg.content})

        return ollama_msgs

    def _build_ollama_tools(
        self, tool_declarations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Wrap JARVIS tool declarations into Ollama's expected format:
        {"type": "function", "function": {name, description, parameters}}
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": decl["name"],
                    "description": decl.get("description", ""),
                    "parameters": decl.get("parameters", {}),
                },
            }
            for decl in tool_declarations
        ]

    def _parse_response(self, resp: dict[str, Any]) -> ModelResponse:
        """
        Parse an Ollama /api/chat response into a standardized ModelResponse.

        Ollama response structure:
        {
          "message": {
            "role": "assistant",
            "content": "...",       <- final text (may be empty if tool_calls present)
            "thinking": "...",      <- internal reasoning (always suppressed)
            "tool_calls": [         <- present when model requests tool execution
              {"function": {"name": "...", "arguments": {...}}}
            ]
          }
        }
        """
        message = resp.get("message", {})

        # Extract content — ignore 'thinking' entirely
        raw_content: str = message.get("content") or ""
        text: str | None = raw_content.strip() if raw_content.strip() else None

        # Extract tool calls
        function_calls: list[FunctionCall] = []
        raw_tool_calls = message.get("tool_calls") or []
        for tc in raw_tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, ValueError):
                    logger.warning("Could not parse tool arguments for '%s': %s", name, args)
                    args = {}
            if name:
                function_calls.append(FunctionCall(name=name, args=args or {}))

        return ModelResponse(
            text=text,
            function_calls=function_calls,
            provider=self.get_provider_name(),
            model=self._model,
        )

    # ------------------------------------------------------------------
    #  HTTP helpers
    # ------------------------------------------------------------------

    def _http_post(self, path: str, payload: dict) -> dict[str, Any]:
        url = self._base_url + path
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.URLError as e:
            raise OllamaConnectionError(
                f"Cannot reach Ollama at {self._base_url}: {e.reason}"
            ) from e
        except TimeoutError:
            raise OllamaConnectionError(
                f"Ollama request timed out after {self._timeout}s."
            )

    def _http_get(self, path: str) -> dict[str, Any]:
        url = self._base_url + path
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.URLError as e:
            raise OllamaConnectionError(
                f"Cannot reach Ollama at {self._base_url}: {e.reason}"
            ) from e

    # ------------------------------------------------------------------
    #  Metadata
    # ------------------------------------------------------------------

    def get_provider_name(self) -> str:
        return "ollama"

    def get_model_name(self) -> str:
        return self._model


class OllamaConnectionError(RuntimeError):
    """Raised when the Ollama service is unreachable or returns an error."""
