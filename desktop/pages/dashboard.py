"""Overview / Dashboard page showing live backend health and quick actions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from desktop.components.status_card import StatusCard
from desktop.services.ui_state import HealthSnapshot
from desktop.theme import COLORS


class DashboardPage(QWidget):
    """Overview page displaying live health status cards and functional quick actions."""

    open_chat_requested = Signal()
    open_tools_requested = Signal()
    start_voice_requested = Signal()
    stop_voice_requested = Signal()
    run_diagnostics_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start()
        self._update_clock()

    def _build_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(18)

        # Header Card
        hdr_card = QFrame()
        hdr_card.setObjectName("Card")
        hl = QHBoxLayout(hdr_card)
        hl.setContentsMargins(20, 18, 20, 18)

        left = QVBoxLayout()
        left.setSpacing(4)
        self._greeting_lbl = QLabel("Good evening. JARVIS is ready.")
        self._greeting_lbl.setStyleSheet("font-size: 22px; font-weight: 700;")
        self._sub_lbl = QLabel("Provider: Ollama  •  Model: qwen3.5:4b")
        self._sub_lbl.setStyleSheet(f"font-size: 13px; color: {COLORS['text_secondary']};")
        left.addWidget(self._greeting_lbl)
        left.addWidget(self._sub_lbl)
        hl.addLayout(left)
        hl.addStretch(1)

        right = QVBoxLayout()
        right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._time_lbl = QLabel("--:--:--")
        self._time_lbl.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {COLORS['accent_cyan']};")
        self._date_lbl = QLabel("----")
        self._date_lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_secondary']};")
        right.addWidget(self._time_lbl, alignment=Qt.AlignmentFlag.AlignRight)
        right.addWidget(self._date_lbl, alignment=Qt.AlignmentFlag.AlignRight)
        hl.addLayout(right)
        layout.addWidget(hdr_card)

        # 6 Real Status Cards (2 rows x 3 columns)
        grid = QGridLayout()
        grid.setSpacing(14)

        self._card_ai = StatusCard("AI Engine")
        self._card_ollama = StatusCard("Ollama Connection")
        self._card_stt = StatusCard("Voice Recognition")
        self._card_tts = StatusCard("Speech Generation")
        self._card_wake = StatusCard("Wake-Word Detection")
        self._card_memory = StatusCard("Memory Database")

        grid.addWidget(self._card_ai, 0, 0)
        grid.addWidget(self._card_ollama, 0, 1)
        grid.addWidget(self._card_stt, 0, 2)
        grid.addWidget(self._card_tts, 1, 0)
        grid.addWidget(self._card_wake, 1, 1)
        grid.addWidget(self._card_memory, 1, 2)
        layout.addLayout(grid)

        # Quick Actions Card
        actions_card = QFrame()
        actions_card.setObjectName("Card")
        al = QVBoxLayout(actions_card)
        al.setContentsMargins(18, 16, 18, 16)
        al.setSpacing(12)

        act_title = QLabel("QUICK ACTIONS")
        act_title.setStyleSheet(
            f"font-size: 11px; font-weight: 700; letter-spacing: 1px; color: {COLORS['text_secondary']};"
        )
        al.addWidget(act_title)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_chat = QPushButton("Open Chat")
        btn_chat.setObjectName("PrimaryButton")
        btn_chat.clicked.connect(self.open_chat_requested.emit)

        btn_start_v = QPushButton("Start Voice")
        btn_start_v.setObjectName("AccentButton")
        btn_start_v.clicked.connect(self.start_voice_requested.emit)

        btn_stop_v = QPushButton("Stop Voice")
        btn_stop_v.setObjectName("DangerButton")
        btn_stop_v.clicked.connect(self.stop_voice_requested.emit)

        btn_diag = QPushButton("Run Diagnostics")
        btn_diag.clicked.connect(self._on_run_diagnostics)

        btn_tools = QPushButton("View Tools")
        btn_tools.clicked.connect(self.open_tools_requested.emit)

        for b in (btn_chat, btn_start_v, btn_stop_v, btn_diag, btn_tools):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumHeight(38)
            btn_row.addWidget(b)

        btn_row.addStretch(1)
        al.addLayout(btn_row)

        self._diag_lbl = QLabel("Click 'Run Diagnostics' to verify microphone, openWakeWord, Faster-Whisper, and Piper.")
        self._diag_lbl.setWordWrap(True)
        self._diag_lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_secondary']};")
        al.addWidget(self._diag_lbl)

        layout.addWidget(actions_card)
        layout.addStretch(1)

    def _update_clock(self) -> None:
        now = datetime.now()
        hour = now.hour
        if 5 <= hour < 12:
            period = "morning"
        elif 12 <= hour < 17:
            period = "afternoon"
        else:
            period = "evening"
        self._greeting_lbl.setText(f"Good {period}. JARVIS is ready.")
        self._time_lbl.setText(now.strftime("%H:%M:%S"))
        self._date_lbl.setText(now.strftime("%A, %B %d, %Y"))

    def _on_run_diagnostics(self) -> None:
        self._diag_lbl.setText("Running live subsystem diagnostics…")
        self.run_diagnostics_requested.emit()

    def update_health(self, snap: HealthSnapshot) -> None:
        self._sub_lbl.setText(
            f"Provider: {snap.ai_provider.title()}  •  Model: {snap.ai_model}  •  Tools: {snap.tools_count}"
        )

        self._card_ai.set_status(
            snap.ai_model,
            f"Local AI Only: {'Enabled' if snap.local_ai_only else 'Disabled'}",
            "ok" if snap.ai_connected else "warn",
        )
        self._card_ollama.set_status(
            "Ollama Connected" if snap.ai_connected else "Ollama Unavailable",
            snap.ollama_url if snap.ai_connected else f"Start Ollama: ollama serve ({snap.ollama_url})",
            "ok" if snap.ai_connected else "error",
        )
        self._card_stt.set_status(
            "Faster-Whisper Ready" if snap.stt_available else "STT Unavailable",
            f"Model: {snap.whisper_model} (CPU INT8)",
            "ok" if snap.stt_available else "error",
        )
        self._card_tts.set_status(
            "Piper Ready" if snap.tts_available else "Piper Unavailable",
            f"Voice: {snap.piper_voice}",
            "ok" if snap.tts_available else "warn",
        )
        if snap.wake_detection_active:
            self._card_wake.set_status(
                "Hey JARVIS Enabled",
                f"Mic: {snap.mic_device}",
                "ok",
            )
        elif snap.wake_word_available:
            self._card_wake.set_status(
                "Standby (Stopped)",
                snap.last_error or "Click 'Start Voice' for hands-free activation",
                "warn",
            )
        else:
            self._card_wake.set_status(
                "Wake Word Unavailable",
                snap.last_error or "Run setup_local_models.py to download ONNX assets",
                "error",
            )

        self._card_memory.set_status(
            "SQLite Connected" if snap.memory_enabled else "SQLite Not Initialized",
            "Local persistent memory active" if snap.memory_enabled else "Database inactive",
            "ok" if snap.memory_enabled else "error",
        )

    def show_diagnostics_result(self, data: dict[str, Any]) -> None:
        if "error" in data:
            self._diag_lbl.setText(f"Diagnostics failed: {data['error']}")
            return
        mic = data.get("microphone", {})
        ww = data.get("wake_word", {})
        stt = data.get("stt", {})
        tts = data.get("tts", {})
        parts = [
            f"Microphone: {'PASS' if mic.get('ok') else 'FAIL'} ({mic.get('device', 'N/A')})",
            f"Wake Word: {'PASS' if ww.get('ok') else 'FAIL'}",
            f"Faster-Whisper: {'PASS' if stt.get('ok') else 'FAIL'}",
            f"Piper TTS: {'PASS' if tts.get('ok') else 'FAIL'}",
        ]
        self._diag_lbl.setText("Diagnostics: " + "  |  ".join(parts))
