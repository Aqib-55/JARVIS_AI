"""
Database Manager — SQLite database initialization and connection management.

Creates and manages the JARVIS SQLite database with proper schema,
indexes, and parameterized queries.  API keys and secrets are NEVER stored here.
"""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from config.settings import settings

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2

SCHEMA_SQL = """
-- Conversations
CREATE TABLE IF NOT EXISTS conversations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT      NOT NULL,
    started_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at      TIMESTAMP,
    message_count INTEGER   DEFAULT 0
);

-- Messages
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER,
    role            TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

-- Tasks
CREATE TABLE IF NOT EXISTS tasks (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id  INTEGER,
    user_request     TEXT    NOT NULL,
    status           TEXT    NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','planning','running','waiting_for_approval','completed','failed','cancelled')),
    plan_description TEXT,
    total_steps      INTEGER DEFAULT 0,
    completed_steps  INTEGER DEFAULT 0,
    started_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at     TIMESTAMP,
    error            TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

-- Task steps
CREATE TABLE IF NOT EXISTS task_steps (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id      INTEGER NOT NULL,
    step_number  INTEGER NOT NULL,
    tool_name    TEXT    NOT NULL,
    arguments    TEXT,
    status       TEXT    NOT NULL DEFAULT 'pending',
    result       TEXT,
    error        TEXT,
    started_at   TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

-- Tool execution audit log
CREATE TABLE IF NOT EXISTS tool_executions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER,
    tool_name   TEXT    NOT NULL,
    arguments   TEXT,
    success     INTEGER NOT NULL,
    result      TEXT,
    error       TEXT,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

-- User preferences
CREATE TABLE IF NOT EXISTS user_preferences (
    key        TEXT PRIMARY KEY,
    value      TEXT      NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Important facts (long-term memory)
CREATE TABLE IF NOT EXISTS important_facts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    category   TEXT NOT NULL DEFAULT 'general',
    fact       TEXT NOT NULL,
    source     TEXT DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Notes
CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    content    TEXT NOT NULL,
    tags       TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Reminders
CREATE TABLE IF NOT EXISTS reminders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    reminder_text TEXT NOT NULL,
    due_at        TEXT,
    status        TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'completed', 'dismissed')),
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Todo items
CREATE TABLE IF NOT EXISTS todo_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_text    TEXT NOT NULL,
    priority     TEXT DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high')),
    status       TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'completed')),
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Tool usage metrics
CREATE TABLE IF NOT EXISTS tool_usage_metrics (
    tool_name     TEXT PRIMARY KEY,
    call_count    INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_used_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_info (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created      ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_status           ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_started          ON tasks(started_at);
CREATE INDEX IF NOT EXISTS idx_task_steps_task        ON task_steps(task_id);
CREATE INDEX IF NOT EXISTS idx_tool_exec_task         ON tool_executions(task_id);
CREATE INDEX IF NOT EXISTS idx_tool_exec_time         ON tool_executions(executed_at);
CREATE INDEX IF NOT EXISTS idx_facts_category         ON important_facts(category);
CREATE INDEX IF NOT EXISTS idx_notes_title            ON notes(title);
CREATE INDEX IF NOT EXISTS idx_reminders_status       ON reminders(status);
CREATE INDEX IF NOT EXISTS idx_todo_status            ON todo_items(status);
"""


class DatabaseManager:
    """Manages the SQLite database connection, schema migration, and access."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or settings.DB_PATH
        self._initialized = False

    def initialize(self) -> None:
        """Create database and all tables if they don't exist."""
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)

            with self._get_connection() as conn:
                conn.executescript(SCHEMA_SQL)
                conn.execute(
                    "INSERT OR REPLACE INTO schema_info (key, value) VALUES (?, ?)",
                    ("schema_version", str(SCHEMA_VERSION)),
                )
                conn.commit()

            self._initialized = True
            logger.info("Database initialized at: %s (v%d)", self._db_path, SCHEMA_VERSION)
        except Exception as e:
            logger.error("Failed to initialize database: %s", e)
            raise

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection with proper settings."""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Public connection context manager used by memory modules."""
        if not self._initialized:
            self.initialize()
        with self._get_connection() as conn:
            yield conn

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def is_initialized(self) -> bool:
        return self._initialized
