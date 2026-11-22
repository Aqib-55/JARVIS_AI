"""Tests for the tool registry."""

from tools import ToolDefinition, ToolParameter, ToolResult
from tools.registry import ToolRegistry


def _dummy_tool(text: str = "hello") -> ToolResult:
    """Simple tool for testing."""
    return ToolResult(success=True, result={"echo": text})


class TestToolRegistry:

    def test_register_and_retrieve(self):
        reg = ToolRegistry()
        defn = ToolDefinition(
            name="echo",
            description="Echo tool",
            parameters=[ToolParameter(name="text", type="string", description="Text")],
        )
        reg.register(defn, _dummy_tool)
        assert reg.has_tool("echo")
        assert reg.get_definition("echo") is not None

    def test_execute(self):
        reg = ToolRegistry()
        defn = ToolDefinition(
            name="echo",
            description="Echo tool",
            parameters=[ToolParameter(name="text", type="string", description="Text")],
        )
        reg.register(defn, _dummy_tool)
        result = reg.execute("echo", {"text": "world"})
        assert result.success is True
        assert result.result["echo"] == "world"

    def test_missing_required_param(self):
        reg = ToolRegistry()
        defn = ToolDefinition(
            name="echo",
            description="Echo",
            parameters=[
                ToolParameter(name="text", type="string", description="Text", required=True),
            ],
        )
        reg.register(defn, _dummy_tool)
        is_valid, error = reg.validate_args("echo", {})
        assert is_valid is False
        assert "Missing required" in error

    def test_wrong_type(self):
        reg = ToolRegistry()
        defn = ToolDefinition(
            name="echo",
            description="Echo",
            parameters=[ToolParameter(name="text", type="string", description="Text")],
        )
        reg.register(defn, _dummy_tool)
        is_valid, _error = reg.validate_args("echo", {"text": 123})
        assert is_valid is False

    def test_unknown_tool(self):
        reg = ToolRegistry()
        result = reg.execute("nonexistent", {})
        assert result.success is False

    def test_declarations(self):
        reg = ToolRegistry()
        defn = ToolDefinition(
            name="echo",
            description="Echo tool",
            parameters=[ToolParameter(name="text", type="string", description="Text")],
        )
        reg.register(defn, _dummy_tool)
        decls = reg.get_declarations()
        assert len(decls) == 1
        assert decls[0]["name"] == "echo"
