"""Chat composer with Enter-to-Send, Shift+Enter newline, Send, Mic, and Stop buttons."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.services.ui_state import VoiceState
from desktop.theme import COLORS


class _ComposerTextEdit(QPlainTextEdit):
    """Multiline text input that emits submit on Enter and newline on Shift+Enter."""

    submit_requested = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                event.accept()
                self.submit_requested.emit()
                return
        super().keyPressEvent(event)


class MessageInputWidget(QFrame):
    """Bottom input composer supporting typed chat, push-to-talk mic, and stop controls."""

    send_requested = Signal(str)
    mic_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(10)

        self._editor = _ComposerTextEdit()
        self._editor.setPlaceholderText('Ask JARVIS anything or say "Hey JARVIS"... (Enter to send, Shift+Enter for newline)')
        self._editor.setMinimumHeight(46)
        self._editor.setMaximumHeight(110)
        self._editor.submit_requested.connect(self._on_send)
        row.addWidget(self._editor, stretch=1)

        self._mic_btn = QPushButton("Mic")
        self._mic_btn.setObjectName("AccentButton")
        self._mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mic_btn.setFixedHeight(44)
        self._mic_btn.setMinimumWidth(78)
        self._mic_btn.setToolTip("Trigger Push-to-Talk microphone capture")
        self._mic_btn.clicked.connect(self.mic_requested.emit)
        row.addWidget(self._mic_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("DangerButton")
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.setFixedHeight(44)
        self._stop_btn.setMinimumWidth(72)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setToolTip("Stop active playback or listening")
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        row.addWidget(self._stop_btn)

        self._send_btn = QPushButton("Send")
        self._send_btn.setObjectName("PrimaryButton")
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setFixedHeight(44)
        self._send_btn.setMinimumWidth(86)
        self._send_btn.clicked.connect(self._on_send)
        row.addWidget(self._send_btn)

        root.addLayout(row)

        footer = QHBoxLayout()
        self._state_lbl = QLabel('Voice Status: SAY "HEY JARVIS"')
        self._state_lbl.setStyleSheet(f"font-size: 11px; color: {COLORS['text_secondary']};")
        footer.addWidget(self._state_lbl)
        footer.addStretch(1)
        hint_lbl = QLabel("Local-Only AI  |  Thread-safe request queue")
        hint_lbl.setStyleSheet(f"font-size: 11px; color: {COLORS['text_muted']};")
        footer.addWidget(hint_lbl)
        root.addLayout(footer)

    def _on_send(self) -> None:
        text = self._editor.toPlainText().strip()
        if not text or not self._send_btn.isEnabled():
            return
        self._editor.clear()
        self.send_requested.emit(text)

    def set_busy(self, busy: bool) -> None:
        self._send_btn.setEnabled(not busy)
        self._mic_btn.setEnabled(not busy)
        if busy:
            self._stop_btn.setEnabled(True)

    def set_voice_state(self, state: VoiceState, caption: str) -> None:
        self._state_lbl.setText(f"Voice Status: {caption}")
        can_stop = state in (VoiceState.LISTENING, VoiceState.SPEAKING)
        self._stop_btn.setEnabled(can_stop or not self._send_btn.isEnabled())

    def input_box(self) -> QPlainTextEdit:
        return self._editor

    def send_button(self) -> QPushButton:
        return self._send_btn

    def mic_button(self) -> QPushButton:
        return self._mic_btn
