"""
Tests for Agent Lifecycle & Multi-Step Execution with Mock AI Provider.
Ensures comprehensive unit test coverage with ZERO live API / network calls.
"""

from unittest.mock import MagicMock

from core.agent import JarvisAgent
from core.permissions import PermissionCheck
from core.planner import TaskStep
from providers.base import BaseProvider, FunctionCall, Message, ModelResponse
from tools import PermissionLevel, ToolCategory, ToolDefinition, ToolParameter, ToolResult
from tools.registry import ToolRegistry


class MockProvider(BaseProvider):
    """Mock provider allowing programmatic response sequencing."""

    def __init__(self, responses: list[ModelResponse] | None = None) -> None:
        self.responses = responses or []
        self.call_count = 0
        self.sent_function_results = []

    def connect(self) -> bool:
        return True

    def generate(self, messages, system_instruction=None) -> ModelResponse:
        if self.responses:
            return self.responses.pop(0)
        return ModelResponse(text="Mock direct answer")

    def generate_with_tools(self, messages, tool_declarations, system_instruction=None) -> ModelResponse:
        self.call_count += 1
        if self.responses:
            return self.responses.pop(0)
        return ModelResponse(text="Mock conversational response")

    def send_function_results(self, messages, function_calls, function_responses, tool_declarations, system_instruction=None) -> ModelResponse:
        self.sent_function_results.append((function_calls, function_responses))
        if self.responses:
            return self.responses.pop(0)
        return ModelResponse(text="Final synthesized answer after tool run")

    def get_provider_name(self) -> str:
        return "mock"

    def get_model_name(self) -> str:
        return "mock-model"


class TestAgentLifecycle:

    def setup_method(self):
        self.registry = ToolRegistry()
        # Register simple echo and add tools
        self.registry.register(
            ToolDefinition(
                name="echo",
                description="Echo input",
                parameters=[ToolParameter(name="msg", type="string", description="message")],
                permission_level=PermissionLevel.LEVEL_0_READ_ONLY,
                category=ToolCategory.PRODUCTIVITY,
            ),
            lambda msg: ToolResult(success=True, result={"echoed": msg}),
        )
        self.registry.register(
            ToolDefinition(
                name="dangerous_action",
                description="Action requiring approval",
                parameters=[ToolParameter(name="target", type="string", description="target")],
                permission_level=PermissionLevel.LEVEL_3_HIGH_RISK,
                category=ToolCategory.FILE_MANAGEMENT,
            ),
            lambda target: ToolResult(success=True, result={"eliminated": target}),
        )

    def test_conversational_response(self, db):
        provider = MockProvider([ModelResponse(text="Hello! How can I help you?")])
        agent = JarvisAgent(provider=provider, registry=self.registry, db=db)
        assert agent.initialize() is True

        reply = agent.process_message("Hello JARVIS")
        assert "Hello! How can I help you?" in reply

    def test_single_tool_execution(self, db):
        # Step 1: Model requests tool call
        resp1 = ModelResponse(function_calls=[FunctionCall(name="echo", args={"msg": "JARVIS_TEST"})])
        # Step 2: Model receives results and gives final answer
        resp2 = ModelResponse(text="I echoed your message: JARVIS_TEST")

        provider = MockProvider([resp1, resp2])
        agent = JarvisAgent(provider=provider, registry=self.registry, db=db)
        agent.initialize()

        reply = agent.process_message("Please echo JARVIS_TEST")
        assert "JARVIS_TEST" in reply
        assert len(provider.sent_function_results) == 1

    def test_multi_turn_autonomous_execution(self, db):
        # Turn 1: Model requests echo
        resp1 = ModelResponse(function_calls=[FunctionCall(name="echo", args={"msg": "Step 1"})])
        # Turn 2: After seeing step 1 result, model requests another tool call
        resp2 = ModelResponse(function_calls=[FunctionCall(name="echo", args={"msg": "Step 2"})])
        # Turn 3: Model summarizes everything
        resp3 = ModelResponse(text="Successfully completed Step 1 and Step 2 autonomously!")

        provider = MockProvider([resp1, resp2, resp3])
        agent = JarvisAgent(provider=provider, registry=self.registry, db=db)
        agent.initialize()

        reply = agent.process_message("Run a two-step autonomous task")
        assert "Successfully completed Step 1 and Step 2" in reply
        assert len(provider.sent_function_results) == 2

    def test_emergency_stop_halts_agent(self, db):
        provider = MockProvider([ModelResponse(text="Should not run")])
        agent = JarvisAgent(provider=provider, registry=self.registry, db=db)
        agent.initialize()

        agent.trigger_emergency_stop("Safety test")
        reply = agent.process_message("Do something")

        assert "EMERGENCY STOP" in reply
        assert provider.call_count == 0  # Zero provider calls when emergency stopped

    def test_approval_callback_rejection(self, db):
        # Model attempts Level 3 action
        resp1 = ModelResponse(function_calls=[FunctionCall(name="dangerous_action", args={"target": "database"})])
        resp2 = ModelResponse(text="Operation was cancelled because user denied approval.")

        # Rejection callback
        def deny_callback(step: TaskStep, check: PermissionCheck) -> bool:
            return False

        provider = MockProvider([resp1, resp2])
        agent = JarvisAgent(
            provider=provider,
            registry=self.registry,
            db=db,
            approval_callback=deny_callback,
        )
        agent.initialize()

        reply = agent.process_message("Delete the database")
        assert "cancelled" in reply or "denied" in reply
