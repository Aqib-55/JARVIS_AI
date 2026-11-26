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
from typing import Any, Callable

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
    - Model residency via keep_alive (default 10m) and configurable num_ctx.
    - Optional token streaming with tool-call safety (never streams partial tool JSON).
    - Native tool definitions via the 'tools' parameter.
    - tool_calls parsing from message.tool_calls.
    - Thinking-trace suppression (think=false; message.thinking ignored).
    - Multi-turn conversation history.
    """

    def __init__(
        self,
        base_url: str = "",
        model: str = "",
        timeout: int = 0,
        keep_alive: str = "",
        num_ctx: int = 0,
    ) -> None:
        self._base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self._model = model or settings.OLLAMA_MODEL
        self._timeout = timeout or settings.OLLAMA_TIMEOUT
        self._keep_alive = keep_alive or settings.OLLAMA_KEEP_ALIVE
        self._num_ctx = num_ctx or settings.OLLAMA_NUM_CTX
        self._connected = False
        self._cached_tools_key: tuple[str, ...] | None = None
        self._cached_ollama_tools: list[dict[str, Any]] = []

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

        # 3. Quick sanity generation (also keeps model resident via keep_alive & num_ctx)
        try:
            payload = {
                "model": self._model,
                "messages": [{"role": "user", "content": "OK"}],
                "stream": False,
                "think": False,
                "keep_alive": self._keep_alive,
                "options": {"num_ctx": self._num_ctx},
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
            "Ollama connected — model: %s, endpoint: %s, keep_alive: %s, num_ctx: %d",
            self._model, self._base_url, self._keep_alive, self._num_ctx,
        )
        return True

    # ------------------------------------------------------------------
    #  Generation — no tools
    # ------------------------------------------------------------------

    def generate(
        self,
        messages: list[Message],
        system_instruction: str | None = None,
        stream_callback: Callable[[str], None] | None = None,
    ) -> ModelResponse:
        """Generate a plain text response without tool definitions."""
        if not self._connected:
            return ModelResponse(error="Ollama provider not connected. Call connect() first.")

        use_stream = stream_callback is not None
        payload = self._build_payload(
            messages=messages,
            system_instruction=system_instruction,
            tools=None,
            stream=use_stream,
        )
        try:
            if use_stream:
                return self._http_post_stream(_CHAT_PATH, payload, stream_callback)
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
        stream_callback: Callable[[str], None] | None = None,
    ) -> ModelResponse:
        """
        Generate a response with native tool-call capability.

        Tool definitions are wrapped in Ollama's expected format:
            {"type": "function", "function": {name, description, parameters}}
        """
        if not self._connected:
            return ModelResponse(error="Ollama provider not connected. Call connect() first.")

        use_stream = stream_callback is not None
        ollama_tools = self._build_ollama_tools(tool_declarations)
        payload = self._build_payload(
            messages=messages,
            system_instruction=system_instruction,
            tools=ollama_tools,
            stream=use_stream,
        )
        try:
            if use_stream:
                return self._http_post_stream(_CHAT_PATH, payload, stream_callback)
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
        stream_callback: Callable[[str], None] | None = None,
    ) -> ModelResponse:
        """
        Build a conversation that includes prior messages, assistant tool_calls,
        and tool result messages (role=tool), then request the model's final answer.
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

        use_stream = stream_callback is not None
        ollama_tools = self._build_ollama_tools(tool_declarations)
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": ollama_msgs,
            "stream": use_stream,
            "think": False,
            "keep_alive": self._keep_alive,
            "options": {"num_ctx": self._num_ctx},
        }
        if ollama_tools:
            payload["tools"] = ollama_tools

        try:
            if use_stream:
                return self._http_post_stream(_CHAT_PATH, payload, stream_callback)
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
        stream: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": self._messages_to_ollama(messages, system_instruction),
            "stream": stream,
            "think": False,  # Suppress internal thinking from response
            "keep_alive": self._keep_alive,
            "options": {"num_ctx": self._num_ctx},
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
        Wrap JARVIS tool declarations into Ollama's expected format (cached by names).
        """
        if not tool_declarations:
            return []
        key = tuple(d["name"] for d in tool_declarations)
        if self._cached_tools_key == key and len(self._cached_ollama_tools) == len(tool_declarations):
            return self._cached_ollama_tools

        wrapped = [
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
        self._cached_tools_key = key
        self._cached_ollama_tools = wrapped
        return wrapped

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

    def _http_post_stream(
        self,
        path: str,
        payload: dict,
        stream_callback: Callable[[str], None],
    ) -> ModelResponse:
        """
        Stream NDJSON chunks from /api/chat, forwarding text deltas when no
        tool_calls are present, and assembling the final ModelResponse.
        """
        url = self._base_url + path
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        text_parts: list[str] = []
        raw_tool_calls: list[dict[str, Any]] = []
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    chunk = json.loads(line)
                    msg = chunk.get("message", {})
                    if msg.get("tool_calls"):
                        raw_tool_calls.extend(msg["tool_calls"])
                    delta = msg.get("content") or ""
                    if delta:
                        text_parts.append(delta)
                        if not raw_tool_calls:
                            try:
                                stream_callback(delta)
                            except Exception:
                                pass
        except urllib.error.URLError as e:
            raise OllamaConnectionError(
                f"Cannot reach Ollama at {self._base_url}: {e.reason}"
            ) from e
        except TimeoutError:
            raise OllamaConnectionError(
                f"Ollama request timed out after {self._timeout}s."
            )

        assembled = {
            "message": {
                "role": "assistant",
                "content": "".join(text_parts),
                "tool_calls": raw_tool_calls,
            }
        }
        return self._parse_response(assembled)

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
