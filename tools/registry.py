"""
Tool Registry — central catalog of all tools available to JARVIS.

Tools must be registered here before the agent can use them.
The registry provides tool discovery, categorization, validation,
timeout enforcement, and execution.
"""

import concurrent.futures
import logging
import time
from typing import Any, Callable

from tools import ToolCategory, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Manages all available tools for the JARVIS agent."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, Callable[..., ToolResult]] = {}

    def register(
        self,
        definition: ToolDefinition,
        handler: Callable[..., ToolResult],
    ) -> None:
        """
        Register a tool with its definition and handler function.

        Args:
            definition: The tool's metadata, category, and parameter schema.
            handler: The function that executes the tool.
        """
        if definition.name in self._tools:
            logger.warning("Overwriting existing tool: %s", definition.name)

        self._tools[definition.name] = definition
        self._handlers[definition.name] = handler
        logger.info("Registered tool: %s [%s]", definition.name, definition.category.value)

    def get_definition(self, name: str) -> ToolDefinition | None:
        """Get a tool's definition by name."""
        return self._tools.get(name)

    def get_handler(self, name: str) -> Callable[..., ToolResult] | None:
        """Get a tool's handler function by name."""
        return self._handlers.get(name)

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def list_tools(self) -> list[ToolDefinition]:
        """Return all registered tool definitions."""
        return list(self._tools.values())

    def list_by_category(self, category: ToolCategory) -> list[ToolDefinition]:
        """Return all tool definitions under a specific category."""
        return [tool for tool in self._tools.values() if tool.category == category]

    def get_declarations(self) -> list[dict[str, Any]]:
        """Return all tool declarations in the format AI providers expect."""
        return [tool.to_declaration() for tool in self._tools.values()]

    def validate_args(self, name: str, args: dict[str, Any]) -> tuple[bool, str]:
        """
        Validate arguments against a tool's parameter schema.

        Returns:
            (is_valid, error_message) — error_message is "" when valid.
        """
        definition = self._tools.get(name)
        if definition is None:
            return False, f"Unknown tool: {name}"

        # Check required parameters are present and types match
        for param in definition.parameters:
            if param.required and param.name not in args:
                return False, f"Missing required parameter: {param.name}"

            if param.name in args:
                value = args[param.name]
                if param.type == "string" and not isinstance(value, str):
                    return False, f"Parameter '{param.name}' must be a string."
                elif param.type in ("number", "integer") and not isinstance(value, (int, float)):
                    return False, f"Parameter '{param.name}' must be a number."
                elif param.type == "boolean" and not isinstance(value, bool):
                    return False, f"Parameter '{param.name}' must be a boolean."
                elif param.type == "array" and not isinstance(value, list):
                    return False, f"Parameter '{param.name}' must be a list."
                elif param.type == "object" and not isinstance(value, dict):
                    return False, f"Parameter '{param.name}' must be a dictionary."

                # Enum validation
                if param.enum and value not in param.enum:
                    allowed = ", ".join(param.enum)
                    return False, f"Parameter '{param.name}' must be one of: {allowed}"

        return True, ""

    def execute(self, name: str, args: dict[str, Any], timeout: float | None = None) -> ToolResult:
        """
        Validate and execute a tool with timeout enforcement.

        This does NOT check permissions — that is the executor's job.
        """
        handler = self._handlers.get(name)
        if handler is None:
            return ToolResult(success=False, error=f"Unknown tool: {name}")

        # Validate arguments
        is_valid, error = self.validate_args(name, args)
        if not is_valid:
            return ToolResult(success=False, error=error)

        definition = self._tools[name]
        timeout_seconds = timeout or definition.timeout_seconds

        # Filter to only known parameters so unexpected kwargs don't cause errors
        known_params = {p.name for p in definition.parameters}
        filtered_args = {k: v for k, v in args.items() if k in known_params}

        start_time = time.perf_counter()

        try:
            # Enforce execution timeout
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(handler, **filtered_args)
                try:
                    result = future.result(timeout=timeout_seconds)
                except concurrent.futures.TimeoutError:
                    elapsed = (time.perf_counter() - start_time) * 1000
                    logger.error("Tool '%s' timed out after %.1fs", name, timeout_seconds)
                    return ToolResult(
                        success=False,
                        error=f"Tool '{name}' execution timed out after {timeout_seconds:.1f} seconds.",
                        execution_time_ms=elapsed,
                    )

            elapsed = (time.perf_counter() - start_time) * 1000
            if isinstance(result, ToolResult):
                result.execution_time_ms = elapsed
            else:
                result = ToolResult(success=True, result=result, execution_time_ms=elapsed)

            logger.info("Tool '%s' executed successfully in %.2fms", name, elapsed)
            return result

        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.error("Tool '%s' failed: %s", name, e)
            return ToolResult(
                success=False,
                error=f"Tool execution error: {e}",
                execution_time_ms=elapsed,
            )
