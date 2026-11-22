"""
Task Executor — executes approved task plans with dependency awareness,
retry logic, timeout enforcement, and emergency stop protection.
"""

import logging
import time
from datetime import datetime
from typing import Any, Callable

from core.permissions import PermissionCheck, PermissionManager
from core.planner import StepStatus, TaskPlan, TaskStatus, TaskStep
from tools import ToolResult
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Executes structured task plans step-by-step with dependency checking and safety rules."""

    def __init__(
        self,
        registry: ToolRegistry,
        permission_manager: PermissionManager,
        max_tool_calls: int = 15,
    ) -> None:
        self._registry = registry
        self._permissions = permission_manager
        self._max_tool_calls = max_tool_calls

    def execute_plan(
        self,
        plan: TaskPlan,
        approval_callback: Callable[[TaskStep, PermissionCheck], bool] | None = None,
    ) -> TaskPlan:
        """
        Execute a task plan respecting dependencies and safety checks.

        Args:
            plan: The task plan to execute.
            approval_callback: Interactive callback for actions requiring user confirmation.

        Returns:
            The executed plan with updated step statuses, results, and timing.
        """
        plan.status = TaskStatus.RUNNING
        if not plan.started_at:
            plan.started_at = datetime.now().isoformat()

        # Validate dependency structure
        valid, dep_err = plan.validate_dependencies()
        if not valid:
            plan.status = TaskStatus.FAILED
            plan.error = f"Invalid dependency structure: {dep_err}"
            plan.completed_at = datetime.now().isoformat()
            return plan

        # Prevent runaway execution loops
        if plan.total_steps > self._max_tool_calls:
            logger.warning(
                "Plan has %d steps — truncating to maximum allowed of %d",
                plan.total_steps,
                self._max_tool_calls,
            )
            plan.steps = plan.steps[: self._max_tool_calls]

        # Iteratively execute ready steps until all are done or a failure blocks the rest
        executed_any = True
        while executed_any:
            # Check global emergency stop before every iteration
            if self._permissions.is_emergency_stopped:
                plan.status = TaskStatus.CANCELLED
                plan.error = f"Execution halted by EMERGENCY STOP: {self._permissions.emergency_reason}"
                for s in plan.steps:
                    if s.status == StepStatus.PENDING:
                        s.status = StepStatus.CANCELLED
                break

            ready_steps = plan.get_ready_steps()
            if not ready_steps:
                break

            executed_any = False
            for step in ready_steps:
                success = self._execute_step_with_retries(step, approval_callback)
                executed_any = True

                if not success:
                    # Mark any dependent downstream steps as SKIPPED
                    self._skip_dependent_steps(plan, step.step_number)
                    break

        # Finalize overall plan status
        if plan.status != TaskStatus.CANCELLED:
            if plan.has_failures:
                plan.status = TaskStatus.FAILED
                failed_step = next((s for s in plan.steps if s.status == StepStatus.FAILED), None)
                plan.error = failed_step.error if failed_step else "One or more steps failed."
            else:
                plan.status = TaskStatus.COMPLETED

        plan.completed_at = datetime.now().isoformat()
        return plan

    def _execute_step_with_retries(
        self,
        step: TaskStep,
        approval_callback: Callable[[TaskStep, PermissionCheck], bool] | None = None,
    ) -> bool:
        """Execute a step, retrying up to max_retries if transient failure occurs."""
        attempt = 0
        while attempt <= step.max_retries:
            step.retry_count = attempt
            success = self._execute_step(step, approval_callback)

            if success:
                return True

            attempt += 1
            if attempt <= step.max_retries:
                logger.info(
                    "Retrying step %d (%s) in %.1fs (attempt %d/%d)",
                    step.step_number,
                    step.tool_name,
                    step.retry_delay_seconds,
                    attempt,
                    step.max_retries,
                )
                time.sleep(step.retry_delay_seconds)
                step.status = StepStatus.PENDING  # Reset for retry

        return False

    def _execute_step(
        self,
        step: TaskStep,
        approval_callback: Callable[[TaskStep, PermissionCheck], bool] | None = None,
    ) -> bool:
        """Execute a single task step."""
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now().isoformat()
        logger.info("Executing step %d: %s", step.step_number, step.tool_name)

        # 1. Tool existence check
        definition = self._registry.get_definition(step.tool_name)
        if definition is None:
            step.status = StepStatus.FAILED
            step.error = f"Unknown tool: '{step.tool_name}' is not registered."
            step.completed_at = datetime.now().isoformat()
            logger.error("Step %d failed: %s", step.step_number, step.error)
            return False

        # 2. Argument schema validation
        is_valid, error = self._registry.validate_args(step.tool_name, step.arguments)
        if not is_valid:
            step.status = StepStatus.FAILED
            step.error = f"Invalid arguments: {error}"
            step.completed_at = datetime.now().isoformat()
            logger.error("Step %d failed: %s", step.step_number, step.error)
            return False

        # 3. Permission and authorization check
        perm_check = self._permissions.check(
            definition.permission_level,
            step.tool_name,
            step.arguments,
        )

        if not perm_check.allowed:
            if perm_check.needs_approval:
                step.status = StepStatus.WAITING_FOR_APPROVAL
                if approval_callback:
                    approved = approval_callback(step, perm_check)
                    if not approved:
                        step.status = StepStatus.SKIPPED
                        step.error = "User declined confirmation for this action."
                        step.completed_at = datetime.now().isoformat()
                        return False
                    # Approved: resume execution
                    step.status = StepStatus.RUNNING
                else:
                    step.error = perm_check.reason
                    step.completed_at = datetime.now().isoformat()
                    return False
            else:
                step.status = StepStatus.FAILED
                step.error = perm_check.reason
                step.completed_at = datetime.now().isoformat()
                return False

        # 4. Tool Execution with Timeout
        try:
            result = self._registry.execute(
                step.tool_name,
                step.arguments,
                timeout=definition.timeout_seconds,
            )
            step.completed_at = datetime.now().isoformat()

            if result.success:
                step.status = StepStatus.COMPLETED
                step.result = result.result
                logger.info("Step %d completed successfully (%.1fms)", step.step_number, result.execution_time_ms)
                return True
            else:
                step.status = StepStatus.FAILED
                step.error = result.error
                logger.error("Step %d failed: %s", step.step_number, result.error)
                return False

        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = f"Unexpected execution error: {e}"
            step.completed_at = datetime.now().isoformat()
            logger.error("Step %d exception: %s", step.step_number, e)
            return False

    def _skip_dependent_steps(self, plan: TaskPlan, failed_step_num: int) -> None:
        """Mark any steps that depend on the failed step as SKIPPED."""
        for s in plan.steps:
            if s.status == StepStatus.PENDING and failed_step_num in s.depends_on:
                s.status = StepStatus.SKIPPED
                s.error = f"Skipped because dependency Step {failed_step_num} failed."
                self._skip_dependent_steps(plan, s.step_number)

    def execute_single(
        self,
        tool_name: str,
        args: dict[str, Any],
        approval_callback: Callable[[TaskStep, PermissionCheck], bool] | None = None,
    ) -> ToolResult:
        """Execute a single tool invocation directly."""
        definition = self._registry.get_definition(tool_name)
        if definition is None:
            return ToolResult(success=False, error=f"Unknown tool: '{tool_name}' is not registered.")

        is_valid, error = self._registry.validate_args(tool_name, args)
        if not is_valid:
            return ToolResult(success=False, error=error)

        perm_check = self._permissions.check(
            definition.permission_level, tool_name, args,
        )
        if not perm_check.allowed:
            if perm_check.needs_approval and approval_callback:
                step = TaskStep(step_number=1, tool_name=tool_name, arguments=args)
                approved = approval_callback(step, perm_check)
                if not approved:
                    return ToolResult(success=False, error="User denied confirmation.")
            else:
                return ToolResult(success=False, error=perm_check.reason)

        return self._registry.execute(tool_name, args, timeout=definition.timeout_seconds)
