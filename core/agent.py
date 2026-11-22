"""
JARVIS Agent — the central intelligent task execution orchestrator.

Coordinates:
- Conversation manager (session sliding window)
- AI provider (Gemini with function calling & retry logic)
- Task planner (dependency-aware multi-step planning)
- Task executor (permission validation & execution engine)
- Tool registry (categorized tools across files, system, productivity, dev)
- Memory manager (SQLite-based facts, preferences, metrics, and search)
- Permission manager (4-tier security model & emergency stop)
"""

import logging
from typing import Any, Callable

from config.settings import settings
from core.conversation import ConversationManager
from core.executor import TaskExecutor
from core.permissions import PermissionCheck, PermissionManager
from core.planner import StepStatus, TaskPlan, TaskPlanner, TaskStatus
from memory.conversation_history import ConversationHistoryManager
from memory.database import DatabaseManager
from memory.memory_manager import MemoryManager
from memory.task_history import TaskHistoryManager
from providers.base import (
    BaseProvider,
    FunctionCall,
    FunctionResponse,
    MessageRole,
    ModelResponse,
)
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# Base system instruction defining agent behavior and safety rules
SYSTEM_INSTRUCTION = """\
You are JARVIS, a highly competent, production-minded personal AI task-execution assistant.

Your capabilities:
1. File Management: List, create, read, copy, move, rename, and delete files inside the workspace.
2. System Automation: Check CPU, RAM, and Disk metrics; list processes; launch approved apps and websites.
3. Productivity: Manage persistent notes, reminders, todo tasks, and summarize text.
4. Development Assistance: Create verified Python files, read source code, analyze errors, run sandboxed scripts, and run approved commands.

Operating Principles:
- Understand user intent carefully. When crucial information or parameters are missing, ask for clarification.
- Break complex instructions into clear, logical steps.
- Explain the planned operation before executing moderate or high risk actions.
- Never execute destructive actions (e.g. deleting files) without explicit confirmation.
- If a tool fails, report the error clearly and offer a recovery strategy.
- Never fabricate information — use tools to inspect real state.
- All file operations must stay strictly within approved directories.
"""


