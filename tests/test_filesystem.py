"""Tests for the filesystem tool."""

from unittest.mock import patch

from config.settings import settings
from tools.filesystem import (
    _resolve_safe_path,
    create_file,
    create_folder,
    file_exists,
    list_files,
    read_file,
)


class TestPathSafety:
    """Path traversal must be blocked."""

    def test_normal_path(self, temp_workspace):
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            path, error = _resolve_safe_path("test.txt")
            assert path is not None
            assert error == ""

    def test_subdirectory(self, temp_workspace):
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            path, error = _resolve_safe_path("subdir/test.txt")
            assert path is not None
            assert error == ""

    def test_block_parent_traversal(self, temp_workspace):
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            path, error = _resolve_safe_path("../../etc/passwd")
            assert path is None
            assert "outside the workspace" in error

    def test_block_absolute_outside(self, temp_workspace):
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            path, error = _resolve_safe_path("C:\\Windows\\System32\\config")
            assert path is None
            assert "outside the workspace" in error


class TestListFiles:

    def test_empty_directory(self, temp_workspace):
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            result = list_files(".")
            assert result.success is True
            assert result.result["count"] == 0

    def test_with_files(self, temp_workspace):
        (temp_workspace / "test.txt").write_text("hello")
        (temp_workspace / "subdir").mkdir()
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            result = list_files(".")
            assert result.success is True
            assert result.result["count"] == 2

    def test_nonexistent_directory(self, temp_workspace):
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            result = list_files("nonexistent")
            assert result.success is False


class TestCreateFolder:

    def test_create(self, temp_workspace):
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            result = create_folder("Reports")
            assert result.success is True
            assert result.result["created"] is True
            assert (temp_workspace / "Reports").is_dir()

    def test_nested(self, temp_workspace):
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            result = create_folder("Reports/Monthly/January")
            assert result.success is True
            assert (temp_workspace / "Reports" / "Monthly" / "January").is_dir()

    def test_existing(self, temp_workspace):
        (temp_workspace / "Existing").mkdir()
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            result = create_folder("Existing")
            assert result.success is True
            assert result.result["created"] is False

    def test_outside_workspace(self, temp_workspace):
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            result = create_folder("../../evil")
            assert result.success is False


class TestCreateFile:

    def test_create(self, temp_workspace):
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            result = create_file("hello.txt", "Hello, World!")
            assert result.success is True
            assert (temp_workspace / "hello.txt").read_text() == "Hello, World!"

    def test_no_overwrite(self, temp_workspace):
        (temp_workspace / "existing.txt").write_text("original")
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            result = create_file("existing.txt", "new content")
            assert result.success is False
            assert "already exists" in result.error

    def test_in_subdirectory(self, temp_workspace):
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            result = create_file("subdir/test.txt", "content")
            assert result.success is True
            assert (temp_workspace / "subdir" / "test.txt").exists()


class TestReadFile:

    def test_read(self, temp_workspace):
        (temp_workspace / "test.txt").write_text("Hello, World!", encoding="utf-8")
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            result = read_file("test.txt")
            assert result.success is True
            assert result.result["content"] == "Hello, World!"

    def test_nonexistent(self, temp_workspace):
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            result = read_file("nonexistent.txt")
            assert result.success is False

    def test_outside_workspace(self, temp_workspace):
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            result = read_file("../../secret.txt")
            assert result.success is False


class TestFileExists:

    def test_exists(self, temp_workspace):
        (temp_workspace / "test.txt").write_text("hello")
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            result = file_exists("test.txt")
            assert result.success is True
            assert result.result["exists"] is True

    def test_not_exists(self, temp_workspace):
        with patch.object(settings, "WORKSPACE_DIR", temp_workspace):
            result = file_exists("nope.txt")
            assert result.success is True
            assert result.result["exists"] is False
