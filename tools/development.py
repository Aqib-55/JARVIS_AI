"""
Development Assistance tools for JARVIS AI.

Provides safe Python file creation with syntax checking, code inspection,
error diagnosis, restricted subprocess execution, and whitelisted command runs.
"""

import ast
import logging
import subprocess
import sys
from pathlib import Path

from config.settings import settings
from tools import PermissionLevel, ToolCategory, ToolDefinition, ToolParameter, ToolResult

logger = logging.getLogger(__name__)

# Strict command whitelist for terminal execution
_WHITELISTED_COMMANDS: list[str] = [
    "python --version",
    "pip list",
    "git status",
    "git log",
    "git branch",
    "pytest",
    "dir",
    "echo",
    "hostname",
    "whoami",
]


def create_python_file(file_name: str, code: str) -> ToolResult:
    """
    Create a new Python file in the workspace after verifying syntax.
    """
    clean_name = file_name.strip()
    if not clean_name.endswith(".py"):
        clean_name += ".py"

    workspace = settings.WORKSPACE_DIR.resolve()
    target = (workspace / clean_name).resolve()

    # Security check: must remain inside workspace
    try:
        target.relative_to(workspace)
    except ValueError:
        return ToolResult(success=False, error=f"Access denied: cannot write outside workspace ({workspace}).")

    if target.exists():
        return ToolResult(success=False, error=f"File '{clean_name}' already exists. Overwriting requires approval.")

    # Syntax validation using AST
    try:
        ast.parse(code, filename=clean_name)
    except SyntaxError as e:
        return ToolResult(
            success=False,
            error=f"Python syntax error in generated code at line {e.lineno}: {e.msg}",
        )

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code, encoding="utf-8")
        return ToolResult(
            success=True,
            result={
                "message": f"Python file '{clean_name}' created successfully.",
                "path": clean_name,
                "lines": len(code.splitlines()),
            },
        )
    except Exception as e:
        logger.error("Failed to create Python file: %s", e)
        return ToolResult(success=False, error=f"Failed to create Python file: {e}")


def read_code_file(file_name: str, start_line: int = 1, end_line: int = 200) -> ToolResult:
    """
    Read source code with line numbers from the workspace or project directory.
    """
    workspace = settings.WORKSPACE_DIR.resolve()
    project_root = settings.PROJECT_ROOT.resolve()

    clean = file_name.strip().strip("'\"")
    target = (workspace / clean).resolve()

    # Allow reading from project root if it exists there and not outside project
    if not target.exists():
        alt_target = (project_root / clean).resolve()
        try:
            alt_target.relative_to(project_root)
            target = alt_target
        except ValueError:
            pass

    # Check if target is inside workspace or project root
    is_allowed = False
    for root in (workspace, project_root):
        try:
            target.relative_to(root)
            is_allowed = True
            break
        except ValueError:
            continue

    if not is_allowed:
        return ToolResult(success=False, error=f"Access denied: path is outside allowed workspace and project directories.")

    if not target.exists() or not target.is_file():
        return ToolResult(success=False, error=f"Code file not found: {file_name}")

    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        total_lines = len(lines)
        start = max(1, start_line)
        end = min(total_lines, end_line)

        formatted = [
            f"{i:4d} | {lines[i - 1]}"
            for i in range(start, end + 1)
        ]

        return ToolResult(
            success=True,
            result={
                "file": file_name,
                "total_lines": total_lines,
                "range": f"L{start}-L{end}",
                "content": "\n".join(formatted),
            },
        )
    except Exception as e:
        logger.error("Failed to read code file: %s", e)
        return ToolResult(success=False, error=f"Failed to read code file: {e}")


def explain_code_error(code: str, error_message: str) -> ToolResult:
    """
    Analyze a Python syntax or runtime error and provide automated diagnostics.
    """
    diagnosis = []

    # Check for syntax errors directly via AST
    try:
        ast.parse(code)
        syntax_ok = True
    except SyntaxError as e:
        syntax_ok = False
        diagnosis.append(f"Syntax Error at line {e.lineno}, col {e.offset}: {e.msg}")
        if e.text:
            diagnosis.append(f"Problematic code: {e.text.strip()}")

    err_lower = error_message.lower()
    if "indentationerror" in err_lower:
        diagnosis.append("Fix: Consistent indentation is required. Use 4 spaces per indentation level.")
    elif "nameerror" in err_lower:
        diagnosis.append("Fix: A variable or function is referenced before being defined or imported.")
    elif "typeerror" in err_lower:
        diagnosis.append("Fix: Check argument types or incompatible operator operations.")
    elif "indexerror" in err_lower:
        diagnosis.append("Fix: List/tuple index out of bounds. Verify sequence length before indexing.")
    elif "keyerror" in err_lower:
        diagnosis.append("Fix: Dictionary key does not exist. Use dict.get(key, default) or check key presence.")
    elif "attributeerror" in err_lower:
        diagnosis.append("Fix: Object is None or does not have the specified attribute/method.")

    return ToolResult(
        success=True,
        result={
            "syntax_valid": syntax_ok,
            "error_analyzed": error_message,
            "diagnostic_notes": diagnosis,
        },
    )


