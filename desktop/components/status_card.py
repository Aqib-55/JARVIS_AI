"""Reusable rounded system health/status card component."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from desktop.theme import COLORS


class StatusCard(QFrame):
    """Compact dark card showing real health metrics for one backend subsystem."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusCard")
        self.setMinimumHeight(108)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        top = QHBoxLayout()
        self._title_lbl = QLabel(title.upper())
        self._title_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 700; letter-spacing: 1px; color: {COLORS['text_secondary']};"
        )
        self._dot_lbl = QLabel("●")
        self._dot_lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
        top.addWidget(self._title_lbl)
        top.addStretch(1)
        top.addWidget(self._dot_lbl)
        layout.addLayout(top)

        self._value_lbl = QLabel("Checking…")
        self._value_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {COLORS['text_primary']};"
        )
        self._value_lbl.setWordWrap(True)
        layout.addWidget(self._value_lbl)

        self._detail_lbl = QLabel("")
        self._detail_lbl.setStyleSheet(f"font-size: 11px; color: {COLORS['text_secondary']};")
        self._detail_lbl.setWordWrap(True)
        layout.addWidget(self._detail_lbl)
        layout.addStretch(1)

    def set_status(self, value: str, detail: str = "", level: str = "neutral") -> None:
        """Update displayed status text and indicator color ('ok', 'warn', 'error', 'neutral')."""
        dot_colors = {
            "ok": COLORS["success"],
            "warn": COLORS["warning"],
            "error": COLORS["error"],
            "info": COLORS["accent_cyan"],
            "neutral": COLORS["text_muted"],
        }
        col = dot_colors.get(level, COLORS["text_muted"])
        self._dot_lbl.setStyleSheet(f"font-size: 12px; color: {col};")
        self._value_lbl.setText(value)
        self._detail_lbl.setText(detail)
