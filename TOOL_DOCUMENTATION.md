# JARVIS AI — Tool Catalog & Documentation

All tools are registered in `tools/registry.py` and categorized under 4 primary domains.

---

## 1. File Management (`tools/filesystem.py`)

All operations are sandboxed to `D:\JARVIS_AI\workspace` (or explicitly authorized allowlist directories).

### `list_files`
- **Description**: List files and directories in a workspace folder.
- **Parameters**: `path: string` (optional, default: `"."`).
- **Permission**: Level 0 (Read-Only).

### `create_folder`
- **Description**: Create a new directory.
- **Parameters**: `folder_name: string` (required).
- **Permission**: Level 1 (Low Risk).

### `create_file`
- **Description**: Create a text file (will not overwrite existing).
- **Parameters**: `file_name: string` (required), `content: string` (optional).
- **Permission**: Level 1 (Low Risk).

### `read_file`
- **Description**: Read contents of a text file (max 1 MB).
- **Parameters**: `file_name: string` (required).
- **Permission**: Level 0 (Read-Only).

### `search_files`
- **Description**: Search for files matching a pattern.
- **Parameters**: `pattern: string` (required), `path: string` (optional).
- **Permission**: Level 0 (Read-Only).

### `file_exists`
- **Description**: Verify whether a file or folder exists.
- **Parameters**: `file_name: string` (required).
- **Permission**: Level 0 (Read-Only).

### `rename_file`
- **Description**: Rename a file or directory.
- **Parameters**: `old_path: string` (required), `new_name: string` (required).
- **Permission**: Level 2 (Moderate Risk — requires confirmation).

### `copy_file`
- **Description**: Copy a file to a new destination.
- **Parameters**: `source: string` (required), `destination: string` (required).
- **Permission**: Level 1 (Low Risk).

### `move_file`
- **Description**: Move a file or directory.
- **Parameters**: `source: string` (required), `destination: string` (required).
- **Permission**: Level 2 (Moderate Risk — requires confirmation).

### `delete_file`
- **Description**: Delete a file or directory.
- **Parameters**: `file_name: string` (required), `confirm: boolean` (must be `true`).
- **Permission**: Level 3 (High Risk — requires confirmation).

---

## 2. System Automation (`tools/system_automation.py`)

### `get_system_info`
- **Description**: Get operating system, processor architecture, and Python runtime info.
- **Parameters**: None.
- **Permission**: Level 0 (Read-Only).

### `get_resource_usage`
- **Description**: Check CPU percentage, RAM total/used/free, and Disk storage.
- **Parameters**: None.
- **Permission**: Level 0 (Read-Only).

### `list_processes`
- **Description**: List running processes sorted by RAM or CPU.
- **Parameters**: `limit: integer` (default: 15), `sort_by: string` (`'memory'` or `'cpu'`).
- **Permission**: Level 0 (Read-Only).

### `open_application`
- **Description**: Launch an approved application from the strict whitelist.
- **Parameters**: `app_name: string` (e.g. `'chrome'`, `'notepad'`, `'calculator'`, `'vs code'`, `'edge'`).
- **Permission**: Level 2 (Moderate Risk — requires confirmation).

### `open_website`
- **Description**: Open an HTTP/HTTPS URL in the default browser.
- **Parameters**: `url: string` (required).
- **Permission**: Level 1 (Low Risk).

---

## 3. Productivity (`tools/productivity.py`, `tools/calculator.py`, `tools/datetime_tool.py`)

### `calculator`
- **Description**: Evaluates mathematical expressions using a secure AST parser (no `eval`).
- **Parameters**: `expression: string` (e.g. `"(1500 + 2500) * 1.1"`).
- **Permission**: Level 0 (Read-Only).

### `get_datetime`
- **Description**: Returns formatted date, time, weekday, and local timezone offset.
- **Parameters**: `detail: string` (`'full'`, `'date'`, `'time'`, `'weekday'`, `'timezone'`).
- **Permission**: Level 0 (Read-Only).

### `manage_notes`
- **Description**: Persistent notes management.
- **Parameters**: `action: string` (`'create'`, `'list'`, `'read'`, `'delete'`), `title: string`, `content: string`, `note_id: integer`.
- **Permission**: Level 1 (Low Risk).

### `manage_reminders`
- **Description**: Manage reminders with due dates.
- **Parameters**: `action: string` (`'add'`, `'list'`, `'complete'`, `'delete'`), `text: string`, `due_at: string`, `reminder_id: integer`.
- **Permission**: Level 1 (Low Risk).

### `manage_tasks`
- **Description**: Personal to-do task tracking with priorities.
- **Parameters**: `action: string` (`'add'`, `'list'`, `'complete'`, `'delete'`), `task_text: string`, `priority: string` (`'low'`, `'medium'`, `'high'`), `task_id: integer`.
- **Permission**: Level 1 (Low Risk).

### `summarize_text`
- **Description**: Extract key bullet points and sentence summaries from text.
- **Parameters**: `text: string` (required), `max_points: integer` (default: 5).
- **Permission**: Level 0 (Read-Only).

---

## 4. Development Assistance (`tools/development.py`)

### `create_python_file`
- **Description**: Write a `.py` file after AST-based syntax validation.
- **Parameters**: `file_name: string` (required), `code: string` (required).
- **Permission**: Level 1 (Low Risk).

### `read_code_file`
- **Description**: Read source code files with formatted line numbers.
- **Parameters**: `file_name: string`, `start_line: integer` (default: 1), `end_line: integer` (default: 200).
- **Permission**: Level 0 (Read-Only).

### `explain_code_error`
- **Description**: Analyze traceback or runtime error messages for common Python bugs.
- **Parameters**: `code: string`, `error_message: string`.
- **Permission**: Level 0 (Read-Only).

### `run_python_script`
- **Description**: Execute a `.py` script located inside the workspace with timeout protection (max 30s).
- **Parameters**: `script_name: string` (required), `timeout_seconds: integer` (default: 15).
- **Permission**: Level 2 (Moderate Risk — requires confirmation).

### `execute_approved_command`
- **Description**: Run commands strictly from the whitelist (`python --version`, `pip list`, `git status`, `pytest`, `dir`, `echo`, `hostname`, `whoami`).
- **Parameters**: `command: string`.
- **Permission**: Level 2 (Moderate Risk — requires confirmation).
