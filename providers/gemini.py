"""
Google Gemini AI provider implementation.

Uses the official google-genai SDK (v3.x+).
Handles connection, text generation, tool calling, and error recovery.
"""

import logging
import time
from typing import Any, Callable

from google import genai
from google.genai import types

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


class GeminiProvider(BaseProvider):
    """Google Gemini API provider."""

    def __init__(self, api_key: str = "", model: str = "") -> None:
        self._api_key = api_key or settings.GEMINI_API_KEY
        self._model = model or settings.GEMINI_MODEL
        self._client: genai.Client | None = None

    # ------------------------------------------------------------------
    #  Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Initialize the Gemini client and verify the connection."""
        if not self._api_key:
            logger.error("Gemini connection failed: GEMINI_API_KEY is not configured.")
            return False

        try:
            self._client = genai.Client(api_key=self._api_key)
            # Quick health check
            response = self._client.models.generate_content(
                model=self._model,
                contents="Respond with the single word OK.",
                config=types.GenerateContentConfig(
                    max_output_tokens=200,
                    temperature=0.0,
                ),
            )
            if response.text:
                logger.info("Gemini connection verified (model: %s)", self._model)
                return True
            return False
        except Exception as e:
            logger.error("Failed to connect to Gemini: %s", self._handle_error(e))
            return False

    def _generate_with_retry(
        self,
        call_fn: Callable[[], Any],
        max_attempts: int = 3,
        initial_delay: float = 1.0,
    ) -> Any:
        """Execute a Gemini API call with exponential backoff for transient 503/429 errors."""
        for attempt in range(1, max_attempts + 1):
            try:
                return call_fn()
            except Exception as e:
                s = str(e)
                is_transient = any(code in s for code in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED"))
                if is_transient and attempt < max_attempts:
                    delay = initial_delay * (2 ** (attempt - 1))
                    logger.warning("Transient Gemini API error. Retrying in %.1fs (attempt %d/%d)...", delay, attempt, max_attempts)
                    time.sleep(delay)
                else:
                    raise

    # ------------------------------------------------------------------
    #  Generation
    # ------------------------------------------------------------------

    def generate(
        self,
        messages: list[Message],
        system_instruction: str | None = None,
    ) -> ModelResponse:
        if not self._client:
            return ModelResponse(error="Gemini client not connected. Call connect() first.")
        try:
            contents = self._build_contents(messages)
            config_kwargs: dict[str, Any] = {
                "temperature": 0.7,
                "max_output_tokens": 4096,
            }
            if system_instruction:
                config_kwargs["system_instruction"] = system_instruction
            config = types.GenerateContentConfig(**config_kwargs)

            response = self._generate_with_retry(
                lambda: self._client.models.generate_content(
                    model=self._model, contents=contents, config=config,
                )
            )
            return self._parse_response(response)
        except Exception as e:
            return ModelResponse(error=self._handle_error(e))

    def generate_with_tools(
        self,
        messages: list[Message],
        tool_declarations: list[dict[str, Any]],
        system_instruction: str | None = None,
    ) -> ModelResponse:
        if not self._client:
            return ModelResponse(error="Gemini client not connected. Call connect() first.")
        try:
            contents = self._build_contents(messages)
            tools = self._build_tools(tool_declarations)
            config_kwargs: dict[str, Any] = {
                "tools": tools,
                "temperature": 0.7,
                "max_output_tokens": 4096,
            }
            if system_instruction:
                config_kwargs["system_instruction"] = system_instruction
            config = types.GenerateContentConfig(**config_kwargs)

            response = self._generate_with_retry(
                lambda: self._client.models.generate_content(
                    model=self._model, contents=contents, config=config,
                )
            )
            return self._parse_response(response)
        except Exception as e:
            return ModelResponse(error=self._handle_error(e))

    def send_function_results(
        self,
        messages: list[Message],
        function_calls: list[FunctionCall],
        function_responses: list[FunctionResponse],
        tool_declarations: list[dict[str, Any]],
        system_instruction: str | None = None,
    ) -> ModelResponse:
        """Send function results back so the model can produce a final answer."""
        if not self._client:
            return ModelResponse(error="Gemini client not connected.")
        try:
            contents = self._build_contents(messages)
            tools = self._build_tools(tool_declarations)

            # Append the model's function-call turn
            fc_parts = [
                types.Part(
                    function_call=types.FunctionCall(name=fc.name, args=fc.args)
                )
                for fc in function_calls
            ]
            contents.append(types.Content(role="model", parts=fc_parts))

            # Append our function-response turn
            fr_parts = [
                types.Part(
                    function_response=types.FunctionResponse(
                        name=fr.name, response=fr.response,
                    )
                )
                for fr in function_responses
            ]
            contents.append(types.Content(role="user", parts=fr_parts))

            config_kwargs: dict[str, Any] = {
                "tools": tools,
                "temperature": 0.7,
                "max_output_tokens": 4096,
            }
            if system_instruction:
                config_kwargs["system_instruction"] = system_instruction
            config = types.GenerateContentConfig(**config_kwargs)

            response = self._generate_with_retry(
                lambda: self._client.models.generate_content(
                    model=self._model, contents=contents, config=config,
                )
            )
            return self._parse_response(response)
        except Exception as e:
            return ModelResponse(error=self._handle_error(e))

    # ------------------------------------------------------------------
    #  Private helpers
    # ------------------------------------------------------------------

    def _build_contents(self, messages: list[Message]) -> list[types.Content]:
        """Convert internal Message objects to Gemini Content format."""
        contents: list[types.Content] = []
        for msg in messages:
            role = "user" if msg.role == MessageRole.USER else "model"
            contents.append(
                types.Content(role=role, parts=[types.Part(text=msg.content)])
            )
        return contents

    def _build_tools(
        self, tool_declarations: list[dict[str, Any]],
    ) -> list[types.Tool]:
        """Convert internal tool declarations to Gemini Tool format."""
        fds = []
        for decl in tool_declarations:
            fds.append(
                types.FunctionDeclaration(
                    name=decl["name"],
                    description=decl["description"],
                    parameters=decl.get("parameters"),
                )
            )
        return [types.Tool(function_declarations=fds)]

    def _parse_response(self, response: Any) -> ModelResponse:
        """Parse a Gemini response into our standardized ModelResponse."""
        function_calls: list[FunctionCall] = []
        text: str | None = None

        if response.function_calls:
            for fc in response.function_calls:
                function_calls.append(
                    FunctionCall(
                        name=fc.name,
                        args=dict(fc.args) if fc.args else {},
                    )
                )

        if response.text:
            text = response.text

        return ModelResponse(
            text=text,
            function_calls=function_calls,
            provider=self.get_provider_name(),
            model=self._model,
        )

    def _handle_error(self, error: Exception) -> str:
        """Convert exceptions to user-friendly error messages with credentials redacted."""
        s = str(error)

        # Redact the API key if it appears anywhere in the raw exception
        if self._api_key and self._api_key in s:
            s = s.replace(self._api_key, "[REDACTED_API_KEY]")

        if "API_KEY" in s or "401" in s or "403" in s or "api key not valid" in s.lower():
            msg = "Authentication failed. Please check your GEMINI_API_KEY in .env."
        elif "404" in s or "NOT_FOUND" in s:
            msg = f"Model '{self._model}' not found or no longer available. Please set GEMINI_MODEL in .env to a supported model (e.g. gemini-3.5-flash)."
        elif "429" in s or "RATE_LIMIT" in s.upper():
            msg = "Rate limit exceeded. Please wait a moment and try again."
        elif "503" in s or "UNAVAILABLE" in s:
            msg = "Gemini service temporarily unavailable due to high demand. Please try again in a moment."
        elif "TIMEOUT" in s.upper() or "timed out" in s.lower():
            msg = "Request timed out. Please check your internet connection."
        elif "connection" in s.lower() or "network" in s.lower():
            msg = "Network error. Please check your internet connection."
        else:
            msg = f"Gemini API error: {s}"

        logger.error("Gemini error: %s", msg)
        return msg

    # ------------------------------------------------------------------
    #  Metadata
    # ------------------------------------------------------------------

    def get_provider_name(self) -> str:
        return "gemini"

    def get_model_name(self) -> str:
        return self._model
