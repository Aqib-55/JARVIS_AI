"""Chat message bubble widget with Markdown rendering and Copy Response button."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from desktop.theme import COLORS


class ChatMessageWidget(QWidget):
    """Single message row aligned right (user) or left (assistant/tool/error)."""

    def __init__(
        self,
        role: str,
        content: str,
        timestamp: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.role = role
        self._raw_content = content
        self._ts = timestamp or datetime.now().strftime("%H:%M:%S")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)

        self._bubble = QFrame()
        self._bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._bubble.setMaximumWidth(760)

        if role == "user":
            self._bubble.setObjectName("UserBubble")
            outer.addStretch(1)
            outer.addWidget(self._bubble)
        elif role == "tool":
            self._bubble.setObjectName("ToolBubble")
            outer.addWidget(self._bubble)
            outer.addStretch(1)
        elif role == "error":
            self._bubble.setObjectName("ErrorBubble")
            outer.addWidget(self._bubble)
            outer.addStretch(1)
        else:
            self._bubble.setObjectName("AssistantBubble")
            outer.addWidget(self._bubble)
            outer.addStretch(1)

        inner = QVBoxLayout(self._bubble)
        inner.setContentsMargins(14, 10, 14, 10)
        inner.setSpacing(6)

        # Header: Sender + timestamp + optional Copy button
        hdr = QHBoxLayout()
        sender_map = {
            "user": ("You", COLORS["accent_cyan"]),
            "assistant": ("JARVIS", COLORS["accent_blue"]),
            "tool": ("Tool Activity", COLORS["accent_cyan"]),
            "error": ("System Notice", COLORS["error"]),
        }
        sender_text, sender_col = sender_map.get(role, ("JARVIS", COLORS["accent_cyan"]))
        sender_lbl = QLabel(sender_text)
        sender_lbl.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {sender_col};")

        ts_lbl = QLabel(self._ts)
        ts_lbl.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']};")

        hdr.addWidget(sender_lbl)
        hdr.addSpacing(8)
        hdr.addWidget(ts_lbl)
        hdr.addStretch(1)

        self._copy_btn: QPushButton | None = None
        if role == "assistant":
            btn = QPushButton("Copy")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(22)
            btn.setStyleSheet(
                f"padding: 2px 8px; font-size: 10px; border-radius: 5px; "
                f"background-color: {COLORS['bg_secondary']}; border: 1px solid {COLORS['border']};"
            )
            btn.clicked.connect(self._copy_text)
            hdr.addWidget(btn)
            self._copy_btn = btn

        inner.addLayout(hdr)

        # Body text (Markdown supported for lists/code/emphasis cleanly)
        self._body = QLabel(content)
        self._body.setWordWrap(True)
        self._body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        if role == "assistant":
            self._body.setTextFormat(Qt.TextFormat.MarkdownText)
        else:
            self._body.setTextFormat(Qt.TextFormat.PlainText)
        self._body.setStyleSheet(f"font-size: 13px; color: {COLORS['text_primary']};")
        inner.addWidget(self._body)

    def append_chunk(self, delta: str) -> None:
        self._raw_content += delta
        self._body.setText(self._raw_content)

    def set_content(self, text: str) -> None:
        self._raw_content = text
        self._body.setText(text)

    def get_content(self) -> str:
        return self._raw_content

    def _copy_text(self) -> None:
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(self._raw_content)
        if self._copy_btn is not None:
            self._copy_btn.setText("Copied")
            QTimer.singleShot(1500, lambda: self._copy_btn.setText("Copy") if self._copy_btn else None)
