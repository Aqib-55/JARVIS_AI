"""
Tests for extended tool suites:
- File Management (rename, copy, move, delete with confirmation)
- System Automation (system info, resource usage, process list, app whitelist)
- Productivity (notes, reminders, tasks, summarizer)
- Development Assistance (Python file syntax check, read code, error explainer, script runner, command whitelist)
"""

import sys
from unittest.mock import patch

from config.settings import settings
from tools.development import (
    create_python_file,
    execute_approved_command,
    explain_code_error,
    read_code_file,
    run_python_script,
)
from tools.filesystem import copy_file, delete_file, move_file, rename_file
from tools.productivity import manage_notes, manage_reminders, manage_tasks, summarize_text
from tools.system_automation import get_resource_usage, get_system_info, list_processes, open_application


class TestExtendedFileManagement:

    def test_rename_file(self, temp_workspace):
        f = temp_workspace / "old.txt"
        f.write_text("content", encoding="utf-8")
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            res = rename_file("old.txt", "new.txt")
            assert res.success is True
            assert (temp_workspace / "new.txt").exists()
            assert not (temp_workspace / "old.txt").exists()

    def test_copy_file(self, temp_workspace):
        f = temp_workspace / "orig.txt"
        f.write_text("hello copy", encoding="utf-8")
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            res = copy_file("orig.txt", "copied.txt")
            assert res.success is True
            assert (temp_workspace / "orig.txt").exists()
            assert (temp_workspace / "copied.txt").read_text() == "hello copy"

    def test_move_file(self, temp_workspace):
        f = temp_workspace / "source.txt"
        f.write_text("moving", encoding="utf-8")
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            res = move_file("source.txt", "sub/dest.txt")
            assert res.success is True
            assert not (temp_workspace / "source.txt").exists()
            assert (temp_workspace / "sub" / "dest.txt").exists()

    def test_delete_file_without_confirm(self, temp_workspace):
        f = temp_workspace / "keep.txt"
        f.write_text("data", encoding="utf-8")
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            res = delete_file("keep.txt", confirm=False)
            assert res.success is False
            assert "explicit confirmation" in res.error
            assert f.exists()

    def test_delete_file_with_confirm(self, temp_workspace):
        f = temp_workspace / "remove.txt"
        f.write_text("delete me", encoding="utf-8")
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            res = delete_file("remove.txt", confirm=True)
            assert res.success is True
            assert not f.exists()


class TestSystemAutomationTools:

    def test_get_system_info(self):
        res = get_system_info()
        assert res.success is True
        assert "os" in res.result
        assert "python_version" in res.result

    def test_get_resource_usage(self):
        res = get_resource_usage()
        assert res.success is True
        assert "cpu_usage_percent" in res.result
        assert "ram_total_gb" in res.result

    def test_list_processes(self):
        res = list_processes(limit=5)
        assert res.success is True
        assert len(res.result["processes"]) <= 5

    def test_open_application_whitelist_rejection(self):
        res = open_application("malicious_virus.exe")
        assert res.success is False
        assert "not in the approved whitelist" in res.error


class TestProductivityTools:

    def test_manage_notes_lifecycle(self, db):
        with patch.object(settings, "DB_PATH", db.db_path):
            # Create
            c_res = manage_notes(action="create", title="Test Note", content="Test Body")
            assert c_res.success is True
            note_id = c_res.result["note_id"]

            # Read
            r_res = manage_notes(action="read", note_id=note_id)
            assert r_res.success is True
            assert r_res.result["title"] == "Test Note"

            # List
            l_res = manage_notes(action="list")
            assert l_res.success is True
            assert any(n["id"] == note_id for n in l_res.result["notes"])

            # Delete
            d_res = manage_notes(action="delete", note_id=note_id)
            assert d_res.success is True

    def test_manage_reminders_lifecycle(self, db):
        with patch.object(settings, "DB_PATH", db.db_path):
            add_res = manage_reminders(action="add", text="Call Mom", due_at="tomorrow")
            assert add_res.success is True
            rem_id = add_res.result["reminder_id"]

            list_res = manage_reminders(action="list")
            assert list_res.success is True
            assert any(r["id"] == rem_id for r in list_res.result["reminders"])

            comp_res = manage_reminders(action="complete", reminder_id=rem_id)
            assert comp_res.success is True

    def test_manage_tasks_lifecycle(self, db):
        with patch.object(settings, "DB_PATH", db.db_path):
            t_res = manage_tasks(action="add", task_text="Implement Phase 2", priority="high")
            assert t_res.success is True
            task_id = t_res.result["task_id"]

            list_res = manage_tasks(action="list")
            assert list_res.success is True
            assert any(t["id"] == task_id for t in list_res.result["tasks"])

            c_res = manage_tasks(action="complete", task_id=task_id)
            assert c_res.success is True

    def test_summarize_text(self):
        text = (
            "Artificial intelligence is transforming software engineering. "
            "Automated agents can execute multi-step workflows with proper tool integration. "
            "Security and permission validation are critical for autonomous systems."
        )
        res = summarize_text(text, max_points=2)
        assert res.success is True
        assert len(res.result["summary_points"]) <= 2
        assert res.result["original_word_count"] > 10


class TestDevelopmentTools:

    def test_create_python_file_valid_syntax(self, temp_workspace):
        code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            res = create_python_file("calc.py", code)
            assert res.success is True
            assert (temp_workspace / "calc.py").read_text() == code

    def test_create_python_file_syntax_error(self, temp_workspace):
        bad_code = "def bad_func(:\n    pass"
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            res = create_python_file("bad.py", bad_code)
            assert res.success is False
            assert "syntax error" in res.error.lower()

    def test_read_code_file(self, temp_workspace):
        code = "x = 10\ny = 20\nprint(x + y)\n"
        f = temp_workspace / "math_ops.py"
        f.write_text(code, encoding="utf-8")
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            res = read_code_file("math_ops.py", start_line=1, end_line=2)
            assert res.success is True
            assert "L1-L2" in res.result["range"]
            assert "x = 10" in res.result["content"]

    def test_explain_code_error(self):
        code = "print(1 / 0)"
        res = explain_code_error(code, "ZeroDivisionError: division by zero")
        assert res.success is True
        assert res.result["syntax_valid"] is True

    def test_run_python_script_execution(self, temp_workspace):
        code = "print('JARVIS_TEST_OUTPUT')\n"
        f = temp_workspace / "script.py"
        f.write_text(code, encoding="utf-8")
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            res = run_python_script("script.py", timeout_seconds=5)
            assert res.success is True
            assert "JARVIS_TEST_OUTPUT" in res.result["stdout"]

    def test_execute_approved_command(self, temp_workspace):
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            res = execute_approved_command("python --version")
            assert res.success is True
            assert "Python" in res.result["stdout"] or "Python" in res.result["stderr"]

    def test_execute_approved_command_reject_unauthorized(self, temp_workspace):
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            res = execute_approved_command("rm -rf /")
            assert res.success is False
            assert "not in the approved whitelist" in res.error
