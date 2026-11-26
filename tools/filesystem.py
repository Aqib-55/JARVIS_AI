"""
Filesystem tool — safe file and folder operations.

ALL operations are restricted to the approved JARVIS workspace directory
(or any explicitly added allowlist directories).
Path traversal and access outside approved directories are blocked.
"""

import logging
import os
import shutil
from pathlib import Path

from config.settings import settings
from tools import PermissionLevel, ToolCategory, ToolDefinition, ToolParameter, ToolResult

logger = logging.getLogger(__name__)


# ===================================================================
#  Path safety
# ===================================================================

def _resolve_safe_path(relative_path: str) -> tuple[Path | None, str]:
    """
    Resolve a user-supplied path and verify it stays inside the workspace.

    Returns:
        (resolved_path, error_message) — resolved_path is None on error.
    """
    try:
        workspace = settings.WORKSPACE_DIR.resolve()
        clean = relative_path.strip().strip("'\"")

        # Build an absolute path relative to the workspace
        if os.path.isabs(clean):
            target = Path(clean).resolve()
        else:
            target = (workspace / clean).resolve()

        # Security check: must remain inside the workspace
        try:
            target.relative_to(workspace)
        except ValueError:
            return None, (
                f"Access denied: path '{relative_path}' is outside the workspace "
                f"directory. All file operations are restricted to: {workspace}"
            )

        return target, ""

    except Exception as e:
        return None, f"Invalid path '{relative_path}': {e}"


# ===================================================================
#  Tool handler functions
# ===================================================================

def list_files(path: str = ".") -> ToolResult:
    """List files and directories in a workspace folder."""
    target, error = _resolve_safe_path(path)
    if target is None:
        return ToolResult(success=False, error=error)

    if not target.exists():
        return ToolResult(success=False, error=f"Directory not found: {path}")
    if not target.is_dir():
        return ToolResult(success=False, error=f"Not a directory: {path}")

    try:
        entries = []
        for item in sorted(target.iterdir()):
            entries.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
            })
        return ToolResult(
            success=True,
            result={
                "path": str(target.relative_to(settings.WORKSPACE_DIR.resolve())),
                "entries": entries,
                "count": len(entries),
            },
        )
    except PermissionError:
        return ToolResult(success=False, error=f"Permission denied: {path}")
    except Exception as e:
        return ToolResult(success=False, error=f"Error listing files: {e}")


def create_folder(folder_name: str) -> ToolResult:
    """Create a new folder in the workspace."""
    target, error = _resolve_safe_path(folder_name)
    if target is None:
        return ToolResult(success=False, error=error)

    if target.exists():
        return ToolResult(
            success=True,
            result={"message": f"Folder already exists: {folder_name}", "created": False},
        )

    try:
        target.mkdir(parents=True, exist_ok=True)
        if target.is_dir():
            return ToolResult(
                success=True,
                result={"message": f"Folder created: {folder_name}", "created": True},
            )
        return ToolResult(success=False, error="Folder creation could not be verified.")
    except PermissionError:
        return ToolResult(success=False, error=f"Permission denied creating folder: {folder_name}")
    except Exception as e:
        return ToolResult(success=False, error=f"Error creating folder: {e}")


def create_file(file_name: str, content: str = "") -> ToolResult:
    """Create a new text file in the workspace (will not overwrite existing)."""
    target, error = _resolve_safe_path(file_name)
    if target is None:
        return ToolResult(success=False, error=error)

    if target.exists():
        return ToolResult(
            success=False,
            error=f"File already exists: {file_name}. Overwriting requires approval.",
        )

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        if target.is_file():
            return ToolResult(
                success=True,
                result={"message": f"File created: {file_name}", "size": target.stat().st_size},
            )
        return ToolResult(success=False, error="File creation could not be verified.")
    except PermissionError:
        return ToolResult(success=False, error=f"Permission denied creating file: {file_name}")
    except Exception as e:
        return ToolResult(success=False, error=f"Error creating file: {e}")


def read_file(file_name: str) -> ToolResult:
    """Read a text file from the workspace."""
    target, error = _resolve_safe_path(file_name)
    if target is None:
        return ToolResult(success=False, error=error)

    if not target.exists():
        return ToolResult(success=False, error=f"File not found: {file_name}")
    if not target.is_file():
        return ToolResult(success=False, error=f"Not a file: {file_name}")

    max_size = 1_048_576  # 1 MB
    file_size = target.stat().st_size
    if file_size > max_size:
        return ToolResult(
            success=False,
            error=f"File too large to read ({file_size:,} bytes, max {max_size:,}).",
        )

    try:
        content = target.read_text(encoding="utf-8")
        return ToolResult(
            success=True,
            result={"file": file_name, "content": content, "size": len(content)},
        )
    except UnicodeDecodeError:
        return ToolResult(success=False, error=f"Cannot read binary file: {file_name}")
    except Exception as e:
        return ToolResult(success=False, error=f"Error reading file: {e}")


