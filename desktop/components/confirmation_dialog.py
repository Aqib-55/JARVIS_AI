"""Modal tool execution confirmation dialog wired to existing 4-tier security gates."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.services.ui_state import ToolApprovalRequest
from desktop.theme import COLORS


class ConfirmationDialog(QDialog):
    """Prompts the user before TaskExecutor runs a Level 2 or Level 3 tool."""

    def __init__(
        self,
        request: ToolApprovalRequest,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("JARVIS — Tool Approval Required")
        self.setModal(True)
        self.setMinimumWidth(480)
        self._request = request
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 18)
        layout.setSpacing(12)

        risk_pretty = self._request.risk_level.replace("_", " ").upper()
        badge = QLabel(f"CONFIRMATION REQUIRED  •  {risk_pretty}")
        badge.setStyleSheet(
            f"background-color: #2E2414; border: 1px solid {COLORS['warning']}; "
            f"border-radius: 6px; padding: 6px 10px; color: {COLORS['warning']}; "
            "font-size: 11px; font-weight: 700; letter-spacing: 0.8px;"
        )
        layout.addWidget(badge)

        card = QFrame()
        card.setObjectName("Card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 14, 14, 14)
        cl.setSpacing(8)

        tool_lbl = QLabel(f"Tool: {self._request.tool_name}")
        tool_lbl.setStyleSheet("font-size: 15px; font-weight: 700;")
        cl.addWidget(tool_lbl)

        if self._request.description:
            desc_lbl = QLabel(self._request.description)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
            cl.addWidget(desc_lbl)

        reason_lbl = QLabel(f"Security Policy: {self._request.reason}")
        reason_lbl.setWordWrap(True)
        reason_lbl.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 12px;")
        cl.addWidget(reason_lbl)

        args_title = QLabel("Validated Parameters:")
        args_title.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {COLORS['text_secondary']}; margin-top: 4px;")
        cl.addWidget(args_title)

        args_box = QPlainTextEdit()
        args_box.setReadOnly(True)
        args_box.setMaximumHeight(120)
        args_box.setPlainText(json.dumps(self._request.arguments, indent=2))
        cl.addWidget(args_box)

        layout.addWidget(card)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        reject_btn = QPushButton("Reject")
        reject_btn.setObjectName("DangerButton")
        reject_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reject_btn.clicked.connect(self.reject)

        approve_btn = QPushButton("Approve Execution")
        approve_btn.setObjectName("PrimaryButton")
        approve_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        approve_btn.clicked.connect(self.accept)

        btn_row.addWidget(reject_btn)
        btn_row.addWidget(approve_btn)
        layout.addLayout(btn_row)
