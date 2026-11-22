"""
Tests for enhanced planning engine:
- Dependency validation
- Execution ordering
- Status transitions
- Retry limits
- Cancellation
"""

from core.planner import StepStatus, TaskPlan, TaskPlanner, TaskStatus, TaskStep


class TestEnhancedPlanner:

    def setup_method(self):
        self.planner = TaskPlanner()

    def test_multi_step_plan_creation(self):
        steps = [
            {"tool_name": "create_folder", "arguments": {"folder_name": "Reports"}},
            {"tool_name": "create_file", "arguments": {"file_name": "Reports/q1.txt", "content": "Q1 Data"}, "depends_on": [1]},
        ]
        plan = self.planner.create_multi_step_plan(steps, description="Quarterly Reports")
        assert plan.total_steps == 2
        assert plan.steps[1].depends_on == [1]
        assert plan.status == TaskStatus.PLANNING

    def test_dependency_validation_valid(self):
        plan = TaskPlan(
            steps=[
                TaskStep(step_number=1, tool_name="list_files"),
                TaskStep(step_number=2, tool_name="read_file", depends_on=[1]),
            ]
        )
        is_valid, err = plan.validate_dependencies()
        assert is_valid is True
        assert err == ""

    def test_dependency_validation_circular_or_forward(self):
        plan = TaskPlan(
            steps=[
                TaskStep(step_number=1, tool_name="list_files", depends_on=[2]),
                TaskStep(step_number=2, tool_name="read_file"),
            ]
        )
        is_valid, err = plan.validate_dependencies()
        assert is_valid is False
        assert "Circular or forward" in err

    def test_get_ready_steps_progression(self):
        s1 = TaskStep(step_number=1, tool_name="step1")
        s2 = TaskStep(step_number=2, tool_name="step2", depends_on=[1])
        plan = TaskPlan(steps=[s1, s2])

        # Initially, only s1 is ready
        ready = plan.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].step_number == 1

        # Complete s1
        s1.status = StepStatus.COMPLETED

        # Now s2 becomes ready
        ready = plan.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].step_number == 2

    def test_mark_cancelled(self):
        plan = TaskPlan(
            steps=[
                TaskStep(step_number=1, tool_name="toolA", status=StepStatus.PENDING),
                TaskStep(step_number=2, tool_name="toolB", status=StepStatus.PENDING),
            ]
        )
        plan.mark_cancelled("User requested stop")
        assert plan.status == TaskStatus.CANCELLED
        assert all(s.status == StepStatus.CANCELLED for s in plan.steps)

    def test_step_retry_logic(self):
        step = TaskStep(step_number=1, tool_name="calc", max_retries=2)
        assert step.can_retry is False  # Status is PENDING

        step.status = StepStatus.FAILED
        step.retry_count = 0
        assert step.can_retry is True

        step.retry_count = 2
        assert step.can_retry is False  # Reached max retries
