"""Shared pytest fixtures for JARVIS AI tests."""

import pytest

from memory.database import DatabaseManager


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace directory for filesystem tests."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture
def db(tmp_path):
    """Create a test database in a temp directory."""
    db_path = tmp_path / "data" / "test_jarvis.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    database = DatabaseManager(db_path=db_path)
    database.initialize()
    return database
