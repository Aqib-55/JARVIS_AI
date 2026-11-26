"""Tools catalog page reading directly from the real JARVIS ToolRegistry."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from desktop.theme import COLORS
from tools import PermissionLevel, ToolCategory, ToolDefinition


class ToolsPage(QWidget):
    """Displays all real registered tools grouped by category and permission tier."""

    ask_in_chat_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tools: list[ToolDefinition] = []
        self._emergency_stopped = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # Header + Filter Bar
        hdr = QFrame()
        hdr.setObjectName("Card")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(16, 12, 16, 12)
        hl.setSpacing(10)

        self._count_lbl = QLabel("Registered Tools: 0")
        self._count_lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        hl.addWidget(self._count_lbl)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Filter tools by name or description…")
        self._search_edit.setMinimumWidth(250)
        self._search_edit.setMaximumWidth(340)
        self._search_edit.textChanged.connect(self._render_tools)
        hl.addWidget(self._search_edit)

        self._cat_combo = QComboBox()
        self._cat_combo.addItem("All Categories", "")
        for cat in ToolCategory:
            self._cat_combo.addItem(cat.value.replace("_", " ").title(), cat.value)
        self._cat_combo.currentIndexChanged.connect(self._render_tools)
        hl.addWidget(self._cat_combo)

        hl.addStretch(1)
        policy_note = QLabel("Execution policy: Agent → Registry → Permissions → Executor")
        policy_note.setStyleSheet(f"font-size: 11px; color: {COLORS['accent_cyan']};")
        hl.addWidget(policy_note)
        root.addWidget(hdr)

        # Scrollable tool list
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 8, 0)
        self._list_layout.setSpacing(10)
        self._list_layout.addStretch(1)
        self._scroll.setWidget(self._list_widget)
        root.addWidget(self._scroll, stretch=1)

    def set_tools(self, tools: list[ToolDefinition], emergency_stopped: bool = False) -> None:
        self._tools = list(tools)
        self._emergency_stopped = emergency_stopped
        self._render_tools()

    def _render_tools(self) -> None:
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        query = self._search_edit.text().strip().lower()
        selected_cat = self._cat_combo.currentData()

        filtered = [
            t
            for t in self._tools
            if (not selected_cat or t.category.value == selected_cat)
            and (not query or query in t.name.lower() or query in t.description.lower())
        ]
        self._count_lbl.setText(f"Registered Tools: {len(filtered)} / {len(self._tools)}")

        for cat in ToolCategory:
            cat_tools = [t for t in filtered if t.category == cat]
            if not cat_tools:
                continue

            cat_lbl = QLabel(f"{cat.value.replace('_', ' ').upper()}  ({len(cat_tools)})")
            cat_lbl.setStyleSheet(
                f"font-size: 11px; font-weight: 700; letter-spacing: 1.2px; "
                f"color: {COLORS['accent_cyan']}; margin-top: 8px;"
            )
            self._list_layout.insertWidget(self._list_layout.count() - 1, cat_lbl)

            for tool in cat_tools:
                card = self._build_tool_card(tool)
                self._list_layout.insertWidget(self._list_layout.count() - 1, card)

    def _build_tool_card(self, tool: ToolDefinition) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        cl = QHBoxLayout(card)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(4)

        top_row = QHBoxLayout()
        name_lbl = QLabel(tool.name)
        name_lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        top_row.addWidget(name_lbl)

        perm = tool.permission_level
        if perm in (PermissionLevel.LEVEL_2_MODERATE_RISK, PermissionLevel.LEVEL_3_HIGH_RISK):
            perm_text = f"{perm.value.replace('_', ' ').upper()} • Approval Required"
            perm_col = COLORS["error"] if perm == PermissionLevel.LEVEL_3_HIGH_RISK else COLORS["warning"]
        else:
            perm_text = perm.value.replace("_", " ").upper()
            perm_col = COLORS["success"]

        perm_badge = QLabel(perm_text)
        perm_badge.setStyleSheet(
            f"background-color: {COLORS['bg_secondary']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 8px; padding: 2px 8px; font-size: 10px; font-weight: 700; color: {perm_col};"
        )
        top_row.addWidget(perm_badge)

        status_text = "Blocked (Emergency Stop)" if self._emergency_stopped else "Enabled"
        status_col = COLORS["error"] if self._emergency_stopped else COLORS["accent_cyan"]
        status_badge = QLabel(status_text)
        status_badge.setStyleSheet(
            f"background-color: {COLORS['bg_secondary']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 8px; padding: 2px 8px; font-size: 10px; font-weight: 600; color: {status_col};"
        )
        top_row.addWidget(status_badge)
        top_row.addStretch(1)
        left.addLayout(top_row)

        desc_lbl = QLabel(tool.description)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_secondary']};")
        left.addWidget(desc_lbl)

        params = ", ".join(
            f"{p.name}{'*' if p.required else ''}:{p.type}" for p in tool.parameters
        ) or "none"
        param_lbl = QLabel(f"Parameters: {params}")
        param_lbl.setStyleSheet(f"font-size: 11px; color: {COLORS['text_muted']};")
        left.addWidget(param_lbl)
        cl.addLayout(left, stretch=1)

        ask_btn = QPushButton("Ask JARVIS")
        ask_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ask_btn.setFixedHeight(32)
        ask_btn.setToolTip("Open Chat with a prompt routed safely through JarvisAgent")
        ask_btn.clicked.connect(
            lambda _checked=False, n=tool.name: self.ask_in_chat_requested.emit(
                f"Use {n} to help me."
            )
        )
        cl.addWidget(ask_btn, alignment=Qt.AlignmentFlag.AlignVCenter)
        return card