class JarvisAgent:
    """
    Main JARVIS agent orchestrating intelligent conversation, planning,
    autonomous multi-step execution, memory retrieval, and security enforcement.
    """

    def __init__(
        self,
        provider: BaseProvider,
        registry: ToolRegistry,
        db: DatabaseManager,
        approval_callback: Callable[[Any, PermissionCheck], bool] | None = None,
        max_autonomous_turns: int = 6,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._db = db
        self._max_autonomous_turns = max_autonomous_turns

        # Core modules
        self._conversation = ConversationManager()
        self._planner = TaskPlanner()
        self._permissions = PermissionManager()
        self._executor = TaskExecutor(
            registry=registry,
            permission_manager=self._permissions,
            max_tool_calls=settings.MAX_TOOL_CALLS_PER_TASK,
        )

        # Memory subsystems
        self._task_history = TaskHistoryManager(db)
        self._conversation_history = ConversationHistoryManager(db)
        self._memory_manager = MemoryManager(db)

        # Interactive approval callback
        self._approval_callback = approval_callback

        self._connected = False

    # ------------------------------------------------------------------
    #  Initialization & Shutdown
    # ------------------------------------------------------------------

    def initialize(self) -> bool:
        """Initialize database tables, verify AI provider connection, start session."""
        try:
            self._db.initialize()
            logger.info("Database initialized.")

            self._connected = self._provider.connect()
            if not self._connected:
                logger.error("Failed to connect to AI provider.")
                return False

            logger.info(
                "Connected to %s (%s)",
                self._provider.get_provider_name(),
                self._provider.get_model_name(),
            )

            self._conversation_history.start_session()
            return True

        except Exception as e:
            logger.error("Agent initialization failed: %s", e)
            return False

    def shutdown(self) -> None:
        """Clean up resources and finalize database session."""
        self._conversation_history.end_session()
        logger.info("JARVIS agent shut down.")

    # ------------------------------------------------------------------
    #  Emergency Stop Controls
    # ------------------------------------------------------------------

    def trigger_emergency_stop(self, reason: str = "User triggered emergency stop.") -> None:
        """Trigger global emergency stop."""
        self._permissions.trigger_emergency_stop(reason)

    def clear_emergency_stop(self) -> None:
        """Clear emergency stop."""
        self._permissions.clear_emergency_stop()

    @property
    def is_emergency_stopped(self) -> bool:
        return self._permissions.is_emergency_stopped

    # ------------------------------------------------------------------
    #  Message Processing & Autonomous Multi-Step Execution
    # ------------------------------------------------------------------

    def process_message(self, user_input: str) -> str:
        """
        Process a user instruction end-to-end.
        Supports autonomous multi-step tool calls, context retrieval,
        and safe error recovery.
        """
        if not self._connected:
            return "⚠️ Not connected to AI provider. Please check your configuration."

        if self._permissions.is_emergency_stopped:
            return f"⚠️ Execution is blocked by EMERGENCY STOP: {self._permissions.emergency_reason}\nType /resume to clear emergency stop."

        # Record incoming message
        self._conversation.add_message(MessageRole.USER, user_input)
        self._conversation_history.save_message("user", user_input)

        try:
            # Build dynamic prompt with retrieved user context
            dynamic_instruction = self._build_dynamic_instruction(user_input)

            messages = self._conversation.get_messages()
            tool_declarations = self._registry.get_declarations()

            # First turn: model decides whether to respond directly or request tools
            response = self._provider.generate_with_tools(
                messages=messages,
                tool_declarations=tool_declarations,
                system_instruction=dynamic_instruction,
            )

            if response.is_error:
                return self._store_and_return(f"⚠️ {response.error}")

            # If the model requested tool execution, enter the autonomous execution loop
            if response.has_function_calls:
                return self._autonomous_execution_loop(user_input, response, dynamic_instruction)

            # Plain text response
            reply = response.text or "I'm not sure how to respond to that."
            return self._store_and_return(reply)

        except Exception as e:
            logger.error("Error processing message: %s", e)
            return self._store_and_return(f"⚠️ An unexpected error occurred: {e}")

    def _autonomous_execution_loop(
        self,
        user_request: str,
        initial_response: ModelResponse,
        system_instruction: str,
    ) -> str:
        """
        Executes multi-step tool calls autonomously.
        Runs tool calls -> feeds results back to Gemini -> if Gemini requests further
        tools (e.g. step 2 after inspecting results), repeats until complete or max turns reached.
        """
        current_response = initial_response
        turn = 0
        final_reply = ""

        # Create overall task tracking record in SQLite
        task_id = self._task_history.create_task(
            user_request=user_request,
            conversation_id=self._conversation_history.current_conversation_id,
            plan_description=f"Autonomous execution for: {user_request[:100]}",
            total_steps=len(current_response.function_calls),
        )

        while current_response.has_function_calls and turn < self._max_autonomous_turns:
            turn += 1
            logger.info("Autonomous execution turn %d/%d", turn, self._max_autonomous_turns)

            # Emergency stop check before every turn
            if self._permissions.is_emergency_stopped:
                self._task_history.update_task(
                    task_id=task_id,
                    status=TaskStatus.CANCELLED.value,
                    error=self._permissions.emergency_reason,
                )
                return self._store_and_return(
                    f"⚠️ Execution halted by EMERGENCY STOP: {self._permissions.emergency_reason}"
                )

            function_calls = current_response.function_calls

            # 1. Create plan for this turn
            plan = self._planner.create_plan(
                function_calls=function_calls,
                description=f"Turn {turn}: {user_request}",
            )

            # 2. Execute plan
            plan = self._executor.execute_plan(
                plan=plan,
                approval_callback=self._approval_callback,
            )

            # 3. Persist steps and record tool metrics
            for step in plan.steps:
                self._task_history.save_step(
                    task_id=task_id,
                    step_number=step.step_number,
                    tool_name=step.tool_name,
                    arguments=step.arguments,
                    status=step.status.value,
                    result=step.result,
                    error=step.error,
                )
                self._task_history.log_tool_execution(
                    tool_name=step.tool_name,
                    arguments=step.arguments,
                    success=(step.status == StepStatus.COMPLETED),
                    result=step.result,
                    error=step.error,
                    task_id=task_id,
                )
                # Update persistent metrics
                self._memory_manager.record_tool_usage(
                    tool_name=step.tool_name,
                    success=(step.status == StepStatus.COMPLETED),
                )

            # 4. If any step failed, preserve progress and evaluate recovery
            if plan.has_failures:
                logger.warning("Step in turn %d failed: %s", turn, plan.error)
                self._task_history.update_task(
                    task_id=task_id,
                    status=TaskStatus.FAILED.value,
                    completed_steps=plan.completed_steps,
                    error=plan.error,
                )
                # Inform the model of the failure so it can report or recover gracefully
                func_responses = [
                    FunctionResponse(
                        name=fc.name,
                        response={"status": "error", "error": step.error or "Step failed to execute."},
                    )
                    for fc, step in zip(function_calls, plan.steps)
                ]
                final_model_resp = self._provider.send_function_results(
                    messages=self._conversation.get_messages(),
                    function_calls=function_calls,
                    function_responses=func_responses,
                    tool_declarations=self._registry.get_declarations(),
                    system_instruction=system_instruction,
                )
                reply = final_model_resp.text or f"❌ Task halted at step '{plan.steps[-1].tool_name}': {plan.error}"
                return self._store_and_return(reply)

            # 5. Build function responses for Gemini
            func_responses = []
            for fc, step in zip(function_calls, plan.steps):
                data = step.result if isinstance(step.result, dict) else {"result": step.result}
                func_responses.append(FunctionResponse(name=fc.name, response=data))

            messages = self._conversation.get_messages()
            tool_declarations = self._registry.get_declarations()

            # 6. Send results back to Gemini
            current_response = self._provider.send_function_results(
                messages=messages,
                function_calls=function_calls,
                function_responses=func_responses,
                tool_declarations=tool_declarations,
                system_instruction=system_instruction,
            )

            if current_response.is_error:
                self._task_history.update_task(
                    task_id=task_id,
                    status=TaskStatus.FAILED.value,
                    error=current_response.error,
                )
                return self._store_and_return(f"⚠️ {current_response.error}")

            if current_response.text:
                final_reply = current_response.text

        # Mark task as completed
        self._task_history.update_task(
            task_id=task_id,
            status=TaskStatus.COMPLETED.value,
            completed_steps=turn,
        )

        if not final_reply:
            final_reply = "Task execution completed successfully."

        return self._store_and_return(final_reply)

    def _build_dynamic_instruction(self, user_input: str) -> str:
        """Augment standard system instructions with relevant user context."""
        context = self._memory_manager.get_relevant_context(user_input)
        if context:
            return f"{SYSTEM_INSTRUCTION}\n\n[Retrieved Context from Memory]:\n{context}"
        return SYSTEM_INSTRUCTION

    def _store_and_return(self, reply: str) -> str:
        """Store the assistant response in active conversation and history."""
        self._conversation.add_message(MessageRole.ASSISTANT, reply)
        self._conversation_history.save_message("assistant", reply)
        return reply

    # ------------------------------------------------------------------
    #  Status & Subsystem Access
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return system status dictionary for CLI and diagnostics."""
        return {
            "connected": self._connected,
            "provider": self._provider.get_provider_name(),
            "model": self._provider.get_model_name(),
            "tools": len(self._registry.list_tools()),
            "conversation_messages": self._conversation.message_count,
            "memory": "enabled" if self._db.is_initialized else "disabled",
            "emergency_stopped": self._permissions.is_emergency_stopped,
        }

    def get_recent_tasks(self, limit: int = 5) -> list[dict[str, Any]]:
        """Return recent tasks from history."""
        return self._task_history.get_recent_tasks(limit=limit)

    def clear_conversation(self) -> None:
        """Reset conversation window and begin a new session."""
        self._conversation.clear()
        self._conversation_history.end_session()
        self._conversation_history.start_session()

    @property
    def memory_manager(self) -> MemoryManager:
        return self._memory_manager

    @property
    def permission_manager(self) -> PermissionManager:
        return self._permissions

    @property
    def tool_registry(self) -> ToolRegistry:
        return self._registry