def search_files(pattern: str, path: str = ".") -> ToolResult:
    """Search for files matching a name pattern in the workspace."""
    target, error = _resolve_safe_path(path)
    if target is None:
        return ToolResult(success=False, error=error)

    if not target.exists() or not target.is_dir():
        return ToolResult(success=False, error=f"Directory not found: {path}")

    try:
        matches = []
        workspace_root = settings.WORKSPACE_DIR.resolve()
        for item in target.rglob(f"*{pattern}*"):
            if any(part.startswith(".") for part in item.relative_to(workspace_root).parts):
                continue
            matches.append({
                "path": str(item.relative_to(workspace_root)),
                "type": "directory" if item.is_dir() else "file",
            })
        return ToolResult(
            success=True,
            result={"pattern": pattern, "matches": matches, "count": len(matches)},
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Search error: {e}")


def file_exists(file_name: str) -> ToolResult:
    """Check whether a file or folder exists in the workspace."""
    target, error = _resolve_safe_path(file_name)
    if target is None:
        return ToolResult(success=False, error=error)

    exists = target.exists()
    item_type = (
        "directory" if target.is_dir()
        else "file" if target.is_file()
        else "unknown"
    )
    return ToolResult(
        success=True,
        result={"path": file_name, "exists": exists, "type": item_type if exists else None},
    )


def rename_file(old_path: str, new_name: str) -> ToolResult:
    """Rename a file or folder inside the workspace."""
    src, error = _resolve_safe_path(old_path)
    if src is None:
        return ToolResult(success=False, error=error)

    if not src.exists():
        return ToolResult(success=False, error=f"Item not found: {old_path}")

    # The new target must be in the same parent directory
    dest = src.parent / new_name
    dest_path, dest_error = _resolve_safe_path(str(dest.relative_to(settings.WORKSPACE_DIR.resolve())))
    if dest_path is None:
        return ToolResult(success=False, error=dest_error)

    if dest_path.exists():
        return ToolResult(success=False, error=f"Destination '{new_name}' already exists.")

    try:
        src.rename(dest_path)
        return ToolResult(
            success=True,
            result={"message": f"Renamed '{old_path}' to '{new_name}'", "new_path": str(new_name)},
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Error renaming item: {e}")


def copy_file(source: str, destination: str) -> ToolResult:
    """Copy a file within the workspace."""
    src, error = _resolve_safe_path(source)
    if src is None:
        return ToolResult(success=False, error=error)

    dest, dest_error = _resolve_safe_path(destination)
    if dest is None:
        return ToolResult(success=False, error=dest_error)

    if not src.exists():
        return ToolResult(success=False, error=f"Source file not found: {source}")
    if src.is_dir():
        return ToolResult(success=False, error=f"Source '{source}' is a directory, not a file.")

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return ToolResult(
            success=True,
            result={"message": f"Copied '{source}' to '{destination}'", "size": dest.stat().st_size},
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Error copying file: {e}")


def move_file(source: str, destination: str) -> ToolResult:
    """Move a file or directory within the workspace."""
    src, error = _resolve_safe_path(source)
    if src is None:
        return ToolResult(success=False, error=error)

    dest, dest_error = _resolve_safe_path(destination)
    if dest is None:
        return ToolResult(success=False, error=dest_error)

    if not src.exists():
        return ToolResult(success=False, error=f"Source not found: {source}")

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        return ToolResult(
            success=True,
            result={"message": f"Moved '{source}' to '{destination}'"},
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Error moving item: {e}")


def delete_file(file_name: str, confirm: bool = False) -> ToolResult:
    """
    Delete a file or empty directory in the workspace (Level 3 High Risk).
    Requires explicit confirmation.
    """
    if not confirm:
        return ToolResult(
            success=False,
            error=f"Deletion requires explicit confirmation. Set confirm=True to delete '{file_name}'.",
        )

    target, error = _resolve_safe_path(file_name)
    if target is None:
        return ToolResult(success=False, error=error)

    if not target.exists():
        return ToolResult(success=False, error=f"File or directory not found: {file_name}")

    # Never delete the workspace root itself
    if target == settings.WORKSPACE_DIR.resolve():
        return ToolResult(success=False, error="Cannot delete the workspace root directory.")

    try:
        if target.is_dir():
            # Check if directory has contents
            if any(target.iterdir()):
                shutil.rmtree(target)
            else:
                target.rmdir()
        else:
            target.unlink()

        return ToolResult(
            success=True,
            result={"message": f"Successfully deleted: {file_name}", "deleted": True},
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Error deleting '{file_name}': {e}")


# ===================================================================
#  Tool definitions for the registry
# ===================================================================

list_files_definition = ToolDefinition(
    name="list_files",
    description="List workspace files and folders.",
    parameters=[
        ToolParameter(
            name="path",
            type="string",
            description="Relative subfolder (optional).",
            required=False,
        ),
    ],
    permission_level=PermissionLevel.LEVEL_0_READ_ONLY,
    category=ToolCategory.FILE_MANAGEMENT,
)

create_folder_definition = ToolDefinition(
    name="create_folder",
    description="Create a folder in the workspace.",
    parameters=[
        ToolParameter(
            name="folder_name",
            type="string",
            description="Folder name/path.",
        ),
    ],
    permission_level=PermissionLevel.LEVEL_1_LOW_RISK,
    category=ToolCategory.FILE_MANAGEMENT,
)

create_file_definition = ToolDefinition(
    name="create_file",
    description="Create a text file in the workspace.",
    parameters=[
        ToolParameter(
            name="file_name",
            type="string",
            description="File name/path.",
        ),
        ToolParameter(
            name="content",
            type="string",
            description="Text content.",
            required=False,
        ),
    ],
    permission_level=PermissionLevel.LEVEL_1_LOW_RISK,
    category=ToolCategory.FILE_MANAGEMENT,
)

read_file_definition = ToolDefinition(
    name="read_file",
    description="Read a workspace text file.",
    parameters=[
        ToolParameter(
            name="file_name",
            type="string",
            description="File name/path.",
        ),
    ],
    permission_level=PermissionLevel.LEVEL_0_READ_ONLY,
    category=ToolCategory.FILE_MANAGEMENT,
)

search_files_definition = ToolDefinition(
    name="search_files",
    description="Search workspace files by name pattern.",
    parameters=[
        ToolParameter(
            name="pattern",
            type="string",
            description="Filename pattern.",
        ),
        ToolParameter(
            name="path",
            type="string",
            description="Subfolder (optional).",
            required=False,
        ),
    ],
    permission_level=PermissionLevel.LEVEL_0_READ_ONLY,
    category=ToolCategory.FILE_MANAGEMENT,
)

file_exists_definition = ToolDefinition(
    name="file_exists",
    description="Check if a workspace file or folder exists.",
    parameters=[
        ToolParameter(
            name="file_name",
            type="string",
            description="Name/path to check.",
        ),
    ],
    permission_level=PermissionLevel.LEVEL_0_READ_ONLY,
    category=ToolCategory.FILE_MANAGEMENT,
)

rename_file_definition = ToolDefinition(
    name="rename_file",
    description="Rename a workspace file or folder.",
    parameters=[
        ToolParameter(
            name="old_path",
            type="string",
            description="Current relative path.",
        ),
        ToolParameter(
            name="new_name",
            type="string",
            description="New name.",
        ),
    ],
    permission_level=PermissionLevel.LEVEL_2_MODERATE_RISK,
    category=ToolCategory.FILE_MANAGEMENT,
)

copy_file_definition = ToolDefinition(
    name="copy_file",
    description="Copy a workspace file.",
    parameters=[
        ToolParameter(
            name="source",
            type="string",
            description="Source path.",
        ),
        ToolParameter(
            name="destination",
            type="string",
            description="Destination path.",
        ),
    ],
    permission_level=PermissionLevel.LEVEL_1_LOW_RISK,
    category=ToolCategory.FILE_MANAGEMENT,
)

move_file_definition = ToolDefinition(
    name="move_file",
    description="Move a workspace file or folder.",
    parameters=[
        ToolParameter(
            name="source",
            type="string",
            description="Source path.",
        ),
        ToolParameter(
            name="destination",
            type="string",
            description="Destination path.",
        ),
    ],
    permission_level=PermissionLevel.LEVEL_2_MODERATE_RISK,
    category=ToolCategory.FILE_MANAGEMENT,
)

delete_file_definition = ToolDefinition(
    name="delete_file",
    description="Delete a workspace file/folder (high risk; needs confirm=True).",
    parameters=[
        ToolParameter(
            name="file_name",
            type="string",
            description="Target path.",
        ),
        ToolParameter(
            name="confirm",
            type="boolean",
            description="Confirm deletion.",
            required=False,
        ),
    ],
    permission_level=PermissionLevel.LEVEL_3_HIGH_RISK,
    category=ToolCategory.FILE_MANAGEMENT,
)
