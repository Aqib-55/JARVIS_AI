"""Top status header bar component."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from desktop.services.ui_state import HealthSnapshot, VoiceState
from desktop.theme import COLORS


class TopbarWidget(QFrame):
    """Displays current section title and real backend connectivity badges."""

    emergency_toggle_clicked = Signal(bool)  # True = currently stopped (request resume)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Topbar")
        self.setFixedHeight(60)
        self._is_emergency_stopped = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 10, 24, 10)
        layout.setSpacing(10)

        self._title_lbl = QLabel("Chat")
        self._title_lbl.setObjectName("PageTitle")
        layout.addWidget(self._title_lbl)

        layout.addStretch(1)

        self._conn_badge = QLabel("Ollama: Checking")
        self._conn_badge.setObjectName("Badge")
        layout.addWidget(self._conn_badge)

        self._local_badge = QLabel("Local-Only: True")
        self._local_badge.setObjectName("Badge")
        layout.addWidget(self._local_badge)

        self._voice_badge = QLabel("Voice: IDLE")
        self._voice_badge.setObjectName("Badge")
        layout.addWidget(self._voice_badge)

        self._stop_btn = QPushButton("Emergency Stop")
        self._stop_btn.setObjectName("DangerButton")
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.setFixedHeight(32)
        self._stop_btn.clicked.connect(lambda: self.emergency_toggle_clicked.emit(self._is_emergency_stopped))
        layout.addWidget(self._stop_btn)

    def set_page_title(self, title: str) -> None:
        self._title_lbl.setText(title)

    def update_voice_state(self, state: VoiceState) -> None:
        color_map = {
            VoiceState.IDLE: COLORS["text_secondary"],
            VoiceState.LISTENING: COLORS["accent_cyan"],
            VoiceState.WAKE_DETECTED: COLORS["accent_cyan"],
            VoiceState.TRANSCRIBING: COLORS["accent_blue"],
            VoiceState.THINKING: COLORS["accent_blue"],
            VoiceState.EXECUTING_TOOL: COLORS["warning"],
            VoiceState.SPEAKING: COLORS["success"],
            VoiceState.ERROR: COLORS["error"],
        }
        col = color_map.get(state, COLORS["text_secondary"])
        self._voice_badge.setText(f"Voice: {state.value}")
        self._voice_badge.setStyleSheet(
            f"background-color: {COLORS['bg_secondary']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600; color: {col};"
        )

    def update_health(self, snap: HealthSnapshot) -> None:
        if snap.ai_connected:
            self._conn_badge.setText(f"● {snap.ai_provider.title()} ({snap.ai_model})")
            col = COLORS["success"]
        else:
            self._conn_badge.setText("● Ollama Offline")
            col = COLORS["error"]
        self._conn_badge.setStyleSheet(
            f"background-color: {COLORS['bg_secondary']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600; color: {col};"
        )

        local_col = COLORS["accent_cyan"] if snap.local_ai_only else COLORS["warning"]
        self._local_badge.setText("Local AI Only" if snap.local_ai_only else "Hybrid Mode")
        self._local_badge.setStyleSheet(
            f"background-color: {COLORS['bg_secondary']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600; color: {local_col};"
        )

        self._is_emergency_stopped = snap.emergency_stopped
        if snap.emergency_stopped:
            self._stop_btn.setText("Resume Operations")
            self._stop_btn.setObjectName("AccentButton")
        else:
            self._stop_btn.setText("Emergency Stop")
            self._stop_btn.setObjectName("DangerButton")
        self._stop_btn.style().unpolish(self._stop_btn)
        self._stop_btn.style().polish(self._stop_btn)
