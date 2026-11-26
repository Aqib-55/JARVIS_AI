"""SQLite Memory page exposing only real MemoryManager & history data."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from desktop.theme import COLORS


class MemoryPage(QWidget):
    """Displays facts, preferences, session messages, and task audit logs from SQLite."""

    refresh_requested = Signal()
    search_requested = Signal(str)
    delete_fact_requested = Signal(int)
    delete_pref_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # Search + Refresh Header
        bar = QFrame()
        bar.setObjectName("Card")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 12, 16, 12)
        bl.setSpacing(10)

        self._status_lbl = QLabel("Memory Database: SQLite")
        self._status_lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        bl.addWidget(self._status_lbl)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search facts, notes, tasks, or messages…")
        self._search_edit.returnPressed.connect(self._on_search)
        bl.addWidget(self._search_edit, stretch=1)

        search_btn = QPushButton("Search")
        search_btn.setObjectName("PrimaryButton")
        search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        search_btn.clicked.connect(self._on_search)
        bl.addWidget(search_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._on_refresh)
        bl.addWidget(refresh_btn)

        root.addWidget(bar)

        # Tabs
        self._tabs = QTabWidget()

        # Tab 1: Facts
        facts_w = QWidget()
        fl = QVBoxLayout(facts_w)
        fl.setContentsMargins(12, 12, 12, 12)
        self._facts_table = self._make_table(["ID", "Category", "Fact", "Source", "Created"])
        fl.addWidget(self._facts_table)
        f_btn_row = QHBoxLayout()
        f_btn_row.addStretch(1)
        del_fact_btn = QPushButton("Delete Selected Fact")
        del_fact_btn.setObjectName("DangerButton")
        del_fact_btn.clicked.connect(self._on_delete_fact)
        f_btn_row.addWidget(del_fact_btn)
        fl.addLayout(f_btn_row)
        self._tabs.addTab(facts_w, "Saved Facts")

        # Tab 2: Preferences
        prefs_w = QWidget()
        pl = QVBoxLayout(prefs_w)
        pl.setContentsMargins(12, 12, 12, 12)
        self._prefs_table = self._make_table(["Key", "Value"])
        pl.addWidget(self._prefs_table)
        p_btn_row = QHBoxLayout()
        p_btn_row.addStretch(1)
        del_pref_btn = QPushButton("Delete Selected Preference")
        del_pref_btn.setObjectName("DangerButton")
        del_pref_btn.clicked.connect(self._on_delete_pref)
        p_btn_row.addWidget(del_pref_btn)
        pl.addLayout(p_btn_row)
        self._tabs.addTab(prefs_w, "Preferences")

        # Tab 3: Session Messages
        msg_w = QWidget()
        ml = QVBoxLayout(msg_w)
        ml.setContentsMargins(12, 12, 12, 12)
        self._msgs_table = self._make_table(["Role", "Content", "Created"])
        ml.addWidget(self._msgs_table)
        self._tabs.addTab(msg_w, "Conversation History")

        # Tab 4: Tasks / Search Results
        task_w = QWidget()
        tl = QVBoxLayout(task_w)
        tl.setContentsMargins(12, 12, 12, 12)
        self._tasks_table = self._make_table(["ID", "Request", "Status", "Started"])
        tl.addWidget(self._tasks_table)
        self._tabs.addTab(task_w, "Task History")

        # Tab 5: Search Hits
        hit_w = QWidget()
        hl = QVBoxLayout(hit_w)
        hl.setContentsMargins(12, 12, 12, 12)
        self._search_table = self._make_table(["Domain", "Summary", "Timestamp"])
        hl.addWidget(self._search_table)
        self._tabs.addTab(hit_w, "Search Results")

        root.addWidget(self._tabs, stretch=1)

        note = QLabel(
            "Connected directly to existing SQLite memory (`data/jarvis.db`). "
            "Conversation/task audit rows are read-only; secrets are never stored or displayed."
        )
        note.setStyleSheet(f"font-size: 11px; color: {COLORS['text_muted']};")
        root.addWidget(note)

    @staticmethod
    def _make_table(headers: list[str]) -> QTableWidget:
        tbl = QTableWidget(0, len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.verticalHeader().setVisible(False)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return tbl

    def _on_search(self) -> None:
        q = self._search_edit.text().strip()
        if not q:
            self._on_refresh()
            return
        self.search_requested.emit(q)
        self._tabs.setCurrentIndex(4)

    def _on_refresh(self) -> None:
        self._search_edit.clear()
        self.refresh_requested.emit()

    def _on_delete_fact(self) -> None:
        row = self._facts_table.currentRow()
        if row < 0:
            return
        fact_id_item = self._facts_table.item(row, 0)
        fact_text_item = self._facts_table.item(row, 2)
        if fact_id_item is None:
            return
        fact_id = int(fact_id_item.text())
        preview = fact_text_item.text() if fact_text_item else ""
        reply = QMessageBox.question(
            self,
            "Confirm Fact Deletion",
            f"Delete saved fact #{fact_id}?\n\n{preview}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_fact_requested.emit(fact_id)

    def _on_delete_pref(self) -> None:
        row = self._prefs_table.currentRow()
        if row < 0:
            return
        key_item = self._prefs_table.item(row, 0)
        if key_item is None:
            return
        key = key_item.text()
        reply = QMessageBox.question(
            self,
            "Confirm Preference Deletion",
            f"Delete user preference '{key}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_pref_requested.emit(key)

    def update_overview(self, data: dict[str, Any], db_enabled: bool = True) -> None:
        self._status_lbl.setText(
            "Memory Database: SQLite Connected" if db_enabled else "Memory Database: Disabled"
        )

        facts = data.get("facts", [])
        self._facts_table.setRowCount(len(facts))
        for r, f in enumerate(facts):
            self._facts_table.setItem(r, 0, QTableWidgetItem(str(f.get("id", ""))))
            self._facts_table.setItem(r, 1, QTableWidgetItem(str(f.get("category", ""))))
            self._facts_table.setItem(r, 2, QTableWidgetItem(str(f.get("fact", ""))))
            self._facts_table.setItem(r, 3, QTableWidgetItem(str(f.get("source", ""))))
            self._facts_table.setItem(r, 4, QTableWidgetItem(str(f.get("created_at", ""))))

        prefs = list(data.get("preferences", {}).items())
        self._prefs_table.setRowCount(len(prefs))
        for r, (k, v) in enumerate(prefs):
            self._prefs_table.setItem(r, 0, QTableWidgetItem(str(k)))
            self._prefs_table.setItem(r, 1, QTableWidgetItem(str(v)))

        msgs = data.get("session_messages", [])
        self._msgs_table.setRowCount(len(msgs))
        for r, m in enumerate(msgs):
            self._msgs_table.setItem(r, 0, QTableWidgetItem(str(m.get("role", ""))))
            self._msgs_table.setItem(r, 1, QTableWidgetItem(str(m.get("content", ""))))
            self._msgs_table.setItem(r, 2, QTableWidgetItem(str(m.get("created_at", ""))))

        tasks = data.get("tasks", [])
        self._tasks_table.setRowCount(len(tasks))
        for r, t in enumerate(tasks):
            self._tasks_table.setItem(r, 0, QTableWidgetItem(str(t.get("id", ""))))
            self._tasks_table.setItem(r, 1, QTableWidgetItem(str(t.get("user_request", ""))))
            self._tasks_table.setItem(r, 2, QTableWidgetItem(str(t.get("status", ""))))
            self._tasks_table.setItem(r, 3, QTableWidgetItem(str(t.get("started_at", ""))))

    def update_search_results(self, hits: dict[str, list[dict[str, Any]]]) -> None:
        rows: list[tuple[str, str, str]] = []
        for domain, items in hits.items():
            for item in items:
                text = (
                    item.get("fact")
                    or item.get("title")
                    or item.get("user_request")
                    or item.get("content")
                    or ""
                )
                ts = item.get("created_at") or item.get("started_at") or ""
                rows.append((domain.title(), str(text), str(ts)))

        self._search_table.setRowCount(len(rows))
        for r, (dom, summary, ts) in enumerate(rows):
            self._search_table.setItem(r, 0, QTableWidgetItem(dom))
            self._search_table.setItem(r, 1, QTableWidgetItem(summary))
            self._search_table.setItem(r, 2, QTableWidgetItem(ts))