def run_python_script(script_name: str, timeout_seconds: int = 15) -> ToolResult:
    """
    Run an approved Python script from the workspace in a sandboxed subprocess.
    """
    workspace = settings.WORKSPACE_DIR.resolve()
    target = (workspace / script_name).resolve()

    try:
        target.relative_to(workspace)
    except ValueError:
        return ToolResult(success=False, error=f"Access denied: script must be inside workspace ({workspace}).")

    if not target.exists() or not target.is_file():
        return ToolResult(success=False, error=f"Script not found: {script_name}")

    if not target.name.endswith(".py"):
        return ToolResult(success=False, error="Only .py files can be executed.")

    python_exe = sys.executable

    try:
        proc = subprocess.run(
            [python_exe, str(target)],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=min(max(1, timeout_seconds), 30),
        )

        return ToolResult(
            success=(proc.returncode == 0),
            result={
                "exit_code": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
            },
            error=proc.stderr.strip() if proc.returncode != 0 else None,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            success=False,
            error=f"Script execution timed out after {timeout_seconds} seconds.",
        )
    except Exception as e:
        logger.error("Failed to run script '%s': %s", script_name, e)
        return ToolResult(success=False, error=f"Failed to run script: {e}")


def execute_approved_command(command: str) -> ToolResult:
    """
    Execute a strictly whitelisted command.
    Arbitrary shell commands or administrative actions are rejected.
    """
    clean_cmd = command.strip()

    # Exact or prefix match against approved whitelist
    is_approved = any(
        clean_cmd == approved or clean_cmd.startswith(f"{approved} ")
        for approved in _WHITELISTED_COMMANDS
    )

    if not is_approved:
        allowed = ", ".join(_WHITELISTED_COMMANDS)
        return ToolResult(
            success=False,
            error=f"Command '{command}' is not in the approved whitelist. Whitelisted commands: {allowed}",
        )

    try:
        proc = subprocess.run(
            clean_cmd,
            shell=True,
            cwd=str(settings.WORKSPACE_DIR.resolve()),
            capture_output=True,
            text=True,
            timeout=15,
        )
        return ToolResult(
            success=(proc.returncode == 0),
            result={
                "command": clean_cmd,
                "exit_code": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
            },
            error=proc.stderr.strip() if proc.returncode != 0 else None,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, error=f"Command '{command}' timed out after 15s.")
    except Exception as e:
        logger.error("Error executing command '%s': %s", command, e)
        return ToolResult(success=False, error=f"Execution error: {e}")


# ===================================================================
#  Tool definitions for the registry
# ===================================================================

create_python_file_definition = ToolDefinition(
    name="create_python_file",
    description="Create a syntax-checked Python file in the workspace.",
    parameters=[
        ToolParameter(
            name="file_name",
            type="string",
            description="Filename (e.g. 'script.py').",
        ),
        ToolParameter(
            name="code",
            type="string",
            description="Python code.",
        ),
    ],
    permission_level=PermissionLevel.LEVEL_1_LOW_RISK,
    category=ToolCategory.DEVELOPMENT,
)

read_code_file_definition = ToolDefinition(
    name="read_code_file",
    description="Read source code with line numbers.",
    parameters=[
        ToolParameter(
            name="file_name",
            type="string",
            description="File path.",
        ),
        ToolParameter(
            name="start_line",
            type="integer",
            description="Start line (default 1).",
            required=False,
        ),
        ToolParameter(
            name="end_line",
            type="integer",
            description="End line (default 200).",
            required=False,
        ),
    ],
    permission_level=PermissionLevel.LEVEL_0_READ_ONLY,
    category=ToolCategory.DEVELOPMENT,
)

explain_code_error_definition = ToolDefinition(
    name="explain_code_error",
    description="Diagnose a Python snippet and error traceback.",
    parameters=[
        ToolParameter(
            name="code",
            type="string",
            description="Python code.",
        ),
        ToolParameter(
            name="error_message",
            type="string",
            description="Traceback or error.",
        ),
    ],
    permission_level=PermissionLevel.LEVEL_0_READ_ONLY,
    category=ToolCategory.DEVELOPMENT,
)

run_python_script_definition = ToolDefinition(
    name="run_python_script",
    description="Run a workspace Python script with timeout.",
    parameters=[
        ToolParameter(
            name="script_name",
            type="string",
            description="Script path.",
        ),
        ToolParameter(
            name="timeout_seconds",
            type="integer",
            description="Timeout seconds (default 15).",
            required=False,
        ),
    ],
    permission_level=PermissionLevel.LEVEL_2_MODERATE_RISK,
    category=ToolCategory.DEVELOPMENT,
)

execute_approved_command_definition = ToolDefinition(
    name="execute_approved_command",
    description="Run a whitelisted terminal command (e.g. git status, pip list).",
    parameters=[
        ToolParameter(
            name="command",
            type="string",
            description="Whitelisted command.",
        ),
    ],
    permission_level=PermissionLevel.LEVEL_2_MODERATE_RISK,
    category=ToolCategory.DEVELOPMENT,
)
