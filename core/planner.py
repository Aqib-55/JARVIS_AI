"""
Task Planner — converts instructions and model tool requests into structured,
dependency-aware execution plans.

Supports:
- Multi-step task decomposition
- Task dependency graphs
- Execution ordering
- Status tracking across PENDING, PLANNING, RUNNING, WAITING_FOR_APPROVAL,
  COMPLETED, FAILED, CANCELLED
- Retry limits and failure detection
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from providers.base import FunctionCall

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Lifecycle statuses for a task plan."""
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    """Lifecycle statuses for individual task steps."""
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"

    # Backward compatibility alias
    APPROVAL_NEEDED = "waiting_for_approval"


@dataclass
class TaskStep:
    """A single step within an execution plan."""
    step_number: int
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str | None = None
    depends_on: list[int] = field(default_factory=list)  # Step numbers that must complete first
    max_retries: int = 1
    retry_count: int = 0
    retry_delay_seconds: float = 1.0
    started_at: str | None = None
    completed_at: str | None = None

    @property
    def can_retry(self) -> bool:
        """Whether this step has remaining retry attempts."""
        return self.status == StepStatus.FAILED and self.retry_count < self.max_retries


@dataclass
class TaskPlan:
    """A structured, ordered, dependency-aware plan of tool executions."""
    steps: list[TaskStep] = field(default_factory=list)
    description: str = ""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: TaskStatus = TaskStatus.PENDING
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)

    @property
    def has_failures(self) -> bool:
        return any(s.status == StepStatus.FAILED for s in self.steps)

    @property
    def is_complete(self) -> bool:
        return all(
            s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
            for s in self.steps
        )

    @property
    def needs_approval(self) -> bool:
        return any(
            s.status in (StepStatus.WAITING_FOR_APPROVAL, StepStatus.APPROVAL_NEEDED)
            for s in self.steps
        )

    def add_step(self, step: TaskStep) -> None:
        """Add an execution step to the plan."""
        self.steps.append(step)

    def validate_dependencies(self) -> tuple[bool, str]:
        """
        Validate that all dependencies exist and that there are no circular dependencies.
        """
        step_numbers = {s.step_number for s in self.steps}
        for s in self.steps:
            for dep in s.depends_on:
                if dep not in step_numbers:
                    return False, f"Step {s.step_number} depends on non-existent step {dep}."
                if dep >= s.step_number:
                    return False, f"Circular or forward dependency: Step {s.step_number} depends on step {dep}."
        return True, ""

    def get_ready_steps(self) -> list[TaskStep]:
        """
        Return pending steps whose dependencies have all completed successfully.
        """
        completed_step_nums = {
            s.step_number for s in self.steps if s.status == StepStatus.COMPLETED
        }
        ready = []
        for s in self.steps:
            if s.status == StepStatus.PENDING:
                if all(dep in completed_step_nums for dep in s.depends_on):
                    ready.append(s)
        return ready

    def mark_cancelled(self, reason: str = "Plan cancelled.") -> None:
        """Cancel this plan and all non-completed steps."""
        self.status = TaskStatus.CANCELLED
        self.error = reason
        self.completed_at = datetime.now().isoformat()
        for s in self.steps:
            if s.status in (StepStatus.PENDING, StepStatus.PLANNING, StepStatus.WAITING_FOR_APPROVAL):
                s.status = StepStatus.CANCELLED

    def summary(self) -> str:
        """Human-readable summary of the plan and its progress."""
        lines: list[str] = []
        lines.append(f"Task [{self.task_id}]: {self.description or 'Execution Plan'} ({self.status.value.upper()})")

        icons = {
            StepStatus.PENDING: "⏳",
            StepStatus.PLANNING: "📝",
            StepStatus.RUNNING: "🔄",
            StepStatus.COMPLETED: "✅",
            StepStatus.FAILED: "❌",
            StepStatus.SKIPPED: "⏭️",
            StepStatus.WAITING_FOR_APPROVAL: "🔐",
            StepStatus.CANCELLED: "🚫",
        }
        for step in self.steps:
            icon = icons.get(step.status, "❓")
            desc = step.description or step.tool_name
            dep_info = f" [after {step.depends_on}]" if step.depends_on else ""
            lines.append(f"  {icon} Step {step.step_number}: {desc}{dep_info}")

        return "\n".join(lines)


class TaskPlanner:
    """Decomposes instructions and model tool requests into structured task plans."""

    def create_plan(
        self,
        function_calls: list[FunctionCall],
        description: str = "",
    ) -> TaskPlan:
        """
        Create a task plan from model-generated function calls.

        Args:
            function_calls: Function calls requested by the AI model.
            description: Human-readable description of the overall task.
        """
        steps = []
        for i, fc in enumerate(function_calls, start=1):
            # By default, consecutive function calls depend on the prior step if chained
            depends_on = [i - 1] if i > 1 else []
            steps.append(
                TaskStep(
                    step_number=i,
                    tool_name=fc.name,
                    arguments=fc.args,
                    description=f"Execute {fc.name}",
                    depends_on=depends_on,
                )
            )

        plan = TaskPlan(
            steps=steps,
            description=description,
            status=TaskStatus.PLANNING,
            started_at=datetime.now().isoformat(),
        )
        logger.info("Created task plan '%s' with %d step(s)", plan.task_id, plan.total_steps)
        return plan

    def create_single_step_plan(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        description: str = "",
    ) -> TaskPlan:
        """Convenience: create a plan with a single tool execution step."""
        step = TaskStep(
            step_number=1,
            tool_name=tool_name,
            arguments=arguments,
            description=description or f"Execute {tool_name}",
        )
        return TaskPlan(
            steps=[step],
            description=description,
            status=TaskStatus.PLANNING,
            started_at=datetime.now().isoformat(),
        )

    def create_multi_step_plan(
        self,
        steps_data: list[dict[str, Any]],
        description: str = "",
    ) -> TaskPlan:
        """
        Programmatically construct a multi-step plan with explicit dependencies.

        Each dict in steps_data can specify:
        - tool_name (str, required)
        - arguments (dict, optional)
        - description (str, optional)
        - depends_on (list[int], optional)
        - max_retries (int, optional)
        """
        steps = []
        for i, data in enumerate(steps_data, start=1):
            step = TaskStep(
                step_number=i,
                tool_name=data["tool_name"],
                arguments=data.get("arguments", {}),
                description=data.get("description", f"Execute {data['tool_name']}"),
                depends_on=data.get("depends_on", []),
                max_retries=data.get("max_retries", 1),
            )
            steps.append(step)

        plan = TaskPlan(
            steps=steps,
            description=description,
            status=TaskStatus.PLANNING,
            started_at=datetime.now().isoformat(),
        )
        is_valid, err = plan.validate_dependencies()
        if not is_valid:
            logger.error("Plan validation failed: %s", err)
            plan.status = TaskStatus.FAILED
            plan.error = err

        return plan
